"""WP4-1: 数量読み取りの強化（SPEC §7・§8 の S1〜S7・S11・W1・W2・W5）。implementer の自作の確認。
ブラインド試験（tests/test_blind_generic_quantity.py）とは別。自作の緑は証明ではない。"""
import pytest

from shopping import quantity
from shopping.models import Offer
from shopping.pricing import compare, filter_by_terms, term_in_name
from shopping.quantity import parse_quantity


def o(code, name, price=1000):
    return Offer(mall="rakuten", mall_item_code=code, item_name=name, price=price,
                 item_url=f"https://item.rakuten.co.jp/s/{code}/", item_url_status="ok",
                 shipping_status="included")


def got(text, basis=None):
    q = parse_quantity(text, basis)
    return (q.confidence, q.count_total, q.count_unit, q.content_amount, q.measure_total)


# --- S1 回分 ------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("プロテイン 1kg 約33回分", ("high", 1, "個", 1000.0, 1000.0)),
    ("洗剤 詰め替え 900g×6袋 約50回分", ("high", 6, "袋", 900.0, 5400.0)),
    ("ジェルボール 30回分", ("high", 30, "回分", None, None)),          # 計量値も他の個数も無い時だけ個数
    ("サプリ 30日分 60粒", ("high", 60, "粒", None, None)),
    ("洗剤 6袋 約30回分", ("high", 6, "袋", None, None)),
])
def test_s1_servings_are_not_pieces(text, expected):
    assert got(text) == expected


def test_s1_protein_cheapest_is_the_bigger_bag_per_100g():
    offers = [o("a", "プロテイン 1kg 約33回分", 3000), o("b", "プロテイン 2kg 約66回分", 5000),
              o("c", "プロテイン 3kg 約100回分", 8400)]
    c = compare(offers)
    assert c.basis == "g" and c.cheapest_unit_price.mall_item_code == "b"
    assert [x.mall_item_code for x in c.groups[0].offers] == ["b", "c", "a"]


# --- S2 言い直し ----------------------------------------------------------------------

@pytest.mark.parametrize("text,count,amount", [
    ("水 24本 (500ml×24)", 24, 500.0), ("水 24本（500ml×24本）", 24, 500.0), ("米 2袋 (5kg×2)", 2, 5000.0),
    ("洗剤 6袋 900g×6", 6, 900.0), ("水 24本 【500ml×24】", 24, 500.0),
])
def test_s2_restated_breakdown_is_not_multiplied_twice(text, count, amount):
    q = parse_quantity(text)
    assert (q.confidence, q.count_total, q.content_amount) == ("high", count, amount)


def test_s2_different_numbers_still_multiply():
    assert parse_quantity("12ロール×4袋").count_total == 48
    assert parse_quantity("水 6本 500ml×4").count_total == 24      # 6 と 4 は言い直しではない


# --- S3 総量の併記 ---------------------------------------------------------------------

@pytest.mark.parametrize("text,count,amount,total", [
    ("米 10kg (5kg×2袋)", 2, 5000.0, 10000.0), ("米 5kg×2袋 計10kg", 2, 5000.0, 10000.0),
    ("ドッグフード 7.5kg(2.5kg×3袋)", 3, 2500.0, 7500.0), ("水 500ml 24本 12L", 24, 500.0, 12000.0),
])
def test_s3_total_alongside_breakdown(text, count, amount, total):
    q = parse_quantity(text)
    assert (q.confidence, q.count_total, q.content_amount, q.measure_total) == ("high", count, amount, total)


@pytest.mark.parametrize("text", ["洗剤 900g 1.5kg", "米 10kg (5kg×3袋)", "水 2L 12L", "米 4kg×2袋 計10kg"])
def test_s3_other_mismatches_stay_low(text):
    assert parse_quantity(text).confidence == "low"


# --- S4 数え語 ------------------------------------------------------------------------

@pytest.mark.parametrize("text,count,unit", [
    ("トイレットペーパー 12ロール×4P", 48, "ロール"), ("ティッシュ 12P", 12, "パック"), ("ペン 2pcs", 2, "個"),
    ("ペン 3PC", 3, "個"), ("鉛筆 1ダース", 12, "個"), ("鉛筆 2ダース", 24, "個"), ("ノート 5冊", 5, "冊"),
    ("靴下 3ペア", 3, "ペア"), ("ケーキ 6ヶ", 6, "個"), ("ギフト 5点", 5, "点"),
    ("鉛筆 12本入り 2ダース", 24, "本"),
])
def test_s4_new_counters(text, count, unit):
    q = parse_quantity(text)
    assert (q.confidence, q.count_total, q.count_unit) == ("high", count, unit)


@pytest.mark.parametrize("text", ["洗剤 900g×6ブロック", "石鹸 4ブロック×6個", "石鹸 6ブロック入り×4",
                                  "石鹸 入数6ブロック", "洗剤 1.5kg×3set"])
def test_s4_unknown_counter_in_count_position_is_low(text):
    assert parse_quantity(text).confidence == "low"


@pytest.mark.parametrize("text", ["洗剤 900g×6 ブロック", "お得な3色セット 500ml", "2年保証 単3電池 8本"])
def test_s4_unknown_words_away_from_count_positions_are_ignored(text):
    assert parse_quantity(text).confidence == "high"


# --- W1 ×の無い2段 ----------------------------------------------------------------------

