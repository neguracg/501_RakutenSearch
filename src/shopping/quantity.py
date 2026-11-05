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

# 単位の換算表: 別名 → (次元, 基準単位への係数)。大文字小文字・全角半角は区別せずに引く。
UNITS: dict[str, tuple[str, float]] = {
    "ml": ("volume", 1), "mL": ("volume", 1), "cc": ("volume", 1),
    "L": ("volume", 1000), "ℓ": ("volume", 1000), "リットル": ("volume", 1000),
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
}

# 「12ロール 4パック」のように空白だけで続けても掛け算にする、入れ物を表す数え語
CONTAINERS = frozenset({"パック", "袋", "セット", "ケース", "梱"})

MAX_PLAUSIBLE_COUNT = 100_000

_FILL = r"(?:入り?|入数|セット|組|パック|袋|箱|ケース|梱|各|の)"
_GAP_X = re.compile(rf"\s*(?:{_FILL}\s*)*[×x*]\s*")
_GAP_LABEL = re.compile(rf"\s*(?:{_FILL}\s*)*[×x*]\s*[^\d×x*\s]{{0,4}}\s*")
_GAP_PLAIN = re.compile(r"\s*(?:(?:入り?|入数|約|各)\s*)*")
# 桁数を切る（出店者の書いた巨大な数字列で float が inf になり int() が落ちる事故を防ぐ）
_NUM = r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d{1,9})(?![\d,])(?:\.\d{1,9})?"
_AFTER_SKIP = re.compile(r"\s*(?:分(?![a-z])|相当|換算|あたり|当たり|当り|につき|ごと|限定|まで|以上|以下|以内|未満|から|ずつ)")
_BEFORE_SKIP = re.compile(r"(?:最大|最小)\s*$")
# 販促・価格表記（数量ではない）
_PROMO = [
    re.compile(r"\d+(?:\.\d+)?\s*倍"),                                   # ポイント10倍・2倍
    re.compile(r"\d+(?:\.\d+)?\s*%"),                                    # 最大50%OFF
    re.compile(r"\d[\d,]*(?:\.\d+)?\s*円"),                              # 1000円ポッキリ・1,980円
]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").lower()


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


# ---- 読み取り ----

@dataclass
class _Tok:
    kind: str                 # "count" / "measure" / "bare"
    start: int
    end: int
    n: float = 0.0            # count/bare: 個数、measure: 基準単位に直した量
    word: str = ""            # count: 正規の数え語
    dim: str = ""             # measure: 次元


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
        rf"(?P<num>{_NUM})\s*(?:(?P<unit>{_alt(unit_keys)})(?!サイズ)|(?P<counter>{_alt(counter_keys)}))")


_BARE_RE = re.compile(r"(?:[×*]|(?<![a-z])x)\s*(\d{1,9})(?![\d.]|[a-z])")


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _tokens(s: str) -> list[_Tok]:
    units, counters = _unit_table(), _counter_table()
    rx = _token_re(tuple(units), tuple(counters))
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
            toks.append(_Tok("count", a, m.end(), n=int(value), word=counters[m.group("counter")]))
    taken = {t.start for t in toks}
    for m in _BARE_RE.finditer(s):
        if m.start(1) in taken:
            continue
        if _AFTER_SKIP.match(s, m.end()):
            continue
        toks.append(_Tok("bare", m.start(1), m.end(1), n=int(m.group(1))))
    toks.sort(key=lambda t: t.start)
    return toks


def _joins(s: str, p: _Tok, t: _Tok, group_measures: list[_Tok]) -> bool:
    gap = s[p.end:t.start]
    if t.kind == "bare":
        return bool(_GAP_X.fullmatch(gap))
    if t.kind == "measure" and group_measures:
        # 内容量は 1 グループに 1 つ（寸法は同じ次元を × でつなぐ時だけ）
        return p.kind == "measure" and p.dim == t.dim and bool(_GAP_LABEL.fullmatch(gap))
    if p.kind == "measure" and t.kind == "measure":
        return p.dim == t.dim and bool(_GAP_LABEL.fullmatch(gap))
    if p.kind == "bare" and t.kind != "bare":
        return bool(_GAP_X.fullmatch(gap))
    if p.kind == "count" and t.kind == "count":
        if _GAP_X.fullmatch(gap):
            return True
        return bool(_GAP_PLAIN.fullmatch(gap)) and ("入" in gap or t.word in CONTAINERS)
    return bool(_GAP_X.fullmatch(gap) or _GAP_PLAIN.fullmatch(gap))


