# @owns WP9「型番の内側に現れる同じ表記」と「+ でつながれた構成品の個数」の P0 違反の機構ごとの自作確認。独立試験（ブラインド）の代わりではない
"""WP9: 追加E2E（ChatGPT 起点 60件）の実題名で残った、数量の高信頼の誤り2件の機構を low に倒す（SPEC §7 P0 の徹底）。

機構（語のリストではなく位置・同一性で判定）:
  E1 採用した量（数字＋単位・数え語）と同じ表記が、同じ題名の英数字の語（型番）の内側にも現れる
     （80L とうもろこし … ICBK80L）。独立した量か型番の一部か決められないので low。
     型番だけの題名（独立した 80L が無い）は従来どおり量にしない。
  E2 + ・ & でつながれた構成品の列の中の個数（本体+バッテリ2個+充電器）は、商品全体の個数ではない。low。
どの機構にも、各4件以上の別の言い回しを入れる。真値どおり high のまま残る形も同じ表で固定する。
"""
import pytest

from shopping.quantity import parse_quantity

LOW = {
    "E1": [
        "EPSON エプソン 純正インクカートリッジ 増量タイプ 80L とうもろこし 黒 適合プリンター:EP-982A3 EP-979A3 EP-808A EP-807A ブラック ICBK80L ◆メ",
        "エプソン ICBK80L 純正 80L 増量",
        "エプソン 増量 80L ICBK80L",
        "洗剤 詰め替え S-500ml 500ml",
        "水 NB500ml 500ml×24本",
        "お米 KG-5kg 5kg",
        "ストロー ST-100本 100本入り",
        "ゴミ袋 GP45L 45L 30枚",
        "水 天然水 500ml 24本 型番 KX-500ml",
    ],
    "E2": [
        "【ポイント10倍】マキタ 18V 充電式インパクトドライバー セット品 TD173 純正 本体+バッテリ2個+充電器+収納ケース 正規品 makita TD173DRGX TD173DRGXB TD173DRGXO ブルー ブラック オリーブ イエロー パープル 青 黒 紫 黄 BL1860B",
        "本体+電池2本",
        "掃除機 本体＋替えブラシ4本",
        "掃除機 本体+バッテリー2個+充電器",
        "12ロール+2ロール増量",
        "500ml×24本+おまけ1本",
        "本体+替え刃3個",
        "本体 + バッテリ2個 + 充電器",
        "本体＆ケース2個",
        "インパクトドライバ 本体+3.0Ah電池x2個+急速充電器+ケース",
    ],
}

# 真値どおり high のまま残る形（落ちてはいけない）。(題名, 個数, 1個あたりの内容量)
HIGH = [
    ("水 500ml×24本", 24, 500.0),
    ("トイレットペーパー 12ロール×4パック(48ロール)", 48, None),
    ("水 450ml×3本セット", 3, 450.0),
    ("Pepsi MAX 500ml 24本", 24, 500.0),
    ("天然水500ml24本 24本入り", 24, 500.0),
    ("ケーブル USB-C 1m 2本セット", 2, 1.0),
    ("SH-12M ケーブル 3本セット 1m", 3, 1.0),
    ("BIGCAPA basic＋ 単3形アルカリ乾電池20本パック", 20, None),
    ("Gillette Fusion5+1 髭剃り 替刃4個入", 4, None),
    ("ドッグフード 成犬用 ラム&ライス 12kg (3kg×4袋) 国産", 4, 3000.0),
    ("ティシュー(5箱パック) (+Water) 5箱パック", 5, None),
]

# 型番の内側にしか無い量は量にしない（従来どおり。low か none であって high にはならない）
NO_QUANTITY = [
    "エプソン ICBK80L 純正 インク",
    "洗剤 型番 S-500ml 詰め替え",
    "ストロー ST-100本",
]


@pytest.mark.parametrize("mech,title", [(m, t) for m, ts in LOW.items() for t in ts])
def test_embedded_or_bundled_quantity_is_low(mech, title):
    q = parse_quantity(title)
    assert q.confidence == "low", (mech, title, q)
    assert q.count_total is None and q.measure_total is None


@pytest.mark.parametrize("title,count,amount", HIGH)
def test_unrelated_forms_stay_high(title, count, amount):
    q = parse_quantity(title)
    assert q.confidence == "high" and q.count_total == count and q.content_amount == amount, q


@pytest.mark.parametrize("title", NO_QUANTITY)
def test_quantity_only_inside_a_model_word_is_not_a_quantity(title):
    q = parse_quantity(title)
    assert q.confidence != "high" and q.count_total is None and q.measure_total is None, q


def test_each_mechanism_has_at_least_four_variants():
    assert all(len(v) >= 4 for v in LOW.values())


def test_e1_compares_the_canonical_identity_not_the_raw_text():
    # 80L と 80リットル は同じ量。型番の内側の 80L と、独立した 80リットル も食い違わない=同じ量なので low
    assert parse_quantity("エプソン 80リットル ICBK80L").confidence == "low"
    # 型番の内側が別の量（ICBK80L と 100ml）なら、この規則は何もしない（従来の読み）
    q = parse_quantity("水 ICBK80L 100ml 3本")
    assert q.confidence == "high" and q.count_total == 3 and q.content_amount == 100.0
