from extrator_enem.gabarito import read_gabarito
import pymupdf


def test_gabarito_vazio_nao_vira_anulado(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "QUESTÃO\nGABARITO\n91\nC\n92\nAnulado\n93\n")
    f = tmp_path / "gb.pdf"
    doc.save(f)
    got = read_gabarito(str(f))
    assert got[91] == {"state": "found", "letter": "C"}
    assert got[92]["state"] == "annulled"
    assert 93 not in got  # ausente permanece ausente, nunca "anulado"
