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
