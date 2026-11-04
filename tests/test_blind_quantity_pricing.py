# -*- coding: utf-8 -*-
"""ブラインド試験: quantity.py / pricing.py（SPEC §7, §8, §12 AC3〜AC7）

根拠: docs/SPEC.md §7 数量正規化 / §8 価格比較 / §12 受入条件、
      plans/WP1_phase1_mvp.md の models / quantity / pricing の公開インターフェース。
実装は見ていない。期待値はすべて SPEC・指示書の記述と算術（price / total）から導出した。
sys.path は呼び出し側が src を通す前提。

---------------------------------------------------------------------------
仕様の不足（断定できず、この試験では assert していない点）
---------------------------------------------------------------------------
Q1. caveats の正確な文言は未定義。「空でない」「特定の部分文字列を含む」までしか見ない。
    見ている部分文字列は、指示書が明記した「仕様違い」（仕様違いを含む）と、除外件数の数字のみ。
Q2. 「1枚」でシングル判定（指示書にあるが SPEC 本文に無い）。試験しない。
Q3. 全角英字 ｘ / Ｘ（U+FF58 / U+FF38）を乗算記号として扱うか。「全角×」が × (U+00D7) か ｘ かが不明。
    ここでは × (U+00D7)、ASCII の x / X、✕ (U+2715) を見る。
Q4. 「×」を挟まない並記（例: 6ロール 8パック）や「個」「ケース」単位の袋数表記の扱い。
Q5. 倍巻き表記と m 表記が同居する場合（例: 2倍巻き 30m）の length_m。確定不能として None か、30 か不明。
    倍巻き単独（m 表記なし）の場合のみ None を見る。
Q6. ply / length_m だけ読めて総数が読めない文字列の confidence（"none" か "low" か）。
    「何も読めない」文字列のみ "none" を見る。
Q7. parse_quantity の unit 引数を変えた時の挙動（"ロール" 以外）。既定値の unit が返ることのみ見る。
Q8. 総数が読めない/食い違う時の per_pack / pack_count の値（None か部分値か）。見ない。
Q9. 総数 0、price 0、負値の扱い。見ない。
Q10. compare: quantity=None や confidence!="high" の offer が (a) どのグループに入るか
     (b) required_spec 指定時に除外か残留か（ply/length が None の場合）。
     グループに入った場合は末尾、という指示書の文言だけを条件付きで見る。
     compare が item_name から数量を自動パースするか否かも不明（試験では解析不能な名前を使う）。
Q11. 仕様が違うグループ間で cheapest_price / cheapest_total / cheapest_meeting_quantity を
     取る範囲（グループ横断か、グループ内か）。cheapest_unit_price だけ「未指定時は全グループ横断」が
     指示書に明記されているので見る。他は単一グループの入力でのみ見る。
Q12. 送料不明の offer が required_spec で除外された場合に cheapest_total を None にすべきか。見ない。
Q13. cheapest_meeting_quantity の「最少額」が price か total_price（送料込み）か。
     送料条件を揃えた（全件 included）入力でのみ見る。
Q14. 1m 単価（長さが取れた時の単価）の公開インターフェースが無い。試験しない。
Q15. unit_price が丸め済みの値か未丸めの値か。小数 2 桁の許容誤差 (abs=0.01) で比べる。
     順位付けは「丸める前の値で比較する」(§8) ので、丸め違いで順位が変わる入力を別に用意した。
Q16. cheapest_* の同点時にどちらを返すか。同点の入力を使わない。
Q17. 全件クリーン（同一仕様・全 included）の時に caveats が空であるべきか。
     「送料」「仕様違い」を含まないことだけ見る（空かどうかは見ない）。
Q18. 空リスト・全 price None の時の caveats の中身。list であることだけ見る。
---------------------------------------------------------------------------
"""
import pytest

from shopping.models import Offer, QuantityInfo
from shopping.quantity import parse_quantity
from shopping.pricing import compare, unit_price, total_price


# ---------------------------------------------------------------------------
# helpers（試験部品。業務判定は持たない）
# ---------------------------------------------------------------------------

