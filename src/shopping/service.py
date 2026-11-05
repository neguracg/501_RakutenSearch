# @owns ツール単位の処理（検索・比較・定番品）と、呼び出し側へ返す JSON 化可能な dict の形
"""MCP と CLI の共通処理。失敗は例外ではなく {"ok": False, "error": {...}} で返す。
戻り値に認証情報・生レスポンスは含めない。"""
from __future__ import annotations

import os
import time
import unicodedata
from dataclasses import asdict

from .adapters.base import MarketplaceAdapter
from .adapters.mock import MockAdapter
from .adapters.rakuten import RakutenAdapter
from .config import RakutenCredentials, load_credentials
from .models import Offer, SearchStats
from .orchestrator import Limits, search_many
from .pricing import (Comparison, compare, price_per_m, total_price, unit_price)
from .quantity import parse_quantity
from .regulars import Regular, RegularsError, get_regular

SOURCE = "楽天市場（楽天ウェブサービス）"
CAPTION_MAX = 200
GROUP_OFFERS_MAX = 10
MOCK_ENV = "SHOPPING_MOCK"

_FRESHNESS_NOTE = "価格・在庫は fetched_at 時点の値。キャッシュは24時間以内に取り直すこと。"
_MOCK_NOTE = "これは架空のモックデータで、実在の商品・価格ではない（SHOPPING_MOCK）。"


def is_mock_env() -> bool:
    return os.environ.get(MOCK_ENV) == "1"


def make_adapter(mock: bool | None = None,
                 credentials: RakutenCredentials | None = None) -> MarketplaceAdapter:
    """MCP と CLI が共通で使う Adapter 生成。mock=None なら環境変数 SHOPPING_MOCK=1 を見る。"""
    if mock is None:
        mock = is_mock_env()
    if mock:
        return MockAdapter()
    creds = credentials or load_credentials()
    return RakutenAdapter(creds.app_id, creds.access_key)


def _error(kind: str, message: str, **extra) -> dict:
    out = {"ok": False, "error": {"kind": kind, "message": message}}
    out.update(extra)
    return out


