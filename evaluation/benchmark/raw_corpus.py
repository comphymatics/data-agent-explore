"""Freeze original documents, never Template JSON or evidence-page projections."""
import hashlib
import json
from pathlib import Path
import shutil

RAW_SUFFIXES = {".doc", ".docx", ".xls", ".xlsx", ".pdf", ".md", ".txt", ".csv"}


def inventory(root):
    root=Path(root).resolve()
    if not root.is_dir():
        raise ValueError("raw corpus directory does not exist")
    rows=[]
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("raw corpus cannot contain symbolic links")
        if not path.is_file():
            continue
        if path.suffix.lower() not in RAW_SUFFIXES:
            raise ValueError("raw corpus contains a non-document input: "+path.name)
        rows.append({"path":path.relative_to(root).as_posix(),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size})
    if not rows:
        raise ValueError("empty raw corpus")
    return rows


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def freeze(source, destination):
    rows=inventory(source)
    destination=Path(destination)
    if destination.exists():
        raise ValueError("frozen destination must be new")
    destination.mkdir(parents=True)
    for row in rows:
        target=destination/row["path"]
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(Path(source)/row["path"],target)
        target.chmod(0o444)
    if inventory(destination)!=rows:
        raise ValueError("raw corpus changed during freezing")
    return {"fingerprint":fingerprint(rows),"files":rows}


def verify(root, expected):
    if fingerprint(inventory(root))!=expected:
        raise ValueError("frozen raw corpus was modified")
