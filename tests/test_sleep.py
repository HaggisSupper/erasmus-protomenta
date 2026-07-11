from erasmus.sleep import consolidate
from erasmus.store import Store


def test_sleep_promotes_correction_to_candidate(tmp_path):
    store = Store(str(tmp_path / "e.db"))
    store.init()
    store.add_event("correction", "infer intent before correction")
    result = consolidate(store)
    assert result["experience_candidates"] == 1
