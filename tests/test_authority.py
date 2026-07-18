from erasmus.authority import AuthorityDecision, decide

def test_deny_precedes_allow():
    result = decide("codex", "write", "repo", [{"actor":"*","operation":"*","scope":"*","effect":"allow"},{"actor":"codex","operation":"write","scope":"repo","effect":"deny","reason":"gate"}])
    assert result.decision is AuthorityDecision.DENIED

def test_human_approval_is_explicit():
    result = decide("codex", "merge", "repo", [{"actor":"codex","operation":"merge","scope":"repo","requiresHumanApproval":True}])
    assert result.decision is AuthorityDecision.REQUIRES_HUMAN_APPROVAL
