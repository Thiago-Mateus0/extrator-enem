"""Campos-ouro: valores esperados (lidos no PDF por uma pessoa) e medição de uma extração contra eles.

Mede FIDELIDADE (o texto extraído é o texto da prova?), diferente dos alertas, que só dizem
"olhe aqui". Cada item do arquivo de ouro diz o que deveria sair; `medir` conta acertos.

Comparação ignora espaços (o extrator separa "7 !" e a prova tem "7!"), mas não ignora mais nada.
"""
import json
import re
from collections.abc import Callable
from pathlib import Path

TIPOS = ("alternativa", "enunciado_contem", "tabela")


def _n(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


def visao(q) -> dict:
    """Normaliza um registro (dict de questions/*.json) ou uma `Question` para o que o ouro compara."""
    if isinstance(q, dict):
        ch = q["choices"]
        ch = {c["letter"]: c["text"] for c in ch} if isinstance(ch, list) else ch
        return {"stem": q["stem"], "choices": ch, "tables": [t["rows"] for t in q.get("tables", [])]}
    return {"stem": q.stem, "choices": q.choices,
            "tables": [a["table"]["rows"] for a in q.assets if "table" in a]}


def avaliar(item: dict, q) -> tuple[bool, str]:
    """(passou, obtido) para um item de ouro contra uma questão."""
    v, tipo = visao(q), item["tipo"]
    if tipo == "alternativa":
        obtido = v["choices"].get(item["letra"])
        return _n(obtido) == _n(item["esperado"]), repr(obtido)
    if tipo == "enunciado_contem":
        return _n(item["esperado"]) in _n(v["stem"]), "(trecho ausente)"
    if tipo == "tabela":
        i = item.get("indice", 0)
        obtido = v["tables"][i] if i < len(v["tables"]) else None
        return obtido == item["esperado"], repr(obtido)
    raise ValueError(f"tipo de item de ouro desconhecido: {tipo!r}")


def carregar(caminho: Path) -> dict:
    ouro = json.loads(Path(caminho).read_text(encoding="utf-8"))
    ids = [i["id"] for i in ouro["itens"]]
    if len(ids) != len(set(ids)):
        raise ValueError("ids duplicados no arquivo de ouro")
    for i in ouro["itens"]:
        if i["tipo"] not in TIPOS:
            raise ValueError(f"item {i['id']}: tipo inválido {i['tipo']!r}")
    return ouro


def medir(ouro: dict, obter: Callable[[int, int], object | None]) -> dict:
    """`obter(ano, numero)` devolve a questão (ou None se aquele ano não foi extraído)."""
    acertos, erros, ignorados = [], [], []
    for item in ouro["itens"]:
        q = obter(item["ano"], item["numero"])
        if q is None:
            ignorados.append(item["id"])
            continue
        ok, obtido = avaliar(item, q)
        if ok:
            acertos.append(item["id"])
        else:
            erros.append({"id": item["id"], "esperado": item["esperado"], "obtido": obtido})
    total = len(acertos) + len(erros)
    return {"avaliados": total, "acertos": len(acertos), "erros": erros, "ignorados": ignorados,
            "taxa": round(len(acertos) / total, 3) if total else None}


def obter_de_runs(runs: dict[int, Path]) -> Callable[[int, int], dict | None]:
    """Lê questions/*-NNN.json de uma pasta de execução por ano."""
    def obter(ano: int, numero: int):
        if ano not in runs:
            return None
        achados = sorted((Path(runs[ano]) / "questions").glob(f"*-{numero:03d}.json"))
        return json.loads(achados[0].read_text(encoding="utf-8")) if achados else {"stem": "", "choices": {}}
    return obter
