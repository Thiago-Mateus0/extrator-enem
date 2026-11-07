"""Orquestra: admissão -> worker isolado -> registros -> validação -> publicação -> relatório."""
import csv
import hashlib
import io
import json
import re
import time
from pathlib import Path

from .records import INGESTION_VERSION, build_record
from .sandbox import run_worker
from .store import Store, safe_label


class IdentityError(ValueError):
    pass


def parse_name(name: str) -> dict:
    m = re.match(r"(\d{4})_(?:PV|GB)_.*?D(\d)_CD(\d)", Path(name).name)
    return {"ano": m.group(1), "dia": m.group(2), "caderno": m.group(3)} if m else {}


def _check_identity(ident: dict, meta: dict) -> list[str]:
    """Não mistura gabarito de outro caderno/ano/dia; metadados informados precisam bater com o PDF."""
    erros = []
    p, g = ident["prova"], ident["gabarito"]
    for k in ("caderno", "dia"):
        if p[k] and meta.get(k) and p[k] != meta[k]:
            erros.append(f"prova: {k} no PDF ({p[k]}) difere do informado ({meta[k]})")
        if g and g[k] and p[k] and g[k] != p[k]:
            erros.append(f"gabarito de {k} diferente da prova ({g[k]} vs {p[k]})")
    if g and g["ano"] and meta.get("ano") and g["ano"] != meta["ano"]:
        erros.append(f"gabarito de {g['ano']} para prova informada como {meta['ano']}")
    if not meta.get("ano") or not meta.get("caderno") or not meta.get("dia"):
        erros.append("ano/dia/caderno não identificados: informe --ano --dia --caderno")
    return erros


def validate(records: list[dict], de: int, ate: int, run: Path, gb: dict) -> list[dict]:
    """Validações obrigatórias §8. Cada item: {check, ok, detalhe}."""
    v = []
    nums = [r["number"] for r in records]
    esperado = set(range(de, ate + 1))
    v.append({"check": "intervalo_sem_ausentes_nem_duplicados",
              "ok": set(nums) == esperado and len(nums) == len(set(nums)),
              "detalhe": {"ausentes": sorted(esperado - set(nums)), "duplicadas": sorted({n for n in nums if nums.count(n) > 1})}})
    v.append({"check": "enunciado_nao_vazio", "ok": all(r["stem"].strip() for r in records),
              "detalhe": [r["number"] for r in records if not r["stem"].strip()]})
    v.append({"check": "alternativas_A_E_presentes", "ok": all([c["letter"] for c in r["choices"]] == list("ABCDE") for r in records),
              "detalhe": [r["number"] for r in records if [c["letter"] for c in r["choices"]] != list("ABCDE")]})
    ruins = []
    for r in records:
        for a in r["assets"]:
            p = run / "assets" / f"{a['hash']}.png"
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != a["hash"]:
                ruins.append((r["number"], a["hash"][:12]))
        for s in r["snapshots"]:
            p = run / "snapshots" / f"{s['hash']}.png"
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != s["hash"]:
                ruins.append((r["number"], s["hash"][:12]))
    v.append({"check": "recursos_existem_com_hash_correto", "ok": not ruins, "detalhe": ruins})
    incoer = [r["number"] for r in records if r["answer"]["state"] == "found" and
              r["answer"]["letter"] not in [c["letter"] for c in r["choices"]]]
    v.append({"check": "gabarito_coerente_com_alternativas", "ok": not incoer, "detalhe": incoer})
    v.append({"check": "gabarito_cobre_o_intervalo", "ok": esperado <= set(gb) or not gb,
              "detalhe": sorted(esperado - {int(k) for k in gb}) if gb else "sem gabarito informado"})
    glifo = [r["number"] for r in records if any(i["code"] == "broken_glyph" for i in r["issues"])]
    v.append({"check": "sem_glifos_quebrados", "ok": not glifo, "detalhe": glifo})
    frag = [r["number"] for r in records if any(i["code"] in ("fragmented_formula", "duplicate_choices") for i in r["issues"])]
    v.append({"check": "sem_formulas_fragmentadas_ou_alternativas_iguais", "ok": not frag, "detalhe": frag})
    return v


_HASH_OK = re.compile(r"^[0-9a-f]{64}$")
_CODE_OK = re.compile(r"^[a-z_]{1,40}$")


def _csv_safe(x) -> str:
    s = str(x)
    return "'" + s if s[:1] in "=+-@\t\r|" else s  # proteção contra execução de fórmula em planilha