def q(total, ply="double", length=30.0, conf="high", per_pack=None, pack_count=None):
    """QuantityInfo を直接組み立てる（compare の試験を parse_quantity から独立させる）。"""
    if conf != "high":
        total = None
    return QuantityInfo(
        unit="ロール", per_pack=per_pack, pack_count=pack_count, total=total,
        ply=ply, length_m=length, confidence=conf, evidence="架空",
    )


def mk(code, price, quantity=None, shipping_status="included", shipping_fee=None, name=None):
    """架空の Offer。item_name は数字・数量語を含まない既定にする。"""
    return Offer(
        mall="rakuten",
        mall_item_code=code,
        item_name=name if name is not None else "架空ペーパー " + code,
        price=price,
        item_url="https://item.rakuten.co.jp/fake-shop/" + code + "/",
        item_url_status="ok",
        shipping_status=shipping_status,
        shipping_fee=shipping_fee,
        quantity=quantity,
    )


def codes(group):
    return [o.mall_item_code for o in group.offers]


def all_codes(cmp):
    return [c for g in cmp.groups for c in codes(g)]


def code_of(offer):
    return None if offer is None else offer.mall_item_code


def joined(cmp):
    return "\n".join(cmp.caveats)


def find_group(cmp, ply, length):
    hit = [g for g in cmp.groups if g.ply == ply and g.length_m == length]
    assert len(hit) == 1, "ply=%r length=%r のグループが %d 件" % (ply, length, len(hit))
    return hit[0]


# ===========================================================================
# 1. parse_quantity — 総数の算出（AC4）と表記揺れ（SPEC §7）
# ===========================================================================

# SPEC §7 / AC4: 12ロール×3/×4/×6 → 36/48/72
@pytest.mark.parametrize("text,per_pack,pack_count,total", [
    ("12ロール×3袋", 12, 3, 36),
    ("12ロール×4袋", 12, 4, 48),
    ("12ロール×6袋", 12, 6, 72),
    ("12ロール×3パック", 12, 3, 36),
    ("12ロール×4パック", 12, 4, 48),
    ("12ロール×6パック", 12, 6, 72),
    ("12ロール×4セット", 12, 4, 48),
])
def test_ac4_total_from_roll_times_bags(text, per_pack, pack_count, total):
    info = parse_quantity(text)
    assert info.confidence == "high"
    assert info.per_pack == per_pack
    assert info.pack_count == pack_count
    assert info.total == total


# 指示書 quantity.py: 表記揺れ（x / X / ✕ / 全角数字 / R 表記 / 入 / 括弧）
@pytest.mark.parametrize("text,per_pack,pack_count,total", [
    ("12ロール x 4パック", 12, 4, 48),
    ("12ロール X 4パック", 12, 4, 48),
    ("12ロールx4袋", 12, 4, 48),
    ("12ロールX4袋", 12, 4, 48),
    ("12ロール✕4袋", 12, 4, 48),
    ("12ロール ✕ 4パック", 12, 4, 48),
    ("12R×6", 12, 6, 72),
    ("12R×4", 12, 4, 48),
    ("12ロール入×3", 12, 3, 36),
    ("（12ロール）×4セット", 12, 4, 48),
    ("(12ロール)×4セット", 12, 4, 48),
    ("１２ロール×４袋", 12, 4, 48),
    ("１２ロール×３パック", 12, 3, 36),
    ("１２Ｒ×６", 12, 6, 72),
])
def test_quantity_notation_variants(text, per_pack, pack_count, total):
    info = parse_quantity(text)
    assert info.confidence == "high"
    assert info.per_pack == per_pack
    assert info.pack_count == pack_count
    assert info.total == total


# 12 固定の実装を落とす: 他の入り数でも掛け算になる
@pytest.mark.parametrize("text,total", [
    ("6ロール×8パック", 48),
    ("8ロール×6パック", 48),
    ("24ロール×2袋", 48),
    ("4ロール×5袋", 20),
    ("10ロール×3セット", 30),
])
def test_other_pack_sizes_multiply(text, total):
    info = parse_quantity(text)
    assert info.confidence == "high"
    assert info.total == total


