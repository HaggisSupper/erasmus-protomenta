from erasmus.navigator import Navigator

def test_navigator_indexes_and_routes(tmp_path):
    (tmp_path / "mod.py").write_text("import json\nclass Router:\n  def route(self): pass\n")
    result = Navigator(tmp_path).route("router")
    assert result["candidate_files"] == ["mod.py"] and result["readonly"]
