# @owns 商品名からの数量（個数 × 1個あたり内容量）の読み取り・単位換算表・信頼度判定
"""数量の読み取り。商品の意味（種類・仕様の違い）は持たない。

読むのは「個数」と「1個あたりの内容量（数値＋計量単位）」だけ。単位は表（UNITS / DISPLAY / COUNTERS）で
持ち、表に1行足すだけで増える（単位ごとの if 分岐は書かない）。読めない・矛盾する時は推測で埋めず
total=None にする。
"""
from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass, field

from .models import QuantityInfo

# 単位の換算表: 別名 → (次元, 基準単位への係数)。大文字小文字・全角半角は区別せずに引く（NFKC＋casefold。
# 照合キーが同じになる別名は書かない: mL は ml、ℓ は L と同じ。import 時に検査する）。
UNITS: dict[str, tuple[str, float]] = {
    "ml": ("volume", 1), "cc": ("volume", 1),
    "L": ("volume", 1000), "リットル": ("volume", 1000),
    "ミリリットル": ("volume", 1),
    "g": ("mass", 1), "kg": ("mass", 1000), "mg": ("mass", 0.001),
    "グラム": ("mass", 1), "キログラム": ("mass", 1000),
    "m": ("length", 1), "メートル": ("length", 1), "cm": ("length", 0.01), "mm": ("length", 0.001),
    "km": ("length", 1000), "センチメートル": ("length", 0.01), "ミリメートル": ("length", 0.001),
    "W": ("power", 1), "ワット": ("power", 1), "kW": ("power", 1000), "キロワット": ("power", 1000),
    "mAh": ("charge", 1), "Ah": ("charge", 1000),
    "Wh": ("energy", 1), "kWh": ("energy", 1000),
}

# 表示用: 次元 → (単価を出す時の倍率, ラベル)。ラベルの先頭の数字を除いた部分（"ml" 等）が基準単位名。
DISPLAY: dict[str, tuple[float, str]] = {
    "volume": (100, "100mlあたり"),
    "mass": (100, "100gあたり"),
    "length": (1, "1mあたり"),
    "power": (1, "1Wあたり"),
    "charge": (1, "1mAhあたり"),
    "energy": (1, "1Whあたり"),
    "count": (1, "1個あたり"),
}

# 数え語: 別名 → 正規の数え語。（"R" は「ロール」の略）
COUNTERS: dict[str, str] = {
    "個": "個", "本": "本", "枚": "枚", "袋": "袋", "箱": "箱", "パック": "パック", "缶": "缶",
    "ロール": "ロール", "R": "ロール", "roll": "ロール", "rolls": "ロール",
    "セット": "セット", "組": "組", "足": "足", "着": "着", "台": "台", "錠": "錠", "包": "包",
    "粒": "粒", "ケース": "ケース", "玉": "玉", "束": "束", "巻": "巻", "食": "食", "回分": "回分",
    "点": "点", "冊": "冊", "ペア": "ペア", "ヶ": "個", "ダース": "個",
    "P": "パック", "pc": "個", "pcs": "個",
    "コ": "個", "ケ": "個", "膳": "膳",
}

# 数え語の倍率（別名 → 倍）。ダースは 12 個。ただし内側の個数がある時（12本入り 2ダース）は袋数と同じ扱いで倍率を掛けない
COUNT_MULTIPLIERS: dict[str, int] = {"ダース": 12}

# 使用回数・換算の説明であって個数ではない数え語（S1）。計量値や他の個数が名前にある時は数えない
SERVING_WORDS = frozenset({"回分"})

# 「12ロール 4パック」のように空白だけで続けても掛け算にする、入れ物を表す数え語
CONTAINERS = frozenset({"パック", "袋", "セット", "ケース", "梱"})

# P4: 同じ数が続く時に「外側の入れ物」として掛け算にする容器語（3個入り 3セット → 9）
OUTER_WORDS = frozenset({"セット", "ケース", "パック", "箱", "袋"})

