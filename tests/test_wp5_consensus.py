"""WP5-1: 数量の信頼度を「解釈の一致」で決める（SPEC §7 P0〜P4・X1〜X5、B・C5）。implementer の自作の確認。
独立試験（ブラインド）とは別。自作の緑は証明ではない。"""
import itertools

import pytest

from shopping import quantity
from shopping.quantity import parse_quantity


def got(text, basis=None):
    q = parse_quantity(text, basis)
    return (q.confidence, q.count_total, q.count_unit, q.content_amount, q.measure_total)


def high_count(text):
    q = parse_quantity(text)
    return q.count_total if q.confidence == "high" else q.confidence


# --- P0 / P1 言い直し: 総数の書き方 × 数え語 × 内容量の有無 ------------------------------

CHAINS = ["12本×4パック", "12本 4パック", "12本入 4パック", "12本入り×4パック"]
STATED = ["({n}{w})", " {n}{w}", " 計{n}{w}", " 合計{n}{w}", " 全{n}{w}", "={n}{w}", "（{n}{w}）"]
WORDS = ["本", "パック", "個"]          # 内側と同じ / 外側と同じ / 別語（X2）


@pytest.mark.parametrize("chain,stated,word,measure",
                         list(itertools.product(CHAINS, STATED, WORDS, ["", " 500ml"])))
def test_p1_restated_total_is_not_a_factor(chain, stated, word, measure):
    text = "商品 " + chain + stated.format(n=48, w=word) + measure
    q = parse_quantity(text)
    assert (q.confidence, q.count_total) == ("high", 48), text
    if measure:
        assert q.content_amount == 500 and q.measure_total == 24000


@pytest.mark.parametrize("text,expected", [
    ("トイレットペーパー 12ロール×4パック(48ロール)", 48),
    ("おむつ 64枚×3パック(192枚)", 192),
    ("トイレットペーパー 96ロール(12ロール×8パック)", 96),
    ("商品 48ケース 4ロール×6パック×2ケース", 48),         # 総数が先で、後ろが積（鎖の先読み）
    ("商品 48個(4ロール 6パック 2ケース)", 48),
    ("鉛筆 2ダース(24本)", 24),
])
def test_p1_restatement_before_or_after(text, expected):
    assert high_count(text) == expected


def test_p1_natto_restated_pack_count_keeps_the_content():
    q = parse_quantity("納豆 45g×3パック×16個 (48パック)")
    assert (q.confidence, q.count_total, q.count_unit, q.content_amount, q.measure_total) == \
        ("high", 48, "パック", 45.0, 2160.0)


@pytest.mark.parametrize("text", [
    "12ロール×4パック 計50ロール", "12ロール×4パック(24ロール)", "12本入 4パック 計36本",
    "12ロール×4パック 4パック", "12ロール 4パック 50ロール",
])
def test_p0_disagreeing_total_is_low(text):
    assert parse_quantity(text).confidence == "low"


# --- P2 空白だけの連結は 1 因子の時だけ -----------------------------------------------

def test_p2_blank_join_is_not_added_to_a_chain_of_two_or_more():
    assert high_count("コピー用紙 500枚 5冊") == 2500                       # 1 因子には足す（W1）
    assert parse_quantity("12ロール×4パック 5冊").confidence == "low"       # X3
    assert parse_quantity("12ロール 4パック 5冊").confidence == "low"


# --- P3 / X1 文脈の要る数え語 ---------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("洗剤 900g×6 2点購入", ("high", 6)),
    ("洗剤 900g×6 3点以上でポイント5倍", ("high", 6)),
    ("サプリ 90粒 3ヶ月分", ("high", 90)),
    ("サプリ 90粒 12ヶ月保証", ("high", 90)),
    ("洗剤 900g×6 12ケ月保証", ("high", 6)),
    ("トイレットペーパー 12ロール 10P還元", ("high", 12)),
    ("トイレットペーパー 12ロール 5P増量", ("high", 12)),
    ("トイレットペーパー 12ロール 10PUP", ("high", 12)),
    ("モニター 4K 2160P 12ロール", ("high", 12)),
    ("ギフト 3点セット", ("high", 3)),
    ("ギフト 5点", ("high", 5)),
    ("ケーキ 6ヶ", ("high", 6)),
    ("ヘッドホン 12ヶ月保証", ("none", None)),
    ("ウェブカメラ 1080P", ("none", None)),
])
def test_p3_context_words(text, expected):
    q = parse_quantity(text)
    assert (q.confidence, q.count_total) == expected


