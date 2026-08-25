from __future__ import annotations
from pathlib import Path
import hashlib, yaml

def fingerprint(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_sources(source_dir: str | Path) -> list[dict]:
    source_dir = Path(source_dir)
    manifest = source_dir / "manifest.yaml"
    if manifest.exists():
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        sources = []
        for item in data.get("sources", []):
            p = source_dir / item["path"]
            if p.exists():
                row = dict(item)
                row["path"] = str(p)
                row["fingerprint"] = fingerprint(p)
                sources.append(row)
        if sources:
            return sources

    # Conservative filesystem fallback. Directory names may hint source type but are not treated as truth.
    supported = {".docx", ".xlsx", ".xlsm", ".json", ".md", ".txt", ".sql"}
    out = []
    for p in source_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in supported and p.name != "manifest.yaml":
            rel = p.relative_to(source_dir)
            parent = rel.parts[0] if len(rel.parts) > 1 else "unknown"
            out.append({
                "id": str(rel).replace("\\", "/"),
                "path": str(p),
                "type": parent.replace("-", "_"),
                "fingerprint": fingerprint(p),
            })
    return out
