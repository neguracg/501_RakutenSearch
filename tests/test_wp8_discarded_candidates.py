# @owns WP8-1「採らなかった候補の検査」（SPEC §7 P0 の徹底）の機構ごとの自作確認。独立試験（ブラインド）の代わりではない
"""WP8-1: 題名に現れた「数字＋計量単位・数え語」のうち、読まずに捨てた物も P0 の候補に含める。
採用した総数・内容量と食い違えば low、同じ数なら言い直しなので high のまま。

機構（語のリストではなく、トークン化で候補から落ちる経路ごと）:
  M1 先頭に書かれた個数（【48本】）と、後ろの空白だけでつないだ鎖（48本 2ケース）で総数の候補が食い違う
  M2 「最大／最小」の後ろの量・個数（最大700g）は上限の記述で採らないが、採用した内容量・個数と食い違う
  M3 区切り（_ /）の後ろの択一（シングル_55m・1本/3本セット）と、直前の量に続くハイフンの範囲（500g-1kg）
  M4 直前の量・個数にそのまま続く数字（500ml24本・30m12Rダブル）を型番として黙って捨てない
どの機構にも、各3件以上の別の言い回しを入れる。真値どおり high のまま残る形も同じ表で固定する。
"""
import pytest

from shopping.quantity import parse_quantity

LOW = {
    "M1": [
        "【24本】 炭酸水 500ml 24本 2ケース",
        "【12個】 洗剤 詰め替え 400ml 12個 3パック",
        "【30枚】 マスク 30枚 2パック",
        "【6缶】 ビール 350ml 6缶 4ケース",
    ],
    "M2": [
        "ナッツ 最大1kg 500g 小分け",
        "洗剤 最大2L 1L つめかえ",
        "ラップ 50m 最大100m",
        "コーヒー 200g 3袋 最大6袋",
        "水 500ml 24本 最大2ケース",
    ],
    "M3": [
        "洗剤 500ml 24本 ダブル_1L",
        "洗剤 500g 5袋 プレーン_1kg",
        "歯磨き粉 150g 2個/4個セット",
        "ハミガキ 100g 1本/2本/3本セット",
        "お米 5kg/10kg 選べる",
        "トイレットペーパー 12ロール 55m/30m",
        "ナッツ 500g-1kg 選べる",
        "お茶 500ml/24本入り",
    ],
    "M4": [
        "水 500ml24本",
        "水 2L6本",
        "洗剤 200g5袋",
        "コアレス トイレットペーパー30m12Rダブル",
    ],
}

# 内容量・個数を複数の言い方で書いた（言い直し）形は、同じ数なので high のまま
HIGH = [
    ("トイレットペーパー 12ロール×4パック(48ロール)", 48, None),
    ("水 500ml×24本", 24, 500.0),
    ("水 24本 (500ml×24)", 24, 500.0),
    ("米 200g×5袋", 5, 200.0),
    ("水 500ml 24本", 24, 500.0),
    ("洗剤 500ml 12本入り 2ケース 12本入り", 24, 500.0),
    ("ティッシュ 5箱 ×12パック 60箱", 60, None),
    ("ナッツ 最大500g 500g", 1, 500.0),
    ("水 2L 6本 最大6本", 6, 2000.0),
    ("ケーブル USB-C 1m 2本セット", 2, 1.0),
    ("SH-12M ケーブル 3本セット 1m", 3, 1.0),
    ("お茶 500ml/本 24本", 24, 500.0),
    ("【選べるセット品】乾電池 単3 単4 40本セット", 40, None),
]


@pytest.mark.parametrize("mech,title", [(m, t) for m, ts in LOW.items() for t in ts])
def test_discarded_candidate_that_disagrees_with_the_adopted_value_is_low(mech, title):
    q = parse_quantity(title)
    assert q.confidence == "low", (mech, title, q)
    assert q.count_total is None and q.measure_total is None


@pytest.mark.parametrize("title,count,amount", HIGH)
def test_restated_or_unrelated_forms_stay_high(title, count, amount):
    q = parse_quantity(title)
    assert q.confidence == "high" and q.count_total == count and q.content_amount == amount, q


def test_each_mechanism_has_at_least_three_variants():
    assert all(len(v) >= 3 for v in LOW.values())


# 実題名 T1〜T7（E2E 80件・2026-11-06）。corpus/unseen4_patterns.py と同じ題名で、低信頼の向きを直接固定する
def test_e2e_real_titles_t1_to_t6_are_low_and_t7_stays_high():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parent / "corpus" / "unseen4_patterns.py"
    spec = importlib.util.spec_from_file_location("unseen4", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    titles = [t for t, _ in mod.P]
    assert len(titles) == 7
    for t in titles[:6]:
        assert parse_quantity(t).confidence == "low", t
    q = parse_quantity(titles[6])
    assert q.confidence == "high" and q.count_total == 40