# 指示書: 単品 12ロール のみ → pack_count=1, total=12
@pytest.mark.parametrize("text", [
    "12ロール",
    "トイレットペーパー 12ロール",
    "12ロール入",
    "シングル 50m 12ロール",
])
def test_single_pack_has_pack_count_one(text):
    info = parse_quantity(text)
    assert info.confidence == "high"
    assert info.pack_count == 1
    assert info.total == 12


# 数量以外の数字（長さ・価格・枚数）を総数に混ぜない
@pytest.mark.parametrize("text,total", [
    ("【送料無料】ふんわり紙 トイレットペーパー ダブル 30m 12ロール×4袋 1000円ポッキリ", 48),
    ("ダブル 2枚重ね 12ロール×3袋", 36),
    ("香りなし 27.5m 12ロール×6パック 計72ロール分", 72),
])
def test_unrelated_numbers_do_not_pollute_total(text, total):
    info = parse_quantity(text)
    assert info.confidence == "high"
    assert info.total == total


# SPEC §7: 矛盾しない重複表記（同じ総数を2回書いた）は食い違いではない
def test_repeated_consistent_total_is_still_high():
    info = parse_quantity("12ロール×4袋 （合計48ロール）")
    assert info.confidence == "high"
    assert info.total == 48


def test_evidence_is_nonempty_string_when_read():
    info = parse_quantity("12ロール×4袋")
    assert isinstance(info.evidence, str)
    assert info.evidence != ""


def test_default_unit_is_roll():
    assert parse_quantity("12ロール×4袋").unit == "ロール"


# ===========================================================================
# 2. parse_quantity — ply / length_m（SPEC §7 付随仕様）
# ===========================================================================

@pytest.mark.parametrize("text,ply", [
    ("ダブル 12ロール×4袋", "double"),
    ("2枚重ね 12ロール×4袋", "double"),
    ("シングル 12ロール×4袋", "single"),
    ("12ロール×4袋", None),
])
def test_ply_extraction(text, ply):
    info = parse_quantity(text)
    assert info.ply == ply
    assert info.total == 48          # ply 表記があっても総数が壊れない


@pytest.mark.parametrize("text,length,total", [
    ("ダブル 30m 12ロール×4袋", 30.0, 48),
    ("27.5m 12ロール", 27.5, 12),
    ("25メートル 12ロール×3袋", 25.0, 36),
    ("シングル 50m 12ロール×6パック", 50.0, 72),
])
def test_length_extraction(text, length, total):
    info = parse_quantity(text)
    assert info.length_m == length
    assert info.total == total


def test_no_length_when_not_written():
    assert parse_quantity("ダブル 12ロール×4袋").length_m is None


# 指示書: 2倍巻きなど長さが確定できない → length_m=None（誤った長さを作らない）
@pytest.mark.parametrize("text", [
    "2倍巻き 12ロール×4袋",
    "ダブル 長持ち2倍巻き 12ロール",
])
def test_double_length_roll_leaves_length_unknown(text):
    info = parse_quantity(text)
    assert info.length_m is None


# ===========================================================================
# 3. parse_quantity — 食い違い / 読めない（SPEC §7 confidence）
# ===========================================================================

# SPEC §7: 矛盾する表記が複数ある → 総数 null、confidence low
@pytest.mark.parametrize("text", [
    "48ロール 72ロール",
    "トイレットペーパー 48ロール または 72ロール",
    "12ロール×4袋 12ロール×6袋",
])
def test_conflicting_totals_give_total_none_and_low(text):
    info = parse_quantity(text)
    assert info.total is None
    assert info.confidence == "low"


# SPEC §7: 読み取れない → confidence none
@pytest.mark.parametrize("text", [
    "",
    "トイレットペーパー お得なまとめ買い",
    "香り付き ふんわり 送料無料",
])
def test_unreadable_gives_none(text):
    info = parse_quantity(text)
    assert info.confidence == "none"
    assert info.total is None
    assert info.evidence == ""


