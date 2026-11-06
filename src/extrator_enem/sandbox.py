"""Isolamento real do parser. Falha fechada. Dois backends, escolhidos pela disponibilidade:

- `bwrap`  (Linux com bubblewrap): namespaces + rlimits.
- `docker` (macOS, Windows, Linux): container descartável, sem rede, raiz somente leitura,
  sem capabilities, usuário sem privilégio, limites de memória/CPU/processos/arquivos.

`EXTRATOR_SANDBOX=auto|bwrap|docker` força a escolha (padrão auto: bwrap se existir, senão docker).
Em ambos: rede negada, home inexistente, ambiente sem credenciais, tmpfs exclusivo com teto de volume,
e a MESMA sonda funcional + a mesma validação do tar de saída. Sem backend que prove o isolamento,
a extração é recusada (nunca roda sem isolamento).
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
import tempfile
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


def _backend() -> str:
    pref = os.environ.get("EXTRATOR_SANDBOX", "auto").lower()
    if pref not in ("auto", "bwrap", "docker"):
        raise SandboxUnavailable(f"EXTRATOR_SANDBOX inválido: {pref!r} (use auto, bwrap ou docker)")
    if pref in ("auto", "bwrap") and sys.platform == "linux" and shutil.which("bwrap"):
        return "bwrap"
    if pref in ("auto", "docker") and shutil.which("docker"):
        return "docker"
    raise SandboxUnavailable(
        "isolamento indisponível: precisa de Linux com bubblewrap (bwrap) OU de Docker "
        "(macOS/Windows: instale Docker Desktop, Colima ou Podman-docker). "
        "A extração foi recusada (falha fechada).")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _imagem() -> str:
    """Tag derivada do conteúdo (código + Dockerfile + lock): código novo => imagem nova."""
    h = hashlib.sha256()
    root = _repo_root()
    arqs = [root / "docker" / "Dockerfile", root / "pyproject.toml", root / "requirements.lock"]
    arqs += sorted((root / "src" / "extrator_enem").glob("*.py"))
    for f in arqs:
        if not f.is_file():
            raise SandboxUnavailable(
                f"backend docker precisa do repositório completo (falta {f.name}); "
                "use uma instalação editável (`pip install -e .`) a partir do clone.")
        h.update(f.name.encode() + b"\0" + f.read_bytes())
    return f"extrator-enem-worker:{h.hexdigest()[:12]}"


def _garantir_imagem() -> str:
    tag = _imagem()
    ok = subprocess.run(["docker", "image", "inspect", tag], capture_output=True, timeout=60).returncode == 0
    if not ok:
        r = subprocess.run(["docker", "build", "-q", "-t", tag, "-f", str(_repo_root() / "docker" / "Dockerfile"),
                            str(_repo_root())], capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            raise SandboxUnavailable(f"falha ao construir a imagem do worker (o build precisa de rede; "
                                     f"a execução não): {r.stderr.strip()[-400:]}")
    return tag


def _docker_cmd(worker_args: list[str], ro: dict[str, str], lim: dict, nome: str) -> list[str]:
    """ro: {caminho_no_host: caminho_no_container}. Container sem rede, raiz RO, sem capabilities."""
    tmp_mb = max(lim["saida_max_bytes"] // 2**20, 1)
    cmd = ["docker", "run", "--rm", "-i", "--name", nome, "--pull", "never",
           "--network", "none", "--read-only", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--user", "65534:65534",
           "--memory", str(lim["mem_bytes"]), "--memory-swap", str(lim["mem_bytes"]),
           "--pids-limit", "128", "--cpus", "2",
           "--ulimit", f"cpu={lim['cpu_s']}", "--ulimit", f"fsize={lim['fsize_bytes']}",
           "--ulimit", f"nofile={lim['nofile']}",
           "--tmpfs", f"/out:rw,noexec,nosuid,size={tmp_mb}m,mode=1777",
           "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,mode=1777"]
    for src, dst in ro.items():
        # --mount é lido como CSV: vírgula/aspas/'='/quebra de linha no caminho injetariam opções (ex.: tirar o readonly)
        if re.search(r'[,"=\x00-\x1f]', src + dst):
            raise SandboxUnavailable(f"caminho de mount inseguro para o docker: {src!r}")
        cmd += ["--mount", f"type=bind,src={src},dst={dst},readonly"]
    # `env -i`: ambiente limpo (a imagem base define variáveis como GPG_KEY; a sonda exige zero credenciais)
    return cmd + [_garantir_imagem(), "env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/nonexistent",
                  "PYTHONDONTWRITEBYTECODE=1", "python", "-I", "-m", "extrator_enem.worker", *worker_args]


def _cmd(worker_args: list[str], ro: list[str], rw: list[str]) -> list[str]:
    bwrap = shutil.which("bwrap")
    if sys.platform != "linux" or not bwrap:
        raise SandboxUnavailable(
            "isolamento indisponível: requer Linux com bubblewrap (bwrap). "
            "A extração foi recusada (falha fechada).")
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
    backend = _backend()
    if backend == "docker":
        cmd, pre = _docker_cmd(["--probe"], {}, LIMITES, f"extrator-sonda-{os.getpid()}-{os.urandom(3).hex()}"), None
    else:
        cmd, pre = _cmd(["--probe"], [], []), _preexec(LIMITES)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, preexec_fn=pre)
    except subprocess.TimeoutExpired as ex:
        raise SandboxUnavailable("sonda do isolamento excedeu o tempo (o Docker está rodando?)") from ex
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
    backend = _backend()
    nome = f"extrator-{os.getpid()}-{os.urandom(4).hex()}"
    entrada = None
    if backend == "docker":
        # caminhos de dentro do container; o host só entrega os PDFs somente leitura
        args = ["--pdf", "/in/prova.pdf", "--out", "/out", "--tar-stdout", "--de", str(de), "--ate", str(ate)]
        # o nome do arquivo do usuário nunca chega ao docker: cópia com nome fixo em diretório temporário próprio
        entrada = Path(tempfile.mkdtemp(prefix="extrator-in-"))
        shutil.copyfile(pdf, entrada / "prova.pdf")
        args_gab = []
        if gabarito:
            shutil.copyfile(gabarito, entrada / "gabarito.pdf")
            args_gab = ["--gabarito", "/in/gabarito.pdf"]
        entrada.chmod(0o755)  # o container roda como 65534: precisa ler (o mount é somente leitura)
        for f in entrada.iterdir():
            f.chmod(0o644)
        cmd, pre = _docker_cmd(args + args_gab, {str(entrada): "/in"}, lim, nome), None
    else:
        args = ["--pdf", str(pdf), "--out", "/out", "--tar-stdout", "--de", str(de), "--ate", str(ate)]
        ro = [str(pdf)]
        if gabarito:
            args += ["--gabarito", str(gabarito)]
            ro.append(str(gabarito))
        cmd, pre = _cmd(args, ro, []), _preexec(lim)
        # diretório de trabalho do worker: tmpfs com teto (disco do host não é tocado)
        if "--proc" in cmd:
            i = cmd.index("--proc")
            cmd[i:i] = ["--size", str(lim["saida_max_bytes"]), "--tmpfs", "/out"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=pre)

    def _matar():
        proc.kill()
        if backend == "docker":  # matar o cliente não mata o container
            subprocess.run(["docker", "kill", nome], capture_output=True, timeout=30)
    err_buf = bytearray()

    def _drenar_stderr():
        # esvazia o pipe enquanto o worker roda (evita deadlock) e guarda só os primeiros 64 KiB
        for chunk in iter(lambda: proc.stderr.read(8192), b""):
            if len(err_buf) < 64 * 1024:
                err_buf.extend(chunk[: 64 * 1024 - len(err_buf)])

    dreno = threading.Thread(target=_drenar_stderr, daemon=True)
    dreno.start()
    prazo = threading.Timer(lim["timeout_s"], _matar)  # vale até o wait() terminar
    prazo.start()
    try:
        _receber(proc.stdout, lim["saida_max_bytes"], out)
        rc = proc.wait()
    except BaseException:
        _matar()
        proc.wait()
        raise
    finally:
        prazo.cancel()
        dreno.join(timeout=5)
        if entrada is not None:
            shutil.rmtree(entrada, ignore_errors=True)
    err = err_buf.decode(errors="replace")
    if rc in (-9, -signal.SIGKILL, 137):
        raise RuntimeError(f"worker isolado encerrado à força (tempo excedido de {lim['timeout_s']}s ou limite de recurso)")
    if rc != 0:
        raise RuntimeError(f"worker isolado falhou (código {rc}): {err.strip()[-400:]}")