def _group(s: str, toks: list[_Tok]) -> list[_Group]:
    groups: list[_Group] = []
    for t in toks:
        if groups and _joins(s, groups[-1].toks[-1], t, groups[-1].measures):
            groups[-1].toks.append(t)
        elif t.kind != "bare":      # 直前に何も無い「×6」は個数にしない
            groups.append(_Group([t]))
    return groups


def _total(g: _Group) -> int:
    out = 1
    for t in g.factors:
        out *= int(t.n)
    return out


def _none(evidence: str = "") -> QuantityInfo:
    return QuantityInfo(confidence="none", evidence=evidence)


def _low(evidence: str) -> QuantityInfo:
    return QuantityInfo(confidence="low", evidence=evidence)


def parse_quantity(text: str) -> QuantityInfo:
    s = _normalize(text)
    toks = _tokens(s)
    if not toks:
        return _none()
    groups = _group(s, toks)
    evidence = " / ".join(dict.fromkeys(s[g.toks[0].start:g.toks[-1].end].strip() for g in groups))

    # --- 個数 ---
    cgroups = [g for g in groups if g.factors]
    # 「1ロール30m」「1箱24本入り」の先頭の 1<数え語> は、1個あたりの説明であって個数ではない
    keep: list[_Group] = []
    for i, g in enumerate(cgroups):
        single_one = len(g.factors) == 1 and g.factors[0].kind == "count" and g.factors[0].n == 1
        others = [h for h in cgroups if h is not g and _total(h) != 1]
        if single_one and others:
            nxt = next((h for h in groups if h.toks[0].start >= g.toks[-1].end), None)
            adjacent = nxt is not None and not s[g.toks[-1].end:nxt.toks[0].start].strip()
            if g.measures or adjacent:
                continue
        keep.append(g)
    # 複合表記（12ロール×4袋）の 1 袋あたりと同じ単独の記述（12ロール入り）は矛盾とみなさない
    inner = {h.factors[0].n for h in keep if len(h.factors) > 1}
    keep = [g for g in keep if not (len(g.factors) == 1 and g.factors[0].n in inner
                                     and any(len(h.factors) > 1 for h in keep))]
    totals = {_total(g) for g in keep}
    if len(totals) > 1 or any(t <= 0 or t > MAX_PLAUSIBLE_COUNT for t in totals):
        return _low(evidence)

    # --- 内容量（同じ次元の × でつながる寸法は大きい方。別々に書かれた値が食い違えば矛盾）---
    per_group: list[tuple[str, float, int]] = []
    for g in groups:
        by_dim: dict[str, float] = {}
        for m in g.measures:
            by_dim[m.dim] = max(by_dim.get(m.dim, 0.0), m.n)
        first = {d: next(m.start for m in g.measures if m.dim == d) for d in by_dim}
        per_group += [(d, a, first[d]) for d, a in by_dim.items()]
    dim = amount = None
    if per_group:
        dim = min(per_group, key=lambda x: x[2])[0]
        values = {round(a, 9) for d, a, _ in per_group if d == dim}
        if len(values) > 1:
            return _low(evidence)
        amount = values.pop()

    if keep:
        main = max(keep, key=lambda g: len(g.factors))
        total = totals.pop()
        word = next((t.word for t in main.factors if t.kind == "count"), "個")
    elif amount is not None:
        total, word = 1, "個"
    else:
        return _none()
    return QuantityInfo(
        count_total=total, count_unit=word, content_amount=amount,
        content_dimension=dim, content_unit=base_unit(dim) if dim else None,
        measure_total=None if amount is None else round(total * amount, 9),
        confidence="high", evidence=evidence)