# QuantityInfo の不変条件: confidence != high なら total は None
@pytest.mark.parametrize("text", [
    "48ロール 72ロール",
    "お得なまとめ買い",
])
def test_total_is_none_unless_high(text):
    info = parse_quantity(text)
    assert info.confidence != "high"
    assert info.total is None


# ===========================================================================
# 4. unit_price / total_price（SPEC §7 最終行, §8）
# ===========================================================================

# SPEC §7/§8: 単価は price ÷ 総数（confidence high のみ）
def test_unit_price_basic_values():
    assert unit_price(mk("a", 2400, q(48))) == pytest.approx(50.0, abs=0.01)
    assert unit_price(mk("b", 3240, q(72))) == pytest.approx(45.0, abs=0.01)
    assert unit_price(mk("c", 1000, q(36))) == pytest.approx(27.78, abs=0.01)


# SPEC §7: 単価に使うのは high のみ
def test_unit_price_none_unless_high():
    assert unit_price(mk("a", 2400, q(None, conf="low"))) is None
    assert unit_price(mk("b", 2400, q(None, conf="none"))) is None
    # total が入っていても confidence が high でなければ使わない
    bad = QuantityInfo(unit="ロール", per_pack=12, pack_count=4, total=48, ply="double",
                       length_m=30.0, confidence="low", evidence="架空")
    assert unit_price(mk("c", 2400, bad)) is None


def test_unit_price_none_when_price_or_quantity_missing():
    assert unit_price(mk("a", None, q(48))) is None
    assert unit_price(mk("b", 2400, None)) is None


# 指示書 pricing.py: total_price の4分岐
def test_total_price_included_is_price():
    assert total_price(mk("a", 2400, q(48), shipping_status="included")) == 2400


def test_total_price_separate_with_fee_adds_fee():
    assert total_price(mk("a", 2400, q(48), shipping_status="separate", shipping_fee=800)) == 3200


def test_total_price_separate_with_zero_fee_is_price():
    # fee=0 は「実額あり」。None と取り違えない
    assert total_price(mk("a", 2400, q(48), shipping_status="separate", shipping_fee=0)) == 2400


def test_total_price_separate_without_fee_is_none():
    assert total_price(mk("a", 2400, q(48), shipping_status="separate", shipping_fee=None)) is None


def test_total_price_unknown_is_none():
    assert total_price(mk("a", 2400, q(48), shipping_status="unknown")) is None
    assert total_price(mk("b", 2400, q(48), shipping_status="unknown", shipping_fee=None)) is None


def test_total_price_none_when_price_missing():
    assert total_price(mk("a", None, q(48), shipping_status="included")) is None


# ===========================================================================
# 5. compare — 順位付け（AC3, AC5）
# ===========================================================================

def _ac5_offers():
    # 36ロール 1980円=55.0 / 48ロール 2400円=50.0 / 72ロール 3240円=45.0 （1ロール単価）
    return [
        mk("o48", 2400, q(48)),
        mk("o72", 3240, q(72)),
        mk("o36", 1980, q(36)),
    ]


# AC3: 入り数違いの同一仕様は同じグループ / AC5: 1ロール単価で順位付け
def test_ac3_ac5_pack_sizes_in_one_group_ranked_by_unit_price():
    cmp = compare(_ac5_offers())
    assert len(cmp.groups) == 1
    assert codes(cmp.groups[0]) == ["o72", "o48", "o36"]
    assert cmp.groups[0].ply == "double"
    assert cmp.groups[0].length_m == 30.0


# SPEC §8: 4種類を区別して出す。商品価格最安と単価最安は別商品になる
def test_cheapest_price_and_cheapest_unit_price_are_different_offers():
    cmp = compare(_ac5_offers())
    assert code_of(cmp.cheapest_price) == "o36"
    assert code_of(cmp.cheapest_unit_price) == "o72"
    # 全件 included なので総額最安は商品価格最安と一致する
    assert code_of(cmp.cheapest_total) == "o36"