# 数え語としての条件が文脈で変わる語（P3・X1）。表の別名（正規化後）で持つ
MONTH_COUNTERS = frozenset({"ヶ", "ケ"})       # 直後が「月」なら期間（12ヶ月保証）で個数ではない
SOLO_LOW_COUNTERS = frozenset({"P"})           # ×・入数に続かない単独の NP は high にしない（60P 対応）
MAX_PACK_P = 99                                # P は 1〜99 だけ個数の候補（1080P は画質）

MAX_PLAUSIBLE_COUNT = 100_000
MAX_DIGITS = 9                      # 数値は千区切りを除いて 9 桁まで（S6）

_FILL = r"(?:入り?|入数|セット|組|パック|袋|箱|ケース|梱|各|の)"
_GAP_X = re.compile(rf"\s*(?:{_FILL}\s*)*[×x*]\s*")
_GAP_LABEL = re.compile(rf"\s*(?:{_FILL}\s*)*[×x*]\s*[^\d×x*\s]{{0,4}}\s*")
_GAP_PLAIN = re.compile(r"\s*(?:(?:入り?|入数|約|各)\s*)*")
# 個数と内容量のあいだ（2枚組 34cm）。数え語の間（_GAP_PLAIN）より読み飛ばす語を広げる
_GAP_COUNT_MEASURE = re.compile(rf"\s*(?:(?:入り?|入数|約|各|セット|組|パック|袋|箱|ケース|梱|の)\s*)*")
# 数値の形。桁数の検査は _tokens 側で行う（9 桁を超える数は数量にせず low。出店者の書いた巨大な数字列で
# float が inf になり int() が落ちる事故も防ぐ）
_NUM = r"(?<![\d.,])\d[\d,]*(?:\.\d+)?"
_THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+")
_AFTER_SKIP = re.compile(r"\s*(?:分(?![a-z])|相当|換算|あたり|当たり|当り|につき|ごと|限定|まで|以上|以下|以内|未満|から|ずつ)")
_BEFORE_SKIP = re.compile(r"(?:最大|最小)\s*$")
# 販促・価格表記（数量ではない）
_PROMO = [
    re.compile(r"\d+(?:\.\d+)?\s*倍"),                                   # ポイント10倍・2倍
    re.compile(r"\d+(?:\.\d+)?\s*%"),                                    # 最大50%OFF
    re.compile(r"\d[\d,]*(?:\.\d+)?\s*円"),                              # 1000円ポッキリ・1,980円
]


def _norm(s: str) -> str:
    """照合用の正規化: NFKC＋casefold（全角半角・大文字小文字を区別しない。ℓ→l、L→l）。"""
    return unicodedata.normalize("NFKC", s or "").casefold()


def _normalize(text: str) -> str:
    s = _norm(text)
    for ch in "✕✖⨯":
        s = s.replace(ch, "×")
    s = re.sub(r"[()\[\]{}【】「」『』〈〉《》<>]", " ", s)
    for pat in _PROMO:
        s = pat.sub(" ", s)
    return s


# ---- 表の引き方（表を直接書き換えても効くよう、使う時に引く） ----

def _unit_table() -> dict[str, tuple[str, float]]:
    return {_norm(k): v for k, v in UNITS.items()}


def _counter_table() -> dict[str, str]:
    return {_norm(k): v for k, v in COUNTERS.items()}


def _multiplier_table() -> dict[str, int]:
    return {_norm(k): v for k, v in COUNT_MULTIPLIERS.items()}


def _check_tables() -> None:
    """表の整合を import 時に検査する（S11）。直し忘れは起動できない形で知らせる。"""
    missing = sorted({dim for dim, _ in UNITS.values() if dim not in DISPLAY})
    if missing:
        raise RuntimeError(f"UNITS の次元に DISPLAY の行が無い: {missing}")
    for name, table in (("UNITS", UNITS), ("COUNTERS", COUNTERS)):
        seen: dict[str, str] = {}
        for key in table:
            norm = _norm(key)
            if norm in seen:
                raise RuntimeError(f"{name} の別名が NFKC＋casefold で重複: {seen[norm]!r} と {key!r}")
            seen[norm] = key


_check_tables()


