from .word import WordParser
from .excel import ExcelParser
from .text import TextParser
PARSERS = [WordParser(), ExcelParser(), TextParser()]

def parse_document(source_id, path, source_type="unknown"):
    for p in PARSERS:
        if p.supports(path):
            return p.parse(source_id, path, source_type)
    raise ValueError(f"Unsupported source format: {path}")
