"""Segmentação por marcadores + posição; detecta defeitos sem escondê-los."""
import re
from dataclasses import dataclass, field

from .layout import Line

_Q = re.compile(r"^QUESTÃO\s+(\d+)\s*$", re.IGNORECASE)
_ALT = re.compile(r"^([A-E])(?:\t+| +|$)(.*)$")
_BROKEN_GLYPH = re.compile(r"[\x00-\x08\x0b-\x1f�-]")


@dataclass
class Question:
    number: int
    page_start: int
    page_end: int
    stem: str
    choices: dict[str, str]
    issues: list[dict] = field(default_factory=list)
    regions: dict[str, dict] = field(default_factory=dict)  # posição do marcador de cada alternativa
    assets: list[dict] = field(default_factory=list)  # {hash, kind, page, bbox, role, letter?}
    segments: list[dict] = field(default_factory=list)  # {page, col, bbox} do que a questão ocupa


def _bbox(l: Line) -> list[float]:
    return [round(v, 1) for v in (l.x0, l.y0, l.x1, l.y1)]


def _find_choice_markers(lines: list[Line]) -> dict[str, int] | None:
    """Última sequência A..E em ordem (de trás para frente)."""
    idx: dict[str, int] = {}
    upper = len(lines)
    for letter in "EDCBA":
        found = None
        for i in range(upper - 1, -1, -1):
            m = _ALT.match(lines[i].text)
            if m and m.group(1) == letter:
                found = i
                break
        if found is None:
            return idx or None
        idx[letter] = found
        upper = found
    return idx


def _find_label_grid(lines: list[Line]) -> dict[str, int] | None:
    """Cinco linhas que são só uma letra A–E, juntas no fim da questão, em qualquer ordem."""
    found: dict[str, int] = {}
    for i in range(len(lines) - 1, max(len(lines) - 14, -1), -1):
        t = lines[i].text.strip()
        if re.fullmatch(r"[A-E]", t) and t not in found:
            found[t] = i
        if len(found) == 5:
            return found
    return None


def _is_fragmented(text: str, n_lines: int) -> bool:
    """Fórmula espalhada em muitas linhas curtas (fração, fatorial, expoente no PDF)."""
    toks = text.split()
    if len(toks) < 4 or n_lines < 3:
        return False
    if sum(1 for t in toks if len(t) <= 2) / len(toks) >= 0.7:
        return True
    numeric = sum(1 for t in toks if re.fullmatch(r"[\d.,+\-×÷=/]+", t))
    ops_alone = sum(1 for t in toks if t in {"+", "×", "÷", "-", "−", "="})
    return numeric / len(toks) >= 0.8 and ops_alone >= 1


def split_questions(lines: list[Line], first: int, last: int) -> list[Question]:
    groups: list[tuple[int, list[Line]]] = []
    for ln in lines:
        m = _Q.match(ln.text.strip())
        if m:
            groups.append((int(m.group(1)), []))
        elif groups:
            groups[-1][1].append(ln)
    return [_build(num, body) for num, body in groups if first <= num <= last]


def _assign_figures(figs: list[Line], labels: dict[str, Line]) -> tuple[dict[str, list[Line]], list[Line]]:
    """Figura pertence à alternativa cujo rótulo está na mesma altura (à esquerda da figura).

    Regra geométrica verificável: a altura do centro do rótulo cai dentro da faixa vertical da figura
    e o rótulo fica à esquerda dela; entre candidatos vale o mais próximo em x.
    """
    got: dict[str, list[Line]] = {k: [] for k in labels}
    left: list[Line] = []
    for f in figs:
        cands = []
        for letter, lab in labels.items():
            yc = (lab.y0 + lab.y1) / 2
            if lab.page == f.page and f.y0 - 4 <= yc <= f.y1 + 4 and lab.x0 <= f.x1 - 2:
                cands.append((abs(f.x0 - lab.x1), letter))
        if cands:
            got[min(cands)[1]].append(f)
        else:
            left.append(f)
    return got, left


def _after(body: list[Line], l: Line, ref: Line, inclusive: bool = False) -> bool:
    """`l` vem depois de `ref` na ordem de leitura (comparação por identidade)."""
    pos_l = next(i for i, x in enumerate(body) if x is l)
    pos_r = next(i for i, x in enumerate(body) if x is ref)
    return pos_l >= pos_r if inclusive else pos_l > pos_r


