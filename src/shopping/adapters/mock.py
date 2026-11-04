# @owns SHOPPING_MOCK 用の架空データ Adapter（API を呼ばない）
"""モック Adapter。src/shopping/mock_data.json（架空データ）を楽天の応答形のまま読み、
本物と同じ parse_item で Offer にする。tests/fixtures とは別物。"""
from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from pathlib import Path

from ..models import Offer
from .base import AdapterError, MarketplaceAdapter
from .rakuten import JST, parse_item

MOCK_DATA_PATH = Path(__file__).resolve().parent.parent / "mock_data.json"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


class MockAdapter(MarketplaceAdapter):
    mall = "rakuten"

    def __init__(self, data_path: Path | str | None = None, clock=None):
        self._path = Path(data_path) if data_path else MOCK_DATA_PATH
        self._clock = clock or (lambda: datetime.now(JST))
        self.calls = 0

    def search(self, keyword: str, *, page: int = 1, hits: int = 30,
               ng_keyword: str | None = None, min_price: int | None = None,
               max_price: int | None = None, sort: str = "standard",
               availability: int = 1) -> tuple[list[Offer], int]:
        if not isinstance(keyword, str) or not keyword.strip():
            raise AdapterError("invalid_request")
        if not (1 <= hits <= 30) or page < 1:
            raise AdapterError("invalid_request")
        self.calls += 1
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise AdapterError("unexpected_response") from None
        terms = _norm(keyword).split()
        ng_terms = _norm(ng_keyword).split() if ng_keyword else []
        matched = []
        for item in data.get("Items", []):
            name = _norm(item.get("itemName", ""))
            if not all(t in name for t in terms):
                continue
            if any(t in name for t in ng_terms):
                continue
            price = item.get("itemPrice")
            if min_price is not None and (price is None or price < min_price):
                continue
            if max_price is not None and (price is None or price > max_price):
                continue
            if availability == 1 and item.get("availability") == 0:
                continue
            matched.append(item)
        if sort == "+itemPrice":
            matched.sort(key=lambda i: i.get("itemPrice", 0))
        elif sort == "-itemPrice":
            matched.sort(key=lambda i: -i.get("itemPrice", 0))
        start = (page - 1) * hits
        fetched_at = self._clock().isoformat()
        offers = [parse_item(i, fetched_at) for i in matched[start:start + hits]]
        return offers, len(matched)
