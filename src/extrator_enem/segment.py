"""Segmentação por marcadores + ordem/posição; detecta defeitos sem escondê-los."""
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


def split_questions(lines: list[Line], first: int, last: int, visuals: dict | None = None) -> list[Question]:
    groups: list[tuple[int, list[Line]]] = []
    for ln in lines:
        m = _Q.match(ln.text.strip())
        if m:
            groups.append((int(m.group(1)), []))
        elif groups:
            groups[-1][1].append(ln)
    qs = []
    for num, body in groups:
        if not first <= num <= last:
            continue
        qs.append(_build(num, body, visuals or {}))
    return qs


def _has_visual(visuals: dict, line: Line, nxt_y: float) -> bool:
    """Há imagem/vetor na faixa da alternativa (entre o marcador e o próximo)?"""
    for (x0, y0, x1, y1) in visuals.get(line.page, []):
        if y1 > line.y0 - 2 and y0 < nxt_y and x1 > line.x0 and x0 < line.x0 + 260:
            return True
    return False


def _find_label_grid(body: list[Line]) -> dict[str, int] | None:
    """Cinco linhas que são só uma letra A–E, juntas no fim da questão, em qualquer ordem."""
    tail = len(body) - 1
    found: dict[str, int] = {}
    for i in range(len(body) - 1, max(len(body) - 12, -1), -1):
        t = body[i].text.strip()
        if re.fullmatch(r"[A-E]", t) and t not in found:
            found[t] = i
        if len(found) == 5:
            return found
    return None


def _build(num: int, body: list[Line], visuals: dict) -> Question:
    issues: list[dict] = []
    pages = [l.page for l in body] or [0]
    markers = _find_choice_markers(body)
    choices: dict[str, str] = {}
    image_only: list[str] = []
    n_lines: dict[str, int] = {}
    regions: dict[str, dict] = {}
    labels = _find_label_grid(body) if (not markers or len(markers) < 5) else None
    if labels:
        # alternativas só em figura: letras soltas espalhadas numa grade, fora de ordem
        stem_lines = body[: min(labels.values())]
        for letter, i in labels.items():
            choices[letter] = ""
            regions[letter] = {"page": body[i].page, "bbox": [round(v, 1) for v in (body[i].x0, body[i].y0, body[i].x1, body[i].y1)]}
            if _has_visual(visuals, body[i], body[i].y0 + 150):
                image_only.append(letter)
    elif not markers or len(markers) < 5:
        stem_lines = body
        issues.append({"code": "choices_not_found", "severity": "critical",
                       "message": f"marcadores A–E encontrados: {sorted(markers) if markers else []}"})
    else:
        stem_lines = body[: markers["A"]]
        bounds = sorted(markers.items(), key=lambda kv: kv[1]) + [("_", len(body))]
        for (letter, i), (_, j) in zip(bounds, bounds[1:]):
            first = _ALT.match(body[i].text).group(2)
            rest = [first] + [l.text for l in body[i + 1 : j]]
            choices[letter] = " ".join(t.strip() for t in rest if t.strip()).replace("\ufffc", "").strip()
            n_lines[letter] = sum(1 for t in rest if t.strip())
            regions[letter] = {"page": body[i].page, "bbox": [round(v, 1) for v in (body[i].x0, body[i].y0, body[i].x1, body[i].y1)]}
            if not choices[letter]:
                nxt_y = body[j].y0 if j < len(body) else body[i].y0 + 120
                if body[j - 1 if j < len(body) else i].page == body[i].page and _has_visual(visuals, body[i], nxt_y):
                    image_only.append(letter)
    stem = "\n".join(l.text for l in stem_lines).strip()
    if not stem:
        issues.append({"code": "empty_stem", "severity": "critical", "message": "enunciado vazio"})
    for letter in "ABCDE":
        if letter in image_only:
            issues.append({"code": "choice_image_only", "severity": "info",
                           "message": f"alternativa {letter} existe só como imagem/vetor (sem texto)"})
        elif markers and len(markers) == 5 and not choices.get(letter):
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
    if "\\frac{" in stem or any("\\frac{" in t for t in choices.values()):
        issues.append({"code": "frac_reconstructed", "severity": "review",
                       "message": "fração reconstruída pela geometria do PDF; conferir contra a página (não é leitura literal)"})
    if _BROKEN_GLYPH.search(stem) or any(_BROKEN_GLYPH.search(t) for t in choices.values()):
        issues.append({"code": "broken_glyph", "severity": "critical",
                       "message": "caracteres de controle/privados no texto (fórmula ilegível)"})
    return Question(num, min(pages), max(pages), stem, choices, issues, regions)
