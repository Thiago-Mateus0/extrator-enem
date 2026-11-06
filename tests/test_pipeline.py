import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

from extrator_enem import pipeline
from extrator_enem.sandbox import SandboxUnavailable

P = Path(__file__).resolve().parents[1] / "dados" / "provas"
pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not shutil.which("bwrap") or not (P / "2024_PV_impresso_D2_CD5.pdf").exists(),
    reason="requer Linux + bwrap + PDFs de referência")


@pytest.fixture(scope="module")
def run24(tmp_path_factory):
    d = tmp_path_factory.mktemp("dados")
    rep = pipeline.extract(str(P / "2024_PV_impresso_D2_CD5.pdf"), str(P / "2024_GB_impresso_D2_CD5.pdf"), 91, 180, str(d))
    return d, rep


def test_fim_a_fim_no_sandbox(run24):
    d, rep = run24
    run = Path(rep["_run_dir"])
    assert rep["estado"] == "completo" and rep["encontradas"] == 90
    assert all(v["ok"] for v in rep["validacoes"] if v["check"] in (
        "intervalo_sem_ausentes_nem_duplicados", "recursos_existem_com_hash_correto", "gabarito_coerente_com_alternativas"))
    assert len(list((run / "questions").glob("*.json"))) == 90
    assert (run / "relatorio.md").exists() and (run / "conferencia.csv").exists()
    rec = json.loads((run / "questions" / "q-ec4e704ab401-149.json").read_text())
    assert rec["answer"] == {"letter": "E", "state": "found",
                             "origin": rep["fonte"]["gabarito_sha256"], "origin_label": "gabarito oficial (PDF)"}
    assert rec["source"]["source_id"] == "src-ec4e704ab401" and rec["record_version"] == "2"
    assert all(a["origin"] != "reviewed" for a in (rec["answer"],))


def test_anulada_nao_e_gabarito_vazio(run24):
    _, rep = run24
    run = Path(rep["_run_dir"])
    q102 = json.loads((run / "questions" / "q-ec4e704ab401-102.json").read_text())
    assert q102["answer"]["state"] == "annulled" and q102["answer"]["letter"] is None


def test_reprocessar_preserva_execucao_antiga_e_invalida_revisao(run24):
    d, rep = run24
    sha = rep["fonte"]["prova_sha256"]
    rep2 = pipeline.extract(str(P / "2024_PV_impresso_D2_CD5.pdf"), str(P / "2024_GB_impresso_D2_CD5.pdf"), 91, 180, str(d))
    assert rep2["run_id"] != rep["run_id"] and Path(rep["_run_dir"]).exists()
    cur = json.loads((d / "saida" / "sources" / sha / "current.json").read_text())
    assert cur["run_id"] == rep2["run_id"]
    diff = pipeline.compare(rep["_run_dir"], rep2["_run_dir"])
    assert diff["conteudo_alterado"] == [] and diff["introduzidos"] == []


def test_gabarito_de_outro_ano_e_recusado(tmp_path):
    with pytest.raises(pipeline.IdentityError, match="gabarito de 2025"):
        pipeline.extract(str(P / "2024_PV_impresso_D2_CD5.pdf"), str(P / "2025_GB_impresso_D2_CD5.pdf"),
                         91, 180, str(tmp_path))
    falhas = list(tmp_path.rglob("FALHOU.json"))
    assert falhas and not list(tmp_path.rglob("current.json"))  # nada publicado


def test_renomear_pdf_nao_muda_identidade(tmp_path):
    from extrator_enem.store import Store
    c = tmp_path / "outro_nome.pdf"
    shutil.copy(P / "2024_PV_impresso_D2_CD5.pdf", c)
    assert Store(tmp_path / "d").quarantine(c) == "ec4e704ab4017762ffb1eba84c55285a429d3d02ed0e58258c1171315cb34937"


def test_csv_protegido_contra_formula():
    assert pipeline._csv_safe("=SUM(A1)").startswith("'") and pipeline._csv_safe("@x").startswith("'")
    assert pipeline._csv_safe("normal") == "normal"