def resolve_unit(alias: str) -> tuple[str, float] | None:
    """単位の別名 → (次元, 係数)。無ければ None。"""
    return _unit_table().get(_norm(alias).strip())


def base_unit(dimension: str) -> str:
    """次元の基準単位名（"ml" 等）。表示ラベルの先頭の数字と「あたり」を除いたもの。"""
    label = DISPLAY[dimension][1]
    m = re.fullmatch(r"[\d.]+(.+?)あたり", label)
    return m.group(1) if m else label


def resolve_basis(basis: str) -> tuple[str, str]:
    """比べる単位の指定 → (基準単位名, 次元)。"個" は ("個", "count")。別名（L・kg 等）は基準単位に直す。
    表に無ければ ValueError。"""
    if isinstance(basis, str):
        b = basis.strip()
        if b in ("個", "count"):
            return "個", "count"
        hit = resolve_unit(b)
        if hit is not None and hit[0] in DISPLAY:
            return base_unit(hit[0]), hit[0]
        for dim in DISPLAY:
            if dim != "count" and _norm(base_unit(dim)) == _norm(b):
                return base_unit(dim), dim
    raise ValueError("invalid basis")


def basis_choices() -> list[str]:
    """比べる単位として選べる基準単位名（"個" と、表にある次元の基準単位）。"""
    return ["個"] + [base_unit(d) for d in DISPLAY if d != "count"]


def dimension_of_basis(name: str) -> str:
    return resolve_basis(name)[1]


# ---- 表示用の数の整形（指数表記を使わない。S10）----

def format_amount(x: float | None) -> str:
    """量の表示。整数は千区切り（1,000,000）、小数は末尾の 0 を落として 9 桁まで。指数表記にしない。"""
    if x is None:
        return ""
    if x == int(x):
        return f"{int(x):,}"
    return f"{x:,.9f}".rstrip("0").rstrip(".")


def unit_price_digits(x: float) -> int:
    """単価の小数桁数（唯一の実装）。通常は 2 桁。2 桁で 0.00 になってしまう小さな正の値は有効数字が出るまで
    増やす（最大 4 桁。S10）。"""
    for digits in (2, 3):
        if x <= 0 or round(x, digits) != 0:
            return digits
    return 4


def round_unit_price(x: float | None) -> float | None:
    """JSON など数値で出す単価の丸め（桁数は unit_price_digits）。"""
    return None if x is None else round(x, unit_price_digits(x))


def format_unit_price(x: float) -> str:
    """単価の表示（円）。桁数は unit_price_digits。"""
    return f"{x:,.{unit_price_digits(x)}f}"


# ---- 読み取り ----

@dataclass
class _Tok:
    kind: str                 # "count" / "measure" / "bare"
    start: int
    end: int
    n: float = 0.0            # count/bare: 個数、measure: 基準単位に直した量
    word: str = ""            # count: 正規の数え語
    dim: str = ""             # measure: 次元
    mult: int = 1             # count: 数え語の倍率（ダース=12）
    solo_low: bool = False    # count: 単独だと high にしない数え語（P。X1）


@dataclass
class _Group:
    toks: list[_Tok] = field(default_factory=list)

    @property
    def factors(self) -> list[_Tok]:
        return [t for t in self.toks if t.kind in ("count", "bare")]

    @property
    def measures(self) -> list[_Tok]:
        return [t for t in self.toks if t.kind == "measure"]


def _alt(keys) -> str:
    out = []
    for k in sorted(set(keys), key=lambda x: (-len(x), x)):
        piece = re.escape(k)
        if k[-1:].isascii() and k[-1:].isalpha():
            piece += r"(?![a-wyz]|x(?!\s*\d))"
        out.append(piece)
    return "|".join(out)


@functools.lru_cache(maxsize=8)
def _token_re(unit_keys: tuple[str, ...], counter_keys: tuple[str, ...]):
    return re.compile(
        rf"(?P<num>{_NUM})\s*(?:(?P<unit>{_alt(unit_keys)})(?!サイズ)|(?P<counter>{_alt(counter_keys)})(?!ー))")


