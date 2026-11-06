"""Armazenamento: fonte por hash, execuções imutáveis, current.json atômico, revisões presas ao hash."""
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .records import INGESTION_VERSION

MAX_PDF_BYTES = 200 * 2**20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_label(name: str) -> str:
    """Nome recebido vira só metadado saneado; nunca caminho interno."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name))[:120]


def validate_pdf(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"arquivo inexistente: {path.name}")
    if path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError(f"PDF acima do limite de {MAX_PDF_BYTES} bytes")
    with open(path, "rb") as f:
        if f.read(5) != b"%PDF-":
            raise ValueError(f"{path.name}: assinatura de PDF ausente (conteúdo não é PDF)")


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)  # atômico no mesmo filesystem


@contextmanager
def _lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with open(root / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    # --- fonte -------------------------------------------------------------------------
    def quarantine(self, pdf: Path) -> str:
        """Valida e preserva o original em quarentena, identificado pelo hash (renomear não muda identidade)."""
        validate_pdf(pdf)
        sha = sha256_file(pdf)
        q = self.root / "quarentena"
        q.mkdir(parents=True, exist_ok=True)
        dst = q / f"{sha}.pdf"
        if not dst.exists():
            tmp = q / f".{sha}.{secrets.token_hex(4)}.tmp"
            shutil.copyfile(pdf, tmp)
            os.chmod(tmp, 0o444)
            os.replace(tmp, dst)
        return sha

    def quarantined_path(self, sha: str) -> Path:
        return self.root / "quarentena" / f"{sha}.pdf"

    def source_dir(self, sha: str) -> Path:
        return self.root / "saida" / "sources" / sha

    # --- execuções ---------------------------------------------------------------------
    def new_run(self, sha: str) -> tuple[str, Path]:
        run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}-v{INGESTION_VERSION}"
        d = self.source_dir(sha) / "runs" / run_id
        d.mkdir(parents=True, exist_ok=False)  # nunca sobrescreve execução antiga
        return run_id, d

    def previous_run(self, sha: str) -> str | None:
        cur = self.source_dir(sha) / "current.json"
        return json.loads(cur.read_text())["run_id"] if cur.exists() else None

    def publish(self, sha: str, run_id: str, label: str, meta: dict) -> None:
        sd = self.source_dir(sha)
        sd.mkdir(parents=True, exist_ok=True)
        with _lock(self.root / "saida"):
            mf = sd / "manifest.json"
            m = json.loads(mf.read_text()) if mf.exists() else {"source_id": sha, "labels": [], "runs": []}
            if label not in m["labels"]:
                m["labels"].append(label)
            m["runs"].append({"run_id": run_id, **meta})
            _atomic_write(mf, json.dumps(m, ensure_ascii=False, indent=1).encode())
            _atomic_write(sd / "current.json", json.dumps({"run_id": run_id}).encode())

    # --- revisões ----------------------------------------------------------------------
    def reviews_dir(self) -> Path:
        d = self.root / "saida" / "reviews"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_review(self, qid: str, content_sha: str, verdict: str, reviewer: str, note: str = "") -> Path:
        if verdict not in {"approved", "rejected", "doubt"}:
            raise ValueError("veredito inválido")
        rec = {"question_id": qid, "content_sha256": content_sha, "verdict": verdict, "reviewer": reviewer,
               "origin": "human", "note": note, "at": datetime.now(timezone.utc).isoformat()}
        p = self.reviews_dir() / f"{qid}.json"
        hist = json.loads(p.read_text()) if p.exists() else []
        hist.append(rec)
        _atomic_write(p, json.dumps(hist, ensure_ascii=False, indent=1).encode())
        return p

    def annotate_reprocessing(self, record: dict, previous: dict | None) -> None:
        """Revisão vale só para o hash examinado; mudança de conteúdo => review_stale."""
        info: dict = {"review_stale": False, "stale_reviews": []}
        p = self.reviews_dir() / f"{record['question_id']}.json"
        if p.exists():
            for rv in json.loads(p.read_text()):
                if rv["content_sha256"] != record["content_sha256"]:
                    info["stale_reviews"].append({"verdict": rv["verdict"], "reviewed_content_sha256": rv["content_sha256"]})
            valid = [rv for rv in json.loads(p.read_text()) if rv["content_sha256"] == record["content_sha256"]]
            info["review_stale"] = bool(info["stale_reviews"]) and not valid
            info["valid_review"] = valid[-1]["verdict"] if valid else None
        if previous is not None:
            info["changed_from_previous_run"] = previous["content_sha256"] != record["content_sha256"]
        record["reprocessing"] = info
