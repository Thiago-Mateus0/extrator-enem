"""Parser sobre um PDF sintético gerado aqui mesmo: roda na CI sem as provas oficiais (que não são versionadas)."""
import pymupdf
import pytest

from extrator_enem.layout import read_document
from extrator_enem.segment import split_questions


def _prova(caminho, questoes):
    """Uma página, coluna esquerda: cada questão é uma lista de linhas (marcador, enunciado, alternativas)."""
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for linhas in questoes:
        for linha in linhas:
            page.insert_text((50, y), linha, fontsize=10)
            y += 14
        y += 10
    doc.save(str(caminho))
    return str(caminho)


@pytest.fixture(scope="module")
def questoes(tmp_path_factory):
    pdf = _prova(tmp_path_factory.mktemp("sint") / "prova.pdf", [
        ["QUESTÃO 91", "Qual é a capital do Brasil?",
         "A Rio de Janeiro", "B Brasília", "C São Paulo", "D Salvador", "E Recife"],
        ["QUESTÃO 92", "Quanto é 2 + 2?",
         "A 4", "B 4", "C 4", "D 4", "E 4"],
        ["QUESTÃO 93", "Enunciado sem alternativas reconhecíveis."],
    ])
    linhas, omitidas, assets = read_document(pdf)
    return {q.number: q for q in split_questions(linhas, 91, 93)}


def test_encontra_as_tres_questoes(questoes):
    assert sorted(questoes) == [91, 92, 93]


def test_questao_limpa_sai_sem_alerta(questoes):
    q = questoes[91]
    assert q.stem == "Qual é a capital do Brasil?"
    assert q.choices == {"A": "Rio de Janeiro", "B": "Brasília", "C": "São Paulo", "D": "Salvador", "E": "Recife"}
    assert q.issues == []


def test_alternativas_identicas_viram_alerta_critico(questoes):
    codigos = {i["code"]: i["severity"] for i in questoes[92].issues}
    assert codigos.get("duplicate_choices") == "critical"


def test_sem_alternativas_nao_inventa_resposta(questoes):
    q = questoes[93]
    assert q.choices == {}
    assert {i["code"] for i in q.issues} >= {"choices_not_found"}


def test_questoes_fora_da_faixa_sao_ignoradas(tmp_path):
    pdf = _prova(tmp_path / "p.pdf", [["QUESTÃO 10", "Fora da faixa.", "A a", "B b", "C c", "D d", "E e"]])
    linhas, _, _ = read_document(pdf)
    assert split_questions(linhas, 91, 180) == []


# ---- exemplo de saída documentado (docs/exemplo/questao-91.json) ----
import json
from dataclasses import asdict
from pathlib import Path

from extrator_enem.records import build_record

EXEMPLO = Path(__file__).parent.parent / "docs" / "exemplo" / "questao-91.json"


def registro_exemplo(questoes) -> dict:
    """Registro da questão 91 sintética, com SHA e gabarito fixos de mentira (só para ilustrar o formato)."""
    q = asdict(questoes[91])
    q["snapshots"] = []
    return build_record(q, {"letter": "B", "state": "found"}, "a" * 64, "b" * 64, "prova-sintetica.pdf", "run-exemplo")


def test_exemplo_documentado_esta_atualizado(questoes):
    atual = registro_exemplo(questoes)
    assert json.loads(EXEMPLO.read_text(encoding="utf-8")) == atual, (
        "docs/exemplo/questao-91.json está desatualizado: regrave-o com "
        "json.dumps(registro_exemplo(questoes), ensure_ascii=False, indent=2)")