# 入力順に依存しない
def test_ranking_is_independent_of_input_order():
    base = _ac5_offers()
    for perm in ([0, 1, 2], [2, 1, 0], [1, 2, 0], [2, 0, 1]):
        cmp = compare([base[i] for i in perm])
        assert codes(cmp.groups[0]) == ["o72", "o48", "o36"]
        assert code_of(cmp.cheapest_unit_price) == "o72"


# SPEC §8: 比較は丸める前の値で行う（丸めると 27.78 と 27.78 で並ぶ入力）
def test_ranking_uses_unrounded_unit_price():
    a = mk("ra", 2778, q(100))   # 27.78
    b = mk("rb", 2750, q(99))    # 27.7777...
    cmp = compare([a, b])
    assert codes(cmp.groups[0]) == ["rb", "ra"]
    assert code_of(cmp.cheapest_unit_price) == "rb"


# 指示書: 算出不能は末尾（グループに入った場合）。confidence!=high は単価最安の対象外
def test_low_confidence_offer_is_never_cheapest_unit_price_and_sorted_last():
    good_a = mk("ga", 2400, q(48))
    good_b = mk("gb", 3240, q(72))
    shaky = mk("sh", 500, q(None, conf="low"))     # 最安値だが数量が信用できない
    cmp = compare([shaky, good_a, good_b])
    assert code_of(cmp.cheapest_unit_price) == "gb"
    for g in cmp.groups:
        cs = codes(g)
        if "sh" in cs:
            assert cs[-1] == "sh"
            assert cs[:-1] == ["gb", "ga"]
    # 商品価格の最安は数量の確度と無関係（SPEC §8-1）
    assert code_of(cmp.cheapest_price) == "sh"


# ===========================================================================
# 6. compare — 誤統合しない（AC6）と required_spec
# ===========================================================================

def _spec_mix():
    return [
        mk("d30a", 2400, q(48, "double", 30.0)),   # 50.00
        mk("d30b", 1980, q(36, "double", 30.0)),   # 55.00
        mk("s30", 1800, q(48, "single", 30.0)),    # 37.50（最安だが仕様違い）
        mk("d50", 2000, q(48, "double", 50.0)),    # 41.67
    ]


# AC6: ダブル/シングル・長さ違いは同じグループに入れない
def test_ac6_different_ply_or_length_are_not_merged():
    cmp = compare(_spec_mix())
    assert len(cmp.groups) == 3
    assert sorted(all_codes(cmp)) == ["d30a", "d30b", "d50", "s30"]
    # 各グループ内の offer はグループの ply / length_m と一致する
    for g in cmp.groups:
        for o in g.offers:
            assert (o.quantity.ply, o.quantity.length_m) == (g.ply, g.length_m)
    assert len({g.key for g in cmp.groups}) == 3
    assert sorted(codes(find_group(cmp, "double", 30.0))) == ["d30a", "d30b"]
    assert codes(find_group(cmp, "single", 30.0)) == ["s30"]
    assert codes(find_group(cmp, "double", 50.0)) == ["d50"]


def test_ac6_ply_unknown_is_not_merged_with_known_ply():
    offers = [
        mk("known", 2400, q(48, "double", 30.0)),
        mk("noply", 2000, q(48, None, 30.0)),
    ]
    cmp = compare(offers)
    for g in cmp.groups:
        assert len({(o.quantity.ply, o.quantity.length_m) for o in g.offers}) == 1
    assert len(cmp.groups) == 2


# 指示書: required_spec 未指定で仕様違いを横断して単価比較した時は caveats に「仕様違い」
def test_cross_spec_unit_price_comparison_is_flagged_in_caveats():
    cmp = compare(_spec_mix())
    assert code_of(cmp.cheapest_unit_price) == "s30"   # 横断では 37.5 が最安
    assert cmp.caveats
    assert "仕様違い" in joined(cmp)


# 同一仕様だけなら「仕様違い」「送料」の断り書きは出さない
def test_same_spec_all_included_has_no_spec_or_shipping_caveat():
    cmp = compare(_ac5_offers())
    assert "仕様違い" not in joined(cmp)
    assert "送料" not in joined(cmp)


