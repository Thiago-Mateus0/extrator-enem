"""Testes de referência sobre os PDFs reais (dados/provas, não versionados)."""
from pathlib import Path

import pytest

from extrator_enem.gabarito import read_gabarito
from extrator_enem.layout import read_document
from extrator_enem.segment import split_questions

P = Path(__file__).resolve().parents[1] / "dados" / "provas"


def _load(year):
    pv = P / f"{year}_PV_impresso_D2_CD5.pdf"
    gb = P / f"{year}_GB_impresso_D2_CD5.pdf"
    if not pv.exists() or not gb.exists():
        pytest.skip("PDFs de referência ausentes em dados/provas")
    lines, omitted, vis = read_document(str(pv))
    qs = {q.number: q for q in split_questions(lines, 91, 180, vis)}
    return qs, read_gabarito(str(gb)), omitted


@pytest.fixture(scope="module")
def y24():
    return _load(2024)


@pytest.fixture(scope="module")
def y25():
    return _load(2025)


def codes(q):
    return {i["code"] for i in q.issues}


@pytest.mark.parametrize("fx", ["y24", "y25"])
def test_cobertura_90_questoes_sem_duplicatas(fx, request):
    qs, gb, _ = request.getfixturevalue(fx)
    assert sorted(qs) == list(range(91, 181))
    assert len(gb) == 90


def test_gabarito_distingue_anulado_de_letra(y24, y25):
    assert y24[1][102] == {"state": "annulled", "letter": None}
    assert {n for n, a in y25[1].items() if a["state"] == "annulled"} == {115, 121, 178}
    assert y24[1][149] == {"state": "found", "letter": "E"}
    assert y24[1][141]["letter"] == "E" and y24[1][142]["letter"] == "D"


def test_controle_texto_simples_q130(y24):
    q = y24[0][130]
    assert not q.issues
    assert set(q.choices) == set("ABCDE") and all(q.choices.values())


def test_controle_figuras_q106_alternativas_so_imagem(y24):
    q = y24[0][106]
    assert "empty_choice" not in codes(q) and "choice_image_only" in codes(q)
    assert not any("ENEM" in t for t in q.choices.values())  # marca d'água fora do texto


def test_tabela_q94_preserva_decimais_e_alternativas(y24):
    q = y24[0][94]
    for v in ("9,5", "11,0", "7,7", "6,9", "7,3"):
        assert v in q.stem
    assert [q.choices[k] for k in "ABCDE"] == ["I", "II", "III", "IV", "V"]


@pytest.mark.xfail(strict=True, reason="setas de equilíbrio são vetores sem texto; ainda não recuperadas")
def test_q94_seta_de_equilibrio_preservada(y24):
    assert "⇌" in y24[0][94].stem


ALERTAS = {"fragmented_formula", "broken_glyph", "frac_reconstructed", "missing_reaction_arrow",
           "duplicate_choices", "empty_stem", "choices_not_found"}


@pytest.mark.parametrize("n", [94, 139, 141, 149, 150, 151, 158, 179])
def test_defeitos_conhecidos_2024_sao_sinalizados(y24, n):
    assert codes(y24[0][n]) & ALERTAS


@pytest.mark.parametrize("n", [115, 123, 159, 164, 170, 176])
def test_defeitos_conhecidos_2025_sao_sinalizados(y25, n):
    assert codes(y25[0][n]) & ALERTAS


@pytest.mark.xfail(strict=True, reason="número misto sem barra ('4 5 6 polegadas') ainda passa em silêncio")
def test_q142_numero_misto_sinalizado(y24):
    assert codes(y24[0][142]) & ALERTAS


@pytest.mark.xfail(strict=True, reason="deslocamento figura/alternativa (Q129) exige extração de recursos; não implementada")
def test_q129_2025_deslocamento_de_graficos_sinalizado(y25):
    assert codes(y25[0][129]) & ALERTAS


def test_expoentes_e_subscritos_recuperados(y24, y25):
    assert y24[0][169].choices["B"] == "3 × 2^{20}"
    assert "M_{1}" in y24[0][150].stem
    assert y25[0][176].choices["A"] == "10^{0,5}"
    assert "Ca_{5}(PO_{4})_{3}OH" in y24[0][94].stem


def test_fracoes_reconstruidas_q149_alternativa_a(y24):
    assert y24[0][149].choices["A"] == "\\frac{1}{25} + \\frac{1}{25} + \\frac{1}{25}"


def test_fracao_reconstruida_nunca_passa_limpa(y24, y25):
    for qs, _, _ in (y24, y25):
        for q in qs.values():
            texto = q.stem + "".join(q.choices.values())
            if "\\frac{" in texto:
                assert "frac_reconstructed" in codes(q)


def test_alternativas_em_grade_de_figuras_q144_2025(y25):
    q = y25[0][144]
    assert set(q.regions) == set("ABCDE") and "choices_not_found" not in codes(q)


def test_marca_dagua_removida_com_registro(y24, y25):
    for qs, _, omitted in (y24, y25):
        assert not any("ENEM" in q.stem or any("ENEM" in c for c in q.choices.values()) for q in qs.values())
        assert any(o["reason"] == "marca-dagua" for o in omitted)
