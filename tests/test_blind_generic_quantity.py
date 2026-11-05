"""WP3-0 ブラインド試験: 汎用 数量読み取り(§7) と 価格比較(§8)。

正本: plans/WP3_generic_quantity.md「SPEC §7・§8 の差し替え」節と「インターフェース」節だけ。
実装 (src/shopping の quantity/pricing/service 等) と既存の自作試験は見ずに作成した。
期待値は全て手計算（各テストのコメントに式を残す）。実装担当は読まない・編集しない。
未実装の今は落ちてよい（import は各テストの中で遅延させてあるので、収集は常に通る）。

【未確定の契約一覧 = Q 一覧】SPEC から一意に決まらない点。試験は「確実な所だけ」を固定し、
下の Q に依存する試験は PROVISIONAL (クラス名 Test*Provisional*) に隔離した。
実装後に命名が違う等で落ちた場合は、結果の形を SPEC に確定 → 「再固定の手続き」(分類③) で直す。

  Q0  公開関数と呼び出し形。parse_quantity(text) / compare(offers, include_terms, exclude_terms,
      desired_quantity, basis) を shopping.quantity / shopping.pricing から import する想定
      (指示書の記述)。compare が Offer.quantity を自分で読むのか item_name から再解析するのか不明
      なので、試験側は Offer.quantity = parse_quantity(item_name) を入れてから渡す（どちらでも同値）。
  Q1  結果の入れ物の形が §8 に無い。確実なのは「インターフェース」節の名前だけ:
      候補= unit_price を持つ辞書/オブジェクト（quantity・unit_price_label も持つ）、
      グループ= basis と dimension を持つ、caveats / notes という名前の文字列リスト。
      試験は結果を dataclass/dict/list の入れ子として再帰的にたどり、この名前で見つける
      （入れ物の階層は問わない）。この名前自体が違うと全比較試験が落ちる → SPEC 確定が先。
  Q2  商品単価・単位価格・支払総額・必要数量を満たす最安、の4スロットのフィールド名が不明。
      これに依存する試験は TestWinnerSlotsProvisional に隔離。キー名に unit/total/desired
      系の語を含むかで探す（_slot_names）。確定後は _slot_names だけ直す。
  Q3  unit_price は基準単位あたり(例 1g)か表示単位あたり(例 100g)か。§8 は「単位価格 = 価格 ÷ 量」と
      「表示用に100gあたり」の両方を述べる。→ 絶対値は「1あたり」「表示単位あたり」の
      どちらも許容（比の試験は不変）。表示用ラベルは空白を除いて比較（§8本文は「100ml あたり」、
      インターフェース節は「100gあたり」と空白の揺れ）。
  Q4  basis "個" のラベル文言は「1個あたり」か count_unit 別(「1本あたり」)か → 「1」始まり・「あたり」
      を含む、だけ固定。基準単位 g/ml/m/W は §8 の例どおり「100gあたり」「100mlあたり」「1mあたり」
      「1Wあたり」。mAh/Wh の表示単位は §8 に無いので試験しない。
  Q5  個数に数え語が1つも無い文字列 (例「ミネラルウォーター 2L」「洗剤 900g」) の count_total は
      1 か None か。confidence は high か。→ 確実な試験では数え語を必ず付ける。
      PROVISIONAL で count_total==1 / high を固定（「単独なら単体」からの推測）。
  Q6  数え語が2段のとき count_unit は内側(ロール)か外側(パック)か → count_unit を固定しない
      (総数 count_total だけ固定)。単段・数字だけの ×N（「900g×6」）は「個」(§7 末尾 "無ければ個")。
  Q7  basis 自動判定の「過半（high のもの）」の分母（全候補か high 候補か）と、ちょうど半数の
      扱い → 全会一致/明白な過半の例だけ試験。
  Q8  「単価不明」グループの表現（basis/dimension が None か、別キーか）。→ 「どのグループにも
      基準次元の仲間として入っていない」＋ unit_price が None、だけ固定。
  Q9  basis="個" のグループの dimension の値（None か "count" か）→ 固定しない。
  Q10 desired_quantity: 「必要数量を満たす最安」の「最安」が商品単価(価格)か総額か単位価格か、
      複数個買って満たす案を許すか、basis が L・kg 別名のときの desired の単位(L か ml か)
      → 全解釈で同じ結果になるデータを作り、別名 basis と desired の組は試験しない。
  Q11 送料不明の表現（総額最安フィールドが None か、フラグ付きで残すか）。→ 「総額最安スロットが空、
      または結果のどこかの文字列が 送料 に言及」のどちらかを要求（無言で断定しない）だけ固定。
  Q12 外した件数 notes の書式（「3件」等）。include で外した分も数えるか。→ exclude_terms 単独で外した
      件数の数字がいずれかの notes 文字列に含まれる、だけ固定。単価不明の件数 caveats も同様（PROVISIONAL）。
  Q13 内容量が無い (電池 40本) ときの measure_total は None と想定（count_total × None は計算不能）。
  Q14 矛盾(low)のとき content_dimension / content_unit を None にするか → 固定しない
      (count_total・content_amount・measure_total が None、だけ)。
  Q15 「30cm×50m」のように同じ次元(長さ)で幅×長さを書く商品名は矛盾(low)になる理屈だが、実用上は
      誤判定。SPEC は言及なし → 試験しない（要件の議論として報告）。
  Q16 全角数字・全角英字・「x/X/*」の乗算記号を正規化するか → PROVISIONAL。
  Q17 換算表に足すだけで単位を増やせる(データ駆動)ことは、表の名前が不明なため試験できない。

未試験の観点: 上記 Q、過半のちょうど半数、単位拡張のデータ駆動、価格 None の候補、Web/MCP/CLI/regulars
(インターフェース節の後半=別の層の試験)、mock_data、sort/pages/min_price 等の service 引数。
"""

