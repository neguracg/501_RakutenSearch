"""WP2-5: 公開リモートMCP（{BASE}/mcp・Streamable HTTP・認証なし）。AC-W9 / AC-W2 / AC-W8。
in-process の MCP クライアントで ASGI アプリへ繋ぐ（実 API は呼ばない）。"""
import asyncio
import contextlib
import json

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from fakes import FakeAdapter, make_offer
from shopping.adapters.base import AdapterError
from shopping.credit import CREDIT_TEXT, CREDIT_URL, OPERATOR_SHORT
from shopping.guard import Gate, GuardedAdapter, RateLimiter
from shopping.web import create_app

SECRET_ID = "APPID-SECRET-1234567890"
SECRET_KEY = "ACCESSKEY-SECRET-abcdef"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def pages():
    offers = [make_offer("a", "洗濯洗剤 詰め替え 900g×4袋", 2400, shipping_status="included"),
              make_offer("b", "洗濯洗剤 詰め替え 900g×6袋", 3000, shipping_status="included")]
    return {("洗濯洗剤", 1): (offers, 2)}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("RAKUTEN_APPLICATION_ID", SECRET_ID)
    monkeypatch.setenv("RAKUTEN_ACCESS_KEY", SECRET_KEY)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.negura.website/kaimono")
    monkeypatch.delenv("SHOPPING_MOCK", raising=False)


def make_app(base, adapter=None, limit=1000):
    clock = Clock()
    ad = adapter or FakeAdapter(pages())
    gate = Gate(GuardedAdapter(ad, clock=clock, sleep=clock.sleep), RateLimiter(limit=limit, clock=clock))
    return create_app(base, gate), ad


def run_session(app, base, work, headers=None):
    """app の lifespan を回し、ASGI 経由で MCP クライアントを繋いで work(client) を実行する。"""
    async def inner(connect):
        async with connect(headers) as c:
            return await work(c)
    return run_multi(app, base, inner)


def run_multi(app, base, work):
    """work(connect) に connect(headers) を渡す。1 つの lifespan の中で別 IP のクライアントを複数作れる。"""
    @contextlib.asynccontextmanager
    async def connect(headers=None):
        hc = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),
                                base_url="http://app.negura.website", headers=headers or {})
        async with hc:
            async with Client(streamable_http_client(
                    f"http://app.negura.website{base}/mcp", http_client=hc)) as c:
                yield c

    async def go():
        async with app.router.lifespan_context(app):
            return await work(connect)
    return asyncio.run(asyncio.wait_for(go(), timeout=60))


@pytest.mark.parametrize("base", ["", "/kaimono"])
def test_initialize_list_tools_and_call_compare(base):
    app, ad = make_app(base)

    async def work(c):
        tools = (await c.list_tools()).tools
        r = await c.call_tool("compare_offers", {"keywords": ["洗濯洗剤"],
                                                 "include_terms": ["詰め替え"], "basis": "g"})
        return tools, r

    tools, r = run_session(app, base, work)
    assert {t.name for t in tools} == {"search_products", "compare_offers"}   # AC-W8/W9: 定番品ツールは出さない
    assert not r.is_error
    data = r.structured_content
    assert data["ok"] and data["comparison"]["cheapest_unit_price"]["item_code"] == "b"
    assert len(ad.calls) == 1


def test_tool_results_carry_credit_operator_and_web_for_both_tools():
    app, _ = make_app("/kaimono")

    async def work(c):
        a = await c.call_tool("search_products", {"keywords": ["洗濯洗剤"]})
        b = await c.call_tool("compare_offers", {"keywords": ["洗濯洗剤"]})
        bad = await c.call_tool("compare_offers", {"keywords": ["洗濯洗剤"], "desired_quantity": -1})
        return a, b, bad

    for r in run_session(app, "/kaimono", work):
        d = r.structured_content
        assert d["credit"] == CREDIT_TEXT == "Supported by Rakuten Developers"
        assert d["credit_url"] == CREDIT_URL == "https://developers.rakuten.com/"
        assert d["operator"] == OPERATOR_SHORT == "個人開発者 negura が運営（楽天グループとは無関係）"
        assert d["web"] == "https://app.negura.website/kaimono"
        assert json.loads(r.content[0].text)["credit"] == CREDIT_TEXT   # テキスト側にも入る


