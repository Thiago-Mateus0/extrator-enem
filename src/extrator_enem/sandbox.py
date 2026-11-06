"""Isolamento real do parser: bubblewrap (Linux) + rlimits. Falha fechada.

Backend declarado e testado: Linux com `bwrap`. macOS/Windows: NÃO suportados (recusa explícita).
Rede negada, home inexistente, raiz do sistema somente leitura, ambiente sem credenciais,
diretório temporário exclusivo, limites de CPU/memória/arquivo/descritores/tempo/volume de saída.
"""
import hashlib
import io
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import sysconfig
import tarfile
import threading
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    """O isolamento exigido não está disponível — a extração é recusada."""


LIMITES = {"cpu_s": 600, "mem_bytes": 6 * 2**30, "fsize_bytes": 512 * 2**20, "nofile": 512,
           "timeout_s": 900, "saida_max_bytes": 1024 * 2**20}


def _bind_args(extra_ro: list[str], rw: list[str]) -> list[str]:
    args: list[str] = []
    for p in ["/usr", "/bin", "/sbin", "/lib", "/lib64", "/lib32"]:
        if os.path.islink(p):
            args += ["--symlink", os.readlink(p), p]  # /lib -> usr/lib etc. (histórico: falha de symlink no CI)
        elif os.path.exists(p):
            args += ["--ro-bind", p, p]
    for p in extra_ro:
        if os.path.exists(p):
            args += ["--ro-bind", p, p]
    for p in rw:
        args += ["--bind", p, p]
    return args


def _code_paths() -> list[str]:
    pkg = str(Path(__file__).resolve().parent.parent)  # diretório que contém extrator_enem/
    paths = {pkg, sys.prefix, sys.base_prefix, sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"]}
    # instalação editável: o .pth aponta para outro diretório
    sp = Path(sysconfig.get_paths()["purelib"])
    for pth in sp.glob("*.pth"):
        for ln in pth.read_text(errors="ignore").splitlines():
            if ln.startswith("/") and os.path.isdir(ln):
                paths.add(ln)
    return sorted(p for p in paths if p not in ("/usr", "/"))


def _preexec(lim: dict):
    def f():
        resource.setrlimit(resource.RLIMIT_CPU, (lim["cpu_s"], lim["cpu_s"]))
        resource.setrlimit(resource.RLIMIT_AS, (lim["mem_bytes"], lim["mem_bytes"]))
        resource.setrlimit(resource.RLIMIT_FSIZE, (lim["fsize_bytes"], lim["fsize_bytes"]))
        resource.setrlimit(resource.RLIMIT_NOFILE, (lim["nofile"], lim["nofile"]))
        os.setsid()
    return f


def _cmd(worker_args: list[str], ro: list[str], rw: list[str]) -> list[str]:
    bwrap = shutil.which("bwrap")
    if sys.platform != "linux" or not bwrap:
        raise SandboxUnavailable(
            "isolamento indisponível: requer Linux com bubblewrap (bwrap). "
            "macOS/Windows não são suportados; a extração foi recusada (falha fechada).")
    py = os.path.realpath(sys.executable)
    cmd = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
           "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/nonexistent",
           "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
           "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--chdir", "/tmp"]
    cmd += _bind_args(_code_paths() + ro, rw)
    cmd += [sys.executable if os.path.exists(sys.executable) else py, "-I", "-m", "extrator_enem.worker", *worker_args]
    return cmd


def sonda() -> dict:
    """Prova funcional: rede negada, home inexistente, /usr somente leitura, sem credenciais."""
    cmd = _cmd(["--probe"], [], [])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, preexec_fn=_preexec(LIMITES))
    if r.returncode != 0:
        raise SandboxUnavailable(f"sonda do isolamento falhou ao executar: {r.stderr.strip()[:300]}")
    res = json.loads(r.stdout)
    if not all(res.values()):
        raise SandboxUnavailable(f"isolamento NÃO efetivo (falha fechada): {res}")
    return res


_NOME_OK = re.compile(r"^(?:(?:questions|omitted|gabarito|identity)\.json|(?:assets|snapshots)/[0-9a-f]{64}\.png)$")


def _receber(stream, teto: int, destino: Path) -> None:
    """Lê o tar do worker com contagem corrente de bytes; só aceita arquivos regulares permitidos.

    O worker é tratado como hostil: nada é extraído como o tar mandar (sem symlink, sem caminho livre);
    PNGs são re-hasheados contra o nome. Estourar o teto mata o processo (feito pelo chamador).
    """
    buf = io.BytesIO()
    while True:
        chunk = stream.read(1 << 20)
        if not chunk:
            break
        if buf.tell() + len(chunk) > teto:
            raise RuntimeError("volume de saída do worker acima do limite")
        buf.write(chunk)
    buf.seek(0)
    destino.mkdir(parents=True, exist_ok=True)
    try:
        tf_ctx = tarfile.open(fileobj=buf, mode="r:")
    except tarfile.TarError as ex:
        raise RuntimeError(f"saída do worker inválida (tar ilegível ou vazio): {ex}") from ex
    with tf_ctx as tf:
        for m in tf:
            if not m.isreg() or not _NOME_OK.match(m.name):
                raise RuntimeError(f"saída do worker rejeitada (membro inválido): {m.name[:80]!r}")
            data = tf.extractfile(m).read()
            if m.name.endswith(".png") and hashlib.sha256(data).hexdigest() != Path(m.name).stem:
                raise RuntimeError(f"recurso do worker com hash divergente: {m.name[:80]!r}")
            dst = destino / m.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)


def run_worker(pdf: Path, gabarito: Path | None, out: Path, de: int, ate: int, limites: dict | None = None) -> None:
    pdf, out = pdf.resolve(), out.resolve()
    gabarito = gabarito.resolve() if gabarito else None
    lim = {**LIMITES, **(limites or {})}
    sonda()  # nunca roda o parser sem provar o isolamento
    args = ["--pdf", str(pdf), "--out", "/out", "--tar-stdout", "--de", str(de), "--ate", str(ate)]
    ro = [str(pdf)]
    if gabarito:
        args += ["--gabarito", str(gabarito)]
        ro.append(str(gabarito))
    cmd = _cmd(args, ro, [])
    # diretório de trabalho do worker: tmpfs com teto (disco do host não é tocado)
    if "--proc" in cmd:
        i = cmd.index("--proc")
        cmd[i:i] = ["--size", str(lim["saida_max_bytes"]), "--tmpfs", "/out"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=_preexec(lim))
    err_buf = bytearray()

    def _drenar_stderr():
        # esvazia o pipe enquanto o worker roda (evita deadlock) e guarda só os primeiros 64 KiB
        for chunk in iter(lambda: proc.stderr.read(8192), b""):
            if len(err_buf) < 64 * 1024:
                err_buf.extend(chunk[: 64 * 1024 - len(err_buf)])

    dreno = threading.Thread(target=_drenar_stderr, daemon=True)
    dreno.start()
    prazo = threading.Timer(lim["timeout_s"], proc.kill)  # vale até o wait() terminar
    prazo.start()
    try:
        _receber(proc.stdout, lim["saida_max_bytes"], out)
        rc = proc.wait()
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        prazo.cancel()
        dreno.join(timeout=5)
    err = err_buf.decode(errors="replace")
    if rc == -9 or rc == -signal.SIGKILL:
        raise RuntimeError(f"worker isolado encerrado à força (tempo excedido de {lim['timeout_s']}s ou limite de recurso)")
    if rc != 0:
        raise RuntimeError(f"worker isolado falhou (código {rc}): {err.strip()[-400:]}")
