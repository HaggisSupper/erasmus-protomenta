from erasmus.code_integrations import context7_status, lsp_status

def test_optional_integrations_fail_closed():
    assert lsp_status().name == "lsp" and context7_status().available is False
