"""Registro intermediário de extração por questão (superconjunto do registro v1 do briefing §7.2)."""
import hashlib
import json

INGESTION_VERSION = "1"
RECORD_VERSION = "2"  # v1 + answer.state, regions, assets com papel/bbox


def question_id(source_sha: str, number: int) -> str:
    return f"q-{source_sha[:12]}-{number:03d}"


def content_hash(stem: str, choices: list[dict], tables: list, answer: dict) -> str:
    """Hash do conteúdo revisável: enunciado, alternativas/recursos, tabelas e resposta/origem."""
    canon = {"stem": stem,
             "choices": [{"letter": c["letter"], "text": c["text"], "asset_ids": sorted(c["asset_ids"])} for c in choices],
             "tables": tables,
             "answer": {"letter": answer["letter"], "state": answer["state"], "origin": answer["origin"]}}
    return hashlib.sha256(json.dumps(canon, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_record(q: dict, ans: dict, source_sha: str, gabarito_sha: str | None, source_label: str, run_id: str) -> dict:
    choices = []
    for letter in "ABCDE":
        if letter in q["choices"]:
            ids = sorted({a["hash"] for a in q["assets"] if a["role"] == "choice" and a.get("letter") == letter})
            choices.append({"letter": letter, "text": q["choices"][letter], "asset_ids": ids})
    answer = {"letter": ans["letter"], "state": ans["state"],
              "origin": gabarito_sha if gabarito_sha else None,
              "origin_label": "gabarito oficial (PDF)" if gabarito_sha else None}
    issues = list(q["issues"])
    choice_letters = {c["letter"] for c in choices}
    if ans["state"] == "found":
        c = next((c for c in choices if c["letter"] == ans["letter"]), None)
        if c is None or not (c["text"] or c["asset_ids"]):
            issues.append({"code": "answer_without_choice", "severity": "critical",
                           "message": f"gabarito {ans['letter']} sem alternativa correspondente"})
    elif ans["state"] == "not_provided":
        issues.append({"code": "answer_not_provided", "severity": "review",
                       "message": "questão ausente no gabarito do mesmo caderno (não é anulação)"})
    tables: list = []
    assets = [{"asset_id": a["hash"], "hash": a["hash"], "kind": a["kind"], "page": a["page"], "bbox": a["bbox"],
               "role": a["role"], **({"letter": a["letter"]} if "letter" in a else {})} for a in q["assets"]]
    chash = content_hash(q["stem"], choices, tables, answer)
    return {
        "record_version": RECORD_VERSION,
        "question_id": question_id(source_sha, q["number"]),
        "number": q["number"],
        "status": "needs_review" if any(i["severity"] != "info" for i in issues) else "extracted",
        "content_sha256": chash,
        "stem": q["stem"],
        "choices": choices,
        "tables": tables,
        "answer": answer,
        "location": {"page_start": q["page_start"], "page_end": q["page_end"]},
        "source": {"source_id": f"src-{source_sha[:12]}", "source_sha256": source_sha,
                   "version": INGESTION_VERSION, "label": source_label},
        "assets": assets,
        "snapshots": q["snapshots"],
        "regions": q["regions"],
        "issues": issues,
        "annotations": [],
        "provenance": {"ingestion_version": INGESTION_VERSION, "extractor": "extrator-enem/pymupdf-native",
                       "run_id": run_id, "source_label": source_label},
        "reprocessing": {},
    }
