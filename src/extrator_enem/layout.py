"""Leitura do PDF com posição: ordem de leitura e remoção controlada de mobiliário."""
import re
from dataclasses import dataclass

import pymupdf

_WATERMARK = re.compile(r"(?:ENE[MN][0-9E]{4}\s*){2,}")
# Mobiliário só é removido com evidência (padrão exato) e sempre registrado.
_FURNITURE = [
    ("marca-dagua", re.compile(r"^ENE[MN]\d{4}$")),
    ("codigo-de-barras", re.compile(r"^\*\d+AM\d*\*$")),
    ("rodape", re.compile(r"[•|]\s*\d+º DIA\s*[•|]")),
    ("cabecalho-area", re.compile(r"^(CIÊNCIAS DA NATUREZA|MATEMÁTICA) E SUAS TECNOLOGIAS$")),
    ("cabecalho-faixa", re.compile(r"^Questões de \d+ a \d+\.?$")),
]


@dataclass
class Line:
    page: int  # 1-based
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


_EXEMPT = set("ºª°")


def _span_text(spans) -> str:
    """Junta spans marcando sobrescrito/subscrito como ^{..} / _{..} (convenção LaTeX-like)."""
    spans = [sp for sp in spans if sp["text"]]
    if not spans:
        return ""
    by_size: dict[float, int] = {}
    for sp in spans:
        by_size[round(sp["size"], 1)] = by_size.get(round(sp["size"], 1), 0) + len(sp["text"].strip())
    main_size = max(by_size, key=by_size.get)
    main = max((sp for sp in spans if round(sp["size"], 1) == main_size), key=lambda sp: len(sp["text"].strip()))
    msize, mbase = main["size"], main["origin"][1]
    out = []
    for sp in spans:
        t = sp["text"]
        small = sp["size"] < 0.85 * msize and t.strip() and not set(t.strip()) <= _EXEMPT
        if small and (sp["flags"] & 1 or sp["origin"][1] < mbase - 0.15 * msize):
            out.append("^{" + t.strip() + "}")
        elif small and sp["origin"][1] > mbase + 0.05 * msize:
            out.append("_{" + t.strip() + "}")
        else:
            out.append(t)
    txt = "".join(out)
    txt = re.sub(r"(\^\{[^{}]*)\}\^\{", r"\1", txt)
    txt = re.sub(r"(_\{[^{}]*)\}_\{", r"\1", txt)
    return txt


def _furniture_reason(s: str, y0: float) -> str | None:
    s = s.strip()
    if re.fullmatch(r"\d{1,2}", s) and (y0 < 50 or y0 > 740):
        return "numero-de-pagina"
    for name, rx in _FURNITURE:
        if rx.search(s):
            return name
    return None


def _yc(l: Line) -> float:
    return (l.y0 + l.y1) / 2


def _fractions(lines: list[Line], bars: list[tuple], mid: float) -> list[Line]:
    """Reconstrói frações pela geometria: barra horizontal com texto acima e abaixo.

    Emite \\frac{num}{den} e junta, na mesma linha, o que está na linha de base
    da barra (rótulo da alternativa, operadores, outras frações), em ordem de x.
    """
    if not bars:
        return lines
    consumed: set[int] = set()
    fracs: list[Line] = []
    for bx0, bx1, by in sorted(bars, key=lambda b: (b[2], b[0])):
        def inside(l: Line) -> bool:
            return l.x0 >= bx0 - 4 and l.x1 <= bx1 + 4
        num = [i for i, l in enumerate(lines) if i not in consumed and inside(l) and 0 < by - _yc(l) < 16]
        den = [i for i, l in enumerate(lines) if i not in consumed and inside(l) and 0 < _yc(l) - by < 16]
        if not num or not den:
            continue
        consumed.update(num + den)
        tn = " ".join(lines[i].text.strip() for i in sorted(num, key=lambda i: lines[i].x0))
        td = " ".join(lines[i].text.strip() for i in sorted(den, key=lambda i: lines[i].x0))
        page = lines[num[0]].page
        fracs.append(Line(page, "\\frac{%s}{%s}" % (tn, td), bx0, by - 6, bx1, by + 6))
    if not fracs:
        return lines
    rest = [(i, l) for i, l in enumerate(lines) if i not in consumed]
    # linhas "na altura" das barras: mesma coluna, contíguas em x
    members: list[Line] = list(fracs)
    absorbed: set[int] = set()
    changed = True
    while changed:
        changed = False
        for i, l in rest:
            if i in absorbed:
                continue
            for m in members:
                if abs(_yc(l) - _yc(m)) < 5 and (l.x0 < mid) == (m.x0 < mid) and \
                        (l.x0 - m.x1 < 40 and m.x0 - l.x1 < 40):
                    members.append(l)
                    absorbed.add(i)
                    changed = True
                    break
    rows: list[list[Line]] = []
    for m in sorted(members, key=lambda l: (round(_yc(l)), l.x0)):
        if rows and abs(_yc(rows[-1][0]) - _yc(m)) < 5 and (rows[-1][0].x0 < mid) == (m.x0 < mid):
            rows[-1].append(m)
        else:
            rows.append([m])
    first_idx = {}
    out_lines: list[tuple[int, Line]] = []
    for r in rows:
        r.sort(key=lambda l: l.x0)
        merged = Line(r[0].page, " ".join(l.text.strip() for l in r),
                      min(l.x0 for l in r), min(l.y0 for l in r), max(l.x1 for l in r), max(l.y1 for l in r))
        idx = min((i for i, l in rest if l in r), default=None)
        if idx is None:  # linha só de frações: posiciona pela primeira linha consumida acima
            idx = min((i for i in consumed if abs(_yc(lines[i]) - _yc(merged)) < 20), default=len(lines))
        out_lines.append((idx, merged))
    keep = [(i, l) for i, l in rest if i not in absorbed]
    allx = keep + out_lines
    allx.sort(key=lambda t: t[0])
    return [l for _, l in allx]


