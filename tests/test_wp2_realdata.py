"""WP2-2: 実データで見えた不具合の試験（送料表記の食い違い・URL そのまま）。
WP3 で倍巻き・ply 前提の試験は削除した（道具は商品の意味を判定しない。SPEC §7・§8）。"""
import pytest

from fakes import FakeAdapter, make_offer
from shopping import service
from shopping.adapters.rakuten import parse_item


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
    ad = FakeAdapter({("kk", 1): ([o], 1)})
    r = service.compare_offers(["kk"], adapter=ad, sleep=lambda s: None)
    assert any("食い違" in c for c in r["comparison"]["caveats"])
    r = service.search_products(["kk"], adapter=ad, sleep=lambda s: None)
    assert any("食い違" in n for n in r["notes"])


# --- URL は API が返したまま ---

def test_item_url_kept_as_returned_including_rafcid():
    url = "https://item.rakuten.co.jp/shop/item1/?rafcid=wsc_i_is_ABC"
    it = _item(0)
    it["itemUrl"] = url
    o = parse_item(it, "t")
    assert o.item_url == url and o.item_url_status == "ok"
