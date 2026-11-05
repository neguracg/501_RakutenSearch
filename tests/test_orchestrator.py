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


# --- pages 省略（max_pages=None）＝全件（楽天の 100 ページ天井まで） ---
def _pages_of(total, keyword="a", per_page=30, upto=None):
    """total 件ヒットする語の表。page ごとに別商品を per_page 件（最終ページは端数）。"""
    upto = upto or -(-total // per_page)
    table = {}
    for p in range(1, upto + 1):
        n = max(0, min(per_page, total - (p - 1) * per_page))
        table[(keyword, p)] = ([make_offer(f"{keyword}-{p}-{i}") for i in range(n)], total)
    return table


def test_max_pages_none_fetches_everything_until_hits_run_out():
    ad, offers, stats, _ = run(_pages_of(144), ["a"], max_pages=None)
    s = stats.per_keyword[0]
    assert len(offers) == 144 and [kw["page"] for _, kw in ad.calls] == [1, 2, 3, 4, 5]
    assert (s.api_count, s.received, s.pages_fetched, s.truncated) == (144, 144, 5, False)


def test_max_pages_none_default_is_all():
    ad, offers, _, _ = run(_pages_of(61), ["a"])                      # 引数省略も全件
    assert len(offers) == 61 and len(ad.calls) == 3


def test_max_pages_none_stops_at_rakuten_ceiling_100_and_is_truncated():
    ad, offers, stats, _ = run(_pages_of(5000, upto=101), ["a"], max_pages=None)
    s = stats.per_keyword[0]
    assert len(ad.calls) == 100 and len(offers) == 3000              # 100 ページ × 30 件
    assert (s.api_count, s.received, s.pages_fetched, s.truncated) == (5000, 3000, 100, True)


def test_max_pages_none_exactly_3000_hits_is_not_truncated():
    _, _, stats, _ = run(_pages_of(3000), ["a"], max_pages=None)
    s = stats.per_keyword[0]
    assert (s.pages_fetched, s.received, s.truncated) == (100, 3000, False)


def test_explicit_max_pages_100_is_allowed_and_equals_the_ceiling():
    ad, _, stats, _ = run(_pages_of(5000, upto=101), ["a"], max_pages=100)
    assert len(ad.calls) == 100 and stats.per_keyword[0].truncated is True


def test_stats_has_elapsed_sec_with_one_decimal():
    _, _, stats, _ = run(_pages_of(10), ["a"])
    assert isinstance(stats.elapsed_sec, float) and stats.elapsed_sec >= 0
    assert round(stats.elapsed_sec, 1) == stats.elapsed_sec
