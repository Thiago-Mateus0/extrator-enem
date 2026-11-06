"""Processo isolado: lê o PDF (conteúdo não confiável) e grava resultados intermediários.

Executado SEMPRE dentro do sandbox (ver sandbox.py). Sem credenciais, sem rede.
"""
import argparse
import hashlib
import json
import os
import socket
import sys
from dataclasses import asdict
from pathlib import Path

import pymupdf

from .gabarito import identity_gabarito, identity_prova, read_gabarito
from .layout import read_document
from .segment import split_questions


def _probe() -> dict:
    """Sonda funcional do isolamento: tudo que deveria estar negado precisa falhar."""
    res = {}
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect(("1.1.1.1", 53))
        res["rede_negada"] = False
    except OSError:
        res["rede_negada"] = True
    for nome, caminho in (("home_negado", os.path.expanduser("~/.ssh")), ("usr_somente_leitura", "/usr/x_probe")):
        try:
            if nome == "home_negado":
                res[nome] = not os.path.exists(caminho)
            else:
                open(caminho, "w").close()
                res[nome] = False
        except OSError:
            res[nome] = True
    res["sem_credenciais_no_ambiente"] = not any(
        k.upper().endswith(("KEY", "TOKEN", "SECRET", "PASSWORD")) or k.startswith("ANTHROPIC") for k in os.environ)
    return res


def _snapshots(pdf: str, questions: list, out: Path, dpi: int = 130) -> None:
    doc = pymupdf.open(pdf)
    (out / "snapshots").mkdir(exist_ok=True)
    for q in questions:
        q["snapshots"] = []
        for seg in q["segments"]:
            page = doc[seg["page"] - 1]
            x0, y0, x1, y1 = seg["bbox"]
            clip = pymupdf.Rect(x0 - 6, y0 - 6, x1 + 6, y1 + 6) & page.rect
            png = page.get_pixmap(clip=clip, dpi=dpi).tobytes("png")
            h = hashlib.sha256(png).hexdigest()
            (out / "snapshots" / f"{h}.png").write_bytes(png)
            q["snapshots"].append({"hash": h, "page": seg["page"], "bbox": [round(v, 1) for v in clip]})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--pdf")
    ap.add_argument("--gabarito")
    ap.add_argument("--out")
    ap.add_argument("--de", type=int)
    ap.add_argument("--ate", type=int)
    ap.add_argument("--max-paginas", type=int, default=200)
    a = ap.parse_args()
    if a.probe:
        print(json.dumps(_probe()))
        return 0
    out = Path(a.out)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(a.pdf)
    if len(doc) > a.max_paginas:
        print(f"limite de páginas excedido: {len(doc)} > {a.max_paginas}", file=sys.stderr)
        return 5
    lines, omitted, assets = read_document(a.pdf)
    qs = [asdict(q) for q in split_questions(lines, a.de, a.ate)]
    for h, png in assets.items():
        (out / "assets" / f"{h}.png").write_bytes(png)
    _snapshots(a.pdf, qs, out)
    gb = read_gabarito(a.gabarito) if a.gabarito else {}
    ident = {"prova": identity_prova(a.pdf), "gabarito": identity_gabarito(a.gabarito) if a.gabarito else None,
             "paginas": len(doc)}
    for nome, obj in (("questions", qs), ("omitted", omitted), ("gabarito", gb), ("identity", ident)):
        (out / f"{nome}.json").write_text(json.dumps(obj, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