def _build(num: int, body: list[Line]) -> Question:
    issues: list[dict] = []
    text_lines = [l for l in body if not l.fig]
    pages = [l.page for l in body] or [0]
    markers = _find_choice_markers(text_lines)
    label_lines: dict[str, Line] = {}
    choices: dict[str, str] = {}
    n_lines: dict[str, int] = {}
    regions: dict[str, dict] = {}
    grid = None
    if not markers or len(markers) < 5:
        grid = _find_label_grid(text_lines)

    if markers and len(markers) == 5:
        first_choice_line = text_lines[markers["A"]]
        order = sorted(markers.items(), key=lambda kv: kv[1])
        for k, (letter, i) in enumerate(order):
            j = order[k + 1][1] if k + 1 < len(order) else len(text_lines)
            lab = text_lines[i]
            label_lines[letter] = lab
            first = _ALT.match(lab.text).group(2)
            rest = [first] + [l.text for l in text_lines[i + 1 : j]]
            choices[letter] = " ".join(t.strip() for t in rest if t.strip()).replace("￼", "").strip()
            n_lines[letter] = sum(1 for t in rest if t.strip())
            regions[letter] = {"page": lab.page, "bbox": _bbox(lab)}
    elif grid:
        first_choice_line = min((text_lines[i] for i in grid.values()), key=lambda l: (l.page, l.col, l.y0))
        for letter, i in grid.items():
            label_lines[letter] = text_lines[i]
            choices[letter] = ""
            regions[letter] = {"page": text_lines[i].page, "bbox": _bbox(text_lines[i])}
    else:
        first_choice_line = None
        issues.append({"code": "choices_not_found", "severity": "critical",
                       "message": f"marcadores A–E encontrados: {sorted(markers) if markers else []}"})

    # figuras: a alternativa dona é decidida pela geometria (rótulo na altura da figura), não pela ordem
    assets: list[dict] = []
    all_figs = [l for l in body if l.fig]
    got, rest_figs = _assign_figures(all_figs, label_lines) if label_lines else ({}, all_figs)
    assigned_ids = {id(f) for fs in got.values() for f in fs}
    stem_lines = [l for l in body if id(l) not in assigned_ids and
                  (first_choice_line is None or not _after(body, l, first_choice_line) or not l.fig)
                  and not (l.fig and first_choice_line is not None and _after(body, l, first_choice_line))]
    # linhas de texto após o início das alternativas não fazem parte do enunciado
    if first_choice_line is not None:
        stem_lines = [l for l in stem_lines if l.fig or not _after(body, l, first_choice_line, inclusive=True)]
    image_only: list[str] = []
    for l in stem_lines:
        if l.fig:
            assets.append({**l.fig, "role": "stem"})
    for letter, figs in got.items():
        for f in figs:
            assets.append({**f.fig, "role": "choice", "letter": letter})
        if figs and not choices[letter]:
            image_only.append(letter)
    for f in rest_figs:
        if id(f) in {id(l) for l in stem_lines}:
            continue
        assets.append({**f.fig, "role": "unassigned"})
        issues.append({"code": "asset_unassigned", "severity": "review",
                       "message": f"figura na página {f.page} {f.fig['bbox']} sem alternativa na mesma altura"})

    stem = "\n".join(l.text for l in stem_lines).strip()
    if not stem.replace("\n", "").strip():
        issues.append({"code": "empty_stem", "severity": "critical", "message": "enunciado vazio"})
    for letter in "ABCDE":
        if letter in image_only:
            issues.append({"code": "choice_image_only", "severity": "info",
                           "message": f"alternativa {letter} existe só como imagem/vetor (sem texto)"})
        elif label_lines and not choices.get(letter):
            issues.append({"code": "empty_choice", "severity": "critical", "message": f"alternativa {letter} vazia"})
    for letter, t in choices.items():
        if _is_fragmented(t, n_lines.get(letter, 1)):
            issues.append({"code": "fragmented_formula", "severity": "critical",
                           "message": f"alternativa {letter} parece fração/fórmula fragmentada: {t[:50]!r}"})
    texts = [t for t in choices.values() if t]
    if len(texts) == 5 and len(set(texts)) < 5:
        issues.append({"code": "duplicate_choices", "severity": "critical",
                       "message": "alternativas textualmente idênticas (possível perda de expoente/estrutura)"})
    full = stem + " " + " ".join(choices.values())
    if re.search(r"\((?:aq|s|l|g)\)", full) and not re.search(r"[→⇌⇄⟶⟵↔⇋]", full):
        issues.append({"code": "missing_reaction_arrow", "severity": "review",
                       "message": "equação química com estados físicos mas sem seta no texto (setas costumam ser vetores no PDF)"})
    if "\\frac{" in full:
        issues.append({"code": "frac_reconstructed", "severity": "review",
                       "message": "fração reconstruída pela geometria do PDF; conferir contra a página (não é leitura literal)"})
    if _BROKEN_GLYPH.search(stem) or any(_BROKEN_GLYPH.search(t) for t in choices.values()):
        issues.append({"code": "broken_glyph", "severity": "critical",
                       "message": "caracteres de controle/privados no texto (fórmula ilegível)"})

    # segmentos ocupados pela questão (para recortes de conferência): união por (página, coluna)
    segs: dict[tuple[int, int], list[float]] = {}
    for l in body:
        k = (l.page, l.col)
        b = segs.setdefault(k, [l.x0, l.y0, l.x1, l.y1])
        b[0], b[1], b[2], b[3] = min(b[0], l.x0), min(b[1], l.y0), max(b[2], l.x1), max(b[3], l.y1)
    segments = [{"page": p, "col": c, "bbox": [round(v, 1) for v in b]} for (p, c), b in sorted(segs.items())]
    return Question(num, min(pages), max(pages), stem, choices, issues, regions, assets, segments)
