"""WP3-4 B1/B2: 公開面の入力検査（inputs.validate と Gate.admit）。自作の確認（緑は証明ではない）。"""
import pytest

from fakes import FakeAdapter, make_offer
from shopping import inputs
from shopping.guard import Gate, GuardedAdapter, RateLimited, RateLimiter
from shopping.inputs import InvalidInput, fits_limit, validate

OK = dict(keywords=["洗濯洗剤"])


def test_limit_is_128_utf8_bytes_s8():
    """S8: 検索語・除外語の長さは UTF-8 で 128 バイト以内（全角 42 文字・半角 128 文字）。"""
    assert inputs.MAX_BYTES == 128 and inputs.WIDTH_TEXT == "全角42文字（半角128文字）"
    assert fits_limit("あ" * 42) and not fits_limit("あ" * 43)
    assert fits_limit("x" * 128) and not fits_limit("x" * 129)
    assert fits_limit("ｱ" * 42) and not fits_limit("ｱ" * 43)       # 半角カナも 3 バイト
    assert fits_limit("あ" * 41 + "xxxxx") and not fits_limit("あ" * 41 + "xxxxxx")
    assert not fits_limit(chr(0xD800))                                # エンコードできない文字列は不可


@pytest.mark.parametrize("kw", [
    dict(OK), dict(keywords="洗剤"), dict(keywords=["あ" * 42]), dict(keywords=["x" * 128]),
    dict(keywords=[c * 2 for c in "abcde"]), dict(OK, ng_keyword="aa bb cc dd ee"), dict(OK, ng_keyword="あ" * 42),
    dict(OK, min_price=0, max_price=10_000_000), dict(OK, sort="-reviewCount"),
    dict(OK, include_terms=["あ" * 42] * 5, exclude_terms=["x" * 128]), dict(OK, basis="個"),
    dict(OK, basis="kWh"), dict(OK, basis="L"), dict(OK, basis=""), dict(OK, desired_quantity=0.5),
    dict(OK, desired_quantity=1e12), dict(OK, include_terms="詰め替え"),
])
def test_valid_inputs_pass(kw):
    validate(**kw)


@pytest.mark.parametrize("kw", [
    dict(keywords=[]), dict(keywords=["  "]), dict(keywords=None), dict(keywords=[c * 2 for c in "abcdef"]),
    dict(keywords=["あ" * 43]), dict(keywords=["x" * 129]), dict(keywords=[1]),
    dict(OK, ng_keyword="aa bb cc dd ee ff"), dict(OK, ng_keyword="x" * 129), dict(OK, ng_keyword="あ" * 43), dict(OK, ng_keyword=5),
    dict(OK, min_price=-1), dict(OK, max_price=10_000_001), dict(OK, min_price=True),
    dict(OK, min_price="100"), dict(OK, max_price=1.5), dict(OK, sort="+hacked"), dict(OK, sort=""),
    dict(OK, include_terms=list("abcdef")), dict(OK, exclude_terms=["あ" * 43]),
    dict(OK, include_terms=[1]), dict(OK, exclude_terms={"a": 1}), dict(OK, basis="ふしぎ"),
    dict(OK, basis="x" * 500), dict(OK, basis=5), dict(OK, desired_quantity=0),
    dict(OK, desired_quantity=-1), dict(OK, desired_quantity=True), dict(OK, desired_quantity="5"),
    dict(OK, desired_quantity=float("inf")), dict(OK, desired_quantity=float("nan")),
    dict(OK, desired_quantity=1e13),
])
def test_invalid_inputs_raise_with_a_safe_message(kw):
    with pytest.raises(InvalidInput) as e:
        validate(**kw)
    msg = str(e.value)
    assert msg and "Traceback" not in msg and "x" * 100 not in msg and "あ" * 40 not in msg


def test_all_official_sort_values_are_allowed():
    for s in ("standard", "+affiliateRate", "-affiliateRate", "+reviewCount", "-reviewCount",
              "+reviewAverage", "-reviewAverage", "+itemPrice", "-itemPrice", "+updateTimestamp",
              "-updateTimestamp"):
        validate(**OK, sort=s)


def gate(limit=2):
    ad = FakeAdapter({("洗濯洗剤", 1): ([make_offer("a", "洗剤 900g")], 1)})
    return Gate(GuardedAdapter(ad), RateLimiter(limit=limit)), ad


def test_admit_validates_before_counting_the_ip_budget_or_touching_the_adapter():
    g, ad = gate(limit=2)
    for _ in range(10):
        with pytest.raises(InvalidInput):
            g.admit("203.0.113.1", keywords=["aa"] * 6)
    g.admit("203.0.113.1", **OK, pages=1)
    g.admit("203.0.113.1", **OK, pages=1)
    with pytest.raises(RateLimited):
        g.admit("203.0.113.1", **OK, pages=1)
    assert ad.calls == [] and g.adapter.api_calls == 0


