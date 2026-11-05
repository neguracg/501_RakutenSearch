import pytest

from fakes import FakeAdapter, make_offer
from shopping.adapters.base import AdapterError
from shopping.orchestrator import Limits, search_many


def run(pages, keywords, sleeps=None, **kw):
    ad = FakeAdapter(pages)
    sl = [] if sleeps is None else sleeps
    offers, stats = search_many(ad, keywords, sleep=sl.append, **kw)
    return ad, offers, stats, sl


def test_multiple_keywords_collect_candidates_ac1():
    pages = {("a", 1): ([make_offer("1"), make_offer("2")], 2),
             ("b", 1): ([make_offer("3")], 1)}
    _, offers, stats, _ = run(pages, ["a", "b"])
    assert sorted(o.mall_item_code for o in offers) == ["1", "2", "3"]
    assert stats.total_received == 3 and stats.unique_offers == 3
    assert [(s.keyword, s.api_count, s.received, s.error) for s in stats.per_keyword] == [
        ("a", 2, 2, None), ("b", 1, 1, None)]
    assert stats.stopped_reason is None and stats.fetched_at


def test_dedupe_by_item_code_keeps_both_keywords_ac2():
    pages = {("a", 1): ([make_offer("1"), make_offer("2")], 2),
             ("b", 1): ([make_offer("2"), make_offer("3")], 2)}
    _, offers, stats, _ = run(pages, ["a", "b"])
    by = {o.mall_item_code: o for o in offers}
    assert len(offers) == 3
    assert by["2"].matched_keywords == ["a", "b"]
    assert by["1"].matched_keywords == ["a"] and by["3"].matched_keywords == ["b"]
    assert stats.duplicates_removed == 1 and stats.total_received == 4
    assert stats.unique_offers == 3


def test_same_keyword_twice_does_not_duplicate_keyword_label():
    pages = {("a", 1): ([make_offer("1")], 1)}
    _, offers, _, _ = run(pages, ["a", "a"])
    assert offers[0].matched_keywords == ["a"]


def test_paging_stops_when_all_fetched():
    pages = {("a", 1): ([make_offer("1"), make_offer("2")], 3),
             ("a", 2): ([make_offer("3")], 3)}
    ad, offers, stats, _ = run(pages, ["a"], max_pages=3, hits=2)
    assert len(offers) == 3 and len(ad.calls) == 2  # 3 ページ目は取りに行かない
    assert stats.per_keyword[0].api_count == 3


def test_max_pages_respected():
    pages = {("a", p): ([make_offer(f"{p}-{i}") for i in range(2)], 100) for p in (1, 2, 3, 4)}
    ad, offers, _, _ = run(pages, ["a"], max_pages=2, hits=2)
    assert len(ad.calls) == 2 and len(offers) == 4


def test_filters_are_passed_through():
    ad, _, _, _ = run({("a", 1): ([], 0)}, ["a"], ng_keyword="x", min_price=10, max_price=20,
                      sort="+itemPrice", hits=5)
    kw = ad.calls[0][1]
    assert kw["ng_keyword"] == "x" and kw["min_price"] == 10 and kw["max_price"] == 20
    assert kw["sort"] == "+itemPrice" and kw["hits"] == 5 and kw["page"] == 1


def test_429_stops_everything_remaining():
    pages = {("a", 1): ([make_offer("1")], 1),
             ("b", 1): AdapterError("http_429"),
             ("c", 1): ([make_offer("9")], 1)}
    ad, offers, stats, _ = run(pages, ["a", "b", "c"])
    assert [c[0] for c in ad.calls] == ["a", "b"]  # c は呼ばない
    assert stats.stopped_reason == "rate_limited"
    assert [o.mall_item_code for o in offers] == ["1"]
    assert stats.per_keyword[-1].keyword == "b" and stats.per_keyword[-1].error == "http_429"


def test_429_on_page2_stops_remaining_pages_and_keywords():
    pages = {("a", 1): ([make_offer("1")], 100),
             ("a", 2): AdapterError("http_429")}
    ad, offers, stats, _ = run(pages, ["a", "b"], max_pages=3, hits=1)
    assert len(ad.calls) == 2 and stats.stopped_reason == "rate_limited"
    assert len(offers) == 1


@pytest.mark.parametrize("kind", ["http_403", "timeout", "network_error", "invalid_json",
                                  "unexpected_response", "http_500"])
