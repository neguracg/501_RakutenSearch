"""WP3-0 ブラインド試験: 汎用 数量読み取り(§7) と 価格比較(§8)。

正本: plans/WP3_generic_quantity.md の「SPEC §7・§8 の差し替え」「インターフェース」
「確定した契約」(Q0〜Q17 への回答)。src/shopping の実装と既存の自作試験は見ずに作成。
期待値は全て手計算（式を各テストのコメントに残す）。実装担当は読まない・編集しない。
import は各テストの中で遅延させてあるので、未実装でも収集は常に通る。

確定した契約の使い方（試験が前提にしている名前）:
  parse_quantity(text) -> QuantityInfo(count_total, count_unit, content_amount, content_dimension,
                                      content_unit, measure_total, confidence, evidence)
  compare(offers, include_terms, exclude_terms, desired_quantity, basis) -> Comparison
    Comparison: basis / basis_label / groups[ComparisonGroup(basis, dimension, offers)] /
                unknown_offers / cheapest_price / cheapest_unit_price / cheapest_total /
                cheapest_for_quantity / caveats / notes
    Offer.unit_price = 表示単位あたり（100mlあたりの円等）、Offer.unit_price_label = 空白なし。

試験していない観点: 価格 None の候補、service/MCP/CLI/Web/regulars/mock_data、sort/pages/
min_price 等、UNITS/DISPLAY/COUNTERS への1行追加で単位が増えること（定数名は契約にあるが
中身の形に依存するため）、複数買い、include と exclude を併用したときの notes の件数の
数え方（適用順が不明）、mAh/Wh の比較（ラベルのみ契約にある）。
"""

from __future__ import annotations

import itertools
import re

import pytest

CAVEAT = "仕様の違い（濃縮・層数・型番・色など）は判定していません。商品名で確認してください。"

_UNSET = object()  # 「このフィールドは試験しない」

# --------------------------------------------------------------------------
# 部品
# --------------------------------------------------------------------------


def _parse(text):
    from shopping.quantity import parse_quantity

    return parse_quantity(text)


def _conf(q):
    c = q.confidence
    return getattr(c, "value", c)


_seq = itertools.count(1)


def _offer(name, price, shipping_status="included", shipping_fee=None, caption=None):
    from shopping.models import Offer
    from shopping.quantity import parse_quantity

    n = next(_seq)
    return Offer(
        mall="rakuten",
        mall_item_code=f"blind:{n}",
        item_name=name,
        price=price,
        item_url=f"https://example.invalid/blind/{n}",
        item_url_status="ok",
        shipping_status=shipping_status,
        shipping_fee=shipping_fee,
        caption=caption,
        quantity=parse_quantity(name),
    )


def _compare(offers, **kw):
    from shopping.pricing import compare

    return compare(offers, **kw)


def _names(offers):
    return [o.item_name for o in offers]


def _grouped(r):
    """グループに入っている全 Offer。"""
    return [o for g in r.groups for o in g.offers]


def _all_names(r):
    return set(_names(_grouped(r))) | set(_names(r.unknown_offers))


def _by_name(r, name):
    for o in _grouped(r) + list(r.unknown_offers):
        if o.item_name == name:
            return o
    raise AssertionError(f"{name!r} が結果に無い。あるのは {sorted(_all_names(r))}")


def _group_of(r, name):
    for g in r.groups:
        if name in _names(g.offers):
            return g
    return None


def _nospace(s):
    return re.sub(r"\s+", "", s or "")


def _assert_up(r, name, expected):
    """Offer.unit_price は表示単位あたり (Q3)。丸める前の値。"""
    o = _by_name(r, name)
    assert o.unit_price == pytest.approx(expected, rel=1e-4), f"{name!r}: {o.unit_price} != {expected}"


def _assert_single_group(r, names, basis, dimension, label):
    assert r.basis == basis
    assert len(r.groups) == 1, [g.basis for g in r.groups]
    g = r.groups[0]
    assert g.basis == basis and g.dimension == dimension
    assert set(names) == set(_names(g.offers))
    for n in names:
        assert _by_name(r, n).unit_price_label == label


# --------------------------------------------------------------------------
# データセット（手計算）
# --------------------------------------------------------------------------

# 洗剤 g。measure = 5400g / 4800g / 2000g。100gあたり = 55.5556 / 75 / 50
D1 = "花王 洗濯洗剤 詰め替え 900g×6袋"
D2 = "ライオン 洗濯洗剤 詰め替え 1.2kg×4袋"
D3 = "洗濯洗剤 本体 2kg×1個"


def _detergents():
    return [_offer(D1, 3000), _offer(D2, 3600), _offer(D3, 1000)]


# 飲料 ml。measure = 18000 / 12000 / 12000。100mlあたり = 11 / 20 / 10
B1 = "天然水 2L×9本"
B2 = "天然水 500ml×24本"
B3 = "ミネラルウォーター 1.5L×8本"


def _beverages():
    return [_offer(B1, 1980), _offer(B2, 2400), _offer(B3, 1200)]


# 電池 個。count = 40 / 40(20×2) / 100。1個あたり = 50 / 45 / 40
T1 = "単3電池 40本"
T2 = "単3形 アルカリ乾電池 20本入り×2パック"
T3 = "単3電池 100本"


def _batteries():
    return [_offer(T1, 2000), _offer(T2, 1800), _offer(T3, 4000)]


# ソーラーパネル W。measure = 200 / 200 / 200。1Wあたり = 100 / 120 / 90
P1 = "ソーラーパネル 100W×2枚"
P2 = "ソーラーパネル 200W 1枚"
P3 = "ソーラーパネル 50W×4枚"


def _panels():
    return [_offer(P1, 20000), _offer(P2, 24000), _offer(P3, 18000)]


# トイレットペーパー: 長さなら 600m/300m/1440m、個なら 12/12/48
R1 = "トイレットペーパー シングル 50m×12ロール"
R2 = "トイレットペーパー ダブル 25m×12ロール"
R3 = "トイレットペーパー ダブル 30m×12ロール×4パック"


def _rolls():
    return [_offer(R1, 600), _offer(R2, 450), _offer(R3, 2400)]


# --------------------------------------------------------------------------
# §7 数量の読み取り
# --------------------------------------------------------------------------

# (text, count_total, count_unit, dimension, content_unit, content_amount, measure_total)
PARSE_CASES = [
    # 900g×6 は 内容量900g・個数6（数字だけの×6）。count_unit は無ければ「個」
    ("花王 洗濯洗剤 詰め替え 900g×6", 6, "個", "mass", "g", 900, 5400),
    ("洗濯洗剤 詰め替え 900g×6袋", 6, "袋", "mass", "g", 900, 5400),
    ("ライオン 洗濯洗剤 詰め替え用 1.2kg×4袋", 4, "袋", "mass", "g", 1200, 4800),
    # 飲料: 2000*9=18000, 500*24=12000, 1500*8=12000, 2000*6=12000
    ("ミネラルウォーター 2L×9本", 9, "本", "volume", "ml", 2000, 18000),
    ("天然水 500ml×24本", 24, "本", "volume", "ml", 500, 12000),
    ("天然水 1.5L×8本", 8, "本", "volume", "ml", 1500, 12000),
    ("お茶 2リットル×6本", 6, "本", "volume", "ml", 2000, 12000),
    ("ジュース 500cc×24本", 24, "本", "volume", "ml", 500, 12000),
    ("炭酸水 2ℓ×6本", 6, "本", "volume", "ml", 2000, 12000),
    ("ミネラルウォーター 500mL×24本", 24, "本", "volume", "ml", 500, 12000),
    # 電池: 「単3」の3は個数ではない。内容量なし (Q13: measure_total=None)
    ("単3電池 40本", 40, "本", None, None, None, None),
    # Q6: 数え語が2段のとき count_unit は内側（1つめ）。20*2=40
    ("単3形 アルカリ乾電池 20本入り×2パック", 40, "本", None, None, None, None),
    # ソーラーパネル: 100*2=200, 200*1=200
    ("ソーラーパネル 100W×2枚", 2, "枚", "power", "W", 100, 200),
    ("ソーラーパネル 200W 1枚", 1, "枚", "power", "W", 200, 200),
    ("ソーラーパネル 100W 2枚セット", 2, _UNSET, "power", "W", 100, 200),
    # モバイルバッテリー: 10000*2
    ("モバイルバッテリー 10000mAh 2個", 2, "個", "charge", "mAh", 10000, 20000),
    # トイレットペーパー: 50m が1ロールの内容量。50*12=600、30*(12*4)=1440
    ("トイレットペーパー シングル 50m×12ロール", 12, "ロール", "length", "m", 50, 600),
    ("トイレットペーパー ダブル 30m×12ロール×4パック", 48, "ロール", "length", "m", 30, 1440),
    ("トイレットペーパー ダブル 12ロール", 12, "ロール", None, None, None, None),  # 層数は読まない
    ("トイレットペーパー 12R×4", 48, _UNSET, None, None, None, None),  # R=ロール、12*4
    ("トイレットペーパー 4パック×12ロール", 48, "パック", None, None, None, None),  # Q6: 内側=1つめ
    ("トイレットペーパー 12ロール×4パック", 48, "ロール", None, None, None, None),
    ("洗剤 3袋入り×2", 6, "袋", None, None, None, None),  # 数字だけの×2は直前の個数に掛ける
    ("ティッシュ 12ロール×6", 72, "ロール", None, None, None, None),
]


