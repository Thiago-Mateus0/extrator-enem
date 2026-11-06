import json
import threading

from extrator_enem.records import content_hash
from extrator_enem.store import Store, safe_label


def test_nome_vira_so_metadado_saneado():
    assert safe_label("../../etc/passwd") == "passwd"
    assert "/" not in safe_label("a/b c.pdf")


def test_execucao_nova_nunca_sobrescreve_e_ids_unicos(tmp_path):
    st = Store(tmp_path)
    ids = []
    def go():
        ids.append(st.new_run("abc")[0])
    ts = [threading.Thread(target=go) for _ in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(set(ids)) == 20  # concorrentes não colidem


def test_current_json_atomico_e_manifesto(tmp_path):
    st = Store(tmp_path)
    for r in ("r1", "r2"):
        st.publish("abc", r, "prova.pdf", {"estado": "completo"})
    d = st.source_dir("abc")
    assert json.loads((d / "current.json").read_text()) == {"run_id": "r2"}
    assert [x["run_id"] for x in json.loads((d / "manifest.json").read_text())["runs"]] == ["r1", "r2"]
    assert not list(d.glob(".*.tmp"))


def test_revisao_antiga_nao_vale_para_conteudo_novo(tmp_path):
    st = Store(tmp_path)
    ans = {"letter": "C", "state": "found", "origin": "g"}
    ch = lambda t: [{"letter": "A", "text": t, "asset_ids": []}]
    h1 = content_hash("enunciado", ch("x"), [], ans)
    h2 = content_hash("enunciado", ch("y"), [], ans)
    assert h1 != h2
    assert h1 != content_hash("enunciado", ch("x"), [], {**ans, "letter": "D"})  # gabarito entra no hash
    st.save_review("q-1", h1, "approved", "thiago")
    rec = {"question_id": "q-1", "content_sha256": h2}
    st.annotate_reprocessing(rec, None)
    assert rec["reprocessing"]["review_stale"] is True
    rec = {"question_id": "q-1", "content_sha256": h1}
    st.annotate_reprocessing(rec, None)
    assert rec["reprocessing"]["review_stale"] is False and rec["reprocessing"]["valid_review"] == "approved"
