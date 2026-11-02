"""Cliente HTTP mínimo (solo stdlib): el paquete de Lambda no necesita dependencias."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def _backoff(attempt: int, retry_after: str | None = None) -> float:
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 20.0)
    return min(0.5 * (2 ** attempt), 8.0)


def request(method: str, url: str, *, headers: dict | None = None,
            json_body: dict | None = None, timeout: int = 30,
            retries: int = 3, raw: bool = False):
    data = json.dumps(json_body).encode() if json_body is not None else None
    hdrs = {"User-Agent": "py-guardian", **(headers or {})}
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")

    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
                if raw:
                    return resp.status, body
                try:
                    return resp.status, json.loads(body) if body else {}
                except json.JSONDecodeError:
                    return resp.status, body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in RETRY_STATUS and attempt < retries:
                time.sleep(_backoff(attempt, e.headers.get("Retry-After")))
                continue
            raise HttpError(e.code, body) from None
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries:
                time.sleep(_backoff(attempt))
                continue
            raise
