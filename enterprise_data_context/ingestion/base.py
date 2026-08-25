from pathlib import Path
class Parser:
    extensions = ()
    def supports(self, path):
        return Path(path).suffix.lower() in self.extensions
    def parse(self, source_id, path, source_type="unknown"):
        raise NotImplementedError
