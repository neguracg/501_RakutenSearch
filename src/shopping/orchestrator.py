# @owns 複数キーワード検索の実行制御（ページング・重複排除・統計・流量制限・429打ち切り）
"""検索オーケストレーション。モール固有の知識は持たない（Adapter 越しに呼ぶだけ）。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .adapters.base import AdapterError
from .models import KeywordStat, Offer, SearchStats

JST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Limits:
    max_keywords: int = 5
    max_pages: int = 3
    min_interval_sec: float = 1.0


def _validate(keywords, max_pages: int, hits: int, limits: Limits) -> None:
    if not keywords:
        raise ValueError("keywords must not be empty")
    if len(keywords) > limits.max_keywords:
        raise ValueError(f"too many keywords: {len(keywords)} > {limits.max_keywords}")
    if max_pages < 1:
        raise ValueError("max_pages must be >= 1")
    if max_pages > limits.max_pages:
        raise ValueError(f"too many pages: {max_pages} > {limits.max_pages}")
    if not (1 <= hits <= 30):
        raise ValueError("hits must be 1..30")
    if limits.min_interval_sec < 0:
        raise ValueError("min_interval_sec must be >= 0")


def search_many(adapter, keywords: list[str], *, max_pages: int = 1, hits: int = 30,
                limits: Limits = Limits(), sleep=time.sleep,
                **filters) -> tuple[list[Offer], SearchStats]:
    """keywords を順に検索し、mall_item_code で重複排除した Offer と統計を返す。

    上限超えは ValueError（黙って切らない・通信前に判定）。
    http_429 は残り全部を打ち切る。他の AdapterError はそのキーワードだけ記録して続行。
    """
    keywords = list(keywords)
    _validate(keywords, max_pages, hits, limits)

    stats = SearchStats(fetched_at=datetime.now(JST).isoformat())
    unique: dict[tuple[str, str], Offer] = {}
    requested_any = False

    for keyword in keywords:
        stat = KeywordStat(keyword=keyword)
        stats.per_keyword.append(stat)
        rate_limited = False
        for page in range(1, max_pages + 1):
            if requested_any:
                sleep(limits.min_interval_sec)
            requested_any = True
            try:
                offers, api_count = adapter.search(keyword, page=page, hits=hits, **filters)
            except AdapterError as exc:
                stat.error = exc.kind
                rate_limited = exc.kind == "http_429"
                break
            if stat.api_count is None:
                stat.api_count = api_count
            stat.received += len(offers)
            stats.total_received += len(offers)
            for offer in offers:
                key = (offer.mall, offer.mall_item_code)
                existing = unique.get(key)
                if existing is None:
                    offer.matched_keywords = [keyword]
                    unique[key] = offer
                else:
                    stats.duplicates_removed += 1
                    if keyword not in existing.matched_keywords:
                        existing.matched_keywords.append(keyword)
            if not offers or page * hits >= api_count:
                break
        if rate_limited:
            stats.stopped_reason = "rate_limited"
            break

    stats.unique_offers = len(unique)
    return list(unique.values()), stats
