"""WP2-3: 公開Web（AC-W1〜W8）。実 API は呼ばない（FakeAdapter / MockAdapter）。"""
import re
import threading

import pytest
from fastapi.testclient import TestClient

from fakes import FakeAdapter, make_offer
from shopping.adapters.base import AdapterError
from shopping.adapters.mock import MockAdapter
from shopping.guard import Gate, GuardedAdapter, RateLimiter
from shopping.web import create_app
from shopping.credit import CREDIT_HTML, FRESHNESS_TEXT, OPERATOR_TEXT

SECRET_ID = "APPID-SECRET-1234567890"
SECRET_KEY = "ACCESSKEY-SECRET-abcdef"
CREDIT = '<a href="https://developers.rakuten.com/" target="_blank">Supported by Rakuten Developers</a>'


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def offers():
    return [make_offer("a", "トイレットペーパー ダブル 30m 12ロール×4袋", 2400, shipping_status="included"),
            make_offer("b", "トイレットペーパー ダブル 2倍巻き 12ロール", 1500, shipping_status="separate"),
            make_offer("c", "トイレットペーパー シングル 12ロール", 700, shipping_status="unknown")]


def fake(pages=None):
    return FakeAdapter(pages or {("トイレットペーパー", 1): (offers(), 3)})


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("RAKUTEN_APPLICATION_ID", SECRET_ID)
    monkeypatch.setenv("RAKUTEN_ACCESS_KEY", SECRET_KEY)
    monkeypatch.delenv("SHOPPING_MOCK", raising=False)


def make_client(base="", adapter=None, limiter=None, clock=None):
    clock = clock or Clock()
    ga = GuardedAdapter(adapter or fake(), clock=clock, sleep=clock.sleep)
    gate = Gate(ga, limiter or RateLimiter(limit=1000, clock=clock))
    app = create_app(base, gate)
    return TestClient(app, raise_server_exceptions=False), gate, ga


def attr_urls(html):
    return re.findall(r'(?:href|action|formaction|src)="([^"]*)"', html)


PATHS = ["/", "/search?q=トイレットペーパー", "/compare?q=トイレットペーパー"]


@pytest.mark.parametrize("base", ["", "/kaimono"])
def test_all_routes_ok_and_links_under_base_path(base):
    c, _, _ = make_client(base)
    for p in PATHS:
        r = c.get(base + p)
        assert r.status_code == 200, p
        for u in attr_urls(r.text):
            ok = (u == base or u.startswith(base + "/")
                  or u.startswith("https://developers.rakuten.com/")
                  or u.startswith("https://item.rakuten.co.jp/"))
            assert ok and (base or u != ""), (p, u)
        if base:
            assert all(u.startswith(("/kaimono", "https://")) for u in attr_urls(r.text))
    h = c.get(base + "/healthz")
    assert h.status_code == 200 and h.json() == {"ok": True, "credentials": True}


