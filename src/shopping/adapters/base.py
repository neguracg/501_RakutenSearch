"""モール Adapter の共通インターフェースとエラー型。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Offer


class AdapterError(Exception):
    """kind だけを持つ。URL・キー・応答本文は絶対に含めない。"""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind

    def __str__(self) -> str:
        return self.kind

    def __repr__(self) -> str:
        return f"AdapterError({self.kind!r})"


class MarketplaceAdapter(ABC):
    mall: str = ""

    @abstractmethod
    def search(self, keyword: str, *, page: int = 1, hits: int = 30,
               ng_keyword: str | None = None, min_price: int | None = None,
               max_price: int | None = None, sort: str = "standard",
               availability: int = 1) -> tuple[list[Offer], int]:
        """(offers, api_count) を返す。失敗は AdapterError(kind)。"""
