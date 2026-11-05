"""AC11: MCP クライアントからモック検索結果を取得できる（in-process と stdio 子プロセスの両方）。"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from shopping.mcp_server import build_server

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "regulars.sample.json"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SHOPPING_MOCK", "1")
    monkeypatch.setenv("SHOPPING_REGULARS_PATH", str(SAMPLE))
    # 認証情報なしでも動くこと
    monkeypatch.delenv("RAKUTEN_APPLICATION_ID", raising=False)
    monkeypatch.delenv("RAKUTEN_ACCESS_KEY", raising=False)


def call(name, args):
    async def go():
        async with Client(build_server()) as c:
            return await c.call_tool(name, args)
    return asyncio.run(asyncio.wait_for(go(), timeout=30))


def test_lists_three_tools_with_japanese_descriptions():
    async def go():
        async with Client(build_server()) as c:
            return await c.list_tools()
    tools = asyncio.run(asyncio.wait_for(go(), timeout=30)).tools
    by = {t.name: t for t in tools}
    assert set(by) == {"search_products", "compare_offers", "find_regular_item"}
    for t in tools:
        assert t.description and len(t.description) > 80
        assert any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in t.description)
    assert "keywords" in by["search_products"].input_schema["properties"]
    props = by["compare_offers"].input_schema["properties"]
    for k in ("include_terms", "exclude_terms", "basis", "desired_quantity"):
        assert k in props
    assert "required_spec" not in props and "unit" not in props
    assert by["find_regular_item"].input_schema["required"] == ["regular_id"]


def test_ac11_search_products_returns_mock_candidates():
    r = call("search_products", {"keywords": ["洗濯洗剤 詰め替え"]})
    assert not r.is_error
    data = r.structured_content
    assert data["ok"] and data["mock"] is True and data["returned"] > 0
    assert all(o["url"] for o in data["offers"])
    # テキスト側にも同じ JSON が入っている
    assert json.loads(r.content[0].text)["returned"] == data["returned"]


def test_compare_offers_via_mcp():
    r = call("compare_offers", {"keywords": ["洗濯洗剤 詰め替え"],
                                "include_terms": ["詰め替え"], "exclude_terms": ["本体"],
                                "basis": "g", "desired_quantity": 5000})
    c = r.structured_content["comparison"]
    assert c["cheapest_unit_price"]["quantity"]["confidence"] == "high"
    assert c["cheapest_total"] is None and c["caveats"]


def test_find_regular_item_via_mcp():
    r = call("find_regular_item", {"regular_id": "detergent-refill"})
    d = r.structured_content
    assert d["ok"] and d["regular"]["id"] == "detergent-refill"


def test_find_regular_item_unknown_id_is_reported_in_result():
    r = call("find_regular_item", {"regular_id": "zzz"})
    assert r.structured_content["ok"] is False
    assert r.structured_content["error"]["kind"] == "regulars_not_found"


def test_invalid_arguments_do_not_crash_server():
    r = call("search_products", {"keywords": []})
    assert r.structured_content["ok"] is False
    assert r.structured_content["error"]["kind"] == "invalid_request"


def test_stdio_default_is_mock_and_live_needs_explicit_env(monkeypatch):
    # B4: SHOPPING_MOCK が無くてもモック。SHOPPING_LIVE=1 の時だけ実 API の Adapter（認証情報が無ければ安全に止まる）
    monkeypatch.delenv("SHOPPING_MOCK")
    r = call("search_products", {"keywords": ["洗濯洗剤"]})
    assert r.structured_content["ok"] and r.structured_content["mock"] is True
    monkeypatch.setenv("SHOPPING_LIVE", "1")
    monkeypatch.setattr("shopping.service.load_credentials",
                        lambda *a, **k: __import__("shopping.config", fromlist=["x"]).RakutenCredentials("", ""))
    r = call("search_products", {"keywords": ["洗濯洗剤"]})
    assert r.structured_content["ok"] is False and r.structured_content["error"]["kind"] == "missing_credentials"


def test_stdio_subprocess_serves_mock_without_credentials():
    """実際に `python -m shopping.mcp_server` を子プロセスで起動して stdio 越しに呼ぶ。"""
    from mcp.client.stdio import stdio_client
    from mcp.client.session import ClientSession

    env = {k: v for k, v in os.environ.items()
           if k not in ("RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY")}
    env.update(PYTHONPATH=str(ROOT / "src"), SHOPPING_MOCK="1", PYTHONIOENCODING="utf-8")
    params = StdioServerParameters(command=sys.executable, args=["-m", "shopping.mcp_server"],
                                   env=env, cwd=str(ROOT))

    async def go():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool("search_products",
                                               {"keywords": ["洗濯洗剤"]})
    r = asyncio.run(asyncio.wait_for(go(), timeout=60))
    data = r.structured_content or json.loads(r.content[0].text)
    assert data["ok"] and data["mock"] is True and data["returned"] > 0
