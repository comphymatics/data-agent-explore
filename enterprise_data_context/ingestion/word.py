from pathlib import Path
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table
from .base import Parser
from enterprise_data_context.models import DocumentIR, DocumentElement, SourceLocation

class WordParser(Parser):
    extensions = (".docx",)

    def parse(self, source_id, path, source_type="unknown"):
        path = Path(path)
        doc = Document(path)
        elems, stack = [], []
        idx = 0
        for child in doc.element.body.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                p = Paragraph(child, doc)
                text = p.text.strip()
                if not text:
                    continue
                style = (p.style.name if p.style else "") or ""
                level = None
                if style.lower().startswith("heading"):
                    try:
                        level = int(style.split()[-1])
                    except Exception:
                        level = 1
                    while stack and stack[-1][0] >= level:
                        stack.pop()
                    stack.append((level, text))
                section = " > ".join(x[1] for x in stack) if stack else None
                elems.append(DocumentElement(
                    type="heading" if level else "paragraph", id=f"p-{idx}",
                    text=text, title=text if level else None, level=level,
                    metadata={"style": style},
                    source=SourceLocation(source_id, str(path), section=section)
                ))
                idx += 1
            elif tag == "tbl":
                table = Table(child, doc)
                rows = [[c.text.strip() for c in r.cells] for r in table.rows]
                section = " > ".join(x[1] for x in stack) if stack else None
                headers = rows[0] if rows else []
                body = rows[1:] if len(rows) > 1 else []
                elems.append(DocumentElement(
                    type="table", id=f"t-{idx}", headers=headers, rows=body,
                    metadata={"row_count": len(rows), "col_count": max((len(r) for r in rows), default=0)},
                    source=SourceLocation(source_id, str(path), section=section, table=f"table-{idx}")
                ))
                idx += 1
        return DocumentIR(source_id, str(path), source_type, {"format": "docx"}, elems)