from __future__ import annotations

import dataclasses
import enum
import itertools
import re

import pytest

CAVEAT = "仕様の違い（濃縮・層数・型番・色など）は判定していません。商品名で確認してください。"

_UNSET = object()  # 「このフィールドは試験しない」

# --------------------------------------------------------------------------
# 部品（遅延 import・Offer 作成・結果の再帰的な読み取り）
# --------------------------------------------------------------------------


def _parse(text):
    from shopping.quantity import parse_quantity

    return parse_quantity(text)


def _field(obj, name):
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def _conf(q):
    c = _field(q, "confidence")
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


def _plain(o, depth=0):
    if depth > 14:
        return None
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: _plain(getattr(o, f.name), depth + 1) for f in dataclasses.fields(o)}
    if isinstance(o, enum.Enum):
        return o.value
    if isinstance(o, dict):
        return {str(k): _plain(v, depth + 1) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [_plain(v, depth + 1) for v in o]
    if o is None or isinstance(o, (str, int, float, bool)):
        return o
    if hasattr(o, "__dict__"):
        return {k: _plain(v, depth + 1) for k, v in vars(o).items() if not k.startswith("_")}
    return str(o)


def _dicts(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _dicts(v)


def _find_str(node, key):
    for d in _dicts(node):
        if isinstance(d.get(key), str):
            return d[key]
    return None


def _find_dict(node, key):
    for d in _dicts(node):
        if isinstance(d.get(key), dict):
            return d[key]
    return None


def _names_in(node):
    out = set()
    for d in _dicts(node):
        v = d.get("item_name")
        if isinstance(v, str):
            out.add(v)
    return out


def _nospace(s):
    return re.sub(r"\s+", "", s or "")


def _compare(offers, **kw):
    from shopping.pricing import compare

    return _plain(compare(offers, **kw))


def _candidates(plain):
    """unit_price を持つ辞書を item_name で引く（Q1）。"""
    found = {}
    for d in _dicts(plain):
        if "unit_price" in d:
            name = _find_str(d, "item_name")
            if name is not None:
                found.setdefault(name, d)
    return found


def _cand(plain, name):
    c = _candidates(plain)
    assert name in c, f"候補 {name!r} が結果に無い (Q1)。あるのは {sorted(c)}"
    return c[name]


def _groups(plain):
    """basis と dimension の両方を持つ（ルートでも候補でもない）辞書 = グループ (Q1)。"""
    out = []

    def rec(node, is_root):
        if isinstance(node, dict):
            if (
                not is_root
                and "basis" in node
                and "dimension" in node
                and "unit_price" not in node
                and "item_name" not in node
            ):
                out.append(node)
                return
            for v in node.values():
                rec(v, False)
        elif isinstance(node, list):
            for v in node:
                rec(v, False)

    rec(plain, True)
    return out


def _bases_of(plain, name):
    return {g["basis"] for g in _groups(plain) if name in _names_in(g)}


def _together(plain, a, b):
    return any({a, b} <= _names_in(g) for g in _groups(plain))


def _strings_under(plain, key):
    out = []

    def collect(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            for x in v:
                collect(x)

    for d in _dicts(plain):
        if key in d:
            collect(d[key])
    return out


def _up(plain, name):
    return _cand(plain, name)["unit_price"]


def _label(plain, name):
    return _nospace(_cand(plain, name).get("unit_price_label"))


def _factor(label):
    m = re.match(r"(\d+)", label or "")
    return int(m.group(1)) if m else 1


def _assert_up(plain, name, per_basis_unit):
    """単位価格の絶対値。基準単位あたり、または表示単位あたり、のどちらも許す (Q3)。"""
    up = _up(plain, name)
    assert up is not None, f"{name!r} の unit_price が None"
    f = _factor(_label(plain, name))
    assert up == pytest.approx(per_basis_unit, rel=1e-3) or up == pytest.approx(
        per_basis_unit * f, rel=1e-3
    ), f"{name!r}: unit_price={up} 期待 {per_basis_unit} または {per_basis_unit * f}"


def _assert_ratio(plain, a, b, ratio):
    ua, ub = _up(plain, a), _up(plain, b)
    assert ua is not None and ub is not None
    assert ua / ub == pytest.approx(ratio, rel=1e-3)


def _slot_names(plain, must, any_of=(), forbid=()):
    """4スロット(Q2)のキー名が不明なので、キー名の部分一致で探し、その値の中の商品名を返す。"""
    keys, names = [], set()
    for d in _dicts(plain):
        for k, v in d.items():
            kl = k.lower()
            if (
                all(m in kl for m in must)
                and (not any_of or any(a in kl for a in any_of))
                and not any(f in kl for f in forbid)
            ):
                keys.append(k)
                names |= _names_in(v)
    return keys, names


_CHEAP = ("cheap", "min", "best", "lowest")
_DESIRED = ("desired", "required", "satisf", "enough", "meet", "need", "fulfil")


def _unit_slot(plain):
    return _slot_names(plain, ("unit",), _CHEAP, forbid=("label",))


def _total_slot(plain):
    return _slot_names(plain, ("total",), _CHEAP)


def _desired_slot(plain):
    return _slot_names(plain, (), _DESIRED, forbid=("quantity",))


# --------------------------------------------------------------------------
# データセット（手計算）
# --------------------------------------------------------------------------

# 洗剤 g。measure = 5400g / 4800g / 2000g。単価/g = 0.5555.. / 0.75 / 0.5
D1 = "花王 洗濯洗剤 詰め替え 900g×6袋"
D2 = "ライオン 洗濯洗剤 詰め替え 1.2kg×4袋"
D3 = "洗濯洗剤 本体 2kg×1個"


def _detergents():
    return [_offer(D1, 3000), _offer(D2, 3600), _offer(D3, 1000)]


# 飲料 ml。measure = 18000 / 12000 / 12000。単価/ml = 0.11 / 0.2 / 0.1
B1 = "天然水 2L×9本"
B2 = "天然水 500ml×24本"
B3 = "ミネラルウォーター 1.5L×8本"


def _beverages():
    return [_offer(B1, 1980), _offer(B2, 2400), _offer(B3, 1200)]


# 電池 個。count = 40 / 40(20×2) / 100。単価/個 = 50 / 45 / 40
T1 = "単3電池 40本"
T2 = "単3形 アルカリ乾電池 20本入り×2パック"
T3 = "単3電池 100本"


def _batteries():
    return [_offer(T1, 2000), _offer(T2, 1800), _offer(T3, 4000)]


# ソーラーパネル W。measure = 200 / 200 / 200。単価/W = 100 / 120 / 90
P1 = "ソーラーパネル 100W×2枚"
P2 = "ソーラーパネル 200W 1枚"
P3 = "ソーラーパネル 50W×4枚"


def _panels():
    return [_offer(P1, 20000), _offer(P2, 24000), _offer(P3, 18000)]


# トイレットペーパー: 長さ(m)基準なら 600m/300m/1440m、個基準なら 12/12/48
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
    # 洗剤: 900g×6 は 内容量900g・個数6（数字だけの×6）。count_unit は無ければ「個」
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
    # 電池: 「単3」の3は個数ではない。内容量なし
    ("単3電池 40本", 40, "本", None, None, None, None),
    # 20本入り×2パック = 40。入り数が単段のときの count_unit は固定しない (Q6)
    ("単3形 アルカリ乾電池 20本入り×2パック", 40, _UNSET, None, None, None, None),
    # ソーラーパネル: 100*2=200, 200*1=200
    ("ソーラーパネル 100W×2枚", 2, "枚", "power", "W", 100, 200),
    ("ソーラーパネル 200W 1枚", 1, "枚", "power", "W", 200, 200),
    ("ソーラーパネル 100W 2枚セット", 2, _UNSET, "power", "W", 100, 200),
    # モバイルバッテリー: 10000*2
    ("モバイルバッテリー 10000mAh 2個", 2, "個", "charge", "mAh", 10000, 20000),
    # トイレットペーパー: 長さ50m が1ロールの内容量。50*12=600、30*(12*4)=1440
    ("トイレットペーパー シングル 50m×12ロール", 12, "ロール", "length", "m", 50, 600),
    ("トイレットペーパー ダブル 30m×12ロール×4パック", 48, _UNSET, "length", "m", 30, 1440),
    ("トイレットペーパー ダブル 12ロール", 12, "ロール", None, None, None, None),  # 層数は読まない
    ("トイレットペーパー 12R×4", 48, _UNSET, None, None, None, None),  # R=ロール、12*4
    ("トイレットペーパー 4パック×12ロール", 48, _UNSET, None, None, None, None),  # 順不同
    ("トイレットペーパー 12ロール×4パック", 48, _UNSET, None, None, None, None),
    ("洗剤 3袋入り×2", 6, _UNSET, None, None, None, None),  # 数字だけの×2は直前の個数に掛ける
    ("ティッシュ 12ロール×6", 72, _UNSET, None, None, None, None),
]


@pytest.mark.parametrize(
    "text,count,cunit,dim,unit,amount,measure", PARSE_CASES, ids=[c[0] for c in PARSE_CASES]
)
def test_parse_quantity_expected(text, count, cunit, dim, unit, amount, measure):
    # §7 個数×内容量・基準単位への換算・measure_total = count_total × content_amount
    q = _parse(text)
    assert _conf(q) == "high", text
    assert _field(q, "count_total") == count
    if cunit is not _UNSET:
        assert _field(q, "count_unit") == cunit
    assert _field(q, "content_dimension") == dim
    assert _field(q, "content_unit") == unit
    if amount is None:
        assert _field(q, "content_amount") is None
        assert _field(q, "measure_total") is None  # Q13
    else:
        assert _field(q, "content_amount") == pytest.approx(amount)
        assert _field(q, "measure_total") == pytest.approx(measure)
    ev = _field(q, "evidence")
    assert isinstance(ev, str) and ev.strip()


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
    # §7 換算表。個数は問わず内容量の換算だけ見る（Q5 を避ける）
    q = _parse(text)
    assert _field(q, "content_dimension") == dim
    assert _field(q, "content_unit") == unit
    assert _field(q, "content_amount") == pytest.approx(amount)


COUNT_WORDS = [
    "個", "本", "枚", "袋", "箱", "パック", "缶", "ロール", "セット", "組", "足", "着",
    "台", "錠", "包", "粒", "ケース", "玉", "束", "巻", "食", "回分",
]  # fmt: skip


@pytest.mark.parametrize("word", COUNT_WORDS)
def test_parse_count_word_table(word):
    # §7 数え語の表。12<数え語> は総数12・数え語がそのまま count_unit
    q = _parse(f"テスト商品 12{word}")
    assert _field(q, "count_total") == 12
    assert _field(q, "count_unit") == word
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
    assert _field(q, "count_total") == count
    if amount is not None:
        assert _field(q, "content_amount") == pytest.approx(amount)


@pytest.mark.parametrize(
    "text",
    ["ポイント10倍 最大50%OFF 送料無料 1000円ポッキリ", "おすすめ洗剤 ポイント10倍", "", "ギフト券"],
)
def test_parse_unreadable_is_none(text):
    # §7 読めなければ none（販促だけの文字列に数量は無い）
    q = _parse(text)
    assert _conf(q) == "none"
    assert _field(q, "measure_total") is None


CONFLICT_CASES = [
    "飲料 500ml 2L ×6本",  # 同じ次元(体積)で値が違う内容量
    "洗濯洗剤 詰め替え 900g 1000g ×3袋",
    "単3電池 40本 48本",  # 総数が食い違う個数表記
    "トイレットペーパー 12ロール 18ロール",
]


@pytest.mark.parametrize("text", CONFLICT_CASES)
def test_parse_conflict_is_low_and_nulls(text):
    # §7 矛盾 → low、総数・内容量を null
    q = _parse(text)
    assert _conf(q) == "low"
    assert _field(q, "count_total") is None
    assert _field(q, "content_amount") is None
    assert _field(q, "measure_total") is None


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
    assert _field(q, "count_total") == count
    assert _field(q, "content_amount") == pytest.approx(amount)


def test_parse_result_has_all_section7_fields():
    q = _parse("ミネラルウォーター 2L×9本")
    for name in (
        "count_total", "count_unit", "content_amount", "content_dimension",
        "content_unit", "measure_total", "confidence", "evidence",
    ):  # fmt: skip
        _field(q, name)


# --------------------------------------------------------------------------
# §8 価格比較
# --------------------------------------------------------------------------


def test_compare_mass_auto_basis_groups_sizes_together():
    # §8 過半が同じ次元(mass) → 基準 g。サイズ違い・入り数違いはグループを分けない
    r = _compare(_detergents())
    for n in (D1, D2, D3):
        assert _bases_of(r, n) == {"g"}
        assert "100gあたり" in _label(r, n)
    assert _together(r, D1, D2) and _together(r, D2, D3)
    assert all(g["dimension"] == "mass" for g in _groups(r) if D1 in _names_in(g))
    # 3000/5400=0.5556, 3600/4800=0.75, 1000/2000=0.5 → 比 1.1111, 1.5
    _assert_ratio(r, D1, D3, 3000 / 5400 / 0.5)
    _assert_ratio(r, D2, D3, 1.5)
    _assert_up(r, D3, 0.5)
    _assert_up(r, D2, 0.75)


def test_compare_volume_auto_basis():
    # §8 体積 → ml。1980/18000=0.11, 2400/12000=0.2, 1200/12000=0.1
    r = _compare(_beverages())
    for n in (B1, B2, B3):
        assert _bases_of(r, n) == {"ml"}
        assert "100mlあたり" in _label(r, n)
    assert _together(r, B1, B2) and _together(r, B2, B3)
    assert all(g["dimension"] == "volume" for g in _groups(r) if B1 in _names_in(g))
    _assert_up(r, B1, 0.11)
    _assert_up(r, B2, 0.2)
    _assert_up(r, B3, 0.1)
    _assert_ratio(r, B2, B3, 2.0)


def test_compare_count_only_auto_basis_is_piece():
    # §8 内容量の次元が無ければ「個」。2000/40=50, 1800/40=45, 4000/100=40
    r = _compare(_batteries())
    for n in (T1, T2, T3):
        assert _bases_of(r, n) == {"個"}
        lab = _label(r, n)
        assert lab.startswith("1") and "あたり" in lab  # Q4
    assert _together(r, T1, T2) and _together(r, T2, T3)
    _assert_up(r, T1, 50)
    _assert_up(r, T2, 45)
    _assert_up(r, T3, 40)


def test_compare_power_auto_basis():
    # §8 W。20000/200=100, 24000/200=120, 18000/200=90
    r = _compare(_panels())
    for n in (P1, P2, P3):
        assert _bases_of(r, n) == {"W"}
        assert "1Wあたり" in _label(r, n)
    assert _together(r, P1, P2) and _together(r, P2, P3)
    assert all(g["dimension"] == "power" for g in _groups(r) if P1 in _names_in(g))
    _assert_up(r, P1, 100)
    _assert_up(r, P2, 120)
    _assert_up(r, P3, 90)


def test_compare_length_auto_basis():
    # §8 m。600/600=1.0, 450/300=1.5, 2400/1440=1.6667
    r = _compare(_rolls())
    for n in (R1, R2, R3):
        assert _bases_of(r, n) == {"m"}
        assert "1mあたり" in _label(r, n)
    assert _together(r, R1, R3)
    assert all(g["dimension"] == "length" for g in _groups(r) if R1 in _names_in(g))
    _assert_up(r, R1, 1.0)
    _assert_up(r, R2, 1.5)
    _assert_up(r, R3, 2400 / 1440)


def test_compare_explicit_piece_basis_overrides_dimension():
    # §8 basis 明示 "個"。同じ3商品が個基準になる: 600/12=50, 450/12=37.5, 2400/48=50
    r = _compare(_rolls(), basis="個")
    for n in (R1, R2, R3):
        assert _bases_of(r, n) == {"個"}
    assert _together(r, R1, R2) and _together(r, R2, R3)
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
    # §8 L・kg の別名は基準単位に正規化
    r = _compare(offers_fn(), basis=alias)
    for n in names:
        assert _bases_of(r, n) == {canonical}
        assert label in _label(r, n)


def test_compare_dimension_mismatch_goes_to_unknown_group_auto():
    # §8 過半(3/4 が mass) → g。体積の商品は g の量が読めない = 単価不明
    liquid = "洗濯洗剤 液体 800ml×2本"
    offers = _detergents() + [_offer(liquid, 700)]
    r = _compare(offers)
    assert _bases_of(r, D1) == {"g"}
    assert _together(r, D1, D3)
    assert not _together(r, D1, liquid) and not _together(r, D3, liquid)
    assert _up(r, liquid) is None


def test_compare_explicit_basis_ml_flips_which_group_is_unknown():
    # §8 同じデータで basis="ml" → 液体だけが単価を持ち、g の商品は単価不明
    liquid = "洗濯洗剤 液体 800ml×2本"
    offers = _detergents() + [_offer(liquid, 700)]
    r = _compare(offers, basis="ml")
    assert _bases_of(r, liquid) == {"ml"}
    _assert_up(r, liquid, 700 / 1600)  # 0.4375
    for n in (D1, D2, D3):
        assert _up(r, n) is None
        assert not _together(r, n, liquid)


def test_compare_basis_with_no_readable_quantity_all_unknown():
    r = _compare(_detergents(), basis="ml")
    for n in (D1, D2, D3):
        assert _up(r, n) is None


def test_compare_unreadable_and_low_confidence_have_no_unit_price():
    # §7/§8 単価計算に使うのは high のみ
    none_name = "洗濯洗剤 詰め替え おすすめ"
    low_name = "洗濯洗剤 900g 1000g ×3袋"
    r = _compare(_detergents() + [_offer(none_name, 100), _offer(low_name, 100)])
    assert _up(r, none_name) is None
    assert _up(r, low_name) is None
    assert not _together(r, D1, none_name) and not _together(r, D1, low_name)
    assert _bases_of(r, D1) == {"g"}


def test_compare_minority_dimension_does_not_decide_piece_vs_dimension():
    # §8 過半が同次元でなければ「個」: 電池2件(内容量なし)+洗剤1件 → 個
    # 洗剤は count 6 なので個基準で 3000/6=500
    det = "洗濯洗剤 詰め替え 900g×6袋"
    r = _compare([_offer(T1, 2000), _offer(T3, 4000), _offer(det, 3000)])
    for n in (T1, T3, det):
        assert _bases_of(r, n) == {"個"}
    assert _together(r, T1, det)
    _assert_up(r, det, 500)
    _assert_up(r, T1, 50)


def test_compare_candidate_carries_new_quantity_fields():
    # インターフェース: 各候補に quantity（新項目）と unit_price・unit_price_label
    r = _compare(_detergents())
    c = _cand(r, D1)
    assert isinstance(c.get("unit_price_label"), str)
    q = _find_dict(c, "quantity")
    assert q is not None
    assert q["count_total"] == 6
    assert q["content_dimension"] == "mass"
    assert q["measure_total"] == pytest.approx(5400)
    assert q["confidence"] == "high"


# --- include / exclude ----------------------------------------------------

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
    assert set(_candidates(r)) == {N1, N3, N5}


def test_exclude_terms_drops_if_any_term_in_name():
    # §8 exclude_terms: どれかを含むものは外す。N2(本体) N3(濃縮) N4(業務用) が外れる
    r = _compare(_filter_offers(), exclude_terms=["本体", "濃縮", "業務用"])
    assert set(_candidates(r)) == {N1, N5, N6}


def test_include_and_exclude_combined():
    r = _compare(_filter_offers(), include_terms=["洗濯洗剤", "詰め替え"], exclude_terms=["濃縮"])
    assert set(_candidates(r)) == {N1, N5}


def test_no_terms_keeps_everything():
    r = _compare(_filter_offers())
    assert set(_candidates(r)) == {N1, N2, N3, N4, N5, N6}


def test_filter_terms_are_judged_on_item_name_only():
    # §8 「商品名に含む」。キャプションだけにある語では残らない・外れない
    a = _offer("洗濯洗剤 900g×6袋", 3000, caption="詰め替え用 濃縮")
    b = _offer("洗濯洗剤 詰め替え 900g×6袋", 3000)
    r = _compare([a, b], include_terms=["詰め替え"])
    assert set(_candidates(r)) == {b.item_name}
    r2 = _compare([a, b], exclude_terms=["濃縮"])
    assert set(_candidates(r2)) == {a.item_name, b.item_name}


def test_exclude_count_appears_in_notes():
    # §8 外した件数を notes に出す。3件外す（残り3件）→ いずれかの notes に「3」(Q12)
    r = _compare(_filter_offers(), exclude_terms=["本体", "濃縮", "業務用"])
    notes = _strings_under(r, "notes")
    assert notes, "notes が無い (Q1)"
    assert any("3" in n for n in notes), notes


# --- caveats --------------------------------------------------------------


def _has_caveat(r):
    return any(_nospace(CAVEAT) in _nospace(c) for c in _strings_under(r, "caveats"))


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
# PROVISIONAL: 結果スロットの命名 (Q2) や未確定の挙動 (Q5/Q11/Q12/Q16) に依存する試験
# 実装後に命名が違って落ちた場合は SPEC に結果の形を確定してから再固定する。
# --------------------------------------------------------------------------


def _need_slot(keys, kind):
    assert keys, f"{kind} スロットのキーが結果に見つからない (Q2: 命名が未確定)"


class TestWinnerSlotsProvisional:
    def test_unit_price_cheapest_compares_unrounded_values(self):
        # §8 単価は丸める前の値で比較。A=1000/3000g=33.3333/100g, B=3333/10000g=33.3300/100g
        # 2桁に丸めると両方 33.33 で同点 → 先に並べた A が勝ってしまう。生の値なら B が最安
        a = "洗濯洗剤 業務用 3kg×1袋"
        b = "洗濯洗剤 業務用 10kg×1袋"
        r = _compare([_offer(a, 1000), _offer(b, 3333)])
        keys, names = _unit_slot(r)
        _need_slot(keys, "単位価格最安")
        assert b in names and a not in names

    def test_unit_price_cheapest_ignores_unknown_and_low(self):
        # §8 単価不明・low は最安判定から外す（安い値段でも）。最安は D3 (0.5/g)
        r = _compare(
            _detergents()
            + [_offer("洗濯洗剤 詰め替え おすすめ", 1), _offer("洗濯洗剤 900g 1000g ×3袋", 10)]
        )
        keys, names = _unit_slot(r)
        _need_slot(keys, "単位価格最安")
        assert D3 in names
        assert "洗濯洗剤 詰め替え おすすめ" not in names
        assert "洗濯洗剤 900g 1000g ×3袋" not in names

    def test_desired_quantity_is_in_basis_unit_ml(self):
        # §8 desired_quantity は basis の単位で解釈。basis=ml, desired=10000ml
        # w1 18000ml(1980円) w3 12000ml(1200円) は満たす。w2 6000ml(700円) は満たさない。
        # 複数買い(w2 を2個=1400円)でも 1200円の w3 が最安、単価も w3(0.1/ml) が満たす中で最安
        w1 = "天然水 2L×9本"
        w2 = "天然水 500ml×12本"
        w3 = "ミネラルウォーター 1.5L×8本"
        r = _compare(
            [_offer(w1, 1980), _offer(w2, 700), _offer(w3, 1200)],
            basis="ml",
            desired_quantity=10000,
        )
        keys, names = _desired_slot(r)
        _need_slot(keys, "必要数量を満たす最安")
        assert w3 in names
        assert w2 not in names  # 全体の価格最安 (700円) だが必要量に届かない

    def test_desired_quantity_in_piece_basis(self):
        # §8 basis=個, desired=100 → 100本以上: T3(100本, 4000円)。T1/T2 は40本で足りない
        # 複数買いでも T1×3=6000, T2×3=5400 > 4000
        r = _compare(_batteries(), basis="個", desired_quantity=100)
        keys, names = _desired_slot(r)
        _need_slot(keys, "必要数量を満たす最安")
        assert T3 in names
        assert T1 not in names and T2 not in names

    def test_shipping_unknown_total_cheapest_not_asserted(self):
        # §8 送料不明なら支払総額最安を断定しない (Q11)
        offers = [
            _offer(B1, 1980, shipping_status="unknown"),
            _offer(B3, 1200, shipping_status="unknown"),
        ]
        r = _compare(offers)
        _cand(r, B1)  # 結果が空でないこと（スロットが無いだけで素通りさせない）
        keys, names = _total_slot(r)

        def all_strings(node):
            if isinstance(node, str):
                yield node
            elif isinstance(node, dict):
                for v in node.values():
                    yield from all_strings(v)
            elif isinstance(node, list):
                for v in node:
                    yield from all_strings(v)

        mentions = any("送料" in s for s in all_strings(r))
        assert (not names) or mentions, "送料不明なのに総額最安を無言で断定している"

    def test_total_cheapest_includes_shipping_fee(self):
        # §8 支払総額 = 価格+送料。X: 1000+800=1800 (別途)、Y: 1500 (込み)。
        # 同じ 12000ml なので 単位価格最安は X (1000/12000)、総額最安は Y
        x = "天然水 2L×6本 送料別"
        y = "天然水 2L×6本 送料込"
        r = _compare(
            [
                _offer(x, 1000, shipping_status="separate", shipping_fee=800),
                _offer(y, 1500, shipping_status="included"),
            ]
        )
        ukeys, unames = _unit_slot(r)
        tkeys, tnames = _total_slot(r)
        _need_slot(ukeys, "単位価格最安")
        _need_slot(tkeys, "支払総額最安")
        assert x in unames and y not in unames
        assert y in tnames and x not in tnames

    def test_unknown_count_is_reported_in_caveats(self):
        # §8 単価不明の件数を caveats に出す。2件 → caveats のどこかに「2」と「不明」(Q12)
        r = _compare(
            _detergents()
            + [_offer("洗濯洗剤 詰め替え おすすめ", 100), _offer("洗濯洗剤 900g 1000g ×3袋", 100)]
        )
        cav = " ".join(_strings_under(r, "caveats"))
        assert "不明" in cav and "2" in cav


class TestParseProvisional:
    def test_no_counter_word_means_single_piece(self):
        # §7 「単独なら単体」からの推測 (Q5)。2L の1本 → count 1, measure 2000
        q = _parse("ミネラルウォーター 2L")
        assert _field(q, "count_total") == 1
        assert _field(q, "measure_total") == pytest.approx(2000)
        assert _conf(q) == "high"

    def test_fullwidth_digits_and_letters(self):
        # Q16
        q = _parse("洗濯洗剤 詰め替え ９００ｇ×６袋")
        assert _field(q, "count_total") == 6
        assert _field(q, "content_amount") == pytest.approx(900)

    def test_x_as_multiplication_sign(self):
        # Q16
        q = _parse("洗濯洗剤 詰め替え 900g x 6袋")
        assert _field(q, "count_total") == 6
        assert _field(q, "content_amount") == pytest.approx(900)


# --------------------------------------------------------------------------
# 試験部品の自己検査（実装に依存しない。今も通る）
# --------------------------------------------------------------------------


@dataclasses.dataclass
class _FakeQ:
    count_total: int
    measure_total: float


@dataclasses.dataclass
class _FakeOffer:
    item_name: str
    quantity: _FakeQ


@dataclasses.dataclass
class _FakeCand:
    offer: _FakeOffer
    unit_price: float | None
    unit_price_label: str


@dataclasses.dataclass
class _FakeGroup:
    basis: str
    dimension: str | None
    items: list


@dataclasses.dataclass
class _FakeResult:
    groups: list
    cheapest_unit_price: _FakeCand | None
    caveats: list
    notes: list


def _fake_result():
    a = _FakeCand(_FakeOffer("A 900g×6袋", _FakeQ(6, 5400)), 0.5555, "100g あたり")
    b = _FakeCand(_FakeOffer("B 2kg×1個", _FakeQ(1, 2000)), 0.5, "100gあたり")
    u = _FakeCand(_FakeOffer("U ???", _FakeQ(0, 0)), None, "")
    return _FakeResult(
        groups=[_FakeGroup("g", "mass", [a, b]), _FakeGroup(None, None, [u])],
        cheapest_unit_price=b,
        caveats=[CAVEAT],
        notes=["3件を除外"],
    )


class TestHelpersSelfCheck:
    def test_candidates_and_groups_found_in_nested_structure(self):
        p = _plain(_fake_result())
        assert set(_candidates(p)) == {"A 900g×6袋", "B 2kg×1個", "U ???"}
        assert _bases_of(p, "A 900g×6袋") == {"g"}
        assert _together(p, "A 900g×6袋", "B 2kg×1個")
        assert not _together(p, "A 900g×6袋", "U ???")
        assert _up(p, "U ???") is None

    def test_label_and_factor(self):
        p = _plain(_fake_result())
        assert _label(p, "A 900g×6袋") == "100gあたり"
        assert _factor(_label(p, "A 900g×6袋")) == 100
        assert _factor("1mあたり") == 1

    def test_assert_up_accepts_both_scales(self):
        p = _plain(_fake_result())
        _assert_up(p, "B 2kg×1個", 0.5)
        p["groups"][0]["items"][1]["unit_price"] = 50.0
        _assert_up(p, "B 2kg×1個", 0.5)
        with pytest.raises(AssertionError):
            _assert_up(p, "B 2kg×1個", 0.7)

    def test_strings_and_caveat(self):
        p = _plain(_fake_result())
        assert _has_caveat(p)
        assert _strings_under(p, "notes") == ["3件を除外"]

    def test_slot_names_find_by_key_substring(self):
        p = _plain(_fake_result())
        keys, names = _unit_slot(p)
        assert keys == ["cheapest_unit_price"] and names == {"B 2kg×1個"}
        tkeys, _ = _total_slot(p)
        assert tkeys == []

    def test_offer_helper_prefilled_fields(self):
        from shopping.models import Offer  # 現行の Offer 定義 (フィールド名) だけに依存

        o = _offer("テスト 12個", 100)
        assert isinstance(o, Offer)
        assert o.item_name == "テスト 12個" and o.price == 100
        assert o.mall_item_code.startswith("blind:")
