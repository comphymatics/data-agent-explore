from enterprise_data_context.models import CanonicalContext
from enterprise_data_context.quality import validate_contexts

def test_duplicate_path():
    a=CanonicalContext("a","metric","A","data://metrics/x")
    b=CanonicalContext("b","metric","B","data://metrics/x")
    issues=validate_contexts([a,b])
    assert any(x["code"]=="duplicate_path" for x in issues)
