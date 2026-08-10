import json
from pathlib import Path


def test_ieee_sales_bundle_is_retrieval_only_and_citation_bound():
    root = Path(__file__).resolve().parent.parent
    bundle = json.loads((root / "configs" / "domain-bundle.ieee-sales.example.json").read_text())
    assert bundle["ieee_retrieval"]["source_policy"] == "licensed_documents_only"
    assert bundle["ieee_retrieval"]["training"] is False
    assert bundle["ieee_retrieval"]["citation_required"] is True
    assert bundle["ieee_retrieval"]["source_dir_env"] == "ERASMUS_IEEE_SOURCE_DIR"
    assert bundle["routing"]["pricing_calculation"] == "deterministic_rules"
