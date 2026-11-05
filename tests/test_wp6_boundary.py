# @owns 数え語の直後の境界（SPEC §7 P5〜P7）の自作確認。独立試験（ブラインド）の代わりではない
"""WP6: 数え語の直後の境界（P5）・連結位置で捨てる時は low（P6）・数え語の位置の未知語（P7）。"""
import pytest

from shopping import pricing, quantity
from shopping.quantity import parse_quantity


def _cm(title):
    q = parse_quantity(title)
    return q.confidence, q.count_total, q.measure_total


# --- P5: 数え語の直後に文字が続く数は個数にしない（購入系・付属系・仕様の数）---------------------

@pytest.mark.parametrize("title,expected", [
    ("洗剤 詰め替え 900g 2点お買い上げでポイント5倍", ("high", 1, 900.0)),
    ("シャンプー 詰め替え 350ml 2点ご購入で送料無料", ("high", 1, 350.0)),
    ("ボディソープ 500ml 2本同時購入でポイント10倍", ("high", 1, 500.0)),
    ("シャンプー 400ml 2点目半額クーポン対象", ("high", 1, 400.0)),
    ("モバイルバッテリー 20000mAh 22.5W 2台同時充電 PSE認証", ("high", 1, 20000.0)),
    ("電源タップ 延長コード 3m 3個口 雷ガード", ("high", 1, 3.0)),
    ("掃除機 150W 替えフィルター2個付属", ("high", 1, 150.0)),
    ("お試しサンプル3包プレゼント 洗顔料 100g", ("high", 1, 100.0)),
])
def test_p5_a_number_followed_by_a_letter_is_not_a_count(title, expected):
    assert _cm(title) == expected


@pytest.mark.parametrize("title", [
    "5本指ソックス レディース 22-24cm", "T字カミソリ 3枚刃 使い捨て", "ダイヤル式 南京錠 4ケタ 防犯",
    "サイクルヘルメット 6ヶ所通気口", "折りたたみ傘 5本骨 軽量", "スマホケース ガラスフィルム2枚付き",
])
def test_p5_spec_numbers_make_no_count(title):
    q = parse_quantity(title)
    assert q.confidence != "high" or q.count_total in (None, 1)


@pytest.mark.parametrize("title,expected", [
    ("洗剤 500ml 12個入り", ("high", 12, 6000.0)),
    ("洗剤 500ml 12個 セット", ("high", 12, 6000.0)),
    ("洗剤 500ml 3個セット", ("high", 3, 1500.0)),
    ("洗剤 500ml 6本パック", ("high", 6, 3000.0)),
    ("水 500ml×24本", ("high", 24, 12000.0)),
    ("水 500ml 24本=12L", ("high", 24, 12000.0)),
    ("水 500ml 24本、送料無料", ("high", 24, 12000.0)),
    ("水 500ml 24本・送料無料", ("high", 24, 12000.0)),
    ("水 500ml 24本/箱", ("high", 24, 12000.0)),
    ("水 500ml 24本（送料無料）", ("high", 24, 12000.0)),
    ("水 【500ml 24本】", ("high", 24, 12000.0)),
    ("ビール 350ml 24缶ケース", ("high", 24, 8400.0)),
    ("6缶350ml", ("high", 6, 2100.0)),
    ("トイレットペーパー 12ロール30m ダブル", ("high", 12, 360.0)),
    ("水 2L 6本 ケース", ("high", 6, 12000.0)),
])
def test_p5_whitelisted_boundaries_still_count(title, expected):
    assert _cm(title) == expected


@pytest.mark.parametrize("title", ["洗剤 500ml 5コーヒー", "洗剤 500ml 3ケーブル", "洗剤 500ml 3ケーキ"])
def test_p5_a_long_vowel_after_ko_or_ke_is_not_a_count(title):
    assert _cm(title) == ("high", 1, 500.0)


@pytest.mark.parametrize("title", ["洗剤 500ml 6コ入り", "洗剤 500ml 6ケ入り", "洗剤 500ml 6コ セット"])
def test_p5_ko_and_ke_still_count_before_the_whitelist(title):
    assert _cm(title)[:2] == ("high", 6)


def test_p5_has_one_boundary_function_and_no_per_word_exception_lists():
    assert hasattr(quantity, "_counter_boundary_ok")
    assert not hasattr(quantity, "_TEN_NOT_COUNT")
    assert not hasattr(quantity, "MONTH_COUNTERS")


@pytest.mark.parametrize("title", ["サプリ 90粒 12ヶ月保証", "洗剤 900g×6 3点以上でポイント5倍", "洗剤 900g×6 2点購入"])
def test_p5_replaces_the_old_month_and_ten_lists(title):
    assert parse_quantity(title).count_total in (6, 90)


# --- P6: 連結位置で捨てる時は low --------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("コーヒー ドリップ 8g×100P", ("high", 100, 800.0)),
    ("ティーバッグ 緑茶 2g×100P×3袋", ("high", 300, 600.0)),
    ("ティーバッグ 2g×200P×2袋", ("high", 400, 800.0)),
])
def test_p6_a_linked_p_is_not_capped_at_99(title, expected):
    assert _cm(title) == expected


@pytest.mark.parametrize("title", [
    "洗剤 500ml×2点お買い上げ",           # ×の直後で個数に採れない
    "洗剤 500ml 2個お得×3",                # 直後に×
    "洗剤 500ml 入数 2点お買い上げ",       # 入数の直後
    "洗剤 500ml×1.5個",                   # 小数は個数にできない
])
def test_p6_dropping_a_count_at_a_linking_position_is_low(title):
    assert parse_quantity(title).confidence == "low"


def test_p6_a_solo_p_keeps_the_99_cap_and_x1():
    assert parse_quantity("ウェブカメラ 1080P").confidence == "none"
    assert _cm("トイレットペーパー 12ロール 1080P") == ("high", 12, None)
    assert parse_quantity("ティッシュ 12P").confidence == "low"
    assert parse_quantity("紙コップ 205ml 100P").confidence == "low"      # 100 を数え、単独の P は low


# --- P7: 計量値・個数に空白で続く「数字＋表に無い語」---------------------------------------

@pytest.mark.parametrize("title", [
    "洗剤 900g 6ブロック", "ヨーグルト 400g 12カップ", "ソース 300ml 6ボトル", "ゼリー 130g 12パウチ",
    "水 500ml 24本 6ボトル",
])
def test_p7_unknown_katakana_counter_after_a_quantity_is_low(title):
    assert parse_quantity(title).confidence == "low"


@pytest.mark.parametrize("title", [
    "洗剤 500ml 12個 1年保証", "洗剤 500ml 6本 3色", "電池 12本 4K対応", "洗剤 500ml 6本 60日分",
])
def test_p7_kanji_and_ascii_words_are_not_flagged(title):
    assert parse_quantity(title).confidence == "high"


# --- 単価の丸めは pricing が所有する（@owns）---------------------------------------------

def test_unit_price_rounding_lives_in_pricing_only():
    for name in ("unit_price_digits", "round_unit_price", "format_unit_price"):
        assert hasattr(pricing, name)
        assert not hasattr(quantity, name)
    assert pricing.round_unit_price(0.004) == 0.004
    assert pricing.format_unit_price(123.456) == "123.46"
