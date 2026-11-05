# @owns 複数キーワード検索の実行制御（ページング・重複排除・統計・流量制限・429打ち切り）
"""検索オーケストレーション。モール固有の知識は持たない（Adapter 越しに呼ぶだけ）。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .adapters.base import AdapterError
from .inputs import MAX_HITS, MAX_PAGES, check_page_range
from .models import KeywordStat, Offer, SearchStats

JST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Limits:
    max_keywords: int = 5          # 検索語の数。楽天由来ではなくこのアプリの既存仕様（SPEC §6・inputs.MAX_KEYWORDS と同じ値）
    min_interval_sec: float = 1.0  # 出典: 楽天ウェブサービスの 1 秒 1 リクエスト
    # 1 回の呼び出しの取得時間の上限。出典: Cloudflare の既定プロキシ読み取りタイムアウト 100 秒（超えると 524 で全損）に、
    # 応答の生成・送信の余裕 20 秒を見込んだ 80 秒。超えそうなら取れた分で止めて next_page を返す
    time_budget_sec: float = 80.0


def _validate(keywords, max_pages: int | None, start_page: int, hits: int, limits: Limits) -> None:
    if not keywords:
        raise ValueError("keywords must not be empty")
    if len(keywords) > limits.max_keywords:
        raise ValueError(f"too many keywords: {len(keywords)} > {limits.max_keywords}")
    check_page_range(start_page, max_pages)     # 1〜100 の整数と start_page+pages-1 ≤ 100（楽天の天井）。不正は InvalidInput(ValueError)
    if not (1 <= hits <= MAX_HITS):       # 楽天の hits 上限 30（出典: 楽天 IchibaItem Search 仕様）
        raise ValueError("hits must be 1..30")
    if limits.min_interval_sec < 0:
        raise ValueError("min_interval_sec must be >= 0")
    if limits.time_budget_sec <= 0:
        raise ValueError("time_budget_sec must be > 0")


def _finish_stat(stat: KeywordStat, hits: int) -> None:
    """取得を終えた語の last_page・remaining・truncated を決める（next_page は呼び出し側が先に決めておく）。"""
    if stat.pages_fetched:
        stat.last_page = stat.start_page + stat.pages_fetched - 1
    if stat.api_count is not None and stat.last_page is not None:
        reachable = min(stat.api_count, MAX_PAGES * hits)      # 楽天が返すのは 100 ページ目まで
        stat.remaining = max(0, reachable - stat.last_page * hits)
    stat.truncated = stat.next_page is not None


def search_many(adapter, keywords: list[str], *, max_pages: int | None = None, start_page: int = 1,
                hits: int = 30, limits: Limits = Limits(), sleep=time.sleep, clock=None,
                **filters) -> tuple[list[Offer], SearchStats]:
    """keywords を順に検索し、mall_item_code で重複排除した Offer と統計を返す。

    語ごとに start_page 〜 start_page+max_pages-1 ページを取る（max_pages=None は既定の 3 ページ）。
    範囲が楽天の 100 ページ天井を超える指定は ValueError（黙って切らない・通信前に判定）。
    ヒットが尽きたら早く止める。続きがあれば stat.next_page に次のページ番号を入れる。
    1 回の取得が limits.time_budget_sec を超えそうなら、そこで止めて取れた分を返す（stopped_reason=time_limit・
    未取得の語は next_page=start_page）。clock は試験で実時間を固定するために差し替えられる。
    http_429 は残り全部を打ち切る。他の AdapterError はそのキーワードだけ記録して続行。
    """
    clock = clock or time.monotonic       # 呼び出し時に解決（試験で time.monotonic を差し替えられる）
    keywords = list(keywords)
    _validate(keywords, max_pages, start_page, hits, limits)
    pages_wanted = check_page_range(start_page, max_pages)[1]
    end_page = start_page + pages_wanted - 1
    started = clock()

    stats = SearchStats(fetched_at=datetime.now(JST).isoformat())
    unique: dict[tuple[str, str], Offer] = {}
    requests_done = 0

    def time_is_up() -> bool:
        """次の 1 回（直近までの平均所要時間と同じだけかかると見る）を終えた時点で上限を超えるか。"""
        elapsed = clock() - started
        return elapsed + elapsed / requests_done > limits.time_budget_sec

    for index, keyword in enumerate(keywords):
        stat = KeywordStat(keyword=keyword, start_page=start_page)
        stats.per_keyword.append(stat)
        rate_limited = timed_out = False
        for page in range(start_page, end_page + 1):
            if requests_done:
                if time_is_up():
                    timed_out = True
                    stat.next_page = page
                    break
                sleep(limits.min_interval_sec)
            requests_done += 1
            try:
                offers, api_count = adapter.search(keyword, page=page, hits=hits, **filters)
            except AdapterError as exc:
                stat.error = exc.kind
                rate_limited = exc.kind == "http_429"
                break
            if stat.api_count is None:
                stat.api_count = api_count
            stat.pages_fetched += 1
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
        else:
            # break せずに指定範囲の最後のページまで来た。ヒットが残っていて、楽天の 100 ページ天井の手前なら続きがある
            if stat.api_count is not None and stat.api_count > end_page * hits and end_page < MAX_PAGES:
                stat.next_page = end_page + 1
        _finish_stat(stat, hits)
        if rate_limited:
            stats.stopped_reason = "rate_limited"
            break
        if timed_out:
            stats.stopped_reason = "time_limit"
            for rest in keywords[index + 1:]:       # 未着手の語。続きは最初のページから
                unstarted = KeywordStat(keyword=rest, start_page=start_page, next_page=start_page, truncated=True)
                stats.per_keyword.append(unstarted)
            break

    stats.unique_offers = len(unique)
    stats.elapsed_sec = round(clock() - started, 1)    # 取得にかかった秒
    return list(unique.values()), stats
