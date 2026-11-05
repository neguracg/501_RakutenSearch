import socket
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from fakes import FakeOpener, FakeResponse, http_error, load_fixture
from shopping.adapters.base import AdapterError
from shopping.adapters.rakuten import RakutenAdapter, is_item_url

APP_ID = "FAKEAPPID_123"
KEY = "FAKEACCESSKEY_456"


def CLOCK():
    return datetime(2026, 11, 5, 9, 0, 0, tzinfo=timezone(timedelta(hours=9)))


EMPTY = {"count": 0, "Items": []}


def make(*responses):
    opener = FakeOpener(*responses)
    return RakutenAdapter(APP_ID, KEY, opener=opener, clock=CLOCK), opener


def test_parses_upper_items_fixture():
    ad, _ = make(load_fixture("rakuten_search_upper.json"))
    offers, count = ad.search("トイレットペーパー")
    assert count == 57 and len(offers) == 3
    o = offers[0]
    assert (o.mall, o.mall_item_code, o.price) == ("rakuten", "exshop-a:tp-48", 1980)
    assert o.shipping_status == "included" and o.shipping_fee is None
    assert o.availability is True and o.shop_code == "exshop-a" and o.points_rate == 1
    assert o.review_average == 4.5 and o.review_count == 120
    assert o.fetched_at == "2026-11-05T09:00:00+09:00"
    assert offers[1].shipping_status == "separate"
    assert offers[2].availability is False


def test_parses_lowercase_items():
    ad, _ = make(load_fixture("rakuten_search_lower.json"))
    offers, count = ad.search("x")
    assert count == 1 and len(offers) == 1


@pytest.mark.parametrize("body", [
    {"count": 0},
    {"count": 0, "items": [], "Items": []},
    {"error": "wrong_parameter", "error_description": "x"},
    {"count": 1, "Items": [{"itemName": "a"}]},
    {"Items": []},
    {"count": 1, "Items": "notalist"},
    [],
])
def test_unexpected_shapes(body):
    ad, _ = make(body)
    with pytest.raises(AdapterError) as e:
        ad.search("x")
    assert e.value.kind == "unexpected_response"


def test_search_url_is_needs_review_not_dropped():
    ad, _ = make(load_fixture("rakuten_search_upper.json"))
    offers, _ = ad.search("x")
    assert [o.item_url_status for o in offers] == ["ok", "ok", "needs_review"]
    # 捨てない・作らない: 元の値がそのまま残る
    assert offers[2].item_url == "https://search.rakuten.co.jp/search/mall/exshop-c/"


@pytest.mark.parametrize("url,ok", [
    ("https://item.rakuten.co.jp/shop/item/", True),
    ("https://item.rakuten.co.jp/shop/item", True),
    ("http://item.rakuten.co.jp/shop/item/", False),
    ("https://item.rakuten.co.jp/shop/", False),
    ("https://item.rakuten.co.jp.evil.example/shop/item/", False),
    ("https://user:pw@item.rakuten.co.jp/shop/item/", False),
    ("https://www.rakuten.co.jp/shop/item/", False),
    ("", False), (None, False), (123, False),
])
def test_is_item_url(url, ok):
    assert is_item_url(url) is ok


def test_missing_url_kept_as_needs_review():
    ad, _ = make({"count": 1, "Items": [{"itemCode": "s:i", "itemName": "n", "itemPrice": 100}]})
    offers, _ = ad.search("x")
    assert offers[0].item_url_status == "needs_review" and offers[0].item_url == ""
    assert offers[0].shipping_status == "unknown" and offers[0].availability is None


@pytest.mark.parametrize("exc,kind", [
    (http_error(403), "http_403"),
    (http_error(429), "http_429"),
    (http_error(500), "http_500"),
    (http_error(404), "http_404"),
    (socket.timeout("t"), "timeout"),
    (TimeoutError("t"), "timeout"),
    (URLError("dns SECRET"), "network_error"),
    (URLError(socket.timeout("t")), "timeout"),
    (ConnectionResetError("x"), "network_error"),
])
def test_error_kinds(exc, kind):
    ad, _ = make(exc)
    with pytest.raises(AdapterError) as e:
        ad.search("x")
    assert e.value.kind == kind


@pytest.mark.parametrize("body", [b"<html>not json", b"\xff\xfe\x00bad"])
def test_invalid_json(body):
    ad, _ = make(body)
    with pytest.raises(AdapterError) as e:
        ad.search("x")
    assert e.value.kind == "invalid_json"


