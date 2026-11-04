# @owns 商品名・説明文からの数量/仕様（入り数・シングルダブル・長さ）の読み取りと信頼度判定
"""数量正規化。読み取れない・矛盾する場合は推測で埋めず total=None にする。"""
from __future__ import annotations

import re
import unicodedata

from .models import QuantityInfo

_PACK_WORDS = r"(?:パック|袋|セット|個|箱|ケース|梱|組|パッケージ)"
# '×' なしで「12ロール入り 4パック」と続く形で使える入れ物の語（「個」は限定数と紛れるので除く）
_PACK_WORDS_BARE = r"(?:パック|袋|セット|箱|ケース|梱|組|個(?=セット|パック|入))"
_NOT_COUNT_AFTER = r"(?!\s*(?:メートル|mm|cm|kg|ml|枚|倍|m(?![a-z])|g(?![a-z])|l(?![a-z])|%|\.\d))"
_MAX_PLAUSIBLE_TOTAL = 1000


def _normalize(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "")
    s = s.replace("✕", "×").replace("✖", "×").replace("＊", "*")
    s = re.sub(r"[()\[\]{}【】「」『』〈〉《》]", " ", s)
    return s.lower()


def _unit_pattern(unit: str) -> str:
    if unit == "ロール":
        # R は単独の英字として現れる時だけ（"ROLL" や "R2" 等と紛れない）
        return r"(?:ロール|rolls?|(?<![a-z])r(?![a-z]))"
    return re.escape(unit.lower())


def _detect_ply(s: str) -> str | None:
    found = set()
    if re.search(r"ダブル|(?<![\d.])2\s*枚\s*重ね?|(?<![\d.])2\s*(?:ply|プライ)|二\s*枚\s*重ね?", s):
        found.add("double")
    if re.search(r"シングル|(?<![\d.])1\s*枚\s*重ね?|(?<![\d.])1\s*(?:ply|プライ)|(?<![\d.])1\s*枚", s):
        found.add("single")
    return found.pop() if len(found) == 1 else None


def _detect_length(s: str) -> float | None:
    # 倍巻き等は「長さ」の意味が商品ごとに違う（実長か通常比か）ので確定させない
    if re.search(r"\d+(?:\.\d+)?\s*倍\s*(?:巻|長|ロング)|倍\s*(?:巻|長)|ロング", s):
        return None
    values = set()
    for m in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:メートル|m(?![a-z]))", s):
        values.add(float(m.group(1)))
    values.discard(0.0)
    return values.pop() if len(values) == 1 else None


def parse_quantity(text: str, unit: str = "ロール") -> QuantityInfo:
    s = _normalize(text)
    U = _unit_pattern(unit)
    ply = _detect_ply(s)
    length = _detect_length(s)

    # 「24ロール分」「24ロール相当」は実数ではなく換算の説明なので数えない
    s_count = re.sub(rf"\d+\s*{U}\s*(?:分|相当)", " ", s)

    per_re = re.compile(rf"(?<![\d.])(\d+)\s*{U}(?:\s*入り?)?")
    chain_x = re.compile(rf"\s*[×x*]\s*(\d+)(?!\d){_NOT_COUNT_AFTER}\s*({_PACK_WORDS})?")
    chain_bare = re.compile(rf"\s*(\d+)(?!\d)\s*({_PACK_WORDS_BARE})")

    # (total, per_pack, pack_count, evidence, is_plain)
    cands: list[tuple[int, int, int, str, bool]] = []
    weak: list[tuple[int, int, int, str, bool]] = []
    pos = 0
    while True:
        m = per_re.search(s_count, pos)
        if not m:
            break
        per = int(m.group(1))
        end = m.end()
        packs = 1
        chained = False
        while True:
            nm = chain_x.match(s_count, end) or chain_bare.match(s_count, end)
            if not nm:
                break
            packs *= int(nm.group(1))
            end = nm.end()
            chained = True
        evidence = s_count[m.start():end].strip()
        item = (per * packs, per, packs, evidence, not chained)
        if not chained and per == 1 and re.match(
                r"\s*(?:あたり|当たり|当り|約|(?:\d+(?:\.\d+)?)\s*(?:メートル|m(?![a-z])))", s_count[end:]):
            weak.append(item)  # 「1ロール30m」「1ロールあたり」は個数ではなく長さ等の説明
        else:
            cands.append(item)
        pos = max(end, m.end())

    # 「12ロール入り」単独の説明が、別の複合表記（12ロール×4袋）の 1 袋あたりと同じなら矛盾とみなさない
    compound_pers = {c[1] for c in cands if not c[4]}
    cands = [c for c in cands if not (c[4] and c[0] in compound_pers)]

    if not cands and weak:
        cands = weak
    if not cands:
        return QuantityInfo(unit=unit, per_pack=None, pack_count=None, total=None,
                            ply=ply, length_m=length, confidence="none", evidence="")

    totals = {c[0] for c in cands}
    evidence = " / ".join(dict.fromkeys(c[3] for c in cands))
    implausible = any(c[0] <= 0 or c[0] > _MAX_PLAUSIBLE_TOTAL or c[1] <= 0 or c[2] <= 0
                      for c in cands)
    if len(totals) != 1 or implausible:
        return QuantityInfo(unit=unit, per_pack=None, pack_count=None, total=None,
                            ply=ply, length_m=length, confidence="low", evidence=evidence)
    best = next((c for c in cands if not c[4]), cands[0])
    return QuantityInfo(unit=unit, per_pack=best[1], pack_count=best[2], total=best[0],
                        ply=ply, length_m=length, confidence="high", evidence=evidence)