def read_document(path: str) -> tuple[list[Line], list[dict], dict[int, list[tuple]]]:
    """Linhas em ordem de leitura, registro de omissões e retângulos visuais por página."""
    doc = pymupdf.open(path)
    out: list[Line] = []
    omitted: list[dict] = []
    visuals: dict[int, list[tuple]] = {}
    for pno, page in enumerate(doc, start=1):
        rects = [tuple(i["bbox"]) for i in page.get_image_info()]
        rects += [tuple(d["rect"]) for d in page.get_drawings()
                  if d["rect"].width > 2 or d["rect"].height > 2]
        visuals[pno] = rects
        mid = page.rect.width / 2
        blocks = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
        def _content(b):
            txt = " ".join("".join(sp["text"] for sp in l["spans"]) for l in b["lines"])
            return not (_WATERMARK.search(txt) or _furniture_reason(txt, b["bbox"][1]))

        # página de uma coluna se algum bloco de conteúdo atravessa mais de 60% da largura
        single = any(b["bbox"][2] - b["bbox"][0] > 0.6 * page.rect.width for b in blocks if _content(b))
        left = [b for b in blocks if b["bbox"][2] <= mid + 8]
        right = [b for b in blocks if b["bbox"][0] >= mid - 8]
        if not single and left and right:
            wide = [b for b in blocks if b not in left and b not in right]
            ordered = (sorted(left, key=lambda b: b["bbox"][1])
                       + sorted(right, key=lambda b: b["bbox"][1]) + wide)
        else:
            ordered = sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
        page_start = len(out)
        for b in ordered:
            for ln in b["lines"]:
                raw = _span_text(ln["spans"]).rstrip()
                x0, y0, x1, y1 = ln["bbox"]
                # marca d'água vertical (texto girado só com letras/dígitos da marca)
                if abs(ln["dir"][1]) > 0.5 and re.fullmatch(r"[ENM0-9 ]+", raw.strip() or "x"):
                    omitted.append({"page": pno, "reason": "marca-dagua-vertical", "text": raw.strip()[:60]})
                    continue
                if _WATERMARK.search(raw):
                    omitted.append({"page": pno, "reason": "marca-dagua", "text": raw[:60]})
                    raw = _WATERMARK.sub("", raw).rstrip()
                if not raw.strip():
                    continue
                why = _furniture_reason(raw, y0)
                if why:
                    omitted.append({"page": pno, "reason": why, "text": raw.strip()[:60]})
                    continue
                out.append(Line(pno, raw, x0, y0, x1, y1))
        bars = []
        for d in page.get_drawings():
            for it in d["items"]:
                if it[0] == "l" and abs(it[1].y - it[2].y) < 1:
                    x0, x1, y = min(it[1].x, it[2].x), max(it[1].x, it[2].x), (it[1].y + it[2].y) / 2
                elif it[0] == "re" and it[1].height <= 1.6:
                    x0, x1, y = it[1].x0, it[1].x1, (it[1].y0 + it[1].y1) / 2
                else:
                    continue
                if 4 < x1 - x0 <= 140:
                    bars.append((x0, x1, y))
        out[page_start:] = _fractions(out[page_start:], bars, mid)
    return out, omitted, visuals