@pytest.mark.parametrize(
    "text,count,cunit,dim,unit,amount,measure", PARSE_CASES, ids=[c[0] for c in PARSE_CASES]
)
def test_parse_quantity_expected(text, count, cunit, dim, unit, amount, measure):
    # §7 個数×内容量・基準単位への換算・measure_total = count_total × content_amount
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    if cunit is not _UNSET:
        assert q.count_unit == cunit
    assert q.content_dimension == dim
    assert q.content_unit == unit
    if amount is None:
        assert q.content_amount is None
        assert q.measure_total is None
    else:
        assert q.content_amount == pytest.approx(amount)
        assert q.measure_total == pytest.approx(measure)
    assert isinstance(q.evidence, str) and q.evidence.strip()


# 換算表: (text, dimension, 基準単位, 基準単位での量)
UNIT_CASES = [
    ("商品 750ml", "volume", "ml", 750),
    ("商品 750mL", "volume", "ml", 750),
    ("商品 2L", "volume", "ml", 2000),
    ("商品 1.8ℓ", "volume", "ml", 1800),
    ("商品 1.8リットル", "volume", "ml", 1800),
    ("商品 350cc", "volume", "ml", 350),
    ("商品 250g", "mass", "g", 250),
    ("商品 1.5kg", "mass", "g", 1500),
    ("商品 500mg", "mass", "g", 0.5),
    ("商品 5メートル", "length", "m", 5),
    ("商品 30cm", "length", "m", 0.3),
    ("商品 5mm", "length", "m", 0.005),
    ("商品 2km", "length", "m", 2000),
    ("商品 100W", "power", "W", 100),
    ("商品 100ワット", "power", "W", 100),
    ("商品 1.5kW", "power", "W", 1500),
    ("商品 5000mAh", "charge", "mAh", 5000),
    ("商品 2Ah", "charge", "mAh", 2000),
    ("商品 500Wh", "energy", "Wh", 500),
    ("商品 1.2kWh", "energy", "Wh", 1200),
]


@pytest.mark.parametrize("text,dim,unit,amount", UNIT_CASES, ids=[c[0] for c in UNIT_CASES])
def test_parse_unit_conversion_table(text, dim, unit, amount):
    # §7 換算表。個数は問わず内容量の換算だけ見る
    q = _parse(text)
    assert q.content_dimension == dim
    assert q.content_unit == unit
    assert q.content_amount == pytest.approx(amount)


COUNT_WORDS = [
    "個", "本", "枚", "袋", "箱", "パック", "缶", "ロール", "セット", "組", "足", "着",
    "台", "錠", "包", "粒", "ケース", "玉", "束", "巻", "食", "回分",
]  # fmt: skip


@pytest.mark.parametrize("word", COUNT_WORDS)
def test_parse_count_word_table(word):
    # §7 数え語の表。12<数え語> は総数12・数え語がそのまま count_unit
    q = _parse(f"テスト商品 12{word}")
    assert q.count_total == 12
    assert q.count_unit == word
    assert _conf(q) == "high"


PROMO_CASES = [
    # (text, count_total, content_amount or None)  ※販促・価格表記は数量にしない
    ("洗濯洗剤 詰め替え 900g×6袋 ポイント10倍", 6, 900),
    ("単3電池 40本 最大50%OFF", 40, None),
    ("ミネラルウォーター 2L×9本 送料無料 1000円ポッキリ", 9, 2000),
    ("洗濯洗剤 900g×6袋 ポイント10倍 最大50%OFF 送料無料 1000円ポッキリ", 6, 900),
    # 「24ロール分」「〜相当」「〜あたり」は換算の説明で数えない（矛盾=lowにもならない）
    ("トイレットペーパー 12ロール(24ロール分) ダブル", 12, None),
    ("トイレットペーパー 12ロール 24ロール分相当", 12, None),
    ("ミネラルウォーター 2L×6本 12本相当", 6, 2000),
    ("洗濯洗剤 詰め替え 900g×6袋 100gあたり29円", 6, 900),
    ("天然水 500ml×24本 1本あたり50円", 24, 500),
]


@pytest.mark.parametrize("text,count,amount", PROMO_CASES, ids=[c[0] for c in PROMO_CASES])
def test_parse_ignores_promo_and_explanatory_numbers(text, count, amount):
    q = _parse(text)
    assert _conf(q) == "high"
    assert q.count_total == count
    if amount is not None:
        assert q.content_amount == pytest.approx(amount)


@pytest.mark.parametrize(
    "text",
    ["ポイント10倍 最大50%OFF 送料無料 1000円ポッキリ", "おすすめ洗剤 ポイント10倍", "", "ギフト券"],
)
def test_parse_unreadable_is_none(text):
    # §7 / Q5: 数え語も内容量も無い → none
    q = _parse(text)
    assert _conf(q) == "none"
    assert q.count_total is None
    assert q.measure_total is None


@pytest.mark.parametrize(
    "text,amount,unit,dim",
    [
        ("ミネラルウォーター 2L", 2000, "ml", "volume"),
        ("洗濯洗剤 詰め替え 900g", 900, "g", "mass"),
        ("ソーラーパネル 100W", 100, "W", "power"),
    ],
)
def test_parse_content_only_means_single_piece(text, amount, unit, dim):
    # Q5: 数え語が無く内容量だけある → count_total=1, count_unit="個", high
    q = _parse(text)
    assert _conf(q) == "high"
    assert q.count_total == 1
    assert q.count_unit == "個"
    assert q.content_dimension == dim and q.content_unit == unit
    assert q.measure_total == pytest.approx(amount)


CONFLICT_CASES = [
    "飲料 500ml 2L ×6本",  # 同じ次元(体積)で値が違う内容量（×でつながない並記）
    "洗濯洗剤 詰め替え 900g 1000g ×3袋",
    "単3電池 40本 48本",  # 総数が食い違う個数表記
    "トイレットペーパー 12ロール 18ロール",
]


@pytest.mark.parametrize("text", CONFLICT_CASES)
def test_parse_conflict_is_low_and_nulls(text):
    # §7 矛盾 → low、総数・内容量を null。Q14: content_dimension・content_unit も None
    q = _parse(text)
    assert _conf(q) == "low"
    assert q.count_total is None
    assert q.content_amount is None
    assert q.measure_total is None
    assert q.content_dimension is None
    assert q.content_unit is None


@pytest.mark.parametrize(
    "text,count,amount",
    [
        ("天然水 2L(2000ml)×6本", 6, 2000),  # 同じ量の別単位表記は矛盾ではない
        ("洗濯洗剤 詰め替え 900g(0.9kg)×6袋", 6, 900),
    ],
)
def test_parse_same_value_in_other_unit_is_not_conflict(text, count, amount):
    q = _parse(text)
    assert _conf(q) == "high"
    assert q.count_total == count
    assert q.content_amount == pytest.approx(amount)


@pytest.mark.parametrize(
    "text,count,amount_m,measure_m",
    [
        # Q15: 同じ次元の値が × でつながる寸法表記 → 矛盾でなく寸法、大きい方が内容量
        ("ラップ 30cm×50m", 1, 50, 50),
        ("アルミホイル 幅45cm×長さ100m", 1, 100, 100),
        ("養生テープ 48mm×25m 5巻", 5, 25, 125),
        ("ラップ 30cm×50m×3本", 3, 50, 150),
        # 数え語の付かない裸の数 (34) は個数にしない。大きい方 85cm = 0.85m
        ("ふきん 34×85cm", 1, 0.85, 0.85),
    ],
)
def test_parse_dimension_notation_takes_larger(text, count, amount_m, measure_m):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.content_dimension == "length" and q.content_unit == "m"
    assert q.content_amount == pytest.approx(amount_m)
    assert q.count_total == count
    assert q.measure_total == pytest.approx(measure_m)