@pytest.mark.parametrize("text,count,unit", [
    ("コピー用紙 500枚 5冊", 2500, "枚"), ("単3 4本入 3パック", 12, "本"),
    ("ティッシュ 200組 5箱", 1000, "組"),
])
def test_w1_two_stage_counters_without_times(text, count, unit):
    q = parse_quantity(text)
    assert (q.confidence, q.count_total, q.count_unit) == ("high", count, unit)


@pytest.mark.parametrize("text,count", [
    ("電池 12本 12本入り", 12), ("1箱 24本入り", 24), ("12ロール×4袋 1袋12ロール入り", 48),
    ("ティッシュ 6個 6個入り", 6),
])
def test_w1_restating_same_counter_is_not_multiplied(text, count):
    assert parse_quantity(text).count_total == count


# --- S5 複数次元 ------------------------------------------------------------------------

def test_s5_explicit_basis_uses_that_dimension_in_parse_and_compare():
    name = "モバイルバッテリー 22.5W 急速充電 10000mAh"
    assert parse_quantity(name).content_dimension == "power"              # 自動は先頭の次元
    q = parse_quantity(name, "mAh")
    assert (q.content_dimension, q.content_amount, q.measure_total) == ("charge", 10000.0, 10000.0)
    assert parse_quantity(name, "ふしぎ").content_dimension == "power"
    c = compare([o("a", name, 5000), o("b", "モバイルバッテリー 20000mAh 18W", 8000)], basis="mAh")
    assert c.basis == "mAh" and c.cheapest_unit_price.mall_item_code == "b"
    assert c.cheapest_unit_price.unit_price == pytest.approx(8000 / 20000)
    a = next(x for x in c.groups[0].offers if x.mall_item_code == "a")      # 先頭の次元は W だが mAh で出る
    assert a.unit_price == pytest.approx(5000 / 10000) and not c.unknown_offers
    auto = compare([o("a", name, 5000), o("b", "モバイルバッテリー 20000mAh 18W", 8000)])
    assert auto.basis == "個"          # 先頭の次元が割れる（W と mAh）ので過半にならず個


# --- S6 桁数 ----------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["洗剤 1234567890g", "洗剤 1,234,567,890個", "水 " + "9" * 400 + "ml",
                                  "洗剤 900g×1234567890"])
def test_s6_more_than_nine_digits_is_low(text):
    q = parse_quantity(text)
    assert q.confidence == "low" and q.count_total is None and q.measure_total is None


def test_s6_nine_digits_and_thousands_separators_are_fine():
    assert parse_quantity("水 999,999,999ml").content_amount == 999999999.0
    assert parse_quantity("水 1,000ml×3").content_amount == 1000.0
    assert parse_quantity("洗剤 1,5kg").confidence == "none"             # 千区切りの形でないカンマ


def test_s6_compare_survives_huge_numbers():
    c = compare([o("a", "洗剤 " + "9" * 400 + "g", 100), o("b", "洗剤 900g", 300)], basis="g")
    assert [x.mall_item_code for x in c.unknown_offers] == ["a"]
    assert c.cheapest_unit_price.mall_item_code == "b"


# --- S7 語の境界 --------------------------------------------------------------------------

@pytest.mark.parametrize("term,name,hit", [
    ("2l", "水 12l", False), ("2l", "水 1.2l", False), ("2l", "水 2l×6", True), ("2l", "水 12l 2l", True),
    ("500mah", "電池 1500mah", False), ("500mah", "電池 1,500mah", False), ("500mah", "電池 500mah", True),
    ("2", "水 2.5l", False), ("2", "水 2l", True), ("2", "水 12l", False), ("2", "水 2,500ml", False),
    ("詰め替え", "洗剤 詰め替え 2l", True), ("l", "水 12l", True),     # 数字で始まらない/終わらない語は部分一致
    ("2l", "水 2lサイズ", True),
])
def test_s7_digit_boundaries(term, name, hit):
    assert term_in_name(term, name) is hit


def test_s7_filter_normalizes_width_and_case():
    offers = [o("a", "水 ２Ｌ×6"), o("b", "水 12L×1"), o("c", "水 1.2l")]
    kept, notes = filter_by_terms(offers, ["2L"], None)
    assert [x.mall_item_code for x in kept] == ["a"] and notes == ["含む語で除外: 2件"]
    kept, notes = filter_by_terms(offers, None, ["２l"])
    assert [x.mall_item_code for x in kept] == ["b", "c"] and notes == ["除く語で除外: 1件"]


# --- S11 表の整合 --------------------------------------------------------------------------

def test_s11_every_unit_dimension_has_a_display_row_and_no_duplicate_keys():
    assert {dim for dim, _ in quantity.UNITS.values()} <= set(quantity.DISPLAY)
    for table in (quantity.UNITS, quantity.COUNTERS):
        keys = [quantity._norm(k) for k in table]
        assert len(keys) == len(set(keys))
    assert quantity.resolve_unit("ℓ") == quantity.resolve_unit("L") == quantity.resolve_unit("l")
    assert quantity.resolve_unit("mL") == quantity.resolve_unit("ml")


def test_s11_missing_display_row_fails_at_import_time(monkeypatch):
    monkeypatch.setitem(quantity.UNITS, "oz", ("weight_unknown", 1))
    with pytest.raises(RuntimeError):
        quantity._check_tables()


def test_s11_alias_collision_fails_at_import_time(monkeypatch):
    monkeypatch.setitem(quantity.UNITS, "ＭＬ", ("volume", 1))      # NFKC＋casefold で ml と同じ
    with pytest.raises(RuntimeError):
        quantity._check_tables()
