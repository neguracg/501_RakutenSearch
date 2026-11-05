"""WP4-2/3: 公開入口 4 つ × 入力項目の未固定セルと、S8〜S10・基準単位の検査一本化・service 既定モックの固定。
implementer の自作の確認（緑は証明ではない）。実 API は呼ばない。

入口: web_search（/search）・web_compare（/compare）・mcp_search（search_products）・mcp_compare（compare_offers）。
弾くべき不正入力は、どの入口でも (1) 拒否される (2) アダプタ（API）を呼ばない (3) IP 別の回数を消費しない。
"""
import threading

import pytest
from fastapi.testclient import TestClient

from fakes import FakeAdapter, make_offer
from shopping import inputs, service
from shopping.adapters import rakuten
from shopping.credit import CREDIT_TEXT
from shopping.guard import Gate, GuardedAdapter, RateLimiter
from shopping.inputs import InvalidInput
from shopping.pricing import compare
from shopping.web import create_app

from test_mcp_http import RPC_HEADERS


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def offers():
    return [make_offer("a", "洗濯洗剤 詰め替え 900g×4袋", 2400, shipping_status="included"),
            make_offer("b", "洗濯洗剤 詰め替え 1.5kg", 1500, shipping_status="included"),
            make_offer("c", "洗濯洗剤 本体 400g", 700, shipping_status="included")]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("RAKUTEN_APPLICATION_ID", "APPID-SECRET-1234567890")
    monkeypatch.setenv("RAKUTEN_ACCESS_KEY", "ACCESSKEY-SECRET-abcdef")
    monkeypatch.delenv("SHOPPING_MOCK", raising=False)


def make_env(limit=2):
    clock = Clock()
    ad = FakeAdapter({("洗濯洗剤", 1): (offers(), 3)})
    gate = Gate(GuardedAdapter(ad, clock=clock, sleep=clock.sleep), RateLimiter(limit=limit, clock=clock))
    return TestClient(create_app("", gate), raise_server_exceptions=False), ad


# 入口ごとの呼び出し。(rejected: bool, detail) を返す。IP は固定して回数枠の消費を見る
IP = "203.0.113.77"


def web(client, path, params):
    r = client.get(path, params=params, headers={"CF-Connecting-IP": IP})
    return r.status_code == 400, r


def mcp(client, tool, args):
    args = dict({"pages": 1}, **args)    # 既定の pages は 3 ページ（回数制限の重み 3）。この表は 1 回=1 回分で数えたいので 1 に固定する
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}
    r = client.post("/mcp", json=body, headers=dict(RPC_HEADERS, **{"CF-Connecting-IP": IP}))
    assert r.status_code == 200, r.text
    d = r.json()["result"]["structuredContent"]
    assert d["credit"] == CREDIT_TEXT
    rejected = d["ok"] is False and d["error"]["kind"] == "invalid_request"
    return rejected, d


def call(entrance, client, fields):
    """fields: 共通の項目名（keywords/ng_keyword/min_price/max_price/sort/include_terms/exclude_terms/basis/
    desired_quantity）を入口ごとの引数名に直して送る。入口が持たない項目なら None（セル対象外）。"""
    web_names = {"keywords": "q", "ng_keyword": "ng", "min_price": "min_price", "max_price": "max_price",
                 "include_terms": "include", "exclude_terms": "exclude", "basis": "basis"}
    if entrance.startswith("web"):
        params = {}
        for k, v in fields.items():
            if k not in web_names:
                return None                       # sort・desired_quantity は Web に入力欄が無い
            if k == "keywords":
                v = ",".join(v)
            elif k in ("include_terms", "exclude_terms"):
                v = " ".join(v)
            params[web_names[k]] = v
        if entrance == "web_compare" or "basis" not in fields:
            return web(client, "/compare" if entrance == "web_compare" else "/search", params)
        return web(client, "/search", params)
    tool = "search_products" if entrance == "mcp_search" else "compare_offers"
    if tool == "search_products" and {"basis", "desired_quantity"} & set(fields):
        return None                               # 一覧には basis・desired_quantity の引数が無い
    return mcp(client, tool, fields)


ENTRANCES = ["web_search", "web_compare", "mcp_search", "mcp_compare"]
VALID = {"keywords": ["洗濯洗剤"]}

# 不正な値（共通の項目名 → 値のリスト）
INVALID = {
    "keywords": [list("abcdef"), ["あ" * 43], ["x" * 129]],
    "ng_keyword": ["x" * 129, "あ" * 43, "a b c d e f"],
    "min_price": [-1, 10_000_001],
    "max_price": [-1, 10_000_001],
    "include_terms": [["x" * 129], ["あ" * 43], list("abcdef")],
    "exclude_terms": [["x" * 129], ["あ" * 43], list("abcdef")],
    "basis": ["ふしぎ", "1個", "x" * 500],
    "sort": ["bogus", "+hacked"],
    "desired_quantity": [0, -5, 1e13],
}
CELLS = [(e, f, v) for e in ENTRANCES for f, vs in INVALID.items() for v in vs]


def _wire(entrance, field, value):
    """Web は価格を文字列で受けるので、整数を文字列にする。"""
    return str(value) if entrance.startswith("web") and field in ("min_price", "max_price") else value


