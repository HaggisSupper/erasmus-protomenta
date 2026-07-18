import json
from unittest.mock import patch
import subprocess
from erasmus.worker_mcp import WorkerMcpServer
from erasmus.work_package import WorkPackage

def test_worker_provenance_can_be_recorded_in_state_packet(tmp_path):
    server = WorkerMcpServer((tmp_path,))
    with patch("erasmus.worker_mcp.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "ok", "")):
        result = server.call("worker_review", {"project_root": str(tmp_path), "worker": "agy", "prompt": "review"})
    packet = WorkPackage("wp-1", "agy", "worker-review", "local", tuple(result["provenance"].values()), ("tests/test_worker_mcp.py",), "tested", "git revert")
    assert json.loads(packet.to_json())["status"] == "tested"
