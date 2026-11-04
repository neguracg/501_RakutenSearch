import pytest

from shopping.quantity import parse_quantity


@pytest.mark.parametrize("text,per,packs,total", [
    ("トイレットペーパー 12ロール×4袋", 12, 4, 48),
    ("12ロール×3パック", 12, 3, 36),
    ("12R×6", 12, 6, 72),
    ("12ロール x 4パック", 12, 4, 48),
    ("12ロール入×3", 12, 3, 36),
    ("（12ロール）×4セット", 12, 4, 48),
    ("(12ロール)×4セット", 12, 4, 48),
    ("１２ロール×４袋", 12, 4, 48),          # 全角数字
    ("12ロール＊6", 12, 6, 72),
    ("12ロール入り 4パック", 12, 4, 48),
    ("12ロール×4袋×2箱", 12, 8, 96),
    ("12ロール", 12, 1, 12),                  # 単品
    ("12r×6", 12, 6, 72),
])
def test_notation_variants_high(text, per, packs, total):
    q = parse_quantity(text)
    assert (q.per_pack, q.pack_count, q.total, q.confidence) == (per, packs, total, "high")
    assert q.unit == "ロール" and q.evidence


def test_single_item_pack_count_is_one():
    q = parse_quantity("トイレットペーパー 12ロール シングル")
    assert q.pack_count == 1 and q.total == 12 and q.ply == "single"


def test_ac4_totals():
    assert [parse_quantity(f"12ロール×{n}").total for n in (3, 4, 6)] == [36, 48, 72]


@pytest.mark.parametrize("text,ply", [
    ("12ロール×4袋 ダブル", "double"),
    ("12ロール 2枚重ね", "double"),
    ("12ロール 2枚重", "double"),
    ("12ロール シングル", "single"),
    ("12ロール 1枚重ね", "single"),
    ("12ロール 1枚", "single"),
    ("12ロール", None),
    ("12ロール シングル ダブル 選べる", None),   # 矛盾は確定しない
    ("12ロール 21枚入", None),                    # 21枚 を 1枚 と誤読しない
])
def test_ply(text, ply):
    assert parse_quantity(text).ply == ply


@pytest.mark.parametrize("text,length", [
    ("12ロール ダブル 30m", 30.0),
    ("12ロール シングル 27.5m", 27.5),
    ("12ロール 25メートル", 25.0),
    ("12ロール 30ｍ", 30.0),                      # 全角
    ("12ロール", None),
    ("12ロール 2倍巻き", None),                   # 倍巻きは長さを確定しない
    ("12ロール 2倍巻き 55m", None),
    ("12ロール 30m 1440m", None),                 # 食い違う長さは確定しない
    ("12ロール 幅114mm", None),                   # mm は長さではない
])
def test_length(text, length):
    assert parse_quantity(text).length_m == length


def test_length_is_not_taken_as_pack_count():
    q = parse_quantity("12ロール×30m")
    assert q.length_m == 30.0 and q.total == 12 and q.pack_count == 1


def test_per_roll_length_not_counted_as_roll():
    q = parse_quantity("12ロール×4袋 1ロール30m")
    assert q.total == 48 and q.confidence == "high" and q.length_m == 30.0
    q = parse_quantity("12ロール 1ロールあたり 25m")
    assert q.total == 12


def test_double_length_roll_equivalent_not_counted():
    q = parse_quantity("12ロール（24ロール分）シングル")
    assert q.total == 12 and q.confidence == "high"
    q = parse_quantity("12ロール×4袋 通常の96ロール相当")
    assert q.total == 48


def test_conflicting_totals_are_low_and_none():
    q = parse_quantity("トイレットペーパー 48ロール 送料無料 72ロール")
    assert q.total is None and q.confidence == "low" and "48" in q.evidence and "72" in q.evidence
    q = parse_quantity("12ロール×4袋 / 12ロール×6袋")
    assert q.total is None and q.confidence == "low"


def test_same_total_twice_is_high():
    q = parse_quantity("12ロール×4袋 合計48ロール")
    assert q.total == 48 and q.confidence == "high"


def test_pack_description_same_as_per_pack_is_not_conflict():
    q = parse_quantity("12ロール×4袋 1袋12ロール入り")
    assert q.total == 48 and q.confidence == "high"


@pytest.mark.parametrize("text", ["", "トイレットペーパー", "ティッシュ 5箱", None])
def test_unreadable_is_none(text):
    q = parse_quantity(text)
    assert q.confidence == "none" and q.total is None and q.evidence == ""


def test_implausible_total_is_low():
    q = parse_quantity("99999ロール")
    assert q.total is None and q.confidence == "low"


def test_ply_and_length_kept_even_when_total_unknown():
    q = parse_quantity("ダブル 30m トイレットペーパー")
    assert q.confidence == "none" and q.ply == "double" and q.length_m == 30.0


def test_other_unit():
    q = parse_quantity("ティッシュ 5箱×12パック", unit="箱")
    assert (q.total, q.confidence, q.unit) == (60, "high", "箱")


def test_does_not_match_inside_words():
    # ROLL を含む英単語・R で始まる単語を「R」と読まない
    q = parse_quantity("12 RICH PAPER")
    assert q.confidence == "none"
