"""Leitura do gabarito oficial; distingue letra, anulado e ausente."""
import re

import pymupdf


def read_gabarito(path: str) -> dict[int, dict]:
    doc = pymupdf.open(path)
    toks = [l.strip() for p in doc for l in p.get_text().split("\n") if l.strip()]
    out: dict[int, dict] = {}
    for i, t in enumerate(toks[:-1]):
        if re.fullmatch(r"\d{2,3}", t):
            v = toks[i + 1]
            if re.fullmatch(r"[A-E]", v):
                out[int(t)] = {"state": "found", "letter": v}
            elif v.lower().startswith("anulad"):
                out[int(t)] = {"state": "annulled", "letter": None}
    return out
