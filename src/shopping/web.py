# @owns 公開Webアプリの HTTP 入口（ルーティング・入力検査・BASE_PATH・エラー画面）。流量保護は guard、画面は web_view に委譲
"""公開Web（FastAPI）。誰でも開ける・ログイン無し。楽天 API を呼ぶのはこのサーバーだけで、
アクセスキー・アプリIDはブラウザへ一切渡さない。search / compare のみ（定番品は出さない）。
{BASE}/mcp にリモートMCP（Streamable HTTP・認証なし・2 ツール）を同居させ、Web と同じ Gate を通す。

起動: PYTHONPATH=src BASE_PATH=/kaimono uvicorn shopping.web:app
"""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import service
from .config import load_credentials
from .guard import Gate, RateLimited, client_ip_var, pick_client_ip
from .mcp_server import build_server
from .orchestrator import Limits
from .web_view import group_title, render

PAGES = 1
HITS = 30
MAX_KEYWORDS = 5
MAX_KEYWORD_CHARS = 60
MAX_PRICE = 10_000_000

_SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                                "base-uri 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
# 利用者に見せる失敗の種別（例外本文・URL・キーは出さない）
_BUSY_KINDS = {"http_429", "timeout", "busy", "network_error"}


def normalize_base_path(value: str | None) -> str:
    v = (value or "").strip()
    if v in ("", "/"):
        return ""
    return "/" + v.strip("/")


def _page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
    base = request.app.state.base
    return HTMLResponse(render(name, base, **ctx), status_code=status, headers=_SECURITY_HEADERS)


def _message(request: Request, status: int, heading: str, *paragraphs: str, headers=None):
    resp = _page(request, "message.html", status, heading=heading, paragraphs=list(paragraphs))
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


def _client_ip(request: Request) -> str:
    return pick_client_ip(request.headers.get("cf-connecting-ip"),
                          request.client.host if request.client else None)


def parse_keywords(q: str | None) -> list[str] | str:
    """改行・カンマ区切りで 1〜5 語。不正なら利用者向けの説明文字列を返す。"""
    parts = [p.strip() for p in re.split(r"[\n\r,，、]+", q or "") if p.strip()]
    if not parts:
        return "検索したい言葉を入力してください。"
    if len(parts) > MAX_KEYWORDS:
        return f"検索語は {MAX_KEYWORDS} 語までです（{len(parts)} 語入力されています）。"
    if any(len(p) > MAX_KEYWORD_CHARS for p in parts):
        return f"1 語は {MAX_KEYWORD_CHARS} 文字までです。"
    return parts


def parse_terms(raw: str | None) -> list[str] | None:
    """含む語・除く語: 空白・カンマ区切り。"""
    parts = [p for p in re.split(r"[\s,，、]+", raw or "") if p]
    return parts or None


def _parse_price(raw: str | None, label: str) -> int | None | str:
    if raw is None or raw.strip() == "":
        return None
    t = raw.strip().replace(",", "").replace("，", "")
    if not t.isdigit() or int(t) > MAX_PRICE:
        return f"{label}は 0〜{MAX_PRICE:,} の整数で入力してください。"
    return int(t)


class _McpMiddleware:
    """{BASE}/mcp への HTTP を MCP の ASGI アプリへ渡し、呼び出し元 IP を guard に伝える。"""

    def __init__(self, app, mcp_app, path: str):
        self.app = app
        self.mcp_app = mcp_app
        self.path = path

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].rstrip("/") == self.path:
            headers = dict(scope.get("headers") or [])
            ip = pick_client_ip(headers.get(b"cf-connecting-ip", b"").decode("latin-1") or None,
                                (scope.get("client") or (None,))[0])
            token = client_ip_var.set(ip)
            try:
                await self.mcp_app(dict(scope, path=self.path), receive, send)
            finally:
                client_ip_var.reset(token)
            return
        await self.app(scope, receive, send)