_IRI_AFTER = re.compile(r"\s*入")
_P_NOT_COUNT = re.compile(r"\s*(?:還元|倍|up|アップ|ポイント|増量)")
_TEN_NOT_COUNT = re.compile(r"\s*(?:購入|以上|まで|で)")
_BARE_RE = re.compile(r"(?:[×*]|(?<![a-z])x)\s*(\d+)(?![\d.]|[a-z])")
# 数字の直後に続く語（表にあるかどうかは別途判定する）
_WORD_AFTER_NUM = re.compile(r"(?<![\d.,])(\d{1,9})([^\W\d_]+)")
_UNK_BEFORE = re.compile(r"(?:[×*]|(?<![a-z])x|入数)\s*$")
_UNK_AFTER = re.compile(r"\s*(?:入り?|入数)?\s*(?:[×*]|x)\s*\d")


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _digits_ok(raw: str) -> bool | None:
    """数値の文字列の桁検査。True=読める、False=桁が多すぎる（low）、None=千区切りの形でない（数量にしない）。"""
    integer = raw.split(".")[0]
    if "," in integer and not _THOUSANDS.fullmatch(integer):
        return None
    return len(integer.replace(",", "")) <= MAX_DIGITS


def _tokens(s: str, flags: list[str]) -> list[_Tok]:
    """flags に "oversize"（桁が多すぎる数）を積む。"""
    units, counters, mults = _unit_table(), _counter_table(), _multiplier_table()
    rx = _token_re(tuple(units), tuple(counters))
    months = {_norm(w) for w in MONTH_COUNTERS}
    solo_low = {_norm(w) for w in SOLO_LOW_COUNTERS}
    toks: list[_Tok] = []
    for m in rx.finditer(s):
        a = m.start("num")
        prev = s[a - 1] if a > 0 else ""
        # 英字・ハイフン等の直後の数字は型番の一部（SH-12M）。ただし直前の数量に続く「x」は乗算記号
        times = prev == "x" and ((a > 1 and not s[a - 2].isascii()) or (toks and toks[-1].end == a - 1))
        if prev and not times and ((prev.isascii() and prev.isalpha()) or prev in "-_./"):
            continue
        if _AFTER_SKIP.match(s, m.end()) or _BEFORE_SKIP.search(s[max(0, a - 4):a]):
            continue
        ok = _digits_ok(m.group("num"))
        if ok is None:
            continue
        if not ok:
            flags.append("oversize")
            continue
        value = _num(m.group("num"))
        if m.group("unit"):
            dim, factor = units[m.group("unit")]
            amount = round(value * factor, 9)
            if amount <= 0:
                continue
            toks.append(_Tok("measure", a, m.end(), n=amount, dim=dim))
        else:
            if value != int(value):
                continue
            key = m.group("counter")
            word = counters[key]
            if key in solo_low and not (1 <= value <= MAX_PACK_P
                                        and not _P_NOT_COUNT.match(s, m.end())):
                continue                             # 1080P・10P還元は個数ではない（P3・X1）
            if key in months and s[m.end():m.end() + 1] == "月":
                continue                             # 12ヶ月保証・3ヶ月分は期間（P3）
            if word == "点" and _TEN_NOT_COUNT.match(s, m.end()):
                continue                             # 2点購入・3点以上は販促（P3）
            toks.append(_Tok("count", a, m.end(), n=int(value), word=word,
                             mult=mults.get(key, 1), solo_low=key in solo_low))
    taken = {t.start for t in toks}
    for m in _BARE_RE.finditer(s):
        if m.start(1) in taken:
            continue
        if _AFTER_SKIP.match(s, m.end()):
            continue
        if len(m.group(1)) > MAX_DIGITS:
            flags.append("oversize")
            continue
        toks.append(_Tok("bare", m.start(1), m.end(1), n=int(m.group(1))))
    toks.sort(key=lambda t: t.start)
    return toks


