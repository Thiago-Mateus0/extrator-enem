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
    col: int = 0  # coluna de leitura (0 em páginas de coluna única)
    fig: dict | None = None  # preenchido quando a "linha" é uma figura/recurso visual


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
        def inside(l: Line, bx0=bx0, bx1=bx1) -> bool:
            return l.x0 >= bx0 - 4 and l.x1 <= bx1 + 4
        num = [i for i, l in enumerate(lines) if i not in consumed and inside(l) and 0 < by - _yc(l) < 16]
        den = [i for i, l in enumerate(lines) if i not in consumed and inside(l) and 0 < _yc(l) - by < 16]
        if not num or not den:
            continue
        consumed.update(num + den)
        tn = " ".join(lines[i].text.strip() for i in sorted(num, key=lambda i: lines[i].x0))
        td = " ".join(lines[i].text.strip() for i in sorted(den, key=lambda i: lines[i].x0))
        page = lines[num[0]].page
        fracs.append(Line(page, "\\frac{%s}{%s}" % (tn, td), bx0, by - 6, bx1, by + 6,
                          lines[num[0]].col))
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
    out_lines: list[tuple[int, Line]] = []
    for r in rows:
        r.sort(key=lambda l: l.x0)
        merged = Line(r[0].page, " ".join(l.text.strip() for l in r),
                      min(l.x0 for l in r), min(l.y0 for l in r), max(l.x1 for l in r), max(l.y1 for l in r),
                      r[0].col)
        idx = min((i for i, l in rest if l in r), default=None)
        if idx is None:  # linha só de frações: posiciona pela primeira linha consumida acima
            idx = min((i for i in consumed if abs(_yc(lines[i]) - _yc(merged)) < 20), default=len(lines))
        out_lines.append((idx, merged))
    keep = [(i, l) for i, l in rest if i not in absorbed]
    allx = keep + out_lines
    allx.sort(key=lambda t: t[0])
    return [l for _, l in allx]


def _tables(page) -> list[dict]:
    """Tabelas com linhas desenhadas: a *estrutura* (células) vem do PDF; o *texto* de cada célula é lido
    por recorte (get_text clip), porque o texto de `Table.extract()` perde espaços e vírgulas decimais."""
    out = []
    try:
        found = page.find_tables().tables
    except Exception:  # detecção é auxiliar: falha vira "sem tabela", nunca derruba a extração
        return out
    for t in found:
        if t.row_count < 2 or t.col_count < 2 or t.bbox[1] < 60 or t.bbox[3] > 745:
            continue
        rows = [[" ".join(page.get_text("text", clip=pymupdf.Rect(c)).split()) if c else "" for c in r.cells]
                for r in t.rows]
        if not any(any(c for c in r) for r in rows):
            continue
        out.append({"bbox": tuple(t.bbox), "rows": rows})
    return out


