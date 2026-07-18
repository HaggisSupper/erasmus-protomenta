"""Minimal read-only Acumatica contract-based REST adapter."""
from __future__ import annotations
import json
from dataclasses import dataclass
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, build_opener, HTTPCookieProcessor

class AcumaticaError(RuntimeError): pass
@dataclass(frozen=True)
class AcumaticaResult:
    status: int
    body: object
    truncated: bool = False

class AcumaticaClient:
    def __init__(self, base_url: str, username: str, password: str, tenant: str | None = None, timeout: int = 30, max_bytes: int = 1_000_000):
        if not base_url.startswith(("http://", "https://")): raise ValueError("base_url must use http or https")
        self.base_url = base_url.rstrip("/") + "/"; self.username = username; self.password = password; self.tenant = tenant; self.timeout = max(1, timeout); self.max_bytes = max(1024, max_bytes); self._opener = build_opener(HTTPCookieProcessor(CookieJar())); self._logged_in = False
    def login(self) -> None:
        payload = {"name": self.username, "password": self.password}
        if self.tenant: payload["tenant"] = self.tenant
        self._request("POST", "entity/auth/login", payload)
        self._logged_in = True
    def logout(self) -> None:
        if self._logged_in:
            try: self._request("POST", "entity/auth/logout", None)
            finally: self._logged_in = False
    def get(self, endpoint: str, query: dict[str, str] | None = None) -> AcumaticaResult:
        if not self._logged_in: raise AcumaticaError("login required")
        path = endpoint.lstrip("/") + (("?" + urlencode(query)) if query else "")
        return self._request("GET", path, None)
    def _request(self, method: str, path: str, payload: object) -> AcumaticaResult:
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(urljoin(self.base_url, path), data=data, method=method, headers={"Accept": "application/json", "Content-Type": "application/json"})
        try:
            with self._opener.open(request, timeout=self.timeout) as response: raw = response.read(self.max_bytes + 1); status = response.status
        except (HTTPError, URLError, TimeoutError) as error: raise AcumaticaError(str(error)) from error
        truncated = len(raw) > self.max_bytes; raw = raw[:self.max_bytes]
        if not raw: return AcumaticaResult(status, None, truncated)
        try: body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error: raise AcumaticaError("Acumatica returned invalid JSON") from error
        if status >= 400: raise AcumaticaError(f"Acumatica HTTP {status}")
        return AcumaticaResult(status, body, truncated)