def _unknown_counter(s: str) -> bool:
    """数字の直後に表に無い語があり、そこが個数の連結位置（×の前後・入数の直後）なら True（S4）。"""
    units, counters = _unit_table(), _counter_table()
    rx = _token_re(tuple(units), tuple(counters))
    for m in _WORD_AFTER_NUM.finditer(s):
        if rx.match(s, m.start(1)):
            continue                              # 表にある単位・数え語（読み取り側で処理する）
        word = re.sub(r"(?:入り?|入数)$", "", m.group(2))
        if not word:
            continue
        if _UNK_BEFORE.search(s[:m.start(1)]) or _UNK_AFTER.match(s, m.start(2) + len(word)):
            return True
    return False


def _joins(s: str, p: _Tok, t: _Tok, g: _Group, flags: list[str],
           t_chain: tuple[int, int]) -> bool:
    """t を直前のトークン p と同じ鎖（グループ）に入れるか。g は p までの鎖。
    t_chain は t が新しい鎖の先頭だった時のその鎖の（個数の積, 因子数）（4ロール×6パック → (24, 2)）。
    flags に "ambiguous"（同数・別の数え語で積か言い直しか決められない）を積む。"""
    gap = s[p.end:t.start]
    if t.kind == "bare":
        return bool(_GAP_X.fullmatch(gap))
    if t.solo_low and not (_GAP_X.fullmatch(gap) or ("入" in gap and _GAP_PLAIN.fullmatch(gap))):
        return False                 # NP は ×の直後・入数の直後でだけ連結する（X1・X5）
    if t.kind == "measure" and g.measures:
        # 内容量は 1 グループに 1 つ（寸法は同じ次元を × でつなぐ時だけ）
        return p.kind == "measure" and p.dim == t.dim and bool(_GAP_LABEL.fullmatch(gap))
    if p.kind == "measure" and t.kind == "measure":
        return p.dim == t.dim and bool(_GAP_LABEL.fullmatch(gap))
    if p.kind == "bare" and t.kind != "bare":
        return bool(_GAP_X.fullmatch(gap))
    if p.kind == "count" and t.kind == "count":
        if _GAP_X.fullmatch(gap):
            return True
        if not _GAP_COUNT_MEASURE.fullmatch(gap):
            return False
        facs = g.factors
        t_total, t_facs = t_chain
        if facs and t_total == _total(g):
            # P1: 鎖の積と等しい後続は総数の言い直し（12ロール×4パック 48ロール）。因子にしない。
            # ただし鎖が 1 因子で数が偶然同じ時（3個入り 3セット）は、外側が容器語なら掛け算（P4）、
            # そうでなければ積か言い直しか決められない（X4）ので単価不明に倒す。同じ数え語なら言い直し
            if (len(facs) == 1 and t_facs == 1 and facs[0].mult == 1 and t_total != 1
                    and t.word != facs[0].word):
                if t.word in OUTER_WORDS:
                    return True
                flags.append("ambiguous")
            return False
        if "入" in gap or (t.word in CONTAINERS and all(f.word != t.word for f in facs)):
            return True
        # 外側「5箱」のあとに内側「60個入」が来る順は、W1（内側→外側）とは逆で、積か説明か決められない
        if (len(facs) == 1 and p.n != 1 and _IRI_AFTER.match(s, t.end)
                and not _IRI_AFTER.match(s, p.end)):
            flags.append("ambiguous")
            return False
        # ×の無い2段の数え語「500枚 5冊」「12本入り 2ダース」（W1）。先頭が 1 の「1箱 24本」は
        # 1 個あたりの説明なので連結しない。同じ数え語の言い直し（12本 12本入り）も連結しない。
        # すでに 2 因子以上ある鎖には足さない（P2）
        if len(facs) > 1:
            return False
        return p.n != 1 and (p.word != t.word or t.mult > 1)
    plain = _GAP_COUNT_MEASURE if {p.kind, t.kind} == {"count", "measure"} else _GAP_PLAIN
    return bool(_GAP_X.fullmatch(gap) or plain.fullmatch(gap))


_LOOKAHEAD = 8          # 先読みする鎖の最大トークン数（商品名の鎖はこれより短い）