def test_admit_and_check_share_one_budget():
    g, _ = gate(limit=2)
    g.check("203.0.113.2")
    g.admit("203.0.113.2", **OK, pages=1)
    with pytest.raises(RateLimited):
        g.check("203.0.113.2")


# --- pages・start_page（2026-11-06 #931: 既定 3 ページ＋範囲指定で何件でも） ---
# pages 省略（None）＝既定の 3。整数は 1〜100（楽天 IchibaItem Search の page 上限）。start_page も 1〜100
@pytest.mark.parametrize("pages", [None, 1, 2, 3, 4, 50, 100])
def test_pages_none_or_1_to_100_pass(pages):
    validate(**OK, pages=pages)
    validate(**OK)                                      # 省略（既定）も通る


@pytest.mark.parametrize("pages", [0, 101, -1, 1.5, "2", True, False])
def test_pages_out_of_range_or_non_int_is_invalid(pages):
    with pytest.raises(InvalidInput, match="pages"):
        validate(**OK, pages=pages)


def test_check_pages_and_start_page_return_the_resolved_values():
    assert inputs.DEFAULT_PAGES == 3
    assert inputs.check_pages(None) == 3 and inputs.check_pages(7) == 7
    assert inputs.check_start_page(None) == 1 and inputs.check_start_page(4) == 4


@pytest.mark.parametrize("start,pages", [(None, None), (1, 100), (4, 10), (98, 3), (100, 1), (50, 51), (1, None)])
def test_start_page_range_within_rakuten_ceiling_passes(start, pages):
    validate(**OK, start_page=start, pages=pages)


@pytest.mark.parametrize("start", [0, 101, -1, 1.5, "2", True, False])
def test_start_page_out_of_range_or_non_int_is_invalid(start):
    with pytest.raises(InvalidInput, match="start_page"):
        validate(**OK, start_page=start)


@pytest.mark.parametrize("start,pages", [(99, 3), (100, 2), (98, 4), (51, 51), (2, 100)])
def test_start_page_plus_pages_over_100_is_invalid_and_says_the_rakuten_ceiling(start, pages):
    with pytest.raises(InvalidInput, match="100 ページ目までしか返しません"):
        validate(**OK, start_page=start, pages=pages)


@pytest.mark.parametrize("n,pages", [(5, 100), (5, None), (4, 3), (5, 2)])
def test_no_keywords_times_pages_limit_any_more(n, pages):
    # 以前は 検索語の数×ページ数 ≤ 9 で弾いていた（出典の無い上限だったので撤去）
    validate(keywords=[f"k{i}" for i in range(n)], pages=pages)


def test_rate_limiter_weight_counts_pages_and_rejection_consumes_nothing():
    t = [0.0]
    lim = RateLimiter(limit=5, window=60, clock=lambda: t[0])
    lim.hit("ip", 3)
    lim.hit("ip", 2)                                   # 合計 5 回分でちょうど満杯
    with pytest.raises(RateLimited):
        lim.hit("ip", 1)
    t[0] = 61
    lim.hit("ip", 3)                                   # 窓を出たので通る
    with pytest.raises(RateLimited) as e:
        lim.hit("ip", 3)                               # 3+3 > 5 -> 弾く（数えない）
    assert e.value.retry_after >= 1
    lim.hit("ip", 2)                                   # 弾いた分は消費していない: 3+2=5


def test_rate_limiter_weight_larger_than_limit_is_clamped_so_one_call_can_pass():
    lim = RateLimiter(limit=2, window=60, clock=lambda: 0.0)
    lim.hit("ip", 3)
    with pytest.raises(RateLimited):
        lim.hit("ip", 1)


def test_admit_charges_pages_and_default_is_three():
    gate = Gate(FakeAdapter({}), RateLimiter(limit=10, window=60, clock=lambda: 0.0))
    gate.admit("ip", **OK)                             # pages 省略 = 既定の 3 回分
    gate.admit("ip", **OK, pages=None)                 # 明示 None も 3 回分（計 6）
    gate.admit("ip", **OK, pages=4)                    # 計 10
    with pytest.raises(RateLimited):
        gate.admit("ip", **OK, pages=1)


def test_admit_start_page_does_not_change_the_weight_but_range_is_checked_first():
    gate = Gate(FakeAdapter({}), RateLimiter(limit=3, window=60, clock=lambda: 0.0))
    gate.admit("ip", **OK, start_page=50, pages=2)     # 重みは pages=2
    for _ in range(5):
        with pytest.raises(InvalidInput):
            gate.admit("ip", **OK, start_page=99, pages=3)   # 範囲外は回数を消費しない
    gate.admit("ip", **OK, pages=1)                    # 2+1=3 でちょうど満杯
    with pytest.raises(RateLimited):
        gate.admit("ip", **OK, pages=1)

