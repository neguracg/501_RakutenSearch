"""WP2-2: 実データで見えた不具合の試験（倍巻きの比較グループ・送料表記の食い違い・URL そのまま）。"""
import pytest

from fakes import FakeAdapter, make_offer
from shopping import service
from shopping.adapters.rakuten import parse_item
from shopping.pricing import compare
from shopping.quantity import parse_quantity


@pytest.mark.parametrize("text,label", [
    ("トイレットペーパー ダブル 2倍巻き 12ロール", "x2"),
    ("ダブル 1.5倍巻 8ロール", "x1.5"),
    ("ダブル 3倍長持ち 6ロール", "x3"),
    ("ダブル 1.5倍 12ロール", "x1.5"),
    ("ダブル ２倍巻き 12ロール", "x2"),
    ("ダブル 倍巻き 12ロール", "multi"),
    ("ダブル ロング 12ロール", "long"),
    ("ダブル 12ロール", None),
    ("ダブル 30m 12ロール", None),
    ("ポイント10倍 ダブル 12ロール", None),
    ("ダブル 12ロール 10倍ポイント", None),
    ("ポイント最大5倍 ダブル 12ロール", None),
    ("P10倍 ダブル 12ロール", None),
])
def test_length_label(text, label):
    q = parse_quantity(text)
    assert q.length_label == label
    if label:
        assert q.length_m is None  # 倍巻きの実長は確定させない


def _off(code, name, price=1000):
    o = make_offer(code, name=name, price=price)
    o.quantity = parse_quantity(name)
    return o


def test_long_roll_not_in_same_group_as_plain_unknown_length():
    plain = _off("a", "ダブル 12ロール", 600)
    plain2 = _off("b", "ダブル 12ロール×2", 1100)
    double = _off("c", "ダブル 2倍巻き 12ロール", 900)
    c = compare([plain, plain2, double])
    keys = {g.key: {o.mall_item_code for o in g.offers} for g in c.groups}
    assert keys["double|unknown|ロール"] == {"a", "b"}
    assert keys["double|unknown|ロール|x2"] == {"c"}


def test_different_multipliers_are_separate_groups():
    a = _off("a", "ダブル 2倍巻き 12ロール")
    b = _off("b", "ダブル 1.5倍巻き 12ロール")
    assert len(compare([a, b]).groups) == 2


def test_unknown_length_and_known_length_are_separate():
    a = _off("a", "ダブル 12ロール")
    b = _off("b", "ダブル 30m 12ロール")
    assert len(compare([a, b]).groups) == 2


def test_cheapest_unit_price_ignores_long_roll_when_plain_exists_and_says_so():
    plain = _off("a", "ダブル 12ロール", 1200)             # 100円/ロール
    cheap_long = _off("b", "ダブル 2倍巻き 12ロール", 600)  # 50円/ロール（長さが違うので比べない）
    c = compare([plain, cheap_long])
    assert c.cheapest_unit_price.mall_item_code == "a"
    assert any("倍巻き" in cv for cv in c.caveats)


def test_only_long_rolls_still_rank_within_themselves():
    a = _off("a", "ダブル 2倍巻き 12ロール", 600)
    b = _off("b", "ダブル 2倍巻き 12ロール", 700)
    c = compare([a, b])
    assert c.cheapest_unit_price.mall_item_code == "a"
    assert len(c.groups) == 1


def test_mixed_multipliers_only_long_rolls_get_spec_caveat():
    a = _off("a", "ダブル 2倍巻き 12ロール", 600)
    b = _off("b", "ダブル 3倍巻き 12ロール", 700)
    assert any("仕様違い" in cv for cv in compare([a, b]).caveats)


# --- 送料 ---

def _item(flag, title="商品 12ロール"):
    return {"itemCode": "s:1", "itemName": title, "itemPrice": 1000, "postageFlag": flag,
            "itemUrl": "https://item.rakuten.co.jp/s/1/"}


def test_postage_flag_zero_is_included_one_is_separate():
    # 楽天公式（IchibaItem Search 出力パラメータ postageFlag）: 0=送料込み, 1=送料別
    assert parse_item(_item(0), "t").shipping_status == "included"
    assert parse_item(_item(1), "t").shipping_status == "separate"


def test_title_free_shipping_does_not_override_flag_but_is_flagged():
    o = parse_item(_item(1, "送料無料 ダブル 12ロール"), "t")
    assert o.shipping_status == "separate"
    assert service.shipping_title_conflict(o)
    d = service.offer_to_dict(o)
    assert d["shipping_status"] == "separate" and d["shipping_title_conflict"]


def test_no_conflict_when_title_and_flag_agree():
    assert service.shipping_title_conflict(parse_item(_item(0, "送料無料 12ロール"), "t")) is None
    assert service.shipping_title_conflict(parse_item(_item(1, "12ロール"), "t")) is None
    assert service.shipping_title_conflict(parse_item(_item(1, "送料別 12ロール"), "t")) is None


def test_title_separate_vs_included_flag():
    o = parse_item(_item(0, "送料別 12ロール"), "t")
    assert o.shipping_status == "included" and service.shipping_title_conflict(o)


def test_conflict_appears_in_compare_caveats_and_search_notes():
    o = parse_item(_item(1, "送料無料 ダブル 12ロール"), "t")
    ad = FakeAdapter({("k", 1): ([o], 1)})
    r = service.compare_offers(["k"], adapter=ad, sleep=lambda s: None)
    assert any("食い違" in c for c in r["comparison"]["caveats"])
    r = service.search_products(["k"], adapter=ad, sleep=lambda s: None)
    assert any("食い違" in n for n in r["notes"])


# --- URL は API が返したまま ---

def test_item_url_kept_as_returned_including_rafcid():
    url = "https://item.rakuten.co.jp/shop/item1/?rafcid=wsc_i_is_ABC"
    it = _item(0)
    it["itemUrl"] = url
    o = parse_item(it, "t")
    assert o.item_url == url and o.item_url_status == "ok"