def extract(prova: str, gabarito: str | None, de: int, ate: int, dados: str, meta: dict | None = None) -> dict:
    """Execução imutável; se falhar, o diretório da execução fica com FALHOU.json e nada é publicado."""
    store = Store(dados)
    holder: dict = {}
    try:
        return _extract(prova, gabarito, de, ate, store, meta, holder)
    except Exception as ex:
        run = holder.get("run")
        if run is not None:
            import shutil
            shutil.rmtree(run / "_worker", ignore_errors=True)
            (run / "FALHOU.json").write_text(json.dumps({"erro": f"{type(ex).__name__}: {ex}"}, ensure_ascii=False))
        raise


def _extract(prova, gabarito, de, ate, store, meta, holder) -> dict:
    t0 = time.time()
    meta = {**parse_name(prova), **(meta or {})}
    psha = store.quarantine(Path(prova))
    gsha = store.quarantine(Path(gabarito)) if gabarito else None
    pq, gq = store.quarantined_path(psha), (store.quarantined_path(gsha) if gsha else None)
    run_id, run = store.new_run(psha)
    holder["run"] = run
    scratch = run / "_worker"
    t1 = time.time()
    run_worker(pq, gq, scratch, de, ate)
    t_worker = time.time() - t1
    load = lambda n: json.loads((scratch / f"{n}.json").read_text())
    qs, omitted, gb, ident = load("questions"), load("omitted"), load("gabarito"), load("identity")
    erros = _check_identity(ident, meta)
    if erros:
        raise IdentityError("; ".join(erros))
    label = safe_label(prova)
    prev_id = store.previous_run(psha)
    prev = {}
    if prev_id:
        pdir = store.source_dir(psha) / "runs" / prev_id / "questions"
        prev = {p.stem: json.loads(p.read_text()) for p in pdir.glob("*.json")} if pdir.exists() else {}
    (run / "questions").mkdir()
    records = []
    for q in sorted(qs, key=lambda q: q["number"]):
        ans = gb.get(str(q["number"]), {"state": "not_provided", "letter": None}) if gabarito else \
            {"state": "not_provided", "letter": None}
        rec = build_record(q, ans, psha, gsha, label, run_id)
        store.annotate_reprocessing(rec, prev.get(rec["question_id"]))
        records.append(rec)
        (run / "questions" / f"{rec['question_id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    (run / "assets").mkdir(exist_ok=True)
    (run / "snapshots").mkdir(exist_ok=True)
    for sub in ("assets", "snapshots"):  # já validados (arquivo regular, nome=hash, re-hash) em sandbox._receber
        for f in (scratch / sub).glob("*.png"):
            if f.is_symlink() or not f.is_file():
                raise RuntimeError(f"saída do worker rejeitada: {f.name}")
            f.replace(run / sub / f.name)
    (run / "omitted.json").write_text(json.dumps(omitted, ensure_ascii=False, indent=1))
    for f in scratch.iterdir():
        f.unlink() if f.is_file() else None
    for sub in ("assets", "snapshots"):
        (scratch / sub).rmdir() if (scratch / sub).exists() else None
    scratch.rmdir()

    validacoes = validate(records, de, ate, run, {int(k): v for k, v in gb.items()})
    # recurso referenciado que existe só como imagem não tem transcrição textual
    sem_texto = sorted({r["number"] for r in records for i in r["issues"] if i["code"] == "choice_image_only"})
    stale = [r["question_id"] for r in records if r["reprocessing"].get("review_stale")]
    por_codigo: dict[str, int] = {}
    for r in records:
        for i in r["issues"]:
            por_codigo[i["code"]] = por_codigo.get(i["code"], 0) + 1
    completo = validacoes[0]["ok"] and validacoes[3]["ok"]
    report = {
        "run_id": run_id, "ingestion_version": INGESTION_VERSION, "estado": "completo" if completo else "INCOMPLETO",
        "fonte": {"prova_sha256": psha, "gabarito_sha256": gsha, "label": label, **meta, "paginas": ident["paginas"]},
        "faixa": [de, ate], "esperadas": ate - de + 1, "encontradas": len({r["number"] for r in records}),
        "gabarito": {s: sum(1 for r in records if r["answer"]["state"] == s) for s in ("found", "annulled", "not_provided")},
        "status": {s: sum(1 for r in records if r["status"] == s) for s in ("extracted", "needs_review")},
        "por_codigo": por_codigo,
        "questoes_para_conferir": {r["number"]: sorted({i["code"] for i in r["issues"] if i["severity"] != "info"})
                                   for r in records if r["status"] == "needs_review"},
        "recursos_sem_transcricao_textual": sem_texto,
        "tabelas_estruturadas": {r["number"]: len(r["tables"]) for r in records if r["tables"]},
        "revisoes_obsoletas": stale,
        "omitidos": len(omitted),
        "validacoes": validacoes,
        "metodo": {"extrator": "pymupdf-native", "ocr_visao": "não utilizado", "isolamento": "bwrap + rlimits",
                   "chamadas_externas": 0, "custo": "zero (sem serviços pagos)"},
        "tempo_s": {"total": round(time.time() - t0, 2), "worker_isolado": round(t_worker, 2)},
    }
    (run / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    (run / "relatorio.md").write_text(_relatorio_md(report))
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(["numero", "question_id", "paginas", "alertas", "snapshots"])
    for r in records:
        if r["status"] == "needs_review":
            cods = sorted({i["code"] for i in r["issues"] if i["severity"] != "info" and _CODE_OK.match(i["code"])})
            snaps = [f"snapshots/{s['hash']}.png" for s in r["snapshots"] if _HASH_OK.match(s["hash"])]
            w.writerow([_csv_safe(x) for x in (r["number"], r["question_id"],
                        f"{r['location']['page_start']}-{r['location']['page_end']}",
                        " ".join(cods), " ".join(snaps))])
    (run / "conferencia.csv").write_text(buf.getvalue())
    store.publish(psha, run_id, label, {"estado": report["estado"], "gabarito_sha256": gsha})
    report["_run_dir"] = str(run)
    return report


def _relatorio_md(r: dict) -> str:
    g, s = r["gabarito"], r["status"]
    L = ["# Relatório de extração", "",
         f"- Execução: `{r['run_id']}` — estado: **{r['estado']}**",
         f"- Prova SHA-256: `{r['fonte']['prova_sha256']}`", f"- Gabarito SHA-256: `{r['fonte']['gabarito_sha256']}`",
         f"- Questões: {r['encontradas']}/{r['esperadas']} (faixa {r['faixa'][0]}–{r['faixa'][1]})",
         f"- Gabarito: {g['found']} com letra, {g['annulled']} anuladas, {g['not_provided']} não fornecido",
         f"- Para conferir (alertas): **{s['needs_review']}** de {r['encontradas']}; sem alerta: {s['extracted']} "
         "(*sem alerta ≠ certificada*)",
         f"- Recursos sem transcrição textual (só imagem): questões {r['recursos_sem_transcricao_textual']}",
         f"- Tabelas estruturadas (cabeçalho = 1ª linha, *inferido*): {sum(r['tabelas_estruturadas'].values())} em questões {sorted(r['tabelas_estruturadas'])}",
         f"- Revisões humanas obsoletas por mudança de conteúdo: {r['revisoes_obsoletas'] or 'nenhuma'}",
         f"- Mobiliário/marca d'água removidos (ver omitted.json): {r['omitidos']}",
         f"- Método: {r['metodo']['extrator']}; OCR/visão: {r['metodo']['ocr_visao']}; isolamento: {r['metodo']['isolamento']}; "
         f"custo: {r['metodo']['custo']}; tempo: {r['tempo_s']['total']}s (worker {r['tempo_s']['worker_isolado']}s)", "",
         "> Contagens medem alertas automáticos, não fidelidade. `frac_reconstructed` é reconstrução geométrica:",
         "> confira contra o snapshot. Sem referência de verdade a fidelidade é **não medida**.", "",
         "## Validações", "", "| validação | ok | detalhe |", "|---|---|---|"]
    L += [f"| {v['check']} | {'✅' if v['ok'] else '❌'} | {v['detalhe'] if not v['ok'] else ''} |" for v in r["validacoes"]]
    L += ["", "## Alertas por código", "", "| código | ocorrências |", "|---|---|"]
    L += [f"| {c} | {n} |" for c, n in sorted(r["por_codigo"].items())]
    L += ["", "## Questões para conferir", "", "| questão | alertas |", "|---|---|"]
    L += [f"| {n} | {', '.join(c)} |" for n, c in r["questoes_para_conferir"].items()]
    return "\n".join(L) + "\n"


def compare(run_a: str, run_b: str) -> dict:
    """Baseline x candidato: o que mudou de conteúdo/hash e de alertas, por questão."""
    def load(d):
        return {json.loads(p.read_text())["number"]: json.loads(p.read_text())
                for p in sorted((Path(d) / "questions").glob("*.json"))}
    a, b = load(run_a), load(run_b)
    out = {"corrigidos": [], "mantidos": [], "introduzidos": [], "conteudo_alterado": [], "apenas_em": {}}
    for n in sorted(set(a) | set(b)):
        if n not in a or n not in b:
            out["apenas_em"][n] = "A" if n in a else "B"
            continue
        ca = {i["code"] for i in a[n]["issues"] if i["severity"] != "info"}
        cb = {i["code"] for i in b[n]["issues"] if i["severity"] != "info"}
        if a[n]["content_sha256"] != b[n]["content_sha256"]:
            out["conteudo_alterado"].append(n)
        if ca and not cb:
            out["corrigidos"].append(n)
        elif cb and not ca:
            out["introduzidos"].append(n)
        elif ca and cb:
            out["mantidos"].append(n)
    return out
