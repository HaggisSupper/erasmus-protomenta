from erasmus.store import Store


def test_init(tmp_path):
    store = Store(str(tmp_path / "e.db"))
    store.init()
    store.add_event("correction", "infer local ontology first")
    assert store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
