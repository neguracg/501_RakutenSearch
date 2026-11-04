"""データモデル。不明は None（推測で埋めない）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QuantityInfo:
    unit: str                    # 比較の基準単位（例 "ロール"）
    per_pack: int | None         # 1袋あたり
    pack_count: int | None       # 袋数（単品なら 1）
    total: int | None            # 総数。confidence != "high" なら None
    ply: str | None              # "single" / "double" / None
    length_m: float | None       # 1単位あたりの長さ(m)
    confidence: str              # "high" / "low" / "none"
    evidence: str                # 根拠にした文字列（無ければ ""）


@dataclass
class Offer:
    mall: str
    mall_item_code: str
    item_name: str
    price: int | None
    item_url: str
    item_url_status: str         # "ok" / "needs_review"
    shop_name: str | None = None
    shop_code: str | None = None
    shipping_status: str = "unknown"      # "included" / "separate" / "unknown"
    shipping_fee: int | None = None
    availability: bool | None = None
    points_rate: int | None = None
    review_average: float | None = None
    review_count: int | None = None
    jan: str | None = None
    model_number: str | None = None
    caption: str | None = None
    fetched_at: str | None = None         # ISO8601 JST
    matched_keywords: list[str] = field(default_factory=list)
    quantity: QuantityInfo | None = None


@dataclass
class Product:
    product_key: str
    name: str
    jan: str | None = None
    maker: str | None = None
    model_number: str | None = None
    spec: dict = field(default_factory=dict)
    spec_status: str = "unknown"          # confirmed / extracted / unknown


@dataclass
class KeywordStat:
    keyword: str
    api_count: int | None = None
    received: int = 0
    error: str | None = None


@dataclass
class SearchStats:
    per_keyword: list[KeywordStat] = field(default_factory=list)
    total_received: int = 0
    duplicates_removed: int = 0
    unique_offers: int = 0
    fetched_at: str | None = None
    stopped_reason: str | None = None