def _group(s: str, toks: list[_Tok], flags: list[str]) -> list[_Group]:
    # 各トークンが「新しい鎖の先頭」だったら、その鎖の（個数の積, 因子数）はいくつか。後ろから求める。
    # t の側が積（4ロール×6パック×2ケース）の時、前の記述（48個）がその言い直しかを積で判定するため
    ahead: list[tuple[int, int]] = [(1, 0)] * len(toks)
    for i in range(len(toks) - 1, -1, -1):
        g = _Group([toks[i]])
        for j in range(i + 1, min(len(toks), i + _LOOKAHEAD)):
            if not _joins(s, g.toks[-1], toks[j], g, [], ahead[j]):
                break
            g.toks.append(toks[j])
        ahead[i] = (_total(g), len(g.factors))
    groups: list[_Group] = []
    for i, t in enumerate(toks):
        if groups and _joins(s, groups[-1].toks[-1], t, groups[-1], flags, ahead[i]):
            groups[-1].toks.append(t)
        elif t.kind != "bare":      # 直前に何も無い「×6」は個数にしない
            groups.append(_Group([t]))
        else:
            flags.append("orphan_times")      # 読み飛ばした記述の後ろの「×2」など。倍数が落ちている恐れ
    return groups


def _drop_restated(g: _Group, flags: list[str]) -> _Group:
    """内容量の後ろで、内容量より前に書かれた個数と同じ数が出てきたら言い直し（二重に掛けない。S2）。
    例: 24本 (500ml×24) / 6袋 900g×6 / 2袋 (5kg×2袋)。ただし先の数え語と違う容器語で同数なら掛け算（P4。
    3個入り 400ml×3セット → 9）。"""
    before: dict[float, str] = {}
    seen_measure = False
    kept: list[_Tok] = []
    for t in g.toks:
        if t.kind == "measure":
            seen_measure = True
        elif seen_measure and t.n in before:
            # P4: 同じ数でも、先に書かれた数え語と違う容器語（袋・セット・ケース・パック）なら外側の掛け算。
            # 容器語でない別の数え語（3個入り 400ml×3冊）は積か言い直しか決められない（X4）
            if t.kind == "count" and t.n != 1 and t.word != before[t.n] and t.mult == 1:
                if t.word not in OUTER_WORDS:
                    flags.append("ambiguous")
                    continue
            else:
                continue
        elif not seen_measure:
            before.setdefault(t.n, t.word)
        kept.append(t)
    return _Group(kept)


def _total(g: _Group) -> int:
    out = 1
    alone = len(g.factors) == 1
    for t in g.factors:
        out *= int(t.n) * (t.mult if alone else 1)
    return out


def _none(evidence: str = "") -> QuantityInfo:
    return QuantityInfo(confidence="none", evidence=evidence)


def _low(evidence: str) -> QuantityInfo:
    return QuantityInfo(confidence="low", evidence=evidence)


def _resolve_amount(values: dict[float, bool], count: int) -> float | None:
    """同じ次元の内容量の値（値 → その値と同じ鎖に個数があるか）から 1 個あたりの量を決める。食い違っても、
    大きい方が小さい方×個数で、個数が小さい方に付いているなら総量の併記（5kg×2袋 計10kg）とみなして
    小さい方を 1 個あたりにする（S3）。個数が大きい方に付く「5kg 10kg 2袋」は決められない。決められなければ None。"""
    if len(values) == 1:
        return next(iter(values))
    lo = min(values)
    if count > 1 and all(v == lo or (v == round(lo * count, 9) and not values[v]) for v in values):
        return lo
    return None