def test_instructions_say_public_tool_and_credit_and_no_private_wording():
    app, _ = make_app("")

    async def work(c):
        return c.instructions

    text = run_session(app, "", work)
    assert "公開の買い物リサーチツール" in text and "個人用" not in text
    assert "回答の末尾にクレジット（Supported by Rakuten Developers）を添えること" in text
    assert "caveats" in text


def test_find_regular_item_is_not_callable_on_public_endpoint():
    app, _ = make_app("")

    async def work(c):
        try:
            r = await c.call_tool("find_regular_item", {"regular_id": "detergent-refill"})
        except Exception as exc:  # 未知のツールは MCPError か is_error のどちらでも可
            return str(exc)
        return r

    out = run_session(app, "", work)
    if isinstance(out, str):
        assert "find_regular_item" in out or "nknown" in out or "not" in out.lower()
    else:
        assert out.is_error


async def _search(c):
    return await c.call_tool("search_products", {"keywords": ["洗濯洗剤"]})


def test_mcp_shares_the_same_rate_limit_and_cache_as_web():
    app, ad = make_app("/kaimono", limit=2)

    async def work(connect):
        outs = []
        async with connect({"CF-Connecting-IP": "203.0.113.7"}) as c:
            for _ in range(3):
                outs.append(await _search(c))
        async with connect({"CF-Connecting-IP": "203.0.113.8"}) as c2:   # 別 IP は通る
            other = await _search(c2)
        return outs, other

    outs, other = run_multi(app, "/kaimono", work)
    assert [o.structured_content["ok"] for o in outs] == [True, True, False]
    assert outs[2].structured_content["error"]["kind"] == "rate_limited"
    assert outs[2].structured_content["credit"] == CREDIT_TEXT        # エラーでもクレジットは付く
    assert other.structured_content["ok"]
    assert len(ad.calls) == 1                                          # キャッシュを共有（API は 1 回）


def test_web_and_mcp_count_against_the_same_ip_budget():
    from fastapi.testclient import TestClient
    app, _ = make_app("/kaimono", limit=2)
    web = TestClient(app, raise_server_exceptions=False)
    h = {"CF-Connecting-IP": "203.0.113.20"}
    assert web.get("/kaimono/search?q=洗濯洗剤", headers=h).status_code == 200
    assert web.get("/kaimono/search?q=洗濯洗剤", headers=h).status_code == 200

    out = run_session(app, "/kaimono", _search, headers=h)
    assert out.structured_content["error"]["kind"] == "rate_limited"


def test_pages_argument_is_clamped_with_note():
    offers = pages()[("洗濯洗剤", 1)][0]
    app, ad = make_app("", adapter=FakeAdapter({("洗濯洗剤", 1): (offers, 100),
                                               ("洗濯洗剤", 2): (offers, 100)}))

    async def work(c):
        return await c.call_tool("search_products", {"keywords": ["洗濯洗剤"], "pages": 3})

    d = run_session(app, "", work).structured_content
    assert d["ok"] and any("1 ページ" in n for n in d["notes"])
    assert all(kw.get("page") == 1 for _, kw in ad.calls)


def test_upstream_errors_do_not_leak_keys_and_still_carry_credit():
    app, _ = make_app("", adapter=FakeAdapter({("洗濯洗剤", 1): AdapterError("http_429")}))

    async def work(c):
        return await c.call_tool("compare_offers", {"keywords": ["洗濯洗剤"]})

    r = run_session(app, "", work)
    blob = json.dumps(r.structured_content, ensure_ascii=False)
    assert SECRET_ID not in blob and SECRET_KEY not in blob
    assert r.structured_content["credit"] == CREDIT_TEXT and r.structured_content["ok"] is False


def test_no_secrets_in_any_mcp_response_and_no_cookies():
    app, _ = make_app("/kaimono")

    async def go():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),
                                          base_url="http://app.negura.website") as hc:
                body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
                return await hc.post("/kaimono/mcp", json=body, headers=h)

    r = asyncio.run(asyncio.wait_for(go(), timeout=30))
    assert r.status_code == 200
    assert SECRET_ID not in r.text and SECRET_KEY not in r.text
    assert "set-cookie" not in r.headers


def test_trailing_slash_and_wrong_path():
    app, _ = make_app("/kaimono")

    async def go():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),
                                          base_url="http://app.negura.website") as hc:
                body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
                a = await hc.post("/kaimono/mcp/", json=body, headers=h)
                b = await hc.post("/mcp", json=body, headers=h)
                return a.status_code, b.status_code

    a, b = asyncio.run(asyncio.wait_for(go(), timeout=30))
    assert a == 200 and b == 404
