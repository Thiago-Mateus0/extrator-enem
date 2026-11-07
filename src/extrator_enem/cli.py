import argparse
import json
import sys

from pathlib import Path

from . import ouro
from .pipeline import IdentityError, compare, extract
from .records import question_id
from .sandbox import SandboxUnavailable, sonda
from .store import Store


def _resumo(r: dict) -> str:
    return json.dumps({k: r[k] for k in ("run_id", "estado", "esperadas", "encontradas", "gabarito", "status",
                                         "por_codigo", "tempo_s", "_run_dir")}, ensure_ascii=False, indent=1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="extrator-enem")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="extrai questões de prova + gabarito (parser em sandbox)")
    e.add_argument("prova")
    e.add_argument("--gabarito")
    e.add_argument("--de", type=int, required=True)
    e.add_argument("--ate", type=int, required=True)
    e.add_argument("--dados", required=True, help="raiz de dados (quarentena/ e saida/)")
    e.add_argument("--ano")
    e.add_argument("--dia")
    e.add_argument("--caderno")
    sub.add_parser("sonda", help="prova funcional do isolamento (rede/home/escrita negadas)")
    c = sub.add_parser("compare", help="compara duas execuções (baseline x candidato)")
    c.add_argument("run_a")
    c.add_argument("run_b")
    o = sub.add_parser("ouro", help="mede a fidelidade da extração contra campos-ouro (valores lidos no PDF)")
    o.add_argument("--ouro", required=True, help="arquivo JSON de campos-ouro")
    o.add_argument("--run", action="append", required=True, metavar="ANO=PASTA_DA_EXECUCAO")
    r = sub.add_parser("review", help="registra veredito HUMANO preso ao hash do conteúdo atual")
    r.add_argument("--dados", required=True)
    r.add_argument("--source", required=True, help="source_id (SHA-256 completo da prova)")
    r.add_argument("--numero", type=int, required=True)
    r.add_argument("--verdict", choices=["approved", "rejected", "doubt"], required=True)
    r.add_argument("--by", required=True)
    r.add_argument("--note", default="")
    a = p.parse_args(argv)
    try:
        if a.cmd == "sonda":
            print(json.dumps(sonda(), indent=1))
        elif a.cmd == "extract":
            rep = extract(a.prova, a.gabarito, a.de, a.ate, a.dados,
                          {k: v for k, v in (("ano", a.ano), ("dia", a.dia), ("caderno", a.caderno)) if v})
            print(_resumo(rep))
            return 0 if rep["estado"] == "completo" else 2
        elif a.cmd == "ouro":
            runs = {int(k): Path(v) for k, v in (x.split("=", 1) for x in a.run)}
            res = ouro.medir(ouro.carregar(Path(a.ouro)), ouro.obter_de_runs(runs))
            print(json.dumps(res, ensure_ascii=False, indent=1))
        elif a.cmd == "compare":
            print(json.dumps(compare(a.run_a, a.run_b), ensure_ascii=False, indent=1))
        elif a.cmd == "review":
            st = Store(a.dados)
            cur = json.loads((st.source_dir(a.source) / "current.json").read_text())["run_id"]
            f = st.source_dir(a.source) / "runs" / cur / "questions" / f"{question_id(a.source, a.numero)}.json"
            rec = json.loads(f.read_text())
            print(st.save_review(rec["question_id"], rec["content_sha256"], a.verdict, a.by, a.note))
    except SandboxUnavailable as ex:
        print(f"ERRO (falha fechada): {ex}", file=sys.stderr)
        return 3
    except IdentityError as ex:
        print(f"ERRO de identidade da fonte: {ex}", file=sys.stderr)
        return 4
    except (ValueError, RuntimeError, FileNotFoundError) as ex:
        print(f"ERRO: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
