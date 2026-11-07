import json

import pytest

from extrator_enem import ouro


def _q(stem="", choices=None, tables=()):
    return {"stem": stem, "choices": [{"letter": k, "text": v, "asset_ids": []} for k, v in (choices or {}).items()],
            "tables": [{"rows": r} for r in tables]}


def test_alternativa_ignora_espacos_mas_nao_o_resto():
    item = {"tipo": "alternativa", "letra": "B", "esperado": "\\frac{7!}{4!}"}
    assert ouro.avaliar(item, _q(choices={"B": "\\frac{7 !}{4 !}"}))[0]
    assert not ouro.avaliar(item, _q(choices={"B": "\\frac{7 !}{3 !}"}))[0]
    assert not ouro.avaliar(item, _q(choices={}))[0]  # alternativa ausente reprova


def test_enunciado_contem_e_tabela():
    assert ouro.avaliar({"tipo": "enunciado_contem", "esperado": "1 m^{3}"}, _q(stem="de 1  m^{3} de gás"))[0]
    assert not ouro.avaliar({"tipo": "enunciado_contem", "esperado": "⇌"}, _q(stem="sem seta"))[0]
    rows = [["a", "b"], ["1", "2"]]
    assert ouro.avaliar({"tipo": "tabela", "indice": 0, "esperado": rows}, _q(tables=[rows]))[0]
    assert not ouro.avaliar({"tipo": "tabela", "indice": 0, "esperado": rows}, _q())[0]


def test_medir_conta_acertos_erros_e_ignorados():
    o = {"itens": [
        {"id": "a", "ano": 2024, "numero": 1, "tipo": "enunciado_contem", "esperado": "x"},
        {"id": "b", "ano": 2024, "numero": 1, "tipo": "enunciado_contem", "esperado": "y"},
        {"id": "c", "ano": 2025, "numero": 1, "tipo": "enunciado_contem", "esperado": "x"}]}
    r = ouro.medir(o, lambda ano, n: _q(stem="x") if ano == 2024 else None)
    assert (r["avaliados"], r["acertos"], r["ignorados"], r["taxa"]) == (2, 1, ["c"], 0.5)
    assert [e["id"] for e in r["erros"]] == ["b"]


def test_carregar_rejeita_id_duplicado_e_tipo_invalido(tmp_path):
    base = {"id": "a", "ano": 2024, "numero": 1, "esperado": "x"}
    f = tmp_path / "o.json"
    f.write_text(json.dumps({"itens": [{**base, "tipo": "alternativa"}, {**base, "tipo": "alternativa"}]}))
    with pytest.raises(ValueError, match="duplicados"):
        ouro.carregar(f)
    f.write_text(json.dumps({"itens": [{**base, "tipo": "outro"}]}))
    with pytest.raises(ValueError, match="inválido"):
        ouro.carregar(f)
