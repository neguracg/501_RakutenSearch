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
    dict(keywords=list("abcde")), dict(OK, ng_keyword="a b c d e"), dict(OK, ng_keyword="あ" * 42),
    dict(OK, min_price=0, max_price=10_000_000), dict(OK, sort="-reviewCount"),
    dict(OK, include_terms=["あ" * 42] * 5, exclude_terms=["x" * 128]), dict(OK, basis="個"),
    dict(OK, basis="kWh"), dict(OK, basis="L"), dict(OK, basis=""), dict(OK, desired_quantity=0.5),
    dict(OK, desired_quantity=1e12), dict(OK, include_terms="詰め替え"),
])
def test_valid_inputs_pass(kw):
    validate(**kw)


@pytest.mark.parametrize("kw", [
    dict(keywords=[]), dict(keywords=["  "]), dict(keywords=None), dict(keywords=list("abcdef")),
    dict(keywords=["あ" * 43]), dict(keywords=["x" * 129]), dict(keywords=[1]),
    dict(OK, ng_keyword="a b c d e f"), dict(OK, ng_keyword="x" * 129), dict(OK, ng_keyword="あ" * 43), dict(OK, ng_keyword=5),
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
            g.admit("203.0.113.1", keywords=["a"] * 6)
    g.admit("203.0.113.1", **OK)
    g.admit("203.0.113.1", **OK)
    with pytest.raises(RateLimited):
        g.admit("203.0.113.1", **OK)
    assert ad.calls == [] and g.adapter.api_calls == 0


def test_admit_and_check_share_one_budget():
    g, _ = gate(limit=2)
    g.check("203.0.113.2")
    g.admit("203.0.113.2", **OK)
    with pytest.raises(RateLimited):
        g.check("203.0.113.2")