def _round2(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def offer_to_dict(offer: Offer, known_urls: list[str] | None = None) -> dict:
    q = offer.quantity
    d = {
        "mall": offer.mall,
        "item_code": offer.mall_item_code,
        "name": offer.item_name,
        "price": offer.price,
        "shop_name": offer.shop_name,
        "url": offer.item_url,
        "url_status": offer.item_url_status,
        "shipping_status": offer.shipping_status,
        "shipping_fee": offer.shipping_fee,
        "total_price": total_price(offer),
        "availability": offer.availability,
        "points_rate": offer.points_rate,
        "review_average": offer.review_average,
        "review_count": offer.review_count,
        "shipping_title_conflict": shipping_title_conflict(offer),
        "caption": (offer.caption[:CAPTION_MAX] if offer.caption else offer.caption),
        "fetched_at": offer.fetched_at,
        "matched_keywords": list(offer.matched_keywords),
        "quantity": None if q is None else {
            "total": q.total, "per_pack": q.per_pack, "pack_count": q.pack_count,
            "unit": q.unit, "ply": q.ply, "length_m": q.length_m,
            "length_label": q.length_label,
            "confidence": q.confidence, "evidence": q.evidence},
        "unit_price": _round2(unit_price(offer)),
        "price_per_m": _round2(price_per_m(offer)),
    }
    if known_urls is not None:
        d["is_known_url"] = offer.item_url in known_urls
    return d


def _stats_to_dict(stats: SearchStats) -> dict:
    return asdict(stats)


def _validate_keywords(keywords) -> list[str] | dict:
    if isinstance(keywords, str):
        keywords = [keywords]
    if (not isinstance(keywords, (list, tuple)) or not keywords
            or not all(isinstance(k, str) and k.strip() for k in keywords)):
        return _error("invalid_request", "keywords は空でない文字列のリストで指定する")
    return [k.strip() for k in keywords]


def _search(keywords, adapter, *, pages, hits, limits, sleep, filters):
    """(offers, stats, mock) または エラー dict。"""
    kws = _validate_keywords(keywords)
    if isinstance(kws, dict):
        return kws
    adapter = adapter if adapter is not None else make_adapter()
    mock = isinstance(adapter, MockAdapter)
    if sleep is None:
        sleep = (lambda s: None) if mock else time.sleep
    try:
        offers, stats = search_many(adapter, kws, max_pages=pages, hits=hits,
                                    limits=limits or Limits(), sleep=sleep, **filters)
    except ValueError as exc:  # 上限超え・不正値（メッセージは自前の文言のみ）
        return _error("invalid_request", str(exc))
    if not offers and stats.per_keyword and all(s.error for s in stats.per_keyword):
        first = stats.per_keyword[0].error
        return _error(first, f"全キーワードの検索に失敗した（{first}）",
                      stats=_stats_to_dict(stats), mock=mock)
    return offers, stats, mock


_TITLE_FREE_SHIP = ("送料無料", "送料込", "送料0円", "送料込み")
_TITLE_SEPARATE_SHIP = ("送料別", "別途送料", "送料は別", "送料お客様負担", "送料はお客様負担")


def shipping_title_conflict(offer: Offer) -> str | None:
    """タイトルの送料表記と楽天のフラグ（postageFlag 由来の shipping_status）が食い違う時の説明。

    送料はフラグを正とする（タイトルの文字で送料を決めない）。食い違いは注意として出すだけ。"""
    title = unicodedata.normalize("NFKC", offer.item_name or "")
    if offer.shipping_status == "separate" and any(w in title for w in _TITLE_FREE_SHIP):
        return ("タイトルに「送料無料」等の表記があるが、楽天のデータでは送料別。"
                "条件付き（一定額以上で無料など）の可能性があるため、購入前に商品ページで確認すること")
    if offer.shipping_status == "included" and any(w in title for w in _TITLE_SEPARATE_SHIP):
        return ("タイトルに「送料別」等の表記があるが、楽天のデータでは送料込み。"
                "購入前に商品ページで確認すること")
    return None


def _shipping_conflict_note(offers: list[Offer]) -> str | None:
    n = sum(1 for o in offers if shipping_title_conflict(o))
    if not n:
        return None
    return (f"タイトルの送料表記と楽天のデータ（送料込み/別）が食い違う候補が {n} 件ある。"
            "送料は楽天のデータを正として扱い、タイトルの文字では決めていない。購入前に商品ページで確認すること。")


def _annotate(offers: list[Offer], unit: str) -> None:
    for o in offers:
        o.quantity = parse_quantity(o.item_name, unit=unit)


def _base_notes(offers: list[Offer], stats: SearchStats, mock: bool,
                *, shipping_conflict: bool = True) -> list[str]:
    notes = [_FRESHNESS_NOTE, f"出典: {SOURCE}"]
    if mock:
        notes.insert(0, _MOCK_NOTE)
    review = sum(1 for o in offers if o.item_url_status != "ok")
    if review:
        notes.append(f"商品URLの形式が想定外の候補が {review} 件ある（url_status=needs_review）。"
                     "購入前にリンク先を確認すること。")
    conflict = _shipping_conflict_note(offers) if shipping_conflict else None
    if conflict:
        notes.append(conflict)
    errs = [f"{s.keyword}: {s.error}" for s in stats.per_keyword if s.error]
    if errs:
        notes.append("一部の検索でエラー: " + " / ".join(errs))
    if stats.stopped_reason == "rate_limited":
        notes.append("楽天APIの流量制限(429)で残りの検索を打ち切った。時間をおいて再実行すること。")
    return notes


def search_products(keywords, *, ng_keyword: str | None = None, min_price: int | None = None,
                    max_price: int | None = None, sort: str = "standard", pages: int = 1,
                    hits: int = 30, max_results: int = 30, unit: str = "ロール",
                    adapter: MarketplaceAdapter | None = None, sleep=None,
                    limits: Limits | None = None) -> dict:
    filters = dict(ng_keyword=ng_keyword, min_price=min_price, max_price=max_price, sort=sort)
    r = _search(keywords, adapter, pages=pages, hits=hits, limits=limits, sleep=sleep,
                filters=filters)
    if isinstance(r, dict):
        return r
    offers, stats, mock = r
    _annotate(offers, unit)
    shown = offers[:max(0, max_results)]
    notes = _base_notes(offers, stats, mock)
    if len(shown) < len(offers):
        notes.append(f"候補 {len(offers)} 件のうち先頭 {len(shown)} 件だけ返した（max_results）。")
    return {"ok": True, "source": SOURCE, "mock": mock, "keywords": _validate_keywords(keywords),
            "stats": _stats_to_dict(stats), "returned": len(shown),
            "offers": [offer_to_dict(o) for o in shown], "notes": notes}


def _comparison_to_dict(c: Comparison, known_urls: list[str] | None = None) -> dict:
    def one(o: Offer | None):
        return None if o is None else offer_to_dict(o, known_urls)
    return {
        "groups": [{"key": g.key, "ply": g.ply, "length_m": g.length_m,
                    "length_label": g.length_label, "count": len(g.offers),
                    "offers": [offer_to_dict(o, known_urls) for o in g.offers[:GROUP_OFFERS_MAX]]}
                   for g in c.groups],
        "cheapest_price": one(c.cheapest_price),
        "cheapest_unit_price": one(c.cheapest_unit_price),
        "cheapest_total": one(c.cheapest_total),
        "cheapest_meeting_quantity": one(c.cheapest_meeting_quantity),
        "caveats": list(c.caveats),
    }


def _compare_flow(keywords, required_spec, desired_quantity, *, unit, adapter, pages, hits,
                  limits, sleep, filters, known_urls=None) -> dict:
    if required_spec is not None and not isinstance(required_spec, dict):
        return _error("invalid_request", "required_spec は {\"ply\": \"double\", \"length_m\": 30} 形式の辞書で指定する")
    if desired_quantity is not None and (isinstance(desired_quantity, bool)
                                         or not isinstance(desired_quantity, int)
                                         or desired_quantity <= 0):
        return _error("invalid_request", "desired_quantity は正の整数で指定する")
    r = _search(keywords, adapter, pages=pages, hits=hits, limits=limits, sleep=sleep,
                filters=filters)
    if isinstance(r, dict):
        return r
    offers, stats, mock = r
    _annotate(offers, unit)
    comparison = compare(offers, required_spec=required_spec, desired_quantity=desired_quantity)
    conflict = _shipping_conflict_note(offers)
    if conflict:
        comparison.caveats.append(conflict)
    return {"ok": True, "source": SOURCE, "mock": mock, "keywords": _validate_keywords(keywords),
            "required_spec": required_spec, "desired_quantity": desired_quantity,
            "stats": _stats_to_dict(stats),
            "comparison": _comparison_to_dict(comparison, known_urls),
            "notes": _base_notes(offers, stats, mock, shipping_conflict=False)}


def compare_offers(keywords, required_spec: dict | None = None,
                   desired_quantity: int | None = None, *, ng_keyword: str | None = None,
                   min_price: int | None = None, max_price: int | None = None,
                   sort: str = "standard", pages: int = 1, hits: int = 30, unit: str = "ロール",
                   adapter: MarketplaceAdapter | None = None, sleep=None,
                   limits: Limits | None = None) -> dict:
    filters = dict(ng_keyword=ng_keyword, min_price=min_price, max_price=max_price, sort=sort)
    return _compare_flow(keywords, required_spec, desired_quantity, unit=unit, adapter=adapter,
                         pages=pages, hits=hits, limits=limits, sleep=sleep, filters=filters)


def _regular_info(r: Regular) -> dict:
    return {"id": r.id, "name": r.name, "maker": r.maker, "model_number": r.model_number,
            "jan": r.jan, "unit": r.unit, "required_spec": r.required_spec,
            "desired_quantity": r.desired_quantity, "keywords": r.keywords, "notes": r.notes}


_REGULARS_MESSAGES = {
    "file_not_found": "定番品マスタ（data/regulars.json）が見つからない。"
                      "examples/regulars.sample.json をコピーして作る。",
    "invalid_json": "定番品マスタが正しい JSON ではない。",
    "invalid_format": "定番品マスタの形式が不正。",
    "not_found": "その id の定番品がマスタにない。",
}


def find_regular_item(regular_id: str, *, regulars_path=None, pages: int = 1, hits: int = 30,
                      adapter: MarketplaceAdapter | None = None, sleep=None,
                      limits: Limits | None = None) -> dict:
    if not isinstance(regular_id, str) or not regular_id.strip():
        return _error("invalid_request", "regular_id は文字列で指定する")
    try:
        reg = get_regular(regular_id.strip(), regulars_path)
    except RegularsError as exc:
        msg = _REGULARS_MESSAGES.get(exc.kind, "定番品マスタを読めない。")
        if exc.kind == "invalid_format" and exc.detail:
            msg += f"（{exc.detail}）"
        return _error(f"regulars_{exc.kind}", msg)
    out = _compare_flow(reg.keywords, reg.required_spec or None, reg.desired_quantity,
                        unit=reg.unit, adapter=adapter, pages=pages, hits=hits, limits=limits,
                        sleep=sleep, filters={}, known_urls=reg.known_urls)
    out["regular"] = _regular_info(reg)
    return out