# 指示書: required_spec に合わない offer は比較から除外し、caveats に件数を書く
def test_required_spec_excludes_nonmatching_and_reports_count():
    matches = [
        mk("m1", 2400, q(48, "double", 30.0)),   # 50.0
        mk("m2", 3240, q(72, "double", 30.0)),   # 45.0
    ]
    excluded = [
        mk("x1", 900, q(48, "single", 30.0)),
        mk("x2", 900, q(48, "single", 30.0)),
        mk("x3", 900, q(48, "single", 30.0)),
        mk("x4", 900, q(48, "double", 50.0)),
        mk("x5", 900, q(48, "double", 50.0)),
        mk("x6", 900, q(48, "single", 50.0)),
        mk("x7", 900, q(48, "single", 50.0)),
    ]
    cmp = compare(excluded + matches, required_spec={"ply": "double", "length_m": 30})
    present = all_codes(cmp)
    assert sorted(present) == ["m1", "m2"]
    assert len(cmp.groups) == 1
    assert code_of(cmp.cheapest_price) == "m1"            # 除外された 900 円は選ばれない
    assert code_of(cmp.cheapest_unit_price) == "m2"
    assert cmp.caveats
    assert "7" in joined(cmp)                              # 除外件数 7


# 部分指定: ply だけ指定 → 長さ違いのダブルは残り、シングルだけ除外
def test_required_spec_partial_keeps_other_attributes_free():
    offers = [
        mk("d30", 2400, q(48, "double", 30.0)),
        mk("d50", 2000, q(48, "double", 50.0)),
        mk("s30", 1000, q(48, "single", 30.0)),
    ]
    cmp = compare(offers, required_spec={"ply": "double"})
    assert sorted(all_codes(cmp)) == ["d30", "d50"]
    assert len(cmp.groups) == 2
    assert "s30" not in [code_of(cmp.cheapest_price), code_of(cmp.cheapest_unit_price)]


# ===========================================================================
# 7. compare — 送料不明のとき総額最安と断定しない（AC7）
# ===========================================================================

def _ship_offers(third_status, third_fee=None):
    return [
        mk("i1", 2400, q(48), shipping_status="included"),
        mk("i2", 1980, q(36), shipping_status="included"),
        mk("u1", 5000, q(48), shipping_status=third_status, shipping_fee=third_fee),  # 明らかに高い
    ]


# AC7: 送料不明が1件でも候補にあれば cheapest_total は None、理由は caveats
def test_ac7_unknown_shipping_blocks_cheapest_total():
    cmp = compare(_ship_offers("unknown"))
    assert cmp.cheapest_total is None
    assert cmp.caveats


# AC7: separate で実額なしも同様
def test_ac7_separate_without_fee_blocks_cheapest_total():
    cmp = compare(_ship_offers("separate", None))
    assert cmp.cheapest_total is None
    assert cmp.caveats


# 送料不明は商品価格・単価の判定を止めない
def test_unknown_shipping_does_not_block_price_or_unit_price():
    cmp = compare(_ship_offers("unknown"))
    assert code_of(cmp.cheapest_price) == "i2"
    assert code_of(cmp.cheapest_unit_price) == "i1"      # 2400/48=50.0 < 1980/36=55.0 < 5000/48


# 全件 included → 支払総額最安が決まる
def test_all_included_gives_cheapest_total():
    offers = [
        mk("a", 2400, q(48)),
        mk("b", 1980, q(36)),
        mk("c", 3240, q(72)),
    ]
    cmp = compare(offers)
    assert code_of(cmp.cheapest_total) == "b"


# 送料の実額が全件分かる → price+fee で判定（商品価格最安と別商品になる）
def test_all_fees_known_cheapest_total_uses_price_plus_fee():
    offers = [
        mk("a", 1000, q(36), shipping_status="separate", shipping_fee=800),   # 1800
        mk("b", 1500, q(48), shipping_status="included"),                    # 1500
        mk("c", 1400, q(48), shipping_status="separate", shipping_fee=200),  # 1600
    ]
    cmp = compare(offers)
    assert code_of(cmp.cheapest_price) == "a"
    assert code_of(cmp.cheapest_total) == "b"


