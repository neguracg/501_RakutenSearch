# @owns P5「捨てた数の検査」の全数え語×続く語の表（SPEC §7 P5 補足）の自作確認。独立試験（ブラインド）の代わりではない
"""WP7: 数え語表の全語 × 販促・購入・期間の語。「真の個数＋空白なし直結」は、採用した総数と食い違えば low、一致なら high。
除外は SPEC 例示の3型（ヶ/ケ＋月・点＋購入/以上/まで/で・P＋還元/倍/UP/アップ/増量/ポイント）の組だけ。"""
import pytest

from shopping import quantity
from shopping.quantity import COUNTERS, parse_quantity

SUFFIXES = ["で", "ポイント", "増量", "還元", "UP", "アップ", "購入", "以上", "月"]

# 個数の候補ではないと分かっている組（捨てた数の検査から外す）。ここに無い組は検査する
KNOWN = {("ヶ", "月"), ("ケ", "月"),
         ("点", "購入"), ("点", "以上"), ("点", "で"),
         ("P", "還元"), ("P", "UP"), ("P", "アップ"), ("P", "ポイント"), ("P", "増量")}


# 既知の限界 R3（SPEC §7）: 英字で終わる数え語の直後に英字が続くと、数え語として拾わず（型番・英単語の一部とみなす）、
# 捨てた数にもならない。strict なので、直したら気づく
R3 = {(c, "UP") for c in COUNTERS if c.isascii() and c.isalpha() and c.lower() != "p"}


def _cases(with_r3_xfail=False):
    for c in COUNTERS:
        for s in SUFFIXES:
            marks = []
            if with_r3_xfail and (c, s) in R3:
                marks = [pytest.mark.xfail(reason="R3: 英字の数え語＋英字は捨てた数にならない", strict=True)]
            yield pytest.param(c, s, id=f"{c}+{s}", marks=marks)


@pytest.mark.parametrize("counter,suffix", list(_cases(with_r3_xfail=True)))
def test_mismatching_true_count_glued_to_a_word_is_low_unless_a_known_pair(counter, suffix):
    # 総数は 1（内容量だけ）、捨てた数は 6。食い違うので、既知の非個数の組以外は low
    q = parse_quantity(f"洗剤 500ml 6{counter}{suffix}")
    if (counter, suffix) in KNOWN:
        assert q.confidence == "high" and q.count_total == 1
    else:
        assert q.confidence == "low", (counter, suffix, q)


@pytest.mark.parametrize("counter,suffix", list(_cases()))
def test_matching_true_count_glued_to_a_word_stays_high(counter, suffix):
    # 捨てた数（6）が採用した総数（6本入り＝6）と同じなら言い直しなので high のまま
    q = parse_quantity(f"洗剤 500ml 6本入り 6{counter}{suffix}")
    assert q.confidence == "high" and q.count_total == 6, (counter, suffix, q)


@pytest.mark.parametrize("title", ["洗剤 500ml 6個で1000円", "オレンジジュース 195g缶 30本ポイント10倍",
                                   "炭酸水 500ml 24缶ポイント10倍", "ゼリー 130g 6個で1000円ポッキリ"])
def test_a4_count_words_other_than_the_three_pairs_are_checked(title):
    assert parse_quantity(title).confidence == "low"


@pytest.mark.parametrize("title", ["サプリ 90粒 12ヶ月保証", "サプリ 90粒 12ケ月分", "洗剤 900g×6 2点で送料無料",
                                   "洗剤 900g×6 3点以上でポイント5倍", "洗剤 900g×6 2点購入",
                                   "トイレットペーパー 12ロール 10Pポイント還元", "トイレットペーパー 12ロール 5P増量"])
def test_a4_the_three_known_pairs_are_not_checked(title):
    assert parse_quantity(title).confidence == "high"


def test_a4_the_exclusion_is_keyed_by_counter_not_a_global_word_list():
    assert set(quantity._KNOWN_NOT_COUNT) == {"ヶ", "ケ", "点", "p"}


# --- B1: 捨てた数が採用した総数より小さい時も食い違い -----------------------------------------

@pytest.mark.parametrize("title", ["洗剤 500ml 12本入り 2個付き", "水 500ml 24本入り 2本おまけ", "洗剤 500ml 12個入り 3個送料無料"])
def test_b1_a_dropped_count_smaller_than_the_total_is_also_a_disagreement(title):
    assert parse_quantity(title).confidence == "low"