@pytest.mark.parametrize("entrance,field,value", CELLS)
def test_invalid_input_is_rejected_calls_no_api_and_consumes_no_ip_budget(entrance, field, value):
    client, ad = make_env(limit=2)
    fields = dict(VALID, **{field: _wire(entrance, field, value)})
    with client:
        first = call(entrance, client, fields)
        if first is None:
            pytest.skip("この入口にはその入力項目が無い")
        for _ in range(5):                                       # 回数制限(2)を超えて弾かれ続ける
            rejected, _ = call(entrance, client, fields)
            assert rejected, (entrance, field)
        assert ad.calls == []
        # 回数枠は 2 回ぶん丸ごと残っている（不正入力は消費しない）
        for _ in range(2):
            ok, resp = call(entrance, client, dict(VALID))
            assert not ok
            if entrance.startswith("web"):
                assert resp.status_code == 200
            else:
                assert resp["ok"] is True
    assert len(ad.calls) == 1                                    # 2 回目はキャッシュ


# 境界ちょうどは通る（セルの反対側）
EDGE = {
    "keywords": [list("abcde"), ["あ" * 42], ["x" * 128]],
    "ng_keyword": ["x" * 128, "あ" * 42, "a b c d e"],
    "min_price": [0, 10_000_000],
    "max_price": [0, 10_000_000],
    "include_terms": [["あ" * 42], ["x" * 128], list("abcde")],
    "exclude_terms": [["あ" * 42], ["x" * 128], list("abcde")],
    "basis": ["個", "ml", "kg", "L", "mAh"],
    "sort": ["standard", "+itemPrice"],
    "desired_quantity": [0.5, 1e12],
}


@pytest.mark.parametrize("entrance,field,value", [(e, f, v) for e in ENTRANCES for f, vs in EDGE.items()
                                                  for v in vs])
def test_boundary_values_pass_on_every_entrance(entrance, field, value):
    client, ad = make_env(limit=1000)
    fields = dict(VALID, **{field: _wire(entrance, field, value)})
    # 1語が長い/語が 5 つの検索語は、アダプタに渡る検索語そのものが変わるので FakeAdapter が空を返すだけでよい
    with client:
        res = call(entrance, client, fields)
        if res is None:
            pytest.skip("この入口にはその入力項目が無い")
        rejected, resp = res
        assert not rejected
        if entrance.startswith("web"):
            assert resp.status_code in (200,)
        else:
            assert resp["ok"] is True


# --- C19: GET /mcp は 405 を即返す（SSE を開いて固まらない）-------------------------------------

def test_get_mcp_returns_405_within_a_deadline_not_a_hanging_stream():
    client, _ = make_env()
    out = {}

    def go():
        out["r"] = client.request("GET", "/mcp", headers={"Accept": "text/event-stream"})

    with client:
        t = threading.Thread(target=go, daemon=True)
        t.start()
        t.join(10)
        assert not t.is_alive(), "GET /mcp が応答を返さない（SSE ストリームを開いている）"
    assert out["r"].status_code == 405 and out["r"].headers["allow"] == "POST"


# --- service の省略既定: adapter を渡さなければモック（実 API を呼ばない）-------------------------

@pytest.fixture
def no_live(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("実 API の Adapter が呼ばれた")
    monkeypatch.setattr(rakuten.RakutenAdapter, "search", boom)
    monkeypatch.delenv("SHOPPING_LIVE", raising=False)


def test_service_functions_default_to_mock_when_adapter_is_omitted(no_live):
    s = service.search_products(["洗濯洗剤"])
    c = service.compare_offers(["洗濯洗剤"], include_terms=["詰め替え"])
    r = service.find_regular_item("detergent-refill",
                                  regulars_path=str(__import__("pathlib").Path(__file__).resolve().parent.parent
                                                    / "examples" / "regulars.sample.json"))
    for d in (s, c, r):
        assert d["ok"] and d["mock"] is True, d


def test_service_live_needs_explicit_env_and_stops_without_credentials(monkeypatch):
    monkeypatch.setenv("SHOPPING_LIVE", "1")
    monkeypatch.setattr("shopping.service.load_credentials",
                        lambda *a, **k: __import__("shopping.config", fromlist=["x"]).RakutenCredentials("", ""))
    d = service.search_products(["洗濯洗剤"])
    assert d["ok"] is False and d["error"]["kind"] == "missing_credentials"


# --- basis / desired_quantity の検査は inputs に一本化 --------------------------------------------

def test_service_and_pricing_use_the_inputs_checks_so_messages_match():
    with pytest.raises(InvalidInput) as e1:
        inputs.check_basis("ふしぎ")
    d = service.compare_offers(["洗濯洗剤"], basis="ふしぎ", adapter=FakeAdapter({}))
    assert d["ok"] is False and d["error"]["message"] == str(e1.value)
    with pytest.raises(InvalidInput) as e2:
        inputs.check_desired_quantity(-1)
    d = service.compare_offers(["洗濯洗剤"], desired_quantity=-1, adapter=FakeAdapter({}))
    assert d["error"]["message"] == str(e2.value)
    for bad in (0, -1, True, "5", float("inf"), float("nan"), 1e13):
        with pytest.raises(ValueError):                # InvalidInput は ValueError のサブクラス
            compare([], desired_quantity=bad)
    compare([], desired_quantity=5.5)                  # 正の有限数は通る