def test_zero_fee_separate_counts_as_known_shipping():
    offers = [
        mk("a", 1000, q(36), shipping_status="separate", shipping_fee=0),
        mk("b", 1500, q(48), shipping_status="included"),
    ]
    cmp = compare(offers)
    assert code_of(cmp.cheapest_total) == "a"


# ===========================================================================
# 8. compare — 必要数量を満たす最安（SPEC §8-4）
# ===========================================================================

def _qty_offers():
    return [
        mk("q36", 1500, q(36)),   # 最安価格だが 48 に足りない
        mk("q48", 2600, q(48)),
        mk("q72", 2400, q(72)),   # 48 以上で最少額
        mk("q96", 3800, q(96)),
    ]


def test_cheapest_meeting_quantity_excludes_insufficient_pack():
    cmp = compare(_qty_offers(), desired_quantity=48)
    assert code_of(cmp.cheapest_price) == "q36"
    assert code_of(cmp.cheapest_meeting_quantity) == "q72"
    assert code_of(cmp.cheapest_meeting_quantity) != "q36"


# 境界: 希望数量ちょうどは「満たす」（以上）
def test_cheapest_meeting_quantity_boundary_is_inclusive():
    offers = [mk("a", 1500, q(36)), mk("b", 2000, q(48)), mk("c", 3000, q(72))]
    cmp = compare(offers, desired_quantity=48)
    assert code_of(cmp.cheapest_meeting_quantity) == "b"
    cmp = compare(offers, desired_quantity=49)
    assert code_of(cmp.cheapest_meeting_quantity) == "c"


def test_cheapest_meeting_quantity_none_when_nothing_reaches():
    cmp = compare(_qty_offers(), desired_quantity=200)
    assert cmp.cheapest_meeting_quantity is None


def test_cheapest_meeting_quantity_none_when_not_requested():
    cmp = compare(_qty_offers())
    assert cmp.cheapest_meeting_quantity is None


# 数量が信用できない offer は「満たす」と断定できない
def test_unreliable_quantity_never_meets_quantity():
    offers = [
        mk("shaky", 500, q(None, conf="low")),
        mk("none", 400, q(None, conf="none")),
        mk("ok", 2600, q(48)),
    ]
    cmp = compare(offers, desired_quantity=48)
    assert code_of(cmp.cheapest_meeting_quantity) == "ok"


# ===========================================================================
# 9. 境界: price None / quantity None / 空
# ===========================================================================

def test_empty_list():
    cmp = compare([])
    assert cmp.groups == []
    assert cmp.cheapest_price is None
    assert cmp.cheapest_unit_price is None
    assert cmp.cheapest_total is None
    assert cmp.cheapest_meeting_quantity is None
    assert isinstance(cmp.caveats, list)


def test_empty_list_with_options():
    cmp = compare([], required_spec={"ply": "double", "length_m": 30}, desired_quantity=48)
    assert cmp.groups == []
    assert cmp.cheapest_price is None
    assert isinstance(cmp.caveats, list)


def test_price_none_offer_is_never_chosen_and_does_not_crash():
    offers = [
        mk("np", None, q(48)),
        mk("a", 2400, q(48)),
        mk("b", 3240, q(72)),
    ]
    cmp = compare(offers, desired_quantity=48)
    chosen = [code_of(cmp.cheapest_price), code_of(cmp.cheapest_unit_price),
              code_of(cmp.cheapest_total), code_of(cmp.cheapest_meeting_quantity)]
    assert "np" not in chosen
    assert code_of(cmp.cheapest_price) == "a"
    assert code_of(cmp.cheapest_unit_price) == "b"
    # グループに入った場合は単価算出不能として末尾
    for g in cmp.groups:
        cs = codes(g)
        if "np" in cs:
            assert cs[-1] == "np"


