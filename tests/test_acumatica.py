import json
from unittest.mock import patch

from erasmus.acumatica import AcumaticaClient, AcumaticaError


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit=-1):
        return b'{"ok": true}'


def test_read_only_session_and_get():
    client = AcumaticaClient("https://acumatica.example", "u", "p")
    with patch.object(client._opener, "open", return_value=Response()) as open_call:
        client.login()
        result = client.get("entity/Customer", {"$top": "1"})
        client.logout()
    assert result.body == {"ok": True} and open_call.call_count == 3


def test_get_requires_login():
    client = AcumaticaClient("https://acumatica.example", "u", "p")
    try:
        client.get("entity/Customer")
    except AcumaticaError as error:
        assert "login required" in str(error)
    else:
        raise AssertionError("expected login guard")


def test_external_and_parent_endpoints_are_rejected_before_network():
    from unittest.mock import Mock

    import pytest

    client = AcumaticaClient("https://example.invalid/entity/", "test", "test")
    client._logged_in = True
    client._opener = Mock()
    for endpoint in ("https://attacker.invalid/data", "../secret", "%2e%2e/secret"):
        with pytest.raises(AcumaticaError, match="outside"):
            client.get(endpoint)
    client._opener.open.assert_not_called()


def test_credentials_require_tls_except_explicit_loopback_mode():
    import pytest

    with pytest.raises(ValueError, match="HTTPS"):
        AcumaticaClient("http://erp.invalid", "user", "secret")
    with pytest.raises(ValueError, match="HTTPS"):
        AcumaticaClient("http://127.0.0.1:8080", "user", "secret")
    AcumaticaClient(
        "http://127.0.0.1:8080", "user", "secret", allow_insecure_loopback=True
    )


def test_oversized_json_reports_size_limit_instead_of_parse_error():
    import pytest

    class OversizedResponse(Response):
        def read(self, limit=-1):
            return json.dumps({"data": "x" * 2000}).encode()[:limit]

    client = AcumaticaClient("https://erp.invalid", "user", "secret", max_bytes=1024)
    client._logged_in = True
    with (
        patch.object(client._opener, "open", return_value=OversizedResponse()),
        pytest.raises(AcumaticaError, match="size limit"),
    ):
        client.get("entity/test")