def parse_quantity(text: str, basis: str | None = None) -> QuantityInfo:
    """商品名 → 数量。basis（比べる単位）が内容量の次元で、名前にその次元の内容量があればそれを
    content_* に使う（S5）。省略時は最初に書かれた次元。"""
    s = _normalize(text)
    flags: list[str] = []
    toks = _tokens(s, flags)
    if flags or _unknown_counter(s):
        return _low(s.strip()[:80])
    if not toks:
        return _none()
    # 「30回分」は使用回数・換算の説明。計量値や他の個数があれば数えない（S1）
    if any(t.kind == "count" and t.word in SERVING_WORDS for t in toks) and any(
            t.kind == "measure" or (t.kind == "count" and t.word not in SERVING_WORDS) for t in toks):
        toks = [t for t in toks if not (t.kind == "count" and t.word in SERVING_WORDS)]
    groups = _group(s, toks, flags)
    evidence = " / ".join(dict.fromkeys(s[g.toks[0].start:g.toks[-1].end].strip() for g in groups))
    if flags and groups:                 # 食い違い・倍数の落ち（P0: 失敗の向きは単価不明）
        return _low(evidence)
    # 単独の NP は個数の候補として持つが、他の読み方と一致しない限り high にしない（X1）
    solo = [g for g in groups if g.toks[0].solo_low]
    agreed = {_total(g) for g in groups if g.factors and not g.toks[0].solo_low}
    if any(_total(g) not in agreed for g in solo):
        return _low(evidence)
    groups = [_drop_restated(g, flags) for g in groups]
    if flags and groups:
        return _low(evidence)

    # --- 個数 ---
    cgroups = [g for g in groups if g.factors]
    # 「1ロール30m」「1箱24本入り」の先頭の 1<数え語> は、1個あたりの説明であって個数ではない
    keep: list[_Group] = []
    for g in cgroups:
        single_one = len(g.factors) == 1 and g.factors[0].kind == "count" and g.factors[0].n == 1
        others = [h for h in cgroups if h is not g and _total(h) != 1]
        if single_one and others:
            nxt = next((h for h in groups if h.toks[0].start >= g.toks[-1].end), None)
            adjacent = nxt is not None and not s[g.toks[-1].end:nxt.toks[0].start].strip()
            if g.measures or adjacent:
                continue
        keep.append(g)
    # 複合表記（12ロール×4袋）の 1 袋あたりと同じ単独の記述（12ロール入り）は矛盾とみなさない
    inner = {(h.factors[0].word, h.factors[0].n) for h in keep if len(h.factors) > 1}
    keep = [g for g in keep if not (len(g.factors) == 1
                                     and (g.factors[0].word, g.factors[0].n) in inner
                                     and any(len(h.factors) > 1 for h in keep))]
    totals = {_total(g) for g in keep}
    if len(totals) > 1 or any(t <= 0 or t > MAX_PLAUSIBLE_COUNT for t in totals):
        return _low(evidence)
    total = next(iter(totals)) if keep else 1

    # --- 内容量（同じ次元の × でつながる寸法は大きい方。別々に書かれた値が食い違えば矛盾）---
    per_group: list[tuple[str, float, int, bool]] = []
    for g in groups:
        by_dim: dict[str, float] = {}
        for m in g.measures:
            by_dim[m.dim] = max(by_dim.get(m.dim, 0.0), m.n)
        first = {d: next(m.start for m in g.measures if m.dim == d) for d in by_dim}
        per_group += [(d, a, first[d], bool(g.factors)) for d, a in by_dim.items()]
    amounts: dict[str, float] = {}
    dim = amount = None
    if per_group:
        order: list[str] = []
        for d, _, _, _ in sorted(per_group, key=lambda x: x[2]):
            if d not in order:
                order.append(d)
        for d in order:
            vals: dict[float, bool] = {}
            for dd, a, _, has in per_group:
                if dd == d:
                    vals[round(a, 9)] = vals.get(round(a, 9), False) or has
            resolved = _resolve_amount(vals, total)
            if resolved is not None:
                amounts[d] = resolved
        want = None
        if basis not in (None, ""):
            try:
                want = resolve_basis(basis)[1]
            except ValueError:
                want = None
        if want in amounts:
            dim = want
        elif order[0] in amounts:
            dim = order[0]
        else:
            return _low(evidence)
        amount = amounts[dim]

    if keep:
        main = max(keep, key=lambda g: len(g.factors))
        word = next((t.word for t in main.factors if t.kind == "count"), "個")
    elif amount is not None:
        word = "個"
    else:
        return _none()
    return QuantityInfo(
        count_total=total, count_unit=word, content_amount=amount,
        content_dimension=dim, content_unit=base_unit(dim) if dim else None,
        measure_total=None if amount is None else round(total * amount, 9),
        confidence="high", evidence=evidence, content_amounts=amounts)