def _overlap(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = (a[2] - a[0]) * (a[3] - a[1])
    return (ix * iy) / area if area else 0.0


def _figure_rects(page, tables: list[dict] = ()) -> list[tuple[float, float, float, float, str]]:
    """Recursos visuais da página: rasters e agrupamentos de vetores (gráficos, estruturas)."""
    rects = []
    for im in page.get_image_info():
        x0, y0, x1, y1 = im["bbox"]
        w, h = x1 - x0, y1 - y0
        if min(w, h) < 2 or max(w, h) < 8 or y0 <= 60 or y1 >= 745:
            continue
        if (w > 150 and h < 8) or (h > 150 and w < 8):
            continue  # filetes de separação entre questões/colunas
        rects.append((x0, y0, x1, y1, "raster"))
    for r in page.cluster_drawings():
        w, h = r.width, r.height
        if w < 12 or h < 8 or r.y0 < 60 or r.y1 > 745:
            continue  # barras de fração, sublinhados, arrows finas e mobiliário não são figuras
        if h < 14 and w > 200:
            continue  # filete de seção
        if any(x0 - 3 <= r.x0 and r.x1 <= x1 + 3 and y0 - 3 <= r.y0 and r.y1 <= y1 + 3
               for x0, y0, x1, y1, _ in rects):
            continue  # vetor sobreposto a um raster já contado
        if any(_overlap((r.x0, r.y0, r.x1, r.y1), t["bbox"]) > 0.7 for t in tables):
            continue  # a tabela já vira recurso próprio (kind "table")
        rects.append((r.x0, r.y0, r.x1, r.y1, "vector"))
    return sorted(rects, key=lambda t: (t[1], t[0]))


def _insert_figures(page, pno: int, lines: list[Line], mid: float, single: bool,
                    dpi: int, assets: dict[str, bytes], furn_boxes: list[tuple],
                    tables: list[dict] = ()) -> list[Line]:
    import hashlib
    out = list(lines)
    items = [(*t["bbox"], "table", t) for t in tables]
    items += [(*r, None) for r in _figure_rects(page, tables)]
    for x0, y0, x1, y1, kind, tab in sorted(items, key=lambda t: (t[1], t[0])):
        if any(x0 - 2 <= fx0 and fx1 <= x1 + 2 and y0 - 2 <= fy0 and fy1 <= y1 + 2
               for fx0, fy0, fx1, fy1 in furn_boxes):
            continue  # faixa de cabeçalho de área desenhada como figura: mobiliário
        png = page.get_pixmap(clip=pymupdf.Rect(x0, y0, x1, y1), dpi=dpi).tobytes("png")
        h = hashlib.sha256(png).hexdigest()
        assets[h] = png
        col = 0 if (single or (x0 + x1) / 2 < mid) else 1
        fig = {"hash": h, "kind": kind, "page": pno, "bbox": [round(v, 1) for v in (x0, y0, x1, y1)]}
        if tab is not None:
            fig["table"] = {"asset_id": h, "page": pno, "bbox": fig["bbox"], "n_rows": len(tab["rows"]),
                            "n_cols": len(tab["rows"][0]), "rows": tab["rows"], "header_row": 0,
                            "header_inferred": True, "method": "pymupdf.find_tables(estrutura)+texto por célula"}
        pos = next((i for i, l in enumerate(out) if l.col == col), len(out))
        for i, l in enumerate(out):
            if l.col == col and l.y0 < y0:
                pos = i + 1
        ref = "tabela" if kind == "table" else "figura"
        out.insert(pos, Line(pno, f"[[{ref}:{h[:12]}]]", x0, y0, x1, y1, col, fig))
    return out


def read_document(path: str, dpi: int = 200) -> tuple[list[Line], list[dict], dict[str, bytes]]:
    """Linhas em ordem de leitura, registro de omissões e bytes PNG dos recursos visuais (por hash)."""
    doc = pymupdf.open(path)
    out: list[Line] = []
    omitted: list[dict] = []
    assets: dict[str, bytes] = {}
    for pno, page in enumerate(doc, start=1):
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
        furn_boxes: list[tuple] = []
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
                    if why.startswith("cabecalho"):
                        furn_boxes.append((x0, y0, x1, y1))
                    continue
                out.append(Line(pno, raw, x0, y0, x1, y1, 0 if (single or x0 < mid) else 1))
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
        tables = _tables(page)
        if tables:
            keep = []
            for l in out[page_start:]:
                cx, cy = (l.x0 + l.x1) / 2, (l.y0 + l.y1) / 2
                if not any(t["bbox"][0] <= cx <= t["bbox"][2] and t["bbox"][1] <= cy <= t["bbox"][3] for t in tables):
                    keep.append(l)
            out[page_start:] = keep
        if len(out) == page_start and not tables:
            omitted.append({"page": pno, "reason": "pagina-sem-texto-de-questao",
                            "text": "figuras da página não associadas a questões (capa/contracapa)"})
        else:
            out[page_start:] = _insert_figures(page, pno, out[page_start:], mid, single, dpi, assets, furn_boxes, tables)
    return out, omitted, assets
