# @owns 公開面（Web と リモートMCP）共通の流量保護（API 直列化・短期キャッシュ・IP別回数制限・クライアントIP）
"""service の手前に置く共通層。Web と MCP の両方がこの Gate を通るので、保護は二重実装にしない。

- GuardedAdapter: 楽天 API への呼び出しをプロセス全体で 1 秒 1 回に直列化し、同じ条件はメモリに最大 10 分キャッシュする。
- RateLimiter: キー（IP）別の回数制限。
- Gate.admit: 公開面の入口。入力検査（inputs）→ 回数制限の順で、弾いた入力は API 枠も回数も消費しない。
- 時計と sleep は差し替え可能（試験で実時間を待たない）。
- 例外・ログに URL・キー・応答本文を出さない（AdapterError は kind のみ）。
"""
from __future__ import annotations

import contextvars
import copy
import ipaddress
import os
import threading
import time
from collections import OrderedDict, deque

from .adapters.base import AdapterError, MarketplaceAdapter
from . import inputs
from .adapters.mock import MockAdapter

MIN_INTERVAL_SEC = 1.0
CACHE_TTL_SEC = 600            # 10 分（楽天のキャッシュ上限 24 時間よりずっと短い）
CACHE_MAX_ENTRIES = 300
MAX_WAITERS = 6                # これを超えて待たせない（"busy" を返す）
WAIT_TIMEOUT_SEC = 30.0
RATE_LIMIT_PER_MIN = 20
RATE_WINDOW_SEC = 60.0

# リモートMCP の呼び出し元 IP を、ASGI ミドルウェアからツール関数へ運ぶ
client_ip_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("client_ip", default=None)


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__("rate_limited")
        self.retry_after = retry_after


class GuardedAdapter(MarketplaceAdapter):
    """inner Adapter を 1 秒 1 回に直列化し、同条件の結果を最大 CACHE_TTL_SEC 秒キャッシュする。"""

    def __init__(self, inner: MarketplaceAdapter, *, min_interval: float = MIN_INTERVAL_SEC,
                 ttl: float = CACHE_TTL_SEC, max_entries: int = CACHE_MAX_ENTRIES,
                 max_waiters: int = MAX_WAITERS, wait_timeout: float = WAIT_TIMEOUT_SEC,
                 clock=time.monotonic, sleep=time.sleep):
        self._inner = inner
        self.mall = getattr(inner, "mall", "")
        self.is_mock = isinstance(inner, MockAdapter)
        self._min_interval = min_interval
        self._ttl = min(float(ttl), 24 * 3600.0)
        self._max_entries = max_entries
        self._max_waiters = max_waiters
        self._wait_timeout = wait_timeout
        self._clock = clock
        self._sleep = sleep
        self._call_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._waiters = 0
        self._last_end: float | None = None
        self._cache: OrderedDict[tuple, tuple[float, list, int]] = OrderedDict()
        self.api_calls = 0            # 実際に inner を呼んだ回数（試験・運用の観測用）

    def __repr__(self) -> str:
        return "GuardedAdapter(...)"

    def _key(self, keyword: str, kw: dict) -> tuple:
        return (keyword, tuple(sorted(kw.items())))

    def _cache_get(self, key: tuple):
        with self._state_lock:
            hit = self._cache.get(key)
            if hit is None:
                return None
            stored_at, offers, count = hit
            if self._clock() - stored_at > self._ttl:
                del self._cache[key]
                return None
            return copy.deepcopy(offers), count

    def _cache_put(self, key: tuple, offers: list, count: int) -> None:
        with self._state_lock:
            self._cache[key] = (self._clock(), copy.deepcopy(offers), count)
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def search(self, keyword: str, **kw):
        key = self._key(keyword, kw)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        with self._state_lock:
            if self._waiters >= self._max_waiters:
                raise AdapterError("busy")
            self._waiters += 1
        try:
            if not self._call_lock.acquire(timeout=self._wait_timeout):
                raise AdapterError("busy")
            try:
                cached = self._cache_get(key)   # 待っている間に別の人が同じ検索を済ませたかもしれない
                if cached is not None:
                    return cached
                if self._last_end is not None:
                    wait = self._last_end + self._min_interval - self._clock()
                    if wait > 0:
                        self._sleep(wait)
                try:
                    self.api_calls += 1
                    offers, count = self._inner.search(keyword, **kw)
                finally:
                    self._last_end = self._clock()
                self._cache_put(key, offers, count)
                return copy.deepcopy(offers), count
            finally:
                self._call_lock.release()
        finally:
            with self._state_lock:
                self._waiters -= 1


class RateLimiter:
    """キー別のスライディングウィンドウ。limit 回/window 秒を超えたら RateLimited。"""

    def __init__(self, limit: int = RATE_LIMIT_PER_MIN, window: float = RATE_WINDOW_SEC,
                 clock=time.monotonic, max_keys: int = 5000):
        self._limit = limit
        self._window = window
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            if len(self._hits) > self._max_keys:
                self._hits = {k: d for k, d in self._hits.items()
                              if d and now - d[-1] <= self._window}
            d = self._hits.setdefault(key, deque())
            while d and now - d[0] > self._window:
                d.popleft()
            if len(d) >= self._limit:
                raise RateLimited(max(1, int(self._window - (now - d[0])) + 1))
            d.append(now)


class Gate:
    """Web と MCP が共有する入口。adapter（保護済み）と IP 別回数制限を持つ。"""

    def __init__(self, adapter: MarketplaceAdapter, limiter: RateLimiter | None = None):
        self.adapter = adapter if isinstance(adapter, GuardedAdapter) else GuardedAdapter(adapter)
        self.limiter = limiter or RateLimiter(limit=_env_int("RATE_LIMIT_PER_MIN", RATE_LIMIT_PER_MIN))

    def check(self, ip: str | None) -> None:
        """回数制限。超えたら RateLimited。"""
        self.limiter.hit(ip or "unknown")

    def admit(self, ip: str | None, **fields) -> None:
        """公開面（Web と MCP）の入口。先に入力を検査し（不正なら inputs.InvalidInput）、通ったものだけ回数を数える。
        ロック取得・最小間隔のスリープ・API 呼び出しより前に置くので、弾いた入力は API 枠を消費しない。"""
        inputs.validate(**fields)
        self.check(ip)


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def pick_client_ip(cf_connecting_ip: str | None, peer_host: str | None) -> str:
    """Cloudflare Tunnel 経由なら CF-Connecting-IP、無ければ接続元。不正な値は接続元に倒す。"""
    if cf_connecting_ip:
        try:
            return str(ipaddress.ip_address(cf_connecting_ip.strip()))
        except ValueError:
            pass
    return peer_host or "unknown"