@pytest.mark.parametrize(
    "text",
    [
        "洗濯洗剤 詰め替え ９００ｇ×６袋",  # Q16 全角数字・全角英字 (NFKC)
        "洗濯洗剤 詰め替え 900g x 6袋",
        "洗濯洗剤 詰め替え 900gX6袋",
        "洗濯洗剤 詰め替え 900g*6袋",
        "洗濯洗剤 詰め替え 900g×6袋",
    ],
)
def test_parse_normalizes_width_and_multiplication_sign(text):
    q = _parse(text)
    assert _conf(q) == "high"
    assert q.count_total == 6
    assert q.count_unit == "袋"
    assert q.content_amount == pytest.approx(900)
    assert q.measure_total == pytest.approx(5400)


def test_parse_result_has_all_section7_fields():
    q = _parse("ミネラルウォーター 2L×9本")
    for name in (
        "count_total", "count_unit", "content_amount", "content_dimension",
        "content_unit", "measure_total", "confidence", "evidence",
    ):  # fmt: skip
        assert hasattr(q, name), name


# --------------------------------------------------------------------------
# §8 価格比較: 基準単位・グループ・単位価格
# --------------------------------------------------------------------------


def test_compare_result_shape_and_empty_input():
    # Q1: Comparison の名前
    r = _compare([])
    for name in (
        "basis", "basis_label", "groups", "unknown_offers", "cheapest_price",
        "cheapest_unit_price", "cheapest_total", "cheapest_for_quantity", "caveats", "notes",
    ):  # fmt: skip
        assert hasattr(r, name), name
    assert list(r.groups) == [] and list(r.unknown_offers) == []
    assert r.cheapest_price is None and r.cheapest_unit_price is None


def test_compare_mass_auto_basis_groups_sizes_together():
    # §8 過半が同じ次元(mass) → g。サイズ違い・入り数違いはグループを分けない
    r = _compare(_detergents())
    _assert_single_group(r, (D1, D2, D3), "g", "mass", "100gあたり")
    assert r.basis_label == "100gあたり"
    # 3000/5400*100=55.5556, 3600/4800*100=75, 1000/2000*100=50
    _assert_up(r, D1, 3000 / 5400 * 100)
    _assert_up(r, D2, 75)
    _assert_up(r, D3, 50)
    # Q1: グループ内は単位価格の安い順
    assert _names(r.groups[0].offers) == [D3, D1, D2]


def test_compare_volume_auto_basis():
    # 1980/18000*100=11, 2400/12000*100=20, 1200/12000*100=10
    r = _compare(_beverages())
    _assert_single_group(r, (B1, B2, B3), "ml", "volume", "100mlあたり")
    assert r.basis_label == "100mlあたり"
    _assert_up(r, B1, 11)
    _assert_up(r, B2, 20)
    _assert_up(r, B3, 10)
    assert _names(r.groups[0].offers) == [B3, B1, B2]


def test_compare_count_only_auto_basis_is_piece():
    # §8 内容量の次元が無ければ「個」(Q4, Q9)。2000/40=50, 1800/40=45, 4000/100=40
    r = _compare(_batteries())
    _assert_single_group(r, (T1, T2, T3), "個", "count", "1個あたり")
    assert r.basis_label == "1個あたり"
    _assert_up(r, T1, 50)
    _assert_up(r, T2, 45)
    _assert_up(r, T3, 40)
    assert _names(r.groups[0].offers) == [T3, T2, T1]


def test_compare_power_auto_basis():
    # 20000/200=100, 24000/200=120, 18000/200=90
    r = _compare(_panels())
    _assert_single_group(r, (P1, P2, P3), "W", "power", "1Wあたり")
    _assert_up(r, P1, 100)
    _assert_up(r, P2, 120)
    _assert_up(r, P3, 90)


def test_compare_length_auto_basis():
    # 600/600=1.0, 450/300=1.5, 2400/1440=1.6667
    r = _compare(_rolls())
    _assert_single_group(r, (R1, R2, R3), "m", "length", "1mあたり")
    _assert_up(r, R1, 1.0)
    _assert_up(r, R2, 1.5)
    _assert_up(r, R3, 2400 / 1440)


def test_compare_explicit_piece_basis_overrides_dimension():
    # basis="個": 600/12=50, 450/12=37.5, 2400/48=50
    r = _compare(_rolls(), basis="個")
    _assert_single_group(r, (R1, R2, R3), "個", "count", "1個あたり")
    _assert_up(r, R1, 50)
    _assert_up(r, R2, 37.5)
    _assert_up(r, R3, 50)


@pytest.mark.parametrize(
    "alias,canonical,offers_fn,names,label",
    [
        ("L", "ml", _beverages, (B1, B2, B3), "100mlあたり"),
        ("kg", "g", _detergents, (D1, D2, D3), "100gあたり"),
        ("ml", "ml", _beverages, (B1, B2, B3), "100mlあたり"),
        ("g", "g", _detergents, (D1, D2, D3), "100gあたり"),
    ],
)
def test_compare_explicit_basis_alias_is_normalized(alias, canonical, offers_fn, names, label):
    # §8 L・kg の別名は基準単位に正規化 (Q1: r.basis は正規化後)
    r = _compare(offers_fn(), basis=alias)
    dim = "volume" if canonical == "ml" else "mass"
    _assert_single_group(r, names, canonical, dim, label)


def test_compare_dimension_mismatch_goes_to_unknown_auto():
    # §8 過半(high 4件中3件が mass) → g。体積の商品は g の量が読めない = 単価不明 (Q8)
    liquid = "洗濯洗剤 液体 800ml×2本"
    r = _compare(_detergents() + [_offer(liquid, 700)])
    assert r.basis == "g"
    assert set(_names(r.groups[0].offers)) == {D1, D2, D3}
    assert _names(r.unknown_offers) == [liquid]
    assert _by_name(r, liquid).unit_price is None
    assert _group_of(r, liquid) is None
    # Q8: 件数が caveats に
    assert any("単価を出せない候補: 1件" in c for c in r.caveats), r.caveats


def test_compare_explicit_basis_ml_flips_which_group_is_unknown():
    # 同じデータで basis="ml" → 液体だけが単価を持ち、g の商品は単価不明
    liquid = "洗濯洗剤 液体 800ml×2本"
    r = _compare(_detergents() + [_offer(liquid, 700)], basis="ml")
    assert r.basis == "ml"
    assert _names(r.groups[0].offers) == [liquid]
    assert r.groups[0].dimension == "volume"
    _assert_up(r, liquid, 700 / 1600 * 100)  # 43.75
    assert set(_names(r.unknown_offers)) == {D1, D2, D3}
    assert all(o.unit_price is None for o in r.unknown_offers)
    assert any("単価を出せない候補: 3件" in c for c in r.caveats), r.caveats


def test_compare_basis_with_no_readable_quantity_all_unknown():
    r = _compare(_detergents(), basis="ml")
    assert r.groups == [] or all(not g.offers for g in r.groups)
    assert set(_names(r.unknown_offers)) == {D1, D2, D3}
    assert r.cheapest_unit_price is None


def test_compare_unreadable_and_low_confidence_are_unknown():
    # §7/§8 単価計算に使うのは high のみ。件数 2 が caveats に
    none_name = "洗濯洗剤 詰め替え おすすめ"
    low_name = "洗濯洗剤 900g 1000g ×3袋"
    r = _compare(_detergents() + [_offer(none_name, 100), _offer(low_name, 100)])
    assert r.basis == "g"
    assert set(_names(r.unknown_offers)) == {none_name, low_name}
    assert set(_names(r.groups[0].offers)) == {D1, D2, D3}
    assert _by_name(r, none_name).unit_price is None
    assert _by_name(r, low_name).unit_price is None
    assert any("単価を出せない候補: 2件" in c for c in r.caveats), r.caveats


def test_compare_no_unknown_no_unknown_caveat():
    r = _compare(_detergents())
    assert list(r.unknown_offers) == []
    assert not any("単価を出せない候補" in c for c in r.caveats)


def test_compare_minority_dimension_falls_back_to_piece():
    # Q7: high の過半が同次元でなければ「個」: 電池2件(内容量なし)+洗剤1件 → 個
    # 洗剤は count 6 なので個基準で 3000/6=500
    det = "洗濯洗剤 詰め替え 900g×6袋"
    r = _compare([_offer(T1, 2000), _offer(T3, 4000), _offer(det, 3000)])
    _assert_single_group(r, (T1, T3, det), "個", "count", "1個あたり")
    _assert_up(r, det, 500)
    _assert_up(r, T1, 50)


