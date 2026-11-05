"""WP2-3: 公開面共通の流量保護 guard.py（GuardedAdapter の直列化・キャッシュ・待ち行列）。"""
import threading

import pytest

from fakes import FakeAdapter, make_offer
from shopping.adapters.base import AdapterError
from shopping.guard import GuardedAdapter


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def offers():
    return [make_offer("a", "トイレットペーパー ダブル 30m 12ロール×4袋", 2400, shipping_status="included")]


def fake(pages=None):
    return FakeAdapter(pages or {("トイレットペーパー", 1): (offers(), 3)})


def test_cache_expires_after_ttl_and_ttl_is_capped_at_24h():
    clock = Clock()
    ad = fake()
    ga = GuardedAdapter(ad, clock=clock, sleep=clock.sleep)
    ga.search("トイレットペーパー", page=1, hits=30)
    clock.t += 599
    ga.search("トイレットペーパー", page=1, hits=30)
    assert len(ad.calls) == 1
    clock.t += 2
    ga.search("トイレットペーパー", page=1, hits=30)
    assert len(ad.calls) == 2
    assert GuardedAdapter(ad, ttl=10 ** 9)._ttl <= 24 * 3600


def test_cache_returns_copies_and_is_bounded():
    clock = Clock()
    ad = fake({("トイレットペーパー", 1): (offers(), 3)})
    ga = GuardedAdapter(ad, max_entries=2, clock=clock, sleep=clock.sleep)
    o1, _ = ga.search("トイレットペーパー", page=1, hits=30)
    o1[0].price = 1
    o2, _ = ga.search("トイレットペーパー", page=1, hits=30)
    assert o2[0].price == 2400
    for k in ("x1", "x2", "x3"):
        ga.search(k, page=1, hits=30)
    assert len(ga._cache) == 2


def test_errors_are_not_cached():
    clock = Clock()
    ad = fake({("k", 1): AdapterError("timeout")})
    ga = GuardedAdapter(ad, clock=clock, sleep=clock.sleep)
    for _ in range(2):
        with pytest.raises(AdapterError):
            ga.search("k", page=1, hits=30)
    assert len(ad.calls) == 2


def test_api_calls_are_serialized_at_least_one_second_apart():
    clock = Clock()
    times = []

    class Timed(FakeAdapter):
        def search(self, keyword, **kw):
            times.append(clock())
            return super().search(keyword, **kw)

    ad = Timed({("a", 1): ([], 0), ("b", 1): ([], 0), ("c", 1): ([], 0)})
    ga = GuardedAdapter(ad, clock=clock, sleep=clock.sleep)
    for k in ("a", "b", "c"):
        ga.search(k, page=1, hits=30)
    assert all(b - a >= 1.0 for a, b in zip(times, times[1:])) and len(times) == 3


def test_serialization_holds_across_threads():
    ad_calls = []
    lock = threading.Lock()
    clock = Clock()

    class Slow(FakeAdapter):
        def search(self, keyword, **kw):
            with lock:
                ad_calls.append(clock())
            return [], 0

    ga = GuardedAdapter(Slow({}), clock=clock, sleep=clock.sleep)
    ts = [threading.Thread(target=lambda k=k: ga.search(k, page=1, hits=30)) for k in "abcde"]
    [t.start() for t in ts]
    [t.join() for t in ts]
    ad_calls.sort()
    assert len(ad_calls) == 5 and all(b - a >= 1.0 for a, b in zip(ad_calls, ad_calls[1:]))


def test_too_many_waiters_or_wait_timeout_gives_busy():
    ga = GuardedAdapter(fake(), wait_timeout=0.01)
    ga._call_lock.acquire()
    with pytest.raises(AdapterError) as ei:
        ga.search("x", page=1, hits=30)
    assert ei.value.kind == "busy"
    ga2 = GuardedAdapter(fake(), max_waiters=0)
    with pytest.raises(AdapterError) as ei:
        ga2.search("x", page=1, hits=30)
    assert ei.value.kind == "busy"




def test_cache_hit_is_served_even_while_another_call_holds_the_api_lock():
    clock = Clock()
    ga = GuardedAdapter(fake(), wait_timeout=0.01, clock=clock, sleep=clock.sleep)
    ga.search("トイレットペーパー", page=1, hits=30)
    ga._call_lock.acquire()   # 別の人の API 呼び出し中を模す
    offers_, count = ga.search("トイレットペーパー", page=1, hits=30)   # キャッシュは待たずに返る
    assert count == 3 and offers_
