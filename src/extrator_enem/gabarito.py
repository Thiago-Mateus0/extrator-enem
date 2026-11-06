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


def identity_gabarito(path: str) -> dict:
    t = "\n".join(p.get_text() for p in pymupdf.open(path))
    cad = re.search(r"CADERNO\s*(\d+)", t, re.I)
    ano = re.search(r"Gabarito\s*(\d{4})", t, re.I)
    dia = re.search(r"dia\s*º?\s*\n?\s*(\d)", t, re.I)
    return {"caderno": cad and cad.group(1), "ano": ano and ano.group(1), "dia": dia and dia.group(1)}


def identity_prova(path: str) -> dict:
    doc = pymupdf.open(path)
    for p in list(doc)[:4]:
        m = re.search(r"(\d)º DIA\s*[•|]\s*CADERNO\s*(\d+)", p.get_text())
        if m:
            return {"dia": m.group(1), "caderno": m.group(2)}
    return {"dia": None, "caderno": None}