def test_compare_exactly_half_is_piece():
    # Q7: ちょうど半数は「個」。洗剤(g)1件・水(ml)1件。個基準で 3000/6=500, 2400/24=100
    a = "洗濯洗剤 詰め替え 900g×6袋"
    b = "天然水 500ml×24本"
    r = _compare([_offer(a, 3000), _offer(b, 2400)])
    _assert_single_group(r, (a, b), "個", "count", "1個あたり")
    _assert_up(r, a, 500)
    _assert_up(r, b, 100)


def test_compare_majority_denominator_is_high_candidates_only():
    # Q7: 分母は high の候補。high 3件中 mass 2件(>半数) → g。low/読めない 3件は分母に入れない
    liquid = "洗濯洗剤 液体 800ml×2本"
    low = "洗濯洗剤 900g 1000g ×3袋"
    noq1, noq2 = "洗濯洗剤 おすすめ", "洗濯洗剤 人気"
    r = _compare(
        [_offer(D1, 3000), _offer(D3, 1000), _offer(liquid, 700), _offer(low, 100),
         _offer(noq1, 100), _offer(noq2, 100)]
    )  # fmt: skip
    assert r.basis == "g"
    assert set(_names(r.groups[0].offers)) == {D1, D3}
    assert set(_names(r.unknown_offers)) == {liquid, low, noq1, noq2}


def test_compare_offer_carries_quantity_and_label():
    # インターフェース: 各候補に quantity（新項目）と unit_price・unit_price_label
    r = _compare(_detergents())
    o = _by_name(r, D1)
    assert o.unit_price_label == "100gあたり"
    assert o.quantity.count_total == 6
    assert o.quantity.content_dimension == "mass"
    assert o.quantity.measure_total == pytest.approx(5400)
    assert _conf(o.quantity) == "high"


def test_compare_uses_prefilled_quantity_when_present():
    # Q0: Offer.quantity が入っていればそれを使う（item_name の文面と違っても quantity が正）
    o = _offer("洗濯洗剤 詰め替え 900g×6袋", 3000)
    o.quantity = _parse("洗濯洗剤 詰め替え 1kg×3袋")  # 1000g*3=3000g → 100gあたり 100円
    r = _compare([o])
    assert _by_name(r, o.item_name).unit_price == pytest.approx(100, rel=1e-4)


def test_compare_parses_item_name_when_quantity_missing():
    # Q0: quantity が無ければ parse_quantity(item_name) で読む。3000/5400*100
    o = _offer("洗濯洗剤 詰め替え 900g×6袋", 3000)
    o.quantity = None
    r = _compare([o])
    assert _by_name(r, o.item_name).unit_price == pytest.approx(3000 / 5400 * 100, rel=1e-4)


# --------------------------------------------------------------------------
# §8 include / exclude / caveats / notes
# --------------------------------------------------------------------------

N1 = "洗濯洗剤 詰め替え 900g×6袋"
N2 = "洗濯洗剤 本体 900g×6本"
N3 = "洗濯洗剤 濃縮 詰め替え 900g×6袋"
N4 = "洗濯洗剤 業務用 4kg×2個"
N5 = "洗濯洗剤 詰め替え 1.2kg×4袋"
N6 = "柔軟剤 詰め替え 900g×6袋"


def _filter_offers():
    return [
        _offer(N1, 3000), _offer(N2, 3300), _offer(N3, 3600),
        _offer(N4, 4000), _offer(N5, 3600), _offer(N6, 3100),
    ]  # fmt: skip


def test_include_terms_requires_all_terms_in_name():
    # §8 include_terms: 全部を商品名に含むものだけ残す。N1,N3,N5 が両方を含む
    r = _compare(_filter_offers(), include_terms=["洗濯洗剤", "詰め替え"])
    assert _all_names(r) == {N1, N3, N5}


def test_exclude_terms_drops_if_any_term_in_name():
    # §8 exclude_terms: どれかを含むものは外す。N2(本体) N3(濃縮) N4(業務用) が外れる
    r = _compare(_filter_offers(), exclude_terms=["本体", "濃縮", "業務用"])
    assert _all_names(r) == {N1, N5, N6}


def test_include_and_exclude_combined():
    r = _compare(_filter_offers(), include_terms=["洗濯洗剤", "詰め替え"], exclude_terms=["濃縮"])
    assert _all_names(r) == {N1, N5}


def test_no_terms_keeps_everything_and_no_exclusion_notes():
    r = _compare(_filter_offers())
    assert _all_names(r) == {N1, N2, N3, N4, N5, N6}
    assert not any("除外" in n for n in r.notes)


def test_filter_terms_are_judged_on_item_name_only():
    # §8 「商品名に含む」。キャプションだけにある語では残らない・外れない
    a = _offer("洗濯洗剤 900g×6袋", 3000, caption="詰め替え用 濃縮")
    b = _offer("洗濯洗剤 詰め替え 900g×6袋", 3000)
    assert _all_names(_compare([a, b], include_terms=["詰め替え"])) == {b.item_name}
    assert _all_names(_compare([a, b], exclude_terms=["濃縮"])) == {a.item_name, b.item_name}


def test_exclude_count_in_notes_exact_format():
    # Q12: 「除く語で除外: N件」。3件外す
    r = _compare(_filter_offers(), exclude_terms=["本体", "濃縮", "業務用"])
    assert "除く語で除外: 3件" in r.notes
    assert not any(n.startswith("含む語で除外") for n in r.notes)  # 0件なら出さない


def test_include_count_in_notes_exact_format():
    # Q12: 「含む語で除外: N件」。N2,N4,N6 の3件が「洗濯洗剤」「詰め替え」を満たさない
    r = _compare(_filter_offers(), include_terms=["洗濯洗剤", "詰め替え"])
    assert "含む語で除外: 3件" in r.notes
    assert not any(n.startswith("除く語で除外") for n in r.notes)


def _has_caveat(r):
    return any(_nospace(CAVEAT) in _nospace(c) for c in r.caveats)


@pytest.mark.parametrize(
    "case",
    ["detergents", "batteries", "empty", "all_excluded", "explicit_basis", "unreadable_only"],
)
def test_standing_caveat_always_present(case):
    # §8 caveats に常に1行
    if case == "detergents":
        r = _compare(_detergents())
    elif case == "batteries":
        r = _compare(_batteries())
    elif case == "empty":
        r = _compare([])
    elif case == "all_excluded":
        r = _compare(_detergents(), exclude_terms=["洗濯洗剤"])
    elif case == "explicit_basis":
        r = _compare(_beverages(), basis="L")
    else:
        r = _compare([_offer("ポイント10倍 送料無料", 100)])
    assert _has_caveat(r)


# --------------------------------------------------------------------------
# §8 4種類の最安 (Q1/Q2/Q10/Q11)
# --------------------------------------------------------------------------


def test_cheapest_price_and_unit_price_are_distinct_kinds():
    # 商品単価(価格)最安は D3 (1000円)、単位価格最安も D3 (50/100g)。
    r = _compare(_detergents())
    assert r.cheapest_price.item_name == D3
    assert r.cheapest_unit_price.item_name == D3
    # 飲料: 価格最安 B3 (1200) 、単位価格最安 B3 (10)。B1 が 1980 で2番手
    r2 = _compare(_beverages())
    assert r2.cheapest_price.item_name == B3 and r2.cheapest_unit_price.item_name == B3
    # 電池: 価格最安 T2 (1800)、単位価格最安 T3 (40/個) → 別物
    r3 = _compare(_batteries())
    assert r3.cheapest_price.item_name == T2
    assert r3.cheapest_unit_price.item_name == T3


def test_unit_price_cheapest_compares_unrounded_values():
    # §8 単価は丸める前の値で比較。A=1000/3000*100=33.3333, B=3333/10000*100=33.3300
    # 2桁に丸めると同点 33.33 → 先に並べた A が勝ってしまう。生の値なら B が最安
    a = "洗濯洗剤 業務用 3kg×1袋"
    b = "洗濯洗剤 業務用 10kg×1袋"
    r = _compare([_offer(a, 1000), _offer(b, 3333)])
    assert r.cheapest_unit_price.item_name == b
    assert _names(r.groups[0].offers)[0] == b


def test_unit_price_cheapest_ignores_unknown_and_low():
    # §8 単価不明・low は最安判定から外す（安い値段でも）。最安は D3
    r = _compare(
        _detergents()
        + [_offer("洗濯洗剤 詰め替え おすすめ", 1), _offer("洗濯洗剤 900g 1000g ×3袋", 10)]
    )
    assert r.cheapest_unit_price.item_name == D3


