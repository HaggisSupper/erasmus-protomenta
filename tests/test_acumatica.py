import io
from unittest.mock import patch
from erasmus.acumatica import AcumaticaClient, AcumaticaError

class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit=-1): return b'{"ok": true}'

def test_read_only_session_and_get():
    client = AcumaticaClient("https://acumatica.example", "u", "p")
    with patch.object(client._opener, "open", return_value=Response()) as open_call:
        client.login(); result = client.get("entity/Customer", {"$top": "1"}); client.logout()
    assert result.body == {"ok": True} and open_call.call_count == 3

def test_get_requires_login():
    client = AcumaticaClient("https://acumatica.example", "u", "p")
    try: client.get("entity/Customer")
    except AcumaticaError as error: assert "login required" in str(error)
    else: raise AssertionError("expected login guard")