def create_app(base_path: str | None = None, gate: Gate | None = None) -> FastAPI:
    base = normalize_base_path(os.environ.get("BASE_PATH") if base_path is None else base_path)
    gate = gate or Gate(service.make_adapter())
    mcp_path = f"{base}/mcp"
    # stateless・JSON 応答（Cloudflare Tunnel 越しに SSE の長時間接続へ頼らない）。
    # host を localhost 以外にして DNS rebinding 保護（localhost 限定）を自動有効にしない。
    mcp_app = build_server(public=True, gate=gate).streamable_http_app(
        streamable_http_path=mcp_path, json_response=True, stateless_http=True, host="0.0.0.0")

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = FastAPI(title="買い物リサーチ", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.add_middleware(_McpMiddleware, mcp_app=mcp_app, path=mcp_path)
    app.state.base = base
    app.state.gate = gate
    router = APIRouter()

    def run(request: Request, mode: str, q, ng, min_price, max_price, include=None, exclude=None,
            basis=None):
        form = {"q": q or "", "ng": ng or "", "min_price": min_price or "", "max_price": max_price or "",
                "include": include or "", "exclude": exclude or "", "basis": basis or ""}
        keywords = parse_keywords(q)
        lo = _parse_price(min_price, "価格の下限")
        hi = _parse_price(max_price, "価格の上限")
        ng_word = (ng or "").strip()
        problem = (keywords if isinstance(keywords, str) else lo if isinstance(lo, str)
                   else hi if isinstance(hi, str)
                   else f"除外語は {MAX_KEYWORD_CHARS} 文字までです。" if len(ng_word) > MAX_KEYWORD_CHARS
                   else None)
        if problem:
            return _message(request, 400, "入力を確認してください", problem)
        try:
            gate.check(_client_ip(request))
        except RateLimited as exc:
            return _message(request, 429, "少し待ってからもう一度お試しください",
                            "短い時間にたくさんの検索がありました。しばらくしてからもう一度お試しください。",
                            headers={"Retry-After": str(exc.retry_after)})
        common = dict(ng_keyword=ng_word or None, min_price=lo, max_price=hi, pages=PAGES, hits=HITS,
                      adapter=gate.adapter, sleep=lambda s: None, limits=Limits(min_interval_sec=0))
        if mode == "compare":
            result = service.compare_offers(keywords, parse_terms(include), parse_terms(exclude),
                                            None, (basis or "").strip() or None, **common)
        else:
            result = service.search_products(keywords, max_results=HITS, **common)
        if not result.get("ok"):
            kind = (result.get("error") or {}).get("kind", "")
            if kind in _BUSY_KINDS:
                return _message(request, 503, "楽天側が混雑しています",
                                "楽天市場からの応答が得られませんでした。しばらくしてからもう一度お試しください。",
                                headers={"Retry-After": "30"})
            if kind == "invalid_request":
                return _message(request, 400, "入力を確認してください", "検索条件を確認してください。")
            return _message(request, 503, "検索できませんでした",
                            "現在検索できません。しばらくしてからもう一度お試しください。")
        ctx = dict(mode=mode, keywords=result["keywords"], mock=result["mock"],
                   notes=result["notes"], form=form)
        if mode == "compare":
            c = result["comparison"]
            ctx.update(caveats=c["caveats"], basis_label=c["basis_label"],
                       cheapest=[("商品価格が最安", c["cheapest_price"]),
                                 (f"{c['basis_label']}の単価が最安", c["cheapest_unit_price"]),
                                 ("支払総額が最安（送料が分かる場合のみ）", c["cheapest_total"])],
                       groups=[dict(g, title=group_title(g, c["basis_label"])) for g in c["groups"]],
                       unknown_offers=c["unknown_offers"], unknown_count=c["unknown_count"])
        else:
            ctx.update(offers=result["offers"])
        return _page(request, "results.html", **ctx)

    @router.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return _page(request, "index.html", form={"q": "", "ng": "", "min_price": "", "max_price": "",
                                                  "include": "", "exclude": "", "basis": ""})

    @router.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str | None = None, ng: str | None = None,
               min_price: str | None = None, max_price: str | None = None):
        return run(request, "search", q, ng, min_price, max_price)

    @router.get("/compare", response_class=HTMLResponse)
    def compare(request: Request, q: str | None = None, ng: str | None = None,
                min_price: str | None = None, max_price: str | None = None,
                include: str | None = None, exclude: str | None = None, basis: str | None = None):
        return run(request, "compare", q, ng, min_price, max_price, include, exclude, basis)

    @router.get("/healthz")
    def healthz():
        # 楽天 API は呼ばない。秘密の値は出さず、設定の有無だけ返す
        return JSONResponse({"ok": True, "credentials": load_credentials().present})

    app.include_router(router, prefix=base)
    if base:
        @app.get(base, include_in_schema=False)
        def base_no_slash():
            return RedirectResponse(f"{base}/", status_code=308)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _message(request, 404, "ページが見つかりません", "URL を確認してください。")
        return _message(request, exc.status_code, "リクエストを処理できません", "操作をやり直してください。")

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        # 例外本文・URL・キーを出さない
        return _message(request, 500, "エラーが発生しました", "しばらくしてからもう一度お試しください。")

    return app


app = create_app()