def test_desired_quantity_in_basis_unit_ml():
    # Q10: basis=ml, desired=10000ml。w1 18000ml(1980円) w3 12000ml(1200円) は満たす、
    # w2 6000ml(700円) は満たさない。満たすもののうち価格最小は w3。全体の価格最安 w2 ではない
    w1 = "天然水 2L×9本"
    w2 = "天然水 500ml×12本"
    w3 = "ミネラルウォーター 1.5L×8本"
    offers = [_offer(w1, 1980), _offer(w2, 700), _offer(w3, 1200)]
    r = _compare(offers, basis="ml", desired_quantity=10000)
    assert r.cheapest_for_quantity.item_name == w3
    assert r.cheapest_price.item_name == w2


def test_desired_quantity_alias_basis_is_interpreted_in_base_unit():
    # Q10: basis="L" でも desired は基準単位 ml で解釈 (10000 = 10L)。結果は上と同じ
    w1 = "天然水 2L×9本"
    w2 = "天然水 500ml×12本"
    w3 = "ミネラルウォーター 1.5L×8本"
    r = _compare([_offer(w1, 1980), _offer(w2, 700), _offer(w3, 1200)], basis="L", desired_quantity=10000)
    assert r.basis == "ml"
    assert r.cheapest_for_quantity.item_name == w3


def test_desired_quantity_picks_lowest_price_not_lowest_unit_price():
    # Q10: 価格(price)が最小のもの。q1 12000ml 1000円(8.33/100ml) と q2 10000ml 900円(9.0/100ml)
    # desired=10000 → 両方満たす。価格最小は q2、単位価格最小は q1
    q1 = "天然水 2L×6本"
    q2 = "天然水 1L×10本"
    r = _compare([_offer(q1, 1000), _offer(q2, 900)], desired_quantity=10000)
    assert r.basis == "ml"
    assert r.cheapest_for_quantity.item_name == q2
    assert r.cheapest_unit_price.item_name == q1


def test_desired_quantity_in_piece_basis_and_unreachable():
    # basis=個, desired=100 → 100本以上は T3(4000円) のみ。複数買いは考えない
    r = _compare(_batteries(), basis="個", desired_quantity=100)
    assert r.cheapest_for_quantity.item_name == T3
    # 満たすものが無ければ None、desired 未指定でも None
    assert _compare(_batteries(), basis="個", desired_quantity=1000).cheapest_for_quantity is None
    assert _compare(_batteries()).cheapest_for_quantity is None


def test_desired_quantity_excludes_unknown_quantity():
    # basis の量が読めない候補は満たす判定に入れない（安くても）
    unk = "洗濯洗剤 おすすめ"
    r = _compare(_detergents() + [_offer(unk, 1)], desired_quantity=1000)  # g: D3(2000g) など
    assert r.cheapest_for_quantity.item_name == D3
    assert r.cheapest_for_quantity.item_name != unk


def test_total_cheapest_known_shipping_includes_fee():
    # §8 支払総額 = 価格+送料。X: 1000+800=1800 (別途)、Y: 1500 (込み)。
    # 同じ 12000ml なので 単位価格最安・価格最安は X、総額最安は Y
    x = "天然水 2L×6本 送料別"
    y = "天然水 2L×6本 送料込"
    r = _compare(
        [
            _offer(x, 1000, shipping_status="separate", shipping_fee=800),
            _offer(y, 1500, shipping_status="included"),
        ]
    )
    assert r.cheapest_unit_price.item_name == x
    assert r.cheapest_price.item_name == x
    assert r.cheapest_total.item_name == y


def test_total_cheapest_not_asserted_when_shipping_unknown():
    # Q11: 送料不明の候補があれば cheapest_total=None、caveats に「送料」
    r = _compare(
        [_offer(B1, 1980, shipping_status="unknown"), _offer(B3, 1200, shipping_status="unknown")]
    )
    assert r.cheapest_total is None
    assert any("送料" in c for c in r.caveats), r.caveats
    assert r.cheapest_price.item_name == B3  # 他の3種は出す


def test_total_cheapest_not_asserted_when_any_candidate_unknown_shipping():
    # Q11: 1件でも送料不明の候補があれば断定しない
    r = _compare(
        [
            _offer(B1, 1980, shipping_status="included"),
            _offer(B3, 1200, shipping_status="unknown"),
        ]
    )
    assert r.cheapest_total is None
    assert any("送料" in c for c in r.caveats)


def test_no_shipping_caveat_when_all_shipping_known():
    r = _compare([_offer(B1, 1980, shipping_status="included"), _offer(B3, 1200, shipping_status="included")])
    assert r.cheapest_total.item_name == B3
    assert not any("送料" in c for c in r.caveats if _nospace(CAVEAT) not in _nospace(c))


# --------------------------------------------------------------------------
# 試験部品の自己検査（実装に依存しない。今も通る）
# --------------------------------------------------------------------------


class TestHelpersSelfCheck:
    def test_nospace_and_caveat_matching(self):
        assert _nospace("100 ml あたり") == "100mlあたり"
        assert _nospace(CAVEAT) in _nospace("  " + CAVEAT + " ")

    def test_offer_helper_prefilled_fields(self):
        from shopping.models import Offer  # 現行の Offer 定義 (フィールド名) だけに依存

        o = _offer("テスト 12個", 100, shipping_status="separate", shipping_fee=50)
        assert isinstance(o, Offer)
        assert o.item_name == "テスト 12個" and o.price == 100
        assert o.shipping_status == "separate" and o.shipping_fee == 50
        assert o.mall_item_code.startswith("blind:")
        assert _offer("テスト 12個", 100).mall_item_code != o.mall_item_code

    def test_group_helpers_on_fake_result(self):
        class G:
            def __init__(self, offers):
                self.offers = offers

        class O:
            def __init__(self, name, up):
                self.item_name, self.unit_price = name, up

        class R:
            groups = [G([O("a", 1.0), O("b", 2.0)])]
            unknown_offers = [O("u", None)]

        r = R()
        assert _all_names(r) == {"a", "b", "u"}
        assert _group_of(r, "b") is r.groups[0]
        assert _group_of(r, "u") is None
        _assert_up(r, "b", 2.0)
        with pytest.raises(AssertionError):
            _assert_up(r, "b", 3.0)
        with pytest.raises(AssertionError):
            _by_name(r, "zzz")

    def test_expected_numbers_by_hand(self):
        # データセットの手計算が表の数値と一致すること（算術のみ）
        assert 3000 / 5400 * 100 == pytest.approx(55.5556, rel=1e-5)
        assert 1000 / 3000 * 100 == pytest.approx(33.3333, rel=1e-5)
        assert round(1000 / 3000 * 100, 2) == round(3333 / 10000 * 100, 2)  # 丸めると同点
        assert 3333 / 10000 < 1000 / 3000  # 生の値では B が安い


# ==========================================================================
# WP4-0 追記: plans/WP4_quantity_hardening.md の S1〜S11（上の既存試験は変えない）
# 新しい Q（未確定）:
#   W1 S4 「コピー用紙 500枚 5冊」「鉛筆 12本入り 2ダース」の期待値が一意に決まらない
#      （総数 2500 か 5 か low か）。→ 「500 や 12 だけを high で返さない」弱い形だけ固定。
#   W2 S4 の P/pc/pcs/ダース の count_unit が元の綴りか「個」か → count_total だけ固定。
#   W3 S8(UTF-8 128バイトの Gate/アダプタ共通関数)・S9(一覧での含む語/除く語)・S10(指数表記を
#      使わない表示・単価の小数桁)は関数名/画面の形が契約に無く、ここでは試験しない（implementer
#      の自作試験で固定する）。
#   W4 S11 「import 時に例外」は表を壊して再 import しないと確かめられない → 静的な整合
#      (UNITS の全次元が DISPLAY にある・NFKC 後に重複キーが無い)だけ固定。
#   W5 S7 数字で終わる語の「後ろ」判定は数字のみ試験（小数点は試験しない）。
# ==========================================================================

# --- S1 〜分は個数に数えない --------------------------------------------------

S1_WITH_MEASURE = [
    # (text, count_total, dimension, unit, content, measure)
    ("プロテイン 1kg 約33回分", 1, "mass", "g", 1000, 1000),
    ("洗剤 900g 約50回分", 1, "mass", "g", 900, 900),
    ("サプリ 150g 60日分", 1, "mass", "g", 150, 150),
    ("酵素ドリンク 500ml 30杯分", 1, "volume", "ml", 500, 500),
    ("粉ミルク 800g 20食分", 1, "mass", "g", 800, 800),
    ("洗濯洗剤 詰め替え 900g×6袋 約50回分", 6, "mass", "g", 900, 5400),
]