def test_non_200_status():
    ad, _ = make(FakeResponse(b"{}", status=302))
    with pytest.raises(AdapterError) as e:
        ad.search("x")
    assert e.value.kind == "http_302"


def test_missing_credentials_makes_no_request():
    opener = FakeOpener(EMPTY)
    for a, k in (("", KEY), (APP_ID, ""), ("", "")):
        with pytest.raises(AdapterError) as e:
            RakutenAdapter(a, k, opener=opener).search("x")
        assert e.value.kind == "missing_credentials"
    assert opener.requests == []


def test_crlf_credentials_rejected():
    opener = FakeOpener(EMPTY)
    with pytest.raises(AdapterError):
        RakutenAdapter("a\r\nX-Evil: 1", KEY, opener=opener).search("x")
    assert opener.requests == []


@pytest.mark.parametrize("kw", ["", "   ", "あ" * 50])
def test_invalid_keyword(kw):
    ad, op = make(EMPTY)
    with pytest.raises(AdapterError) as e:
        ad.search(kw)
    assert e.value.kind == "invalid_request" and op.requests == []


def test_request_shape_and_filters():
    ad, op = make(EMPTY)
    ad.search("トイレットペーパー 12ロール", page=2, hits=10, ng_keyword="ダブル以外",
              min_price=100, max_price=3000, sort="+itemPrice", availability=1)
    req = op.requests[0]
    u = urlsplit(req.full_url)
    q = parse_qs(u.query)
    assert u.scheme == "https" and u.hostname == "openapi.rakuten.co.jp"
    assert q["keyword"] == ["トイレットペーパー 12ロール"]
    assert q["formatVersion"] == ["2"] and q["hits"] == ["10"] and q["page"] == ["2"]
    assert q["NGKeyword"] == ["ダブル以外"] and q["minPrice"] == ["100"] and q["maxPrice"] == ["3000"]
    assert q["sort"] == ["+itemPrice"] and q["availability"] == ["1"]
    assert req.get_header("Accesskey") == KEY
    assert op.timeouts[0] and op.timeouts[0] > 0


def test_optional_filters_omitted():
    ad, op = make(EMPTY)
    ad.search("x")
    q = parse_qs(urlsplit(op.requests[0].full_url).query)
    assert "NGKeyword" not in q and "minPrice" not in q and "maxPrice" not in q


@pytest.mark.parametrize("bad", [dict(hits=0), dict(hits=31), dict(page=0)])
def test_bad_paging_rejected(bad):
    ad, op = make(EMPTY)
    with pytest.raises(AdapterError):
        ad.search("x", **bad)
    assert op.requests == []


def test_no_secret_in_exceptions_offers_or_repr():
    cases = [http_error(403), http_error(429), socket.timeout("SECRET"),
             URLError("SECRET"), b"SECRET not json"]
    for c in cases:
        ad, _ = make(c)
        with pytest.raises(AdapterError) as e:
            ad.search("x")
        blob = " ".join([str(e.value), repr(e.value), str(e.value.__cause__),
                         str(e.value.__context__ or "")])
        for s in (APP_ID, KEY, "SECRET", "openapi.rakuten"):
            assert s not in blob
    ad, _ = make(load_fixture("rakuten_search_upper.json"))
    offers, _ = ad.search("x")
    assert APP_ID not in repr(offers) and KEY not in repr(offers)
    assert APP_ID not in repr(ad) and KEY not in repr(ad)


@pytest.mark.parametrize("raw,expected", [
    ("1980", 1980), (" 12 ", 12), ("-5", -5), (7, 7), ("①②", None), ("²", None), ("１２３", None),
    ("٣", None), ("--5", None), ("-", None), ("", None), ("1.5", None), (True, None), (None, None),
    ("9" * 5000, None),
])
def test_to_int_accepts_only_ascii_digits(raw, expected):
    # B3: isdigit() は ①² を真とするのに int() が落ちる。Unicode 数字で例外を出さない
    from shopping.adapters.rakuten import _to_int
    assert _to_int(raw) == expected


def test_parse_item_with_unicode_digit_fields_does_not_raise():
    from shopping.adapters.rakuten import parse_item
    o = parse_item({"itemCode": "s:1", "itemName": "x", "itemPrice": "①²", "postageFlag": "²",
                    "reviewCount": "٣", "itemUrl": "https://item.rakuten.co.jp/s/1/"}, "t")
    assert o.price is None and o.shipping_status == "unknown" and o.review_count is None