def test_other_errors_recorded_and_continue(kind):
    pages = {("a", 1): AdapterError(kind), ("b", 1): ([make_offer("2")], 1)}
    ad, offers, stats, _ = run(pages, ["a", "b"])
    assert [c[0] for c in ad.calls] == ["a", "b"]
    assert stats.per_keyword[0].error == kind and stats.per_keyword[1].error is None
    assert stats.stopped_reason is None
    assert [o.mall_item_code for o in offers] == ["2"]


def test_too_many_keywords_raises_before_any_call():
    ad = FakeAdapter({})
    with pytest.raises(ValueError):
        search_many(ad, [f"k{i}" for i in range(6)], sleep=lambda s: None)
    assert ad.calls == []


def test_too_many_pages_raises_before_any_call():
    ad = FakeAdapter({})
    with pytest.raises(ValueError):
        search_many(ad, ["a"], max_pages=101, sleep=lambda s: None)     # 楽天の page 上限は 100
    assert ad.calls == []


def test_limits_are_configurable():
    ad = FakeAdapter({})
    search_many(ad, [f"k{i}" for i in range(6)], limits=Limits(max_keywords=6),
                sleep=lambda s: None)
    assert len(ad.calls) == 6
    with pytest.raises(ValueError):
        search_many(ad, ["a", "b"], limits=Limits(max_keywords=1), sleep=lambda s: None)


@pytest.mark.parametrize("kw", [dict(max_pages=0), dict(hits=0), dict(hits=31)])
def test_bad_values_raise(kw):
    with pytest.raises(ValueError):
        search_many(FakeAdapter({}), ["a"], sleep=lambda s: None, **kw)


def test_empty_keywords_raises():
    with pytest.raises(ValueError):
        search_many(FakeAdapter({}), [], sleep=lambda s: None)


def test_sleep_between_requests_not_before_first():
    pages = {("a", 1): ([make_offer("1")], 99), ("a", 2): ([make_offer("2")], 99),
             ("b", 1): ([make_offer("3")], 1)}
    _, _, _, sl = run(pages, ["a", "b"], max_pages=2, hits=1)
    # リクエスト 3 回 → 間隔は 2 回、各 1.0 秒以上
    assert len(sl) == 2 and all(s >= 1.0 for s in sl)


def test_single_request_never_sleeps():
    _, _, _, sl = run({("a", 1): ([], 0)}, ["a"])
    assert sl == []


def test_sleep_applied_after_error_too():
    pages = {("a", 1): AdapterError("timeout"), ("b", 1): ([], 0)}
    _, _, _, sl = run(pages, ["a", "b"])
    assert len(sl) == 1


def test_non_adapter_exception_propagates():
    class Boom(FakeAdapter):
        def search(self, keyword, **kw):
            raise RuntimeError("bug")
    with pytest.raises(RuntimeError):
        search_many(Boom({}), ["a"], sleep=lambda s: None)


def test_keyword_stat_pages_fetched_and_truncated():
    def pg(n, p):
        return [make_offer(f"{p}-{i}") for i in range(n)]
    # 取り切った（3 ページで 90 件中 90 件）: truncated でない
    pages = {("a", p): (pg(30, p), 90) for p in (1, 2, 3)}
    _, _, stats, _ = run(pages, ["a"], max_pages=3)
    s = stats.per_keyword[0]
    assert (s.pages_fetched, s.received, s.api_count, s.truncated) == (3, 90, 90, False)
    # 3 ページ取ってもヒットが残る: truncated
    pages = {("a", p): (pg(30, p), 500) for p in (1, 2, 3)}
    _, _, stats, _ = run(pages, ["a"], max_pages=3)
    s = stats.per_keyword[0]
    assert (s.pages_fetched, s.received, s.api_count, s.truncated) == (3, 90, 500, True)
    # 要求 1 ページで終わるが残りあり: truncated
    _, _, stats, _ = run({("a", 1): (pg(30, 1), 500)}, ["a"], max_pages=1)
    assert stats.per_keyword[0].truncated is True and stats.per_keyword[0].pages_fetched == 1
    # ヒットが少なく途中で終わる: truncated でない・取得ページ数は実際の数
    _, _, stats, _ = run({("a", 1): (pg(30, 1), 45), ("a", 2): (pg(15, 2), 45)}, ["a"], max_pages=3)
    s = stats.per_keyword[0]
    assert (s.pages_fetched, s.received, s.truncated) == (2, 45, False)


