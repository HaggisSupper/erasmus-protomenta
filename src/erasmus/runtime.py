from __future__ import annotations

import json
import urllib.request


def complete(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 120,
) -> str:
    body = json.dumps(
        {"model": model, "messages": messages, "stream": False}
    ).encode()
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read())
    return data["choices"][0]["message"]["content"]
