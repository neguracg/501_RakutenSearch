import pytest

from fakes import make_offer
from shopping.models import QuantityInfo
from shopping.pricing import compare, price_per_m, total_price, unit_price


def q(total, ply="double", length=30.0, conf="high", unit="ロール"):
    return QuantityInfo(unit=unit, per_pack=12, pack_count=(total // 12 if total else None),
                        total=total if conf == "high" else None, ply=ply, length_m=length,
                        confidence=conf, evidence="x")


def off(code, price, total=None, ply="double", length=30.0, ship="included", fee=None,
        conf="high", **kw):
    o = make_offer(code, price=price, shipping_status=ship, shipping_fee=fee, **kw)
    o.quantity = q(total, ply, length, conf) if (total is not None or conf != "high") else None
    return o


# --- unit_price / total_price -------------------------------------------------

def test_unit_price_basic_and_unrounded():
    assert unit_price(off("a", 1000, 48)) == pytest.approx(1000 / 48)
    assert unit_price(off("a", 1000, 48)) != round(1000 / 48, 2)


@pytest.mark.parametrize("conf", ["low", "none"])
def test_unit_price_none_unless_high(conf):
    assert unit_price(off("a", 1000, conf=conf)) is None


def test_unit_price_none_without_quantity_or_price():
    assert unit_price(make_offer("a")) is None
    assert unit_price(off("a", None, 48)) is None


@pytest.mark.parametrize("ship,fee,price,expected", [
    ("included", None, 1000, 1000),
    ("included", 500, 1000, 1000),      # 送料込みなら fee は足さない
    ("separate", 500, 1000, 1500),
    ("separate", None, 1000, None),
    ("unknown", None, 1000, None),
    ("unknown", 500, 1000, None),
    ("included", None, None, None),
])
def test_total_price(ship, fee, price, expected):
    assert total_price(make_offer("a", price=price, shipping_status=ship, shipping_fee=fee)) == expected


def test_price_per_m():
    assert price_per_m(off("a", 3000, 60, length=30.0)) == pytest.approx(50 / 30)
    assert price_per_m(off("a", 3000, 60, length=None)) is None


# --- AC3: 入り数違いを同じグループ ------------------------------------------------

def test_ac3_different_pack_sizes_same_group():
    r = compare([off("a", 1500, 36), off("b", 2000, 48), off("c", 3000, 72)])
    assert len(r.groups) == 1 and len(r.groups[0].offers) == 3
    assert r.groups[0].ply == "double" and r.groups[0].length_m == 30.0


# --- AC5: 単位価格で順位付け -----------------------------------------------------

def test_ac5_unit_price_ranking():
    # 単位価格: a=41.67, b=41.0..., c=40.0 → 価格順ではなく単位価格順
    a = off("a", 1500, 36)    # 41.666
    b = off("b", 1968, 48)    # 41.0
    c = off("c", 2880, 72)    # 40.0
    d = off("d", 1200, 12)    # 100
    r = compare([d, a, c, b])
    assert [o.mall_item_code for o in r.groups[0].offers] == ["c", "b", "a", "d"]
    assert r.cheapest_unit_price.mall_item_code == "c"
    assert r.cheapest_price.mall_item_code == "d"  # 商品価格最安は別物


def test_unit_price_unknown_goes_last_in_group():
    r = compare([off("x", 100, conf="none"), off("a", 1500, 36)])
    assert [o.mall_item_code for o in r.groups[0].offers] == ["a", "x"]
    assert r.cheapest_unit_price.mall_item_code == "a"
    assert any("単位価格を出せない" in c for c in r.caveats)


def test_ranking_compares_unrounded_values():
    # 丸めると同値になるが生の値では a が安い
    a = off("a", 1000, 3)    # 333.3333
    b = off("b", 2000, 6)    # 333.3333 (同値)
    c = off("c", 1001, 3)    # 333.6667
    r = compare([c, b, a])
    assert r.cheapest_unit_price.mall_item_code in ("a", "b")
    assert r.groups[0].offers[-1].mall_item_code == "c"


# --- AC6: 仕様違いを誤統合しない --------------------------------------------------

def test_ac6_ply_and_length_separate_groups():
    offers = [off("d30", 2000, 48, "double", 30.0), off("s30", 1500, 48, "single", 30.0),
              off("d50", 2500, 48, "double", 50.0), off("d30b", 2200, 48, "double", 30.0)]
    r = compare(offers)
    keys = {g.key: sorted(o.mall_item_code for o in g.offers) for g in r.groups}
    assert len(r.groups) == 3
    assert keys["double|30m|ロール"] == ["d30", "d30b"]
    assert keys["single|30m|ロール"] == ["s30"] and keys["double|50m|ロール"] == ["d50"]
    assert r.groups[0].key == "double|30m|ロール"  # 候補数の多い束が先頭


def test_ac6_cross_group_unit_price_has_caveat():
    r = compare([off("d30", 2000, 48, "double", 30.0), off("s30", 1500, 48, "single", 30.0)])
    assert r.cheapest_unit_price.mall_item_code == "s30"
    assert any("仕様違いを含む" in c for c in r.caveats)


def test_no_cross_group_caveat_when_single_spec():
    r = compare([off("a", 1500, 36), off("b", 2000, 48)])
    assert not any("仕様違いを含む" in c for c in r.caveats)


def test_required_spec_filters_and_reports_count():
    offers = [off("d30", 2000, 48, "double", 30.0), off("s30", 1000, 48, "single", 30.0),
              off("d50", 900, 48, "double", 50.0), off("unk", 500, 48, None, None)]
    r = compare(offers, required_spec={"ply": "double", "length_m": 30})
    assert [o.mall_item_code for g in r.groups for o in g.offers] == ["d30"]
    assert r.cheapest_unit_price.mall_item_code == "d30"
    assert r.cheapest_price.mall_item_code == "d30"
    assert any("2 件" in c and "除外" in c for c in r.caveats)       # 仕様違い 2 件
    assert any("1 件" in c and "読み取れなかった" in c for c in r.caveats)  # 仕様不明 1 件
    assert not any("仕様違いを含む" in c for c in r.caveats)


def test_required_spec_with_no_quantity_info_excluded_as_unknown():
    r = compare([make_offer("a", price=100)], required_spec={"ply": "double"})
    assert r.groups == [] and r.cheapest_price is None
    assert any("比較できる候補がない" in c for c in r.caveats)


def test_required_spec_unsupported_key_is_reported():
    r = compare([off("a", 1500, 36)], required_spec={"color": "white"})
    assert any("color" in c for c in r.caveats) and r.cheapest_unit_price is not None


# --- AC7: 送料不明は総額最安と断定しない ------------------------------------------

def test_ac7_unknown_shipping_blocks_cheapest_total():
    r = compare([off("a", 1500, 36, ship="included"), off("b", 1000, 36, ship="unknown")])
    assert r.cheapest_total is None
    assert any("送料" in c and "断定できない" in c for c in r.caveats)


def test_ac7_separate_without_fee_blocks_cheapest_total():
    r = compare([off("a", 1500, 36, ship="included"), off("b", 1000, 36, ship="separate")])
    assert r.cheapest_total is None


def test_cheapest_total_when_all_known():
    r = compare([off("a", 1500, 36, ship="included"),
                 off("b", 1000, 36, ship="separate", fee=800),
                 off("c", 1400, 36, ship="separate", fee=50)])
    assert r.cheapest_total.mall_item_code == "c"   # 1500 / 1800 / 1450
    assert not any("断定できない" in c for c in r.caveats)


def test_cheapest_total_ignores_filtered_out_offers():
    offers = [off("a", 1500, 36, ship="included"),
              off("bad", 900, 36, ply="single", ship="unknown")]
    r = compare(offers, required_spec={"ply": "double"})
    assert r.cheapest_total.mall_item_code == "a"


# --- 必要数量を満たす最安 ---------------------------------------------------------

def test_cheapest_meeting_quantity():
    offers = [off("a", 1000, 36), off("b", 1800, 48), off("c", 2900, 72), off("d", 700, 12)]
    r = compare(offers, desired_quantity=48)
    assert r.cheapest_meeting_quantity.mall_item_code == "b"
    r = compare(offers, desired_quantity=100)
    assert r.cheapest_meeting_quantity is None and any("必要数量" in c for c in r.caveats)


def test_meeting_quantity_ignores_unknown_quantity():
    offers = [off("x", 100, conf="low"), off("b", 1800, 48)]
    r = compare(offers, desired_quantity=48)
    assert r.cheapest_meeting_quantity.mall_item_code == "b"
    assert any("入り数不明" in c for c in r.caveats)


def test_no_desired_quantity_means_none():
    assert compare([off("a", 1000, 36)]).cheapest_meeting_quantity is None


# --- 空・価格なし -----------------------------------------------------------------

def test_empty_input():
    r = compare([])
    assert r.groups == [] and r.cheapest_price is None and r.cheapest_unit_price is None
    assert r.cheapest_total is None and r.caveats


def test_offers_without_price_are_not_ranked():
    r = compare([off("a", None, 36), off("b", 1000, 36)])
    assert r.cheapest_price.mall_item_code == "b"
    assert any("価格が不明" in c for c in r.caveats)