def test_keyword_stat_error_is_not_truncated_and_counts_only_fetched_pages():
    pages = {("a", 1): ([make_offer("1")], 500), ("a", 2): AdapterError("timeout")}
    _, _, stats, _ = run(pages, ["a"], max_pages=3)
    s = stats.per_keyword[0]
    assert s.error == "timeout" and s.pages_fetched == 1 and s.truncated is False


# --- pages 省略＝既定 3 ページ・start_page で範囲指定（2026-11-06 #931） ---
def _pages_of(total, keyword="a", per_page=30, upto=None):
    """total 件ヒットする語の表。page ごとに別商品を per_page 件（最終ページは端数）。"""
    upto = upto or -(-total // per_page)
    table = {}
    for p in range(1, upto + 1):
        n = max(0, min(per_page, total - (p - 1) * per_page))
        table[(keyword, p)] = ([make_offer(f"{keyword}-{p}-{i}") for i in range(n)], total)
    return table


def _pages_called(ad):
    return [kw["page"] for _, kw in ad.calls]


def test_default_is_3_pages_90_hits_with_next_page_4_and_remaining_54():
    ad, offers, stats, _ = run(_pages_of(144), ["a"])                 # max_pages 省略
    s = stats.per_keyword[0]
    assert len(offers) == 90 and _pages_called(ad) == [1, 2, 3]
    assert (s.api_count, s.received, s.pages_fetched) == (144, 90, 3)
    assert (s.start_page, s.last_page, s.next_page, s.remaining, s.truncated) == (1, 3, 4, 54, True)
    assert run(_pages_of(144), ["a"], max_pages=None)[2].per_keyword[0].next_page == 4   # None も既定の 3


def test_start_page_4_pages_2_fetches_pages_4_and_5_up_to_the_144th_hit():
    ad, offers, stats, _ = run(_pages_of(144), ["a"], start_page=4, max_pages=2)
    s = stats.per_keyword[0]
    assert _pages_called(ad) == [4, 5] and len(offers) == 54          # 31〜120 は取らず、121〜144 の 24 件と 91〜120 の 30 件
    assert (s.api_count, s.received, s.pages_fetched) == (144, 54, 2)
    assert (s.start_page, s.last_page, s.next_page, s.remaining, s.truncated) == (4, 5, None, 0, False)


def test_start_page_chain_covers_every_hit_exactly_once():
    seen = set()
    start = 1
    while start:
        _, offers, stats, _ = run(_pages_of(144), ["a"], start_page=start, max_pages=2)
        got = {o.mall_item_code for o in offers}
        assert not (got & seen)
        seen |= got
        start = stats.per_keyword[0].next_page
    assert len(seen) == 144


def test_everything_fetched_in_the_default_range_has_no_next_page():
    _, offers, stats, _ = run(_pages_of(61), ["a"])
    s = stats.per_keyword[0]
    assert len(offers) == 61 and (s.last_page, s.next_page, s.remaining, s.truncated) == (3, None, 0, False)


def test_hits_exactly_90_has_no_next_page():
    s = run(_pages_of(90), ["a"])[2].per_keyword[0]
    assert (s.pages_fetched, s.next_page, s.remaining, s.truncated) == (3, None, 0, False)


def test_explicit_100_pages_stops_at_the_rakuten_ceiling_without_next_page():
    ad, offers, stats, _ = run(_pages_of(5000, upto=101), ["a"], max_pages=100)
    s = stats.per_keyword[0]
    assert len(ad.calls) == 100 and len(offers) == 3000
    assert (s.api_count, s.last_page, s.next_page, s.remaining, s.truncated) == (5000, 100, None, 0, False)


def test_range_ending_at_page_100_from_97_has_no_next_page_even_with_more_hits():
    ad, _, stats, _ = run(_pages_of(5000, upto=101), ["a"], start_page=98, max_pages=3)
    s = stats.per_keyword[0]
    assert _pages_called(ad) == [98, 99, 100] and s.next_page is None and s.remaining == 0


def test_range_past_page_100_is_rejected_before_any_call():
    ad = FakeAdapter({})
    for kw in (dict(start_page=99, max_pages=3), dict(start_page=101), dict(start_page=0), dict(start_page=100, max_pages=2)):
        with pytest.raises(ValueError):
            search_many(ad, ["a"], sleep=lambda s: None, **kw)
    assert ad.calls == []
    with pytest.raises(ValueError, match="100 ページ目までしか返しません"):
        search_many(ad, ["a"], start_page=99, max_pages=3, sleep=lambda s: None)


def test_remaining_ignores_hits_beyond_the_100_page_ceiling():
    s = run(_pages_of(5000, upto=101), ["a"], max_pages=3)[2].per_keyword[0]
    assert (s.api_count, s.remaining, s.next_page) == (5000, 2910, 4)  # 3000 - 90


def test_stats_has_elapsed_sec_with_one_decimal():
    _, _, stats, _ = run(_pages_of(10), ["a"])
    assert isinstance(stats.elapsed_sec, float) and stats.elapsed_sec >= 0
    assert round(stats.elapsed_sec, 1) == stats.elapsed_sec


# --- 時間の安全網（80 秒）: 実時間は clock を注入して固定する ---
class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleeper(self, sec):
        return lambda s: setattr(self, "t", self.t + sec)


def _timed_run(pages, keywords, *, per_request_sec, budget=80.0, **kw):
    clock = FakeClock()

    class TimedAdapter(FakeAdapter):
        def search(self, keyword, **k):
            clock.t += per_request_sec
            return super().search(keyword, **k)
    ad = TimedAdapter(pages)
    offers, stats = search_many(ad, keywords, sleep=lambda s: None, clock=clock,
                                limits=Limits(time_budget_sec=budget), **kw)
    return ad, offers, stats


def test_time_budget_stops_at_80_seconds_and_returns_next_page():
    ad, offers, stats = _timed_run(_pages_of(3000), ["a"], per_request_sec=1.0, max_pages=100)
    s = stats.per_keyword[0]
    assert len(ad.calls) == 80 and stats.elapsed_sec == 80.0       # 81 回目は 80 秒を超えるので取りに行かない
    assert len(offers) == 80 * 30
    assert stats.stopped_reason == "time_limit"
    assert (s.pages_fetched, s.last_page, s.next_page, s.truncated) == (80, 80, 81, True)
    assert s.remaining == 3000 - 80 * 30


def test_time_budget_not_hit_when_fast_enough():
    ad, _, stats = _timed_run(_pages_of(3000), ["a"], per_request_sec=0.5, max_pages=100)
    assert len(ad.calls) == 100 and stats.stopped_reason is None
    assert stats.per_keyword[0].next_page is None


def test_time_budget_slow_requests_stop_early_by_prediction():
    ad, _, stats = _timed_run(_pages_of(3000), ["a"], per_request_sec=30.0, max_pages=100)
    assert len(ad.calls) == 2 and stats.per_keyword[0].next_page == 3      # 3 回目は 90 秒になるので取らない


def test_time_budget_always_makes_the_first_request():
    ad, offers, stats = _timed_run(_pages_of(3000), ["a"], per_request_sec=500.0, max_pages=3)
    assert len(ad.calls) == 1 and len(offers) == 30 and stats.per_keyword[0].next_page == 2


def test_time_budget_unstarted_keywords_are_listed_with_next_page_from_the_start():
    pages = {**_pages_of(3000, "a"), **_pages_of(100, "b")}
    ad, offers, stats = _timed_run(pages, ["a", "b", "c"], per_request_sec=1.0, max_pages=100, start_page=1)
    a, b, c = stats.per_keyword
    assert a.next_page == 81 and a.pages_fetched == 80
    for u in (b, c):
        assert (u.pages_fetched, u.api_count, u.next_page, u.remaining, u.truncated) == (0, None, 1, None, True)
    assert {kw for kw, _ in ad.calls} == {"a"} and stats.stopped_reason == "time_limit"


def test_time_budget_unstarted_keyword_after_a_finished_one():
    pages = {**_pages_of(60, "a"), **_pages_of(100, "b")}
    ad, _, stats = _timed_run(pages, ["a", "b"], per_request_sec=30.0, max_pages=5)
    a, b = stats.per_keyword
    assert (a.pages_fetched, a.next_page, a.truncated) == (2, None, False)    # a は取り切った（60 秒）
    assert (b.pages_fetched, b.next_page, b.api_count) == (0, 1, None)        # b の 1 回目は 90 秒になる見込み → 未着手
    assert stats.stopped_reason == "time_limit"


def test_invalid_time_budget_is_rejected():
    with pytest.raises(ValueError):
        search_many(FakeAdapter({}), ["a"], limits=Limits(time_budget_sec=0), sleep=lambda s: None)