@pytest.mark.parametrize("text", [
    "ティッシュ 12P", "ウェブカメラ 60P 対応", "ウェブカメラ 1080P 60P", "12ロール×4パック 60P",
    "ティッシュ 5P 5個", "ティッシュ 5P×12", "水 2L×6本 2P", "12ロール×4パック 3点セット",
])
def test_x1_standalone_np_is_low_and_np_candidate_disagreement_is_low(text):
    assert parse_quantity(text).confidence == "low"


@pytest.mark.parametrize("text,expected", [
    ("ティッシュ 5箱×12P", 60), ("単3 12本入 3P", 36), ("単3 12本入×3P", 36), ("12本入 3ヶ", 36),
    ("12本入 3点", 36), ("ティッシュ 5箱×12P (60P)", 60),
])
def test_x5_np_after_times_or_after_irisuu_is_a_count(text, expected):
    assert high_count(text) == expected


def test_x1_p_must_be_1_to_99():
    assert parse_quantity("商品 100P").confidence == "none"
    assert parse_quantity("商品 0P").confidence == "none"


# --- P4 容器語の同数 / X4 -------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("3個入り 3セット", 9), ("3個入り 3袋", 9), ("3個入り 3箱", 9), ("3個入り 3ケース", 9),
    ("3個入り 400ml×3セット", 9), ("3本パック 3セット", 9), ("3袋 3個入り", "low"),
    ("3個入り 3冊", "low"), ("3個入り 400ml×3冊", "low"), ("タオル 3枚 3組", "low"),
    ("3個入り 3個", 3), ("12本入り 12本", 12),
])
def test_p4_same_number_outer_container_multiplies_otherwise_low(text, expected):
    assert high_count(text) == expected


def test_p1_has_priority_over_p4_when_the_product_matches():
    assert high_count("12ロール×4パック(4パック)") == "low"      # 4 は積(48)ではない → 食い違い
    assert high_count("12ロール×4パック(48パック)") == 48


# --- S3 の精密化: 個数が小さい方の内容量に付く時だけ総量の併記 -----------------------------

def test_s3_count_must_be_attached_to_the_smaller_content():
    assert parse_quantity("米 5kg 10kg 2袋").confidence == "low"
    q = parse_quantity("米 10kg (5kg×2袋)")
    assert (q.confidence, q.count_total, q.content_amount) == ("high", 2, 5000.0)
    q = parse_quantity("米 5kg 2袋 10kg")
    assert (q.confidence, q.count_total, q.content_amount) == ("high", 2, 5000.0)


# --- B: 数え語 コ・ケ・膳 -----------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("洗剤 900g 6ケセット", ("high", 6, "個", 900.0, 5400.0)),
    ("洗剤 900g 6コセット", ("high", 6, "個", 900.0, 5400.0)),
    ("割り箸 100膳 5パック", ("high", 500, "膳", None, None)),
    ("石鹸 80g×6コ入", ("high", 6, "個", 80.0, 480.0)),
    ("石鹸 80g×6ケ", ("high", 6, "個", 80.0, 480.0)),
    ("石鹸 80g×6ケース", ("high", 6, "ケース", 80.0, 480.0)),
])
def test_b_kana_counters(text, expected):
    assert got(text) == expected


def test_b_unknown_counter_in_connecting_position_is_low():
    assert parse_quantity("洗剤 900g×6ブロック").confidence == "low"
    assert parse_quantity("割り箸 100膳×5ブロック").confidence == "low"


