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