@pytest.mark.parametrize(
    "text,count,dim,unit,amount,measure", S1_WITH_MEASURE, ids=[c[0] for c in S1_WITH_MEASURE]
)
def test_s1_bunn_is_not_counted_when_measure_exists(text, count, dim, unit, amount, measure):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    assert q.content_dimension == dim and q.content_unit == unit
    assert q.content_amount == pytest.approx(amount)
    assert q.measure_total == pytest.approx(measure)


def test_s1_kaibun_alone_counts_as_pieces():
    # S1: 計量値が1つも無く「〜回分」だけ → 個数として数える
    q = _parse("ジェルボール 30回分")
    assert _conf(q) == "high"
    assert q.count_total == 30
    assert q.content_amount is None and q.measure_total is None


def test_s1_protein_compare_cheapest_is_2kg():
    # 回分を個数に数えていた旧挙動では最安が狂う。100gあたり:
    # 1kg 3500/1000*100=350, 2kg 6000/2000*100=300, 3kg 9900/3000*100=330, 500g 2000/500*100=400
    p1 = "プロテイン 1kg 約33回分"
    p2 = "プロテイン 2kg 約66回分"
    p3 = "プロテイン 3kg 約100回分"
    p4 = "プロテイン 500g 約16回分"
    r = _compare([_offer(p1, 3500), _offer(p2, 6000), _offer(p3, 9900), _offer(p4, 2000)])
    _assert_single_group(r, (p1, p2, p3, p4), "g", "mass", "100gあたり")
    _assert_up(r, p1, 350)
    _assert_up(r, p2, 300)
    _assert_up(r, p3, 330)
    _assert_up(r, p4, 400)
    assert r.cheapest_unit_price.item_name == p2
    assert _names(r.groups[0].offers) == [p2, p3, p1, p4]


# --- S2 二重に掛けない --------------------------------------------------------

S2_CASES = [
    # (text, count_total, count_unit, content_amount, measure_total)
    ("水 24本 (500ml×24)", 24, "本", 500, 12000),
    ("水 24本（500ml×24）", 24, "本", 500, 12000),
    ("水 24本 【500ml×24】", 24, "本", 500, 12000),
    ("米 2袋 (5kg×2)", 2, "袋", 5000, 10000),
    ("洗剤 6袋 900g×6", 6, "袋", 900, 5400),
]


@pytest.mark.parametrize("text,count,cunit,amount,measure", S2_CASES, ids=[c[0] for c in S2_CASES])
def test_s2_restated_breakdown_is_not_multiplied_twice(text, count, cunit, amount, measure):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    assert q.count_unit == cunit
    assert q.content_amount == pytest.approx(amount)
    assert q.measure_total == pytest.approx(measure)


def test_s2_restated_and_plain_offers_have_equal_unit_price():
    # 2400円/12000ml*100 = 20 が言い直しの有無によらず同じ
    a, b = "水 24本 (500ml×24)", "水 500ml×24本"
    r = _compare([_offer(a, 2400), _offer(b, 2400)])
    _assert_up(r, a, 20)
    _assert_up(r, b, 20)


# --- S3 総量併記 --------------------------------------------------------------

S3_CASES = [
    # 大きい方 = 小さい方 × 個数 → 総量併記（矛盾ではない）
    ("米 10kg (5kg×2袋)", 2, "袋", 5000, 10000),
    ("米 5kg×2袋 計10kg", 2, "袋", 5000, 10000),
    ("ソーラーパネル 200W×2枚 計400W", 2, "枚", 200, 400),
    ("ドッグフード 7.5kg(2.5kg×3袋)", 3, "袋", 2500, 7500),
]


@pytest.mark.parametrize("text,count,cunit,amount,measure", S3_CASES, ids=[c[0] for c in S3_CASES])
def test_s3_total_alongside_breakdown_is_not_a_conflict(text, count, cunit, amount, measure):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    assert q.count_unit == cunit
    assert q.content_amount == pytest.approx(amount)
    assert q.measure_total == pytest.approx(measure)


@pytest.mark.parametrize(
    "text",
    [
        "米 12kg (5kg×2袋)",  # 5*2=10 != 12
        "ソーラーパネル 200W×2枚 計500W",  # 200*2=400 != 500
        "ドッグフード 8kg(2.5kg×3袋)",  # 7.5 != 8
    ],
)
def test_s3_mismatching_total_is_still_low(text):
    q = _parse(text)
    assert _conf(q) == "low", text
    assert q.count_total is None and q.content_amount is None and q.measure_total is None


def test_s3_rice_compare_unit_price():
    # 4000/10000*100=40, 2200/5000*100=44
    a, b = "米 10kg (5kg×2袋)", "米 5kg×1袋"
    r = _compare([_offer(a, 4000), _offer(b, 2200)])
    _assert_up(r, a, 40)
    _assert_up(r, b, 44)
    assert r.cheapest_unit_price.item_name == a


# --- S4 数え語の追加と未知の数え語 ---------------------------------------------

S4_CASES = [
    # (text, count_total, count_unit or _UNSET)
    ("トイレットペーパー 12ロール×4P", 48, "ロール"),
    ("ティッシュ 5箱×12P", 60, "箱"),
    ("単3電池 8本入×3P", 24, "本"),
    ("ボールペン 2pcs", 2, "個"),
    ("ボールペン 3pc", 3, "個"),
    ("ティッシュ 12P", 12, "パック"),
    ("鉛筆 2ダース", 24, "個"),  # ダース=12倍
    ("鉛筆 1ダース", 12, "個"),
    ("ノート 5冊", 5, "冊"),
    ("靴下 3ペア", 3, "ペア"),
    ("ケーキ 6ヶ", 6, "個"),
    ("ギフト 5点", 5, "点"),
]


@pytest.mark.parametrize("text,count,cunit", S4_CASES, ids=[c[0] for c in S4_CASES])
def test_s4_new_counters(text, count, cunit):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    if cunit is not _UNSET:
        assert q.count_unit == cunit


@pytest.mark.parametrize(
    "text",
    [
        "洗濯洗剤 900g×6ブロック",  # ×の後の未知の数え語
        "石鹸 4ブロック×6個",  # ×の前
        "石鹸 6ブロック入り×4",  # 入数の直後
    ],
)
def test_s4_unknown_counter_in_count_position_is_low(text):
    q = _parse(text)
    assert _conf(q) == "low", text
    assert q.count_total is None and q.measure_total is None


@pytest.mark.parametrize(
    "text,count,cunit",
    [
        # W1 確定: ×の無い2段の数え語「N<a>(入り) M<b>」は N×M、count_unit は内側
        ("コピー用紙 500枚 5冊", 2500, "枚"),  # 500*5
        ("単3電池 4本入 3パック", 12, "本"),  # 4*3
        ("鉛筆 12本入り 2ダース", 24, "本"),  # 内側の個数があるとき、ダースは袋数と同じ扱い 12*2
        ("鉛筆 2ダース", 24, "個"),  # 単独のダースは12倍。内側の語が無いので「個」
    ],
)
def test_w1_two_stage_counters_without_times_sign(text, count, cunit):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    assert q.count_unit == cunit


# --- S5 明示 basis は複数次元の中からその次元を使う --------------------------------


def test_s5_parse_keeps_first_dimension():
    q = _parse("モバイルバッテリー 22.5W 10000mAh")
    assert q.content_dimension == "power"
    assert q.content_amount == pytest.approx(22.5)


def test_s5_explicit_basis_uses_that_dimension():
    # basis=mAh: 3000/10000=0.3、5000/20000=0.25 → 2番目が最安。ラベルは 1mAhあたり
    a, b = "モバイルバッテリー 20W 10000mAh", "モバイルバッテリー 30W 20000mAh"
    r = _compare([_offer(a, 3000), _offer(b, 5000)], basis="mAh")
    _assert_single_group(r, (a, b), "mAh", "charge", "1mAhあたり")
    _assert_up(r, a, 0.3)
    _assert_up(r, b, 0.25)
    assert r.cheapest_unit_price.item_name == b


def test_s5_auto_basis_keeps_first_dimension():
    # 自動判定は従来どおり先頭の次元 W: 3000/20=150、5000/30=166.667 → 最初が最安
    a, b = "モバイルバッテリー 20W 10000mAh", "モバイルバッテリー 30W 20000mAh"
    r = _compare([_offer(a, 3000), _offer(b, 5000)])
    _assert_single_group(r, (a, b), "W", "power", "1Wあたり")
    _assert_up(r, a, 150)
    _assert_up(r, b, 5000 / 30)
    assert r.cheapest_unit_price.item_name == a


