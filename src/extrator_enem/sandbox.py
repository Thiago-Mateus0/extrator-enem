"""Isolamento real do parser: bubblewrap (Linux) + rlimits. Falha fechada.

Backend declarado e testado: Linux com `bwrap`. macOS/Windows: NÃO suportados (recusa explícita).
Rede negada, home inexistente, raiz do sistema somente leitura, ambiente sem credenciais,
diretório temporário exclusivo, limites de CPU/memória/arquivo/descritores/tempo/volume de saída.
"""
import json
import os
import resource
import shutil
import subprocess
import sys
import sysconfig
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


def _du(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def run_worker(pdf: Path, gabarito: Path | None, out: Path, de: int, ate: int, limites: dict | None = None) -> None:
    pdf, out = pdf.resolve(), out.resolve()
    gabarito = gabarito.resolve() if gabarito else None
    lim = {**LIMITES, **(limites or {})}
    sonda()  # nunca roda o parser sem provar o isolamento
    out.mkdir(parents=True, exist_ok=True)
    args = ["--pdf", str(pdf), "--out", str(out), "--de", str(de), "--ate", str(ate)]
    ro = [str(pdf)]
    if gabarito:
        args += ["--gabarito", str(gabarito)]
        ro.append(str(gabarito))
    cmd = _cmd(args, ro, [str(out)])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=lim["timeout_s"], preexec_fn=_preexec(lim))
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"tempo excedido ({lim['timeout_s']}s) no worker isolado") from e
    if r.returncode != 0:
        raise RuntimeError(f"worker isolado falhou (código {r.returncode}): {r.stderr.strip()[-400:]}")
    if _du(out) > lim["saida_max_bytes"]:
        raise RuntimeError("volume de saída acima do limite")
