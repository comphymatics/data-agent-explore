from pathlib import Path
import json
from .base import Parser
from enterprise_data_context.models import DocumentIR, DocumentElement, SourceLocation

class TextParser(Parser):
    extensions = (".json", ".md", ".txt", ".sql")
    def parse(self, source_id, path, source_type="unknown"):
        p = Path(path)
        raw = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":
            try:
                raw = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
            except Exception:
                pass
        return DocumentIR(
            source_id, str(p), source_type, {"format": p.suffix.lower()},
            [DocumentElement("text", "text-0", text=raw, source=SourceLocation(source_id, str(p)))]
        )