def test_base_path_without_slash_redirects_and_unprefixed_is_404():
    c, _, _ = make_client("/kaimono")
    r = c.get("/kaimono", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/kaimono/"
    assert c.get("/").status_code == 404 and c.get("/healthz").status_code == 404


def test_index_has_form_with_both_modes():
    c, _, _ = make_client("/kaimono")
    html = c.get("/kaimono/").text
    assert 'formaction="/kaimono/search"' in html and 'formaction="/kaimono/compare"' in html
    for name in ("q", "ng", "min_price", "max_price"):
        assert f'name="{name}"' in html


def test_footer_credit_operator_and_freshness_on_every_page():
    assert CREDIT in CREDIT_HTML
    c, _, _ = make_client("/kaimono", limiter=RateLimiter(limit=1))
    pages = [c.get("/kaimono" + p) for p in PATHS[:2]]          # 2 件目で 429 になる想定
    pages += [c.get("/kaimono/search"), c.get("/kaimono/nothing")]  # 400 と 404
    c2, _, _ = make_client("/kaimono", adapter=fake({("トイレットペーパー", 1): AdapterError("http_429")}))
    pages.append(c2.get("/kaimono/search?q=トイレットペーパー"))      # 503
    pages.append(c.get("/kaimono/compare?q=トイレットペーパー"))
    assert {p.status_code for p in pages} >= {200, 400, 404, 429, 503}
    for r in pages:
        assert CREDIT_HTML in r.text, r.status_code
        assert OPERATOR_TEXT in r.text and FRESHNESS_TEXT in r.text


def test_external_links_only_rakuten():
    c, _, _ = make_client("/kaimono")
    for p in PATHS:
        html = c.get("/kaimono" + p).text
        hosts = set(re.findall(r'https?://([^/"\'\s<]+)', html))
        assert hosts <= {"item.rakuten.co.jp", "developers.rakuten.com"}, (p, hosts)
        assert "github" not in html.lower()


def test_item_link_opens_new_tab_noopener_and_non_rakuten_url_is_not_linked():
    bad = make_offer("z", "トイレットペーパー ダブル 12ロール", 900)
    bad.item_url = "https://evil.example.com/x"
    bad.item_url_status = "needs_review"
    c, _, _ = make_client("/kaimono", adapter=fake({("トイレットペーパー", 1): ([bad] + offers(), 4)}))
    html = c.get("/kaimono/search?q=トイレットペーパー").text
    assert 'target="_blank" rel="noopener"' in html
    assert "evil.example.com" not in html


def test_compare_shows_caveats_notes_groups_and_label_split():
    c, _, _ = make_client("/kaimono")
    html = c.get("/kaimono/compare?q=トイレットペーパー").text
    assert "断定できない理由・注意" in html and "送料が不明" in html
    assert "注意・出典" in html and "楽天市場" in html
    assert "倍巻き" in html   # 倍巻き品は別グループ


def test_search_fixed_pages_and_hits():
    ad = fake()
    c, _, _ = make_client("", adapter=ad)
    c.get("/search?q=トイレットペーパー&pages=3&hits=5")
    assert ad.calls and all(kw.get("page") == 1 and kw.get("hits") == 30 for _, kw in ad.calls)


def test_multiple_keywords_split_by_newline_and_comma_max_five():
    ad = fake()
    c, _, _ = make_client("", adapter=ad)
    assert c.get("/search", params={"q": "あ\nい,う、え"}).status_code == 200
    assert [k for k, _ in ad.calls] == ["あ", "い", "う", "え"]
    assert c.get("/search", params={"q": "1,2,3,4,5,6"}).status_code == 400


@pytest.mark.parametrize("params", [{}, {"q": "  "}, {"q": "x" * 61}, {"q": "a", "min_price": "abc"},
                                    {"q": "a", "max_price": "-5"}, {"q": "a", "ng": "x" * 61}])
def test_invalid_input_is_400_and_does_not_call_api(params):
    ad = fake()
    c, _, _ = make_client("", adapter=ad)
    assert c.get("/search", params=params).status_code == 400
    assert ad.calls == []


def test_price_and_ng_are_passed_through():
    ad = fake()
    c, _, _ = make_client("", adapter=ad)
    c.get("/search", params={"q": "紙", "ng": "訳あり", "min_price": "1,000", "max_price": "5000"})
    kw = ad.calls[0][1]
    assert kw["ng_keyword"] == "訳あり" and kw["min_price"] == 1000 and kw["max_price"] == 5000


# --- AC-W5/W6 流量保護 ---

def test_rate_limit_per_ip_returns_429_and_other_ip_still_ok():
    clock = Clock()
    c, _, _ = make_client("/kaimono", limiter=RateLimiter(limit=3, clock=clock), clock=clock)
    h = {"CF-Connecting-IP": "203.0.113.5"}
    codes = [c.get("/kaimono/search?q=トイレットペーパー", headers=h).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = c.get("/kaimono/search?q=トイレットペーパー", headers=h)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1 and "少し待って" in r.text
    assert c.get("/kaimono/search?q=トイレットペーパー", headers={"CF-Connecting-IP": "203.0.113.9"}).status_code == 200
    clock.t += 61
    assert c.get("/kaimono/search?q=トイレットペーパー", headers=h).status_code == 200


def test_rate_limit_ignores_invalid_forwarded_ip_header():
    clock = Clock()
    c, _, _ = make_client("", limiter=RateLimiter(limit=1, clock=clock), clock=clock)
    h = {"CF-Connecting-IP": "not-an-ip"}
    assert c.get("/search?q=トイレットペーパー", headers=h).status_code == 200
    h2 = {"CF-Connecting-IP": "also-bad"}
    assert c.get("/search?q=トイレットペーパー", headers=h2).status_code == 429  # 同じ接続元として数える


def test_healthz_and_index_are_not_rate_limited():
    c, _, _ = make_client("", limiter=RateLimiter(limit=1))
    for _ in range(5):
        assert c.get("/healthz").status_code == 200 and c.get("/").status_code == 200


def test_cache_second_identical_search_does_not_call_adapter():
    ad = fake()
    c, _, ga = make_client("", adapter=ad)
    c.get("/search?q=トイレットペーパー")
    c.get("/compare?q=トイレットペーパー")
    c.get("/search?q=トイレットペーパー")
    assert len(ad.calls) == 1 and ga.api_calls == 1


def test_cache_key_includes_filters():
    ad = fake()
    c, _, _ = make_client("", adapter=ad)
    c.get("/search?q=トイレットペーパー")
    c.get("/search?q=トイレットペーパー&max_price=1000")
    assert len(ad.calls) == 2


@pytest.mark.parametrize("kind,status", [("http_429", 503), ("timeout", 503), ("busy", 503),
                                         ("http_403", 503), ("missing_credentials", 503)])
def test_adapter_errors_become_friendly_pages_without_leaking(kind, status):
    c, _, _ = make_client("/kaimono", adapter=fake({("トイレットペーパー", 1): AdapterError(kind)}))
    for p in ("/search", "/compare"):
        r = c.get("/kaimono" + p + "?q=トイレットペーパー")
        assert r.status_code == status
        for leak in (kind, SECRET_ID, SECRET_KEY, "Traceback", "AdapterError"):
            assert leak not in r.text
    r = c.get("/kaimono/search?q=トイレットペーパー")
    assert ("混雑" in r.text) == (kind in ("http_429", "timeout", "busy"))


def test_unexpected_exception_is_generic_500_without_detail():
    class Boom(FakeAdapter):
        def search(self, keyword, **kw):
            raise RuntimeError(f"secret {SECRET_KEY}")

    c, _, _ = make_client("", adapter=Boom({}))
    r = c.get("/search?q=a")
    assert r.status_code == 500 and SECRET_KEY not in r.text and CREDIT_HTML in r.text


# --- AC-W2 / W8 ---

def test_no_secret_values_anywhere_in_responses_and_no_cookies():
    c, _, _ = make_client("/kaimono")
    for p in PATHS + ["/healthz", "/search", "/nothing"]:
        r = c.get("/kaimono" + p)
        assert SECRET_ID not in r.text and SECRET_KEY not in r.text
        assert SECRET_ID not in str(r.headers) and SECRET_KEY not in str(r.headers)
        assert "set-cookie" not in r.headers


def test_no_regular_items_or_login_surface():
    c, _, _ = make_client("/kaimono")
    for p in ("/regular", "/regulars", "/login", "/find_regular_item", "/mcp-regular"):
        assert c.get("/kaimono" + p).status_code in (404, 405)
    html = c.get("/kaimono/").text
    assert "定番" not in html and "password" not in html.lower()
    assert "<script" not in html


def test_security_headers_and_no_external_assets():
    c, _, _ = make_client("")
    r = c.get("/")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "<link" not in r.text and "<script" not in r.text and "@import" not in r.text


def test_mock_mode_notes_and_guarded_mock_detection(monkeypatch):
    clock = Clock()
    ga = GuardedAdapter(MockAdapter(), clock=clock, sleep=clock.sleep)
    assert ga.is_mock
    app = create_app("", Gate(ga, RateLimiter(limit=100, clock=clock)))
    c = TestClient(app)
    r = c.get("/search", params={"q": "トイレットペーパー"})
    assert r.status_code == 200 and "架空" in r.text


def test_healthz_does_not_call_api_and_reports_missing_credentials(monkeypatch):
    monkeypatch.delenv("RAKUTEN_APPLICATION_ID")
    monkeypatch.delenv("RAKUTEN_ACCESS_KEY")
    monkeypatch.setattr("shopping.web.load_credentials",
                        lambda: type("C", (), {"present": False})())
    ad = fake()
    c, _, _ = make_client("", adapter=ad)
    r = c.get("/healthz")
    assert r.json() == {"ok": True, "credentials": False} and ad.calls == []