# --- S6 巨大数・千区切り --------------------------------------------------------


def test_s6_thousands_separator_is_read():
    q = _parse("水 2,000ml×6本")
    assert _conf(q) == "high"
    assert q.count_total == 6
    assert q.content_amount == pytest.approx(2000)
    assert q.measure_total == pytest.approx(12000)


def test_s6_nine_digits_are_still_a_quantity():
    q = _parse("素材 123456789g×1個")
    assert _conf(q) == "high"
    assert q.content_amount == pytest.approx(123456789)


@pytest.mark.parametrize(
    "text",
    [
        "素材 1234567890g×2個",  # 10桁
        "素材 1,234,567,890g×2個",  # 千区切りでも10桁
        "電池 10000000000本",  # 個数が10桁
        "素材 " + "9" * 400 + "g×2個",  # float にすると無限大
    ],
    ids=["10digits", "10digits-comma", "count-10digits", "overflow"],
)
def test_s6_too_many_digits_is_low_and_does_not_raise(text):
    q = _parse(text)
    assert _conf(q) == "low"
    assert q.count_total is None and q.content_amount is None and q.measure_total is None


def test_s6_compare_survives_huge_numbers():
    big = "素材 " + "9" * 400 + "g×2個"
    r = _compare([_offer(big, 1000), _offer("素材 2kg×1個", 500)])
    assert big in _names(r.unknown_offers)
    assert _by_name(r, big).unit_price is None


# --- S7 語の照合: 数字の境界と NFKC・casefold -------------------------------------

W1 = "天然水 2L×6本"
W2 = "天然水 12L×1箱"
W3 = "天然水 1.2L×6本"
W4 = "天然水 2Lペット 6本"


def _water_offers():
    return [_offer(W1, 1200), _offer(W2, 2000), _offer(W3, 1100), _offer(W4, 1300)]


def test_s7_include_digit_term_does_not_match_inside_other_numbers():
    r = _compare(_water_offers(), include_terms=["2L"])
    assert _all_names(r) == {W1, W4}


def test_s7_exclude_digit_term_does_not_match_inside_other_numbers():
    r = _compare(_water_offers(), exclude_terms=["2L"])
    assert _all_names(r) == {W2, W3}


def test_s7_mah_term_boundaries():
    a = "モバイルバッテリー 500mAh 1個"
    b = "モバイルバッテリー 1500mAh 1個"
    c = "モバイルバッテリー 5000mAh 1個"
    r = _compare([_offer(a, 1000), _offer(b, 2000), _offer(c, 3000)], include_terms=["500mAh"])
    assert _all_names(r) == {a}
    r2 = _compare([_offer(a, 1000), _offer(b, 2000), _offer(c, 3000)], exclude_terms=["500mAh"])
    assert _all_names(r2) == {b, c}


def test_s7_term_ending_with_digit_does_not_match_before_digit():
    a = "LR6 乾電池 20本"
    b = "LR61 ボタン電池 2本"
    r = _compare([_offer(a, 1000), _offer(b, 500)], include_terms=["LR6"])
    assert _all_names(r) == {a}


@pytest.mark.parametrize("term", ["usb", "USB", "ＵＳＢ", "Usb"])
def test_s7_case_and_width_are_ignored(term):
    a = "USB充電器 2個"
    b = "ACアダプター 2個"
    r = _compare([_offer(a, 1000), _offer(b, 800)], include_terms=[term])
    assert _all_names(r) == {a}


def test_s7_fullwidth_digit_term_matches_halfwidth_name():
    r = _compare(_water_offers(), include_terms=["２Ｌ"])
    assert _all_names(r) == {W1, W4}


# --- S11 表の整合 -------------------------------------------------------------


def test_s11_every_units_dimension_has_a_display_entry():
    from shopping import quantity

    dims = {v[0] for v in quantity.UNITS.values()}
    assert dims, "UNITS が空"
    assert dims <= set(quantity.DISPLAY), dims - set(quantity.DISPLAY)


def test_s11_units_have_no_duplicate_keys_after_nfkc():
    import unicodedata

    from shopping import quantity

    normalized = [unicodedata.normalize("NFKC", k) for k in quantity.UNITS]
    assert len(set(normalized)) == len(normalized)


# --- WP4-0b: W5 小数点・W2 補足・ℓ/l/L の確定 --------------------------------------


def test_w5_digit_ending_term_does_not_match_before_decimal_point():
    # W5: 「2」は「2.5L」の先頭に一致しない（数字で始まる語は直前、数字で終わる語は直後の
    # 数字・小数点を見る）。2L は直後が L なので一致、1.2L は直前が小数点なので不一致
    a = "水 2.5L×4本"
    b = "水 2L×4本"
    c = "水 1.2L×4本"
    r = _compare([_offer(a, 1000), _offer(b, 900), _offer(c, 800)], include_terms=["2"])
    assert _all_names(r) == {b}
    r2 = _compare([_offer(a, 1000), _offer(b, 900), _offer(c, 800)], exclude_terms=["2"])
    assert _all_names(r2) == {a, c}


@pytest.mark.parametrize(
    "text,amount",
    [
        ("商品 2L", 2000),
        ("商品 2l", 2000),
        ("商品 2ℓ", 2000),
        ("商品 1.5l", 1500),
        ("商品 500ML", 500),
        ("商品 1.5KG", 1500),
    ],
)
def test_units_are_matched_after_casefold_l_L_and_script_l(text, amount):
    # 補足: 単位の照合は NFKC+casefold 後。l・L・ℓ はすべてリットル（体積 → ml）
    q = _parse(text)
    assert q.content_dimension in ("volume", "mass")
    assert q.content_unit in ("ml", "g")
    assert q.content_amount == pytest.approx(amount)


def test_units_have_no_duplicate_keys_after_nfkc_casefold():
    import unicodedata

    from shopping import quantity

    keys = [unicodedata.normalize("NFKC", k).casefold() for k in quantity.UNITS]
    dup = {k for k in keys if keys.count(k) > 1}
    assert not dup, dup


# ==========================================================================
# WP5-0 追記: plans/WP5_consensus_quantity.md の P0〜P4（上の既存 220 件は変えない）
# 新しい Q:
#   X1 既存試験が P3 と矛盾する: 「ティッシュ 12P」(→12)・「ケーキ 6ヶ」(→6)・「ギフト 5点」(→5)・
#      COUNT_WORDS の「テスト商品 12回分」(→12) は、P3（P・ヶ・点・回分 は個数の連結位置でだけ
#      数え語）だと数え語にならない。指示は「既存は変えない」なので触っていない。再固定の判断が要る。
#   X2 P1 の「等しい後続・括弧内」が別語（「12ロール×4パック(48個)」）でも言い直しか。
#      P0 の読み（単独の個数 48 も同じ総数を指す）で 48 と固定した。
#   X3 P2 「2因子以上の鎖」の後ろに積と無関係な数え語付きの数が残る場合
#      （「12ロール×4パック 5冊」）は high/low が一意でないので試験しない。
#   X4 P4 の「外側が容器語でない同数」（「3個入り 3冊」）は一意でないので試験しない。
#   X5 P3 の「入数の直後」の P/ヶ/点 は具体例が指示書に無いので試験しない（×の直後と N点セットだけ）。
# ==========================================================================

# --- P0/P1/P2 母集団: {×付き, ×無し} × 総数の書き方 × 総数の数え語 × 内容量 × 一致/不一致 ----

_P_CHAINS = {"x": "12ロール×4パック", "space": "12ロール 4パック"}  # 積 12*4=48
_P_WRITINGS = {
    "paren": "({t})",
    "space": " {t}",
    "kei": " 計{t}",
    "goukei": " 合計{t}",
    "zen": " 全{t}",
    "eq": "={t}",
}
_P_COUNTERS = {"inner": "ロール", "outer": "パック", "other": "個"}


def _p_text(chain, writing, counter, with_content, total):
    t = f"{total}{_P_COUNTERS[counter]}"
    body = _P_CHAINS[chain] + _P_WRITINGS[writing].format(t=t)
    if with_content:
        sep = "×" if chain == "x" else " "
        return f"トイレットペーパー 75m{sep}{body}"
    return f"トイレットペーパー {body}"


_P_GRID = [
    (c, w, k, m)
    for c in _P_CHAINS
    for w in _P_WRITINGS
    for k in _P_COUNTERS
    for m in (False, True)
]
_P_IDS = [f"{c}-{w}-{k}-{'content' if m else 'nocontent'}" for c, w, k, m in _P_GRID]


