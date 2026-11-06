import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

from .gabarito import read_gabarito
from .layout import read_document
from .segment import split_questions


def sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(prova: str, gabarito: str | None, de: int, ate: int, saida: str) -> dict:
    lines, omitted, visuals = read_document(prova)
    qs = split_questions(lines, de, ate, visuals)
    gb = read_gabarito(gabarito) if gabarito else {}
    out = Path(saida)
    out.mkdir(parents=True, exist_ok=True)
    records, nums = [], [q.number for q in qs]
    for q in qs:
        ans = gb.get(q.number, {"state": "not_provided", "letter": None})
        issues = list(q.issues)
        image_only = {i["message"].split()[1] for i in q.issues if i["code"] == "choice_image_only"}
        if ans["state"] == "found" and not q.choices.get(ans["letter"]) and ans["letter"] not in image_only:
            issues.append({"code": "answer_without_choice", "severity": "critical",
                           "message": f"gabarito {ans['letter']} sem alternativa correspondente"})
        records.append({**dataclasses.asdict(q), "issues": issues, "answer": ans,
                        "status": "needs_review" if any(i["severity"] != "info" for i in issues) else "extracted"})
    esperado = set(range(de, ate + 1))
    report = {
        "prova_sha256": sha256(prova),
        "gabarito_sha256": sha256(gabarito) if gabarito else None,
        "esperadas": len(esperado), "encontradas": len(set(nums)),
        "ausentes": sorted(esperado - set(nums)),
        "duplicadas": sorted({n for n in nums if nums.count(n) > 1}),
        "com_problema": sum(1 for r in records if r["status"] == "needs_review"),
        "gabarito": {s: sum(1 for r in records if r["answer"]["state"] == s)
                     for s in ("found", "annulled", "not_provided")},
        "omitidos": len(omitted),
    }
    report["por_codigo"] = {}
    for r in records:
        for i in r["issues"]:
            report["por_codigo"][i["code"]] = report["por_codigo"].get(i["code"], 0) + 1
    report["questoes_para_conferir"] = {
        r["number"]: sorted({i["code"] for i in r["issues"] if i["severity"] != "info"})
        for r in records if r["status"] == "needs_review"}
    (out / "relatorio.md").write_text(_relatorio_md(report))
    (out / "questions.json").write_text(json.dumps(records, ensure_ascii=False, indent=1))
    (out / "omitted.json").write_text(json.dumps(omitted, ensure_ascii=False, indent=1))
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def _relatorio_md(r: dict) -> str:
    g = r["gabarito"]
    linhas = [
        "# Relatório de extração", "",
        f"- Prova SHA-256: `{r['prova_sha256']}`",
        f"- Gabarito SHA-256: `{r['gabarito_sha256']}`",
        f"- Questões: {r['encontradas']}/{r['esperadas']} encontradas; ausentes: {r['ausentes'] or 'nenhuma'}; duplicadas: {r['duplicadas'] or 'nenhuma'}",
        f"- Gabarito: {g['found']} com letra, {g['annulled']} anuladas, {g['not_provided']} sem gabarito",
        f"- Linhas de mobiliário/marca d'água removidas (ver omitted.json): {r['omitidos']}",
        f"- **Questões para conferir: {r['com_problema']}** de {r['encontradas']}", "",
        "> Estas contagens medem *alertas automáticos*, não fidelidade. Questão sem alerta não está certificada;",
        "> `frac_reconstructed` é reconstrução geométrica e precisa ser conferida contra a página.", "",
        "## Alertas por código", "", "| código | ocorrências |", "|---|---|",
    ]
    linhas += [f"| {c} | {n} |" for c, n in sorted(r["por_codigo"].items())]
    linhas += ["", "## Questões para conferir", "", "| questão | alertas |", "|---|---|"]
    linhas += [f"| {n} | {', '.join(c)} |" for n, c in r["questoes_para_conferir"].items()]
    return "\n".join(linhas) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(prog="extrator-enem")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="extrai questões de prova + gabarito")
    e.add_argument("prova")
    e.add_argument("--gabarito")
    e.add_argument("--de", type=int, required=True)
    e.add_argument("--ate", type=int, required=True)
    e.add_argument("--saida", required=True)
    a = p.parse_args()
    if a.cmd == "extract":
        print(json.dumps(extract(a.prova, a.gabarito, a.de, a.ate, a.saida), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
