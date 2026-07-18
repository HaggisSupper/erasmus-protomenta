from erasmus.work_package import WorkPackage

def test_work_package_round_trip_fields():
    packet = WorkPackage("wp-1", "codex", "worker-mcp", "abc", ("src/x.py",), ("tests/test_x.py",), rollback="git revert")
    assert '"package_id": "wp-1"' in packet.to_json()
    assert packet.with_status("tested").status == "tested"