@pytest.mark.parametrize("chain,writing,counter,with_content", _P_GRID, ids=_P_IDS)
def test_p1_restated_total_equal_to_product_is_high(chain, writing, counter, with_content):
    # P0/P1: 総数の言い直しが積(12*4=48)と等しい → 因子にせず 48 のまま high。
    # 内容量あり: 75m × 48 = 3600m
    text = _p_text(chain, writing, counter, with_content, 48)
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == 48, text
    if with_content:
        assert q.content_dimension == "length" and q.content_unit == "m"
        assert q.content_amount == pytest.approx(75)
        assert q.measure_total == pytest.approx(3600)
    else:
        assert q.content_amount is None and q.measure_total is None


@pytest.mark.parametrize("chain,writing,counter,with_content", _P_GRID, ids=_P_IDS)
def test_p0_restated_total_different_from_product_is_low(chain, writing, counter, with_content):
    # P0: 候補の1つでも食い違えば low（単価不明）。積は 48、言い直しは 50
    text = _p_text(chain, writing, counter, with_content, 50)
    q = _parse(text)
    assert _conf(q) == "low", text
    assert q.count_total is None, text
    assert q.measure_total is None, text


P1_EXAMPLES = [
    # (text, count_total, content_amount or None, measure or None)
    ("トイレットペーパー 12ロール×4パック(48ロール)", 48, None, None),
    ("コピー用紙 64枚×3パック(192枚)", 192, None, None),  # 64*3=192
    ("納豆 45g×3パック×16個 (48パック)", 48, 45, 2160),  # 3*16=48、45*48=2160
]


@pytest.mark.parametrize("text,count,amount,measure", P1_EXAMPLES, ids=[c[0] for c in P1_EXAMPLES])
def test_p1_examples_from_spec(text, count, amount, measure):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    if amount is None:
        assert q.measure_total is None
    else:
        assert q.content_amount == pytest.approx(amount)
        assert q.measure_total == pytest.approx(measure)


def test_p1_restated_vs_plain_offers_have_equal_unit_price():
    # 言い直しの有無で単価が変わらない: 4800円/(48*75m)=1.3333円/m
    a = "トイレットペーパー 75m×12ロール×4パック(48ロール)"
    b = "トイレットペーパー 75m×12ロール×4パック"
    r = _compare([_offer(a, 4800), _offer(b, 4800)])
    _assert_single_group(r, (a, b), "m", "length", "1mあたり")
    _assert_up(r, a, 4800 / 3600)
    _assert_up(r, b, 4800 / 3600)


def test_p0_mismatching_restatement_never_becomes_cheapest():
    # 食い違う言い直し(50)は単価不明に倒れ、最安判定に入らない（安い値段でも）
    bad = "トイレットペーパー 75m×12ロール×4パック(50ロール)"
    good = "トイレットペーパー 75m×12ロール×4パック"
    r = _compare([_offer(bad, 100), _offer(good, 4800)])
    assert [o.item_name for o in r.unknown_offers] == [bad]
    assert r.cheapest_unit_price.item_name == good


# --- P4 容器語の同数 ----------------------------------------------------------

P4_CASES = [
    # (text, count_total, content_amount or None, measure or None)
    ("牛乳 3個入り 400ml×3セット", 9, 400, 3600),  # 同じ数でも外側が容器語 → 3*3
    ("お菓子 6本入り 6パック", 36, None, None),
    ("ジュース 4個入 4ケース", 16, None, None),
    ("ゼリー 5個入り 5箱", 25, None, None),
    ("ゼリー 8個入り 8袋", 64, None, None),
    # P1 が優先: 積(3*3=9)と等しい後続は言い直し
    ("ゼリー 3個入り 3セット 9セット", 9, None, None),
]


@pytest.mark.parametrize("text,count,amount,measure", P4_CASES, ids=[c[0] for c in P4_CASES])
def test_p4_same_number_with_container_outer_is_multiplied(text, count, amount, measure):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    if amount is None:
        assert q.measure_total is None
    else:
        assert q.content_amount == pytest.approx(amount)
        assert q.measure_total == pytest.approx(measure)


# --- P3 文脈の要る数え語 ------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "モニター 27インチ 1080P",
        "モニター 4K 2160P",
        "ポイント5Pアップ",
        "3点以上で10%OFF",
        "2点まで",
        "ポイント10P還元",
        "2点購入でクーポン",
        "プリンター 12ヶ月保証",
        "プロテイン 3ヶ月分",
    ],
)
def test_p3_non_quantity_phrases_are_none(text):
    # 数量にしない: 1080P/60P(解像度・fps)、10P還元(ポイント)、2点購入、12ヶ月保証、3ヶ月分
    q = _parse(text)
    assert _conf(q) == "none", text
    assert q.count_total is None and q.measure_total is None


@pytest.mark.parametrize(
    "text,count,amount",
    [
        ("洗濯洗剤 詰め替え 900g×6袋 12ヶ月保証", 6, 900),
        ("洗濯洗剤 詰め替え 900g×6袋 3ヶ月分", 6, 900),
        ("ミネラルウォーター 500ml×24本 10P還元", 24, 500),
        ("天然水 2L×6本 2点購入でクーポン", 6, 2000),
        ("ミネラルウォーター 500ml×24本 1080P", 24, 500),
    ],
)
def test_p3_noise_phrases_do_not_change_a_real_quantity(text, count, amount):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
    if amount is not None:
        assert q.content_amount == pytest.approx(amount)


@pytest.mark.parametrize(
    "text,count",
    [
        ("タオル 3点セット", 3),  # N点セット
        ("みかん 5個入×3ヶ", 15),  # ×の直後のヶ
        ("ティッシュ 5箱×12P", 60),  # ×の直後のP
        ("単3電池 8本入×3P", 24),
    ],
)
def test_p3_counters_in_count_position_still_count(text, count):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count


def test_p3_noise_does_not_create_a_false_cheapest():
    # 「10P還元」「12ヶ月保証」を個数に読むと単価が狂う。真の100mlあたり:
    # a 2400/12000*100=20, b 2000/12000*100=16.667 (最安)
    a = "天然水 500ml×24本 10P還元"
    b = "天然水 500ml×24本 12ヶ月保証"
    r = _compare([_offer(a, 2400), _offer(b, 2000)])
    _assert_up(r, a, 20)
    _assert_up(r, b, 2000 / 12000 * 100)
    assert r.cheapest_unit_price.item_name == b


# --- WP5-0b: X1〜X5 の確定 -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "ティッシュ 100P",  # P は 1〜99 だけ
        "ティッシュ 5P増量",
        "ティッシュ 5PUP",
        "ティッシュ 5Pアップ",
        "ティッシュ 5Pポイント",
        "ティッシュ 5P倍",
        "セット商品 2点でお得",
        "セット商品 3点以上",
    ],
)
def test_x1_p_and_ten_exclusions_are_not_counters(text):
    q = _parse(text)
    assert _conf(q) == "none", text
    assert q.count_total is None


def test_x1_sixty_p_alone_is_a_counter():
    # X1: 60P は数える（1〜99）
    q = _parse("ウェブカメラ 60P")
    assert _conf(q) == "high"
    assert q.count_total == 60


def test_x1_sixty_p_disagreeing_with_other_count_is_low():
    # X1: 他の個数と食い違えば P0 で low
    q = _parse("単3電池 40本 60P")
    assert _conf(q) == "low"
    assert q.count_total is None and q.measure_total is None


def test_x2_other_word_restatement_equal_to_product_is_high():
    q = _parse("トイレットペーパー 12ロール×4パック(48個)")
    assert _conf(q) == "high"
    assert q.count_total == 48


@pytest.mark.parametrize(
    "text",
    [
        "トイレットペーパー 12ロール×4パック 5冊",  # X3 鎖の後ろに積と無関係な数え語付きの数
        "トイレットペーパー 75m×12ロール×4パック 5冊",
        "ゼリー 3個入り 3冊",  # X4 容器語でない同数
        "ゼリー 4個入り 4冊",
    ],
)
def test_x3_x4_conflicting_counter_candidates_are_low(text):
    q = _parse(text)
    assert _conf(q) == "low", text
    assert q.count_total is None and q.measure_total is None


@pytest.mark.parametrize(
    "text,count",
    [
        ("お菓子 12本入 3P", 36),  # X5 入数の直後の P/ヶ/点
        ("お菓子 12本入 3ヶ", 36),
        ("お菓子 12本入 3点", 36),
        ("お菓子 6個入り 4P", 24),
    ],
)
def test_x5_p_ke_ten_right_after_pack_size_count(text, count):
    q = _parse(text)
    assert _conf(q) == "high", text
    assert q.count_total == count