# --- C5: 読み飛ばした記述の後ろの ×N（倍数が落ちる）-------------------------------------

@pytest.mark.parametrize("text", [
    "ジェルボール 900g 30回分 ×2", "プロテイン 1kg 約33回分 ×2", "サプリ 90粒 3ヶ月分 ×2",
])
def test_c5_times_after_skipped_text_is_not_silently_dropped(text):
    assert parse_quantity(text).confidence == "low"


def test_c5_plain_times_and_orphan_alone_are_unchanged():
    assert high_count("ジェルボール 30回分 ×2") == 60
    assert parse_quantity("×6").confidence == "none"
    assert parse_quantity("マット 34×85cm").count_total == 1


# --- 表の整合 ------------------------------------------------------------------------

def test_new_counters_are_in_the_table():
    for key in ("コ", "ケ", "膳"):
        assert key in quantity.COUNTERS


def test_hostile_long_inputs_stay_fast_and_do_not_raise():
    text = "1個 " * 1000
    assert parse_quantity(text).confidence in ("none", "low", "high")


# --- B: S5 明示 basis の時、比べた次元を結果に出す ------------------------------------------

def _offer(code, name, price=3000):
    from shopping.models import Offer
    return Offer(mall="rakuten", mall_item_code=code, item_name=name, price=price,
                 item_url=f"https://item.rakuten.co.jp/s/{code}/", item_url_status="ok",
                 shipping_status="included")


def test_s5_result_says_which_dimension_the_unit_price_used():
    from shopping.pricing import compare
    from shopping.service import offer_to_dict
    offers = [_offer("a", "モバイルバッテリー 10000mAh 22.5W")]
    for basis, dim, label in [("mAh", "charge", "1mAhあたり"), ("W", "power", "1Wあたり"),
                              ("個", "count", "1個あたり"), (None, "charge", "1mAhあたり")]:
        compare(offers, basis=basis)
        d = offer_to_dict(offers[0])
        assert d["unit_price_dimension"] == dim and d["unit_price_label"] == label
        assert d["quantity"]["content_amounts"] == {"charge": 10000.0, "power": 22.5}


def test_s5_unknown_unit_price_has_no_dimension():
    from shopping.pricing import compare
    from shopping.service import offer_to_dict
    offers = [_offer("a", "洗剤 詰め替え")]
    compare(offers, basis="ml")
    assert offer_to_dict(offers[0])["unit_price_dimension"] is None


# --- C1: 単価の丸めは 1 つの実装 ------------------------------------------------------------

def test_c1_json_rounding_and_display_share_one_digit_rule():
    from shopping import service
    from shopping.quantity import format_unit_price, round_unit_price, unit_price_digits
    assert not hasattr(service, "_round_price")
    for x in (123.456, 0.004, 0.0004, 0.00004, 5.0, 0.0):
        assert format_unit_price(x) == f"{round_unit_price(x):,.{unit_price_digits(x)}f}"
    assert round_unit_price(0.004) == 0.004 and round_unit_price(123.456) == 123.46
    assert round_unit_price(None) is None


# --- C3: regulars の desired_quantity は inputs の検査と同じ -------------------------------

@pytest.mark.parametrize("value,ok", [(18000, True), (1.5, True), (0, False), (-1, False),
                                      (True, False), ("3", False), (float("inf"), False), (10**13, False)])
def test_c3_regulars_desired_quantity_uses_the_shared_check(value, ok):
    from shopping.regulars import RegularsError, _parse_one
    entry = {"id": "x", "name": "x", "keywords": ["x"], "desired_quantity": value}
    if ok:
        assert _parse_one(entry, 0).desired_quantity == value
    else:
        with pytest.raises(RegularsError):
            _parse_one(entry, 0)


def test_p0_single_description_only_forgives_the_same_counter_as_the_inner_one():
    assert high_count("12ロール×4袋 12ロール入り") == 48
    assert high_count("12ロール×4パック 12冊") == "low"