def test_all_prices_none():
    cmp = compare([mk("a", None, q(48)), mk("b", None, q(72))])
    assert cmp.cheapest_price is None
    assert cmp.cheapest_unit_price is None
    assert cmp.cheapest_total is None
    assert cmp.cheapest_meeting_quantity is None


def test_quantity_none_offer_is_not_unit_or_quantity_candidate_and_does_not_crash():
    offers = [
        mk("nq", 100, None, name="謎の商品"),
        mk("a", 2400, q(48)),
        mk("b", 3240, q(72)),
    ]
    cmp = compare(offers, desired_quantity=48)
    assert code_of(cmp.cheapest_unit_price) == "b"
    assert code_of(cmp.cheapest_meeting_quantity) == "a"     # 48以上で最少額（2400 < 3240）
    # 単価の算出不能なものが、算出できるものより上に来ない
    for g in cmp.groups:
        cs = codes(g)
        if "nq" in cs:
            assert cs[-1] == "nq"


def test_only_quantity_none_offers():
    cmp = compare([mk("nq1", 100, None, name="謎の商品"), mk("nq2", 200, None, name="謎の品")])
    assert cmp.cheapest_unit_price is None
    assert cmp.cheapest_meeting_quantity is None


def test_required_spec_with_quantity_none_offer_does_not_crash():
    offers = [mk("nq", 100, None, name="謎の商品"), mk("a", 2400, q(48, "double", 30.0))]
    cmp = compare(offers, required_spec={"ply": "double", "length_m": 30})
    assert code_of(cmp.cheapest_unit_price) == "a"


# ===========================================================================
# 10. parse_quantity → compare の一貫試験（AC3〜AC6 を実経路で通す）
# ===========================================================================

def _parsed(code, price, name):
    o = mk(code, price, None, name=name)
    o.quantity = parse_quantity(name)
    return o


def test_end_to_end_parse_then_compare_ac3_to_ac5():
    base = "ふんわり紙 トイレットペーパー ダブル 30m "
    offers = [
        _parsed("e48", 2160, base + "12ロール×4袋"),    # 45.0
        _parsed("e72", 3060, base + "12ロール×6袋"),    # 42.5
        _parsed("e36", 1800, base + "12ロール×3袋"),    # 50.0
    ]
    for o in offers:
        assert o.quantity.confidence == "high"
    cmp = compare(offers)
    assert len(cmp.groups) == 1
    assert codes(cmp.groups[0]) == ["e72", "e48", "e36"]
    assert code_of(cmp.cheapest_unit_price) == "e72"
    assert code_of(cmp.cheapest_price) == "e36"


def test_end_to_end_parse_then_compare_ac6_no_misgrouping():
    offers = [
        _parsed("p1", 2160, "ふんわり紙 ダブル 30m 12ロール×4袋"),
        _parsed("p2", 1700, "ふんわり紙 シングル 30m 12ロール×4袋"),
        _parsed("p3", 1900, "ふんわり紙 ダブル 50m 12ロール×4袋"),
        _parsed("p4", 1800, "ふんわり紙 ダブル 30m 12ロール×3袋"),
    ]
    cmp = compare(offers)
    assert len(cmp.groups) == 3
    assert sorted(codes(find_group(cmp, "double", 30.0))) == ["p1", "p4"]
    assert codes(find_group(cmp, "single", 30.0)) == ["p2"]
    assert codes(find_group(cmp, "double", 50.0)) == ["p3"]
    cmp2 = compare(offers, required_spec={"ply": "double", "length_m": 30})
    assert sorted(all_codes(cmp2)) == ["p1", "p4"]
    assert code_of(cmp2.cheapest_unit_price) == "p1"      # 45.0 < 50.0
    assert "p2" != code_of(cmp2.cheapest_price)


def test_end_to_end_conflicting_title_is_excluded_from_unit_price():
    shaky = _parsed("cx", 100, "ふんわり紙 ダブル 30m 48ロール 72ロール")
    good = _parsed("gd", 2160, "ふんわり紙 ダブル 30m 12ロール×4袋")
    assert shaky.quantity.total is None
    cmp = compare([shaky, good])
    assert code_of(cmp.cheapest_unit_price) == "gd"
