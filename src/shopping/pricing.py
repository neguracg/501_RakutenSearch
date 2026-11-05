# @owns 単位価格・支払総額の算出と最安判定（比較グループ分け・断定できない理由の明示）
"""価格比較。仕様違い（ply/長さ）を誤統合せず、送料不明のときは総額最安を断定しない。"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Offer

_LENGTH_TOLERANCE = 0.01


@dataclass
class ComparisonGroup:
    key: str                          # 比較可能な束の識別子（ply・length_m・unit で作る）
    ply: str | None
    length_m: float | None
    offers: list[Offer]               # 単位価格の安い順（算出不能は末尾）
    length_label: str | None = None   # 倍巻き・長尺の表記（"x2" 等）。通常品とは別の束にする


@dataclass
class Comparison:
    groups: list[ComparisonGroup]
    cheapest_price: Offer | None
    cheapest_unit_price: Offer | None
    cheapest_total: Offer | None
    cheapest_meeting_quantity: Offer | None
    caveats: list[str] = field(default_factory=list)


def unit_price(offer: Offer) -> float | None:
    """price / quantity.total。数量の confidence が high 以外は None。丸めない。"""
    q = offer.quantity
    if q is None or q.confidence != "high" or not q.total or q.total <= 0:
        return None
    if offer.price is None:
        return None
    return offer.price / q.total


def total_price(offer: Offer) -> int | None:
    """included→price、separate かつ fee あり→price+fee、他は None。"""
    if offer.price is None:
        return None
    if offer.shipping_status == "included":
        return offer.price
    if offer.shipping_status == "separate" and offer.shipping_fee is not None:
        return offer.price + offer.shipping_fee
    return None


def price_per_m(offer: Offer) -> float | None:
    """1m あたり価格（単位価格 ÷ 1 単位の長さ）。長さが不明なら None。"""
    up = unit_price(offer)
    q = offer.quantity
    if up is None or q is None or not q.length_m:
        return None
    return up / q.length_m


def group_key(offer: Offer) -> tuple[str | None, float | None, str, str | None]:
    """(ply, length_m, unit, length_label)。倍巻き・長尺は length_label で通常品と分ける。"""
    q = offer.quantity
    if q is None:
        return (None, None, "", None)
    return (q.ply, q.length_m, q.unit, q.length_label)


def _key_str(ply, length_m, unit, length_label=None) -> str:
    length = "unknown" if length_m is None else f"{length_m:g}m"
    base = f"{ply or 'unknown'}|{length}|{unit or 'unknown'}"
    return f"{base}|{length_label}" if length_label else base


def _length_matches(actual: float | None, wanted) -> bool:
    try:
        return actual is not None and abs(actual - float(wanted)) <= _LENGTH_TOLERANCE
    except (TypeError, ValueError):
        return False


def _spec_check(offer: Offer, spec: dict) -> str:
    """'ok' / 'mismatch'（仕様違い）/ 'unknown'（仕様不明）。"""
    q = offer.quantity
    unknown = False
    for k, wanted in spec.items():
        if k == "ply":
            actual = q.ply if q else None
            if actual is None:
                unknown = True
            elif actual != wanted:
                return "mismatch"
        elif k == "length_m":
            actual = q.length_m if q else None
            if actual is None:
                unknown = True
            elif not _length_matches(actual, wanted):
                return "mismatch"
        elif k == "unit":
            actual = q.unit if q else None
            if actual is None:
                unknown = True
            elif actual != wanted:
                return "mismatch"
    return "unknown" if unknown else "ok"


_SUPPORTED_SPEC_KEYS = {"ply", "length_m", "unit"}


def compare(offers: list[Offer], required_spec: dict | None = None,
            desired_quantity: int | None = None) -> Comparison:
    caveats: list[str] = []
    candidates = list(offers)

    if required_spec:
        ignored = sorted(set(required_spec) - _SUPPORTED_SPEC_KEYS)
        if ignored:
            caveats.append(f"未対応の条件は比較に使っていない: {', '.join(ignored)}")
        spec = {k: v for k, v in required_spec.items() if k in _SUPPORTED_SPEC_KEYS}
        kept, mismatch, unknown = [], 0, 0
        for o in candidates:
            r = _spec_check(o, spec)
            if r == "ok":
                kept.append(o)
            elif r == "mismatch":
                mismatch += 1
            else:
                unknown += 1
        if mismatch:
            caveats.append(f"必要仕様に合わない候補 {mismatch} 件を比較から除外した")
        if unknown:
            caveats.append(f"仕様を読み取れなかった候補 {unknown} 件を比較から除外した")
        candidates = kept

    priced = [o for o in candidates if o.price is not None]
    if len(priced) != len(candidates):
        caveats.append(f"価格が不明な候補 {len(candidates) - len(priced)} 件は順位付けから外した")

    # グループ分け（ply・length_m・unit が同じものだけ同じ束。入り数は束の条件にしない）
    buckets: dict[tuple, list[Offer]] = {}
    for o in candidates:
        buckets.setdefault(group_key(o), []).append(o)
    groups: list[ComparisonGroup] = []
    for (ply, length_m, unit, label), members in buckets.items():
        members.sort(key=lambda o: (unit_price(o) is None, unit_price(o) or 0.0,
                                    o.price if o.price is not None else 10**12,
                                    o.mall_item_code))
        groups.append(ComparisonGroup(key=_key_str(ply, length_m, unit, label), ply=ply,
                                      length_m=length_m, offers=members, length_label=label))
    groups.sort(key=lambda g: (-len(g.offers), g.key))

    if not priced:
        caveats.append("比較できる候補がない")
        return Comparison(groups=groups, cheapest_price=None, cheapest_unit_price=None,
                          cheapest_total=None, cheapest_meeting_quantity=None, caveats=caveats)

    cheapest_price = min(priced, key=lambda o: (o.price, o.mall_item_code))

    with_unit = [o for o in priced if unit_price(o) is not None]
    # 倍巻き・長尺は 1 ロールの長さが通常品と違い、ロール単価では比べられない。
    # 通常表記の候補があるなら、全体の「単位価格が最安」の判定から外す
    plain_unit = [o for o in with_unit if group_key(o)[3] is None]
    pool = plain_unit if plain_unit else with_unit
    cheapest_unit = min(pool, key=lambda o: (unit_price(o), o.price, o.mall_item_code)) \
        if pool else None
    if plain_unit and len(plain_unit) != len(with_unit):
        caveats.append(f"倍巻き・長尺の表記がある候補 {len(with_unit) - len(plain_unit)} 件は、"
                       "1ロールの長さが通常品と違うため単位価格の最安の判定から外した"
                       "（別の比較グループで見ること）")
    if len(priced) != len(with_unit):
        caveats.append(f"入り数を確定できず単位価格を出せない候補 {len(priced) - len(with_unit)} 件は"
                       "単位価格の順位付けから外した")
    if not with_unit:
        caveats.append("単位価格を出せる候補がない")

    specs_in_unit = {(o.quantity.ply, o.quantity.length_m, o.quantity.length_label)
                     for o in pool}
    if len(specs_in_unit) > 1:
        caveats.append("仕様違いを含む候補同士で単位価格を比べている"
                       "（シングル/ダブルや長さが異なる）。同じ仕様どうしで比べ直すこと")
    specs_in_price = {(group_key(o)[0], group_key(o)[1], group_key(o)[3]) for o in priced}
    if len(specs_in_price) > 1:
        caveats.append("仕様違いを含むため、商品価格の最安は同じ商品どうしの比較ではない")

    unknown_ship = [o for o in priced if total_price(o) is None]
    if unknown_ship:
        cheapest_total = None
        caveats.append(f"送料が不明な候補が {len(unknown_ship)} 件あるため、"
                       "支払総額の最安は断定できない")
    else:
        cheapest_total = min(priced, key=lambda o: (total_price(o), o.mall_item_code))

    meeting = None
    if desired_quantity is not None:
        ok = [o for o in priced if o.quantity is not None and o.quantity.confidence == "high"
              and o.quantity.total is not None and o.quantity.total >= desired_quantity]
        if ok:
            meeting = min(ok, key=lambda o: (o.price, unit_price(o), o.mall_item_code))
            if total_price(meeting) is None:
                caveats.append("必要数量を満たす最安は商品価格ベースで、送料は含まない（送料不明）")
        else:
            caveats.append(f"必要数量 {desired_quantity} 以上を確実に満たす候補がない")
        unreadable = [o for o in priced if o.quantity is None or o.quantity.confidence != "high"]
        if unreadable:
            caveats.append("入り数不明の候補は必要数量の判定に使っていない")

    return Comparison(groups=groups, cheapest_price=cheapest_price,
                      cheapest_unit_price=cheapest_unit, cheapest_total=cheapest_total,
                      cheapest_meeting_quantity=meeting, caveats=caveats)
