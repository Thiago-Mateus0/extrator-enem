import json
import sys

import pytest

from extrator_enem import sandbox

linux_bwrap = pytest.mark.skipif(sys.platform != "linux" or not __import__("shutil").which("bwrap"),
                                 reason="requer Linux + bwrap")


@linux_bwrap
def test_sonda_prova_isolamento_efetivo():
    res = sandbox.sonda()
    assert res == {"rede_negada": True, "home_negado": True, "usr_somente_leitura": True,
                   "sem_credenciais_no_ambiente": True}


def test_falha_fechada_sem_backend(monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: None)
    with pytest.raises(sandbox.SandboxUnavailable, match="falha fechada"):
        sandbox.sonda()


def test_falha_fechada_se_sonda_detecta_isolamento_ineficaz(monkeypatch):
    class R:
        returncode, stdout, stderr = 0, json.dumps({"rede_negada": False}), ""
    monkeypatch.setattr(sandbox, "_cmd", lambda *a, **k: ["true"])
    monkeypatch.setattr(sandbox.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(sandbox.SandboxUnavailable, match="NÃO efetivo"):
        sandbox.sonda()


@linux_bwrap
def test_parser_real_roda_no_sandbox_e_rejeita_pdf_invalido(tmp_path):
    from extrator_enem.store import Store
    bad = tmp_path / "falso.pdf"
    bad.write_bytes(b"nao sou pdf")
    with pytest.raises(ValueError, match="assinatura de PDF"):
        Store(tmp_path / "d").quarantine(bad)


def _tar_com(membros):
    import io
    import tarfile
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w:") as tf:
        for nome, data, tipo in membros:
            ti = tarfile.TarInfo(nome)
            if tipo == "link":
                ti.type, ti.linkname = tarfile.SYMTYPE, "/etc/passwd"
            else:
                ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data) if tipo != "link" else None)
    b.seek(0)
    return b


def test_saida_do_worker_rejeita_symlink_e_nome_fora_da_lista(tmp_path):
    with pytest.raises(RuntimeError, match="membro inválido"):
        sandbox._receber(_tar_com([("assets/" + "a" * 64 + ".png", b"", "link")]), 10**6, tmp_path / "o1")
    with pytest.raises(RuntimeError, match="membro inválido"):
        sandbox._receber(_tar_com([("../../evil.json", b"{}", "file")]), 10**6, tmp_path / "o2")


def test_saida_do_worker_rejeita_png_com_hash_divergente(tmp_path):
    with pytest.raises(RuntimeError, match="hash divergente"):
        sandbox._receber(_tar_com([("assets/" + "a" * 64 + ".png", b"png-falso", "file")]), 10**6, tmp_path / "o")


def test_saida_do_worker_acima_do_teto_e_abortada_durante_a_leitura(tmp_path):
    with pytest.raises(RuntimeError, match="acima do limite"):
        sandbox._receber(_tar_com([("omitted.json", b"x" * 5000, "file")]), 1000, tmp_path / "o")


def test_saida_valida_e_gravada_pelo_host(tmp_path):
    import hashlib
    png = b"\x89PNGfake"
    h = hashlib.sha256(png).hexdigest()
    sandbox._receber(_tar_com([("omitted.json", b"[]", "file"), (f"assets/{h}.png", png, "file")]), 10**6, tmp_path / "o")
    assert (tmp_path / "o" / f"assets/{h}.png").read_bytes() == png
