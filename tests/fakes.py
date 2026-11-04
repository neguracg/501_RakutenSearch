"""テスト用の偽 opener / 偽 adapter。"""
from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import HTTPError

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._buf = io.BytesIO(body)
        self.status = status

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    """open(req, timeout) を記録し、responses を順に返す（最後の1件は繰り返す）。"""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.timeouts = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        self.timeouts.append(timeout)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, BaseException):
            raise r
        if isinstance(r, (dict, list)):
            return FakeResponse(json.dumps(r).encode("utf-8"))
        if isinstance(r, bytes):
            return FakeResponse(r)
        return r


def http_error(code: int, url="https://example.invalid/x?applicationId=SECRET"):
    return HTTPError(url, code, "msg SECRET", {}, io.BytesIO(b"body SECRET"))
