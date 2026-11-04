# @owns MCP（stdio）の外部インターフェース。ツール定義と説明文だけを持ち、処理は service に委譲する
"""MCP サーバー（mcp 2.3.0 / MCPServer）。stdout は MCP のプロトコル用なので print しない。

起動: python -m shopping.mcp_server   （PYTHONPATH=src）
      SHOPPING_MOCK=1 でモック（API を呼ばない）。
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import service

INSTRUCTIONS = (
    "楽天市場の商品を検索・比較する個人用の買い物リサーチツール。購入操作はしない。"
    "最安を答える時は、返ってきた caveats（断定できない理由）と notes を必ず併せて伝えること。"
    "送料不明の時に『支払総額が最安』と断定しない。仕様（シングル/ダブル・長さ）の違う商品を"
    "同じ商品として比べない。価格・在庫は取得時点の値で、商品URLは各候補の url を使う。"
)

_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                             open_world_hint=True)


def build_server() -> MCPServer:
    server = MCPServer("shopping-research", instructions=INSTRUCTIONS)

    @server.tool(
        name="search_products",
        annotations=_READ_ONLY,
        description=(
            "楽天市場で商品を検索し、候補の一覧を返す（比較はしない）。"
            "条件に合う商品を探して一覧で見たい時に使う。"
            "keywords に検索語を1〜5個（日本語可）渡すと、語ごとに検索して商品コードで重複を除いて統合する"
            "（どの語で見つかったかは matched_keywords）。"
            "ng_keyword は除外語、min_price/max_price は税込価格の範囲（円）、"
            "sort は standard / +itemPrice（安い順）/ -itemPrice（高い順）/ -reviewCount など。"
            "pages は語ごとに取るページ数（1〜3、1ページ30件）。"
            "各候補に商品固有URL(url)、価格、送料区分(shipping_status: included=送料込み/"
            "separate=送料別/unknown)、入り数の読み取り結果(quantity。confidenceがhighの時だけ"
            "total=総数と1ロール単価unit_priceが入る)が付く。"
            "最安を決めたい時は compare_offers を使う。"),
    )
    def search_products(keywords: list[str], ng_keyword: str | None = None,
                        min_price: int | None = None, max_price: int | None = None,
                        sort: str = "standard", pages: int = 1,
                        max_results: int = 30) -> dict[str, Any]:
        return service.search_products(keywords, ng_keyword=ng_keyword, min_price=min_price,
                                       max_price=max_price, sort=sort, pages=pages,
                                       max_results=max_results, adapter=service.make_adapter())

    @server.tool(
        name="compare_offers",
        annotations=_READ_ONLY,
        description=(
            "楽天市場で検索した候補を『同じ仕様どうし』で比較し、最安を4種類に分けて返す: "
            "(1) 商品価格が最安 (2) 1ロール(単位)あたりの単価が最安 "
            "(3) 支払総額が最安（送料が不明な候補が1件でもあれば null＝断定しない） "
            "(4) desired_quantity 以上を満たす中で最安。"
            "『一番安いのはどれ？』『1ロールあたりで比べて』『48ロール以上で最安は？』の時に使う。"
            "required_spec で必要仕様を指定する（例 {\"ply\": \"double\", \"length_m\": 30} は"
            "ダブル・30m。合わない候補は除外され、その件数が caveats に出る）。"
            "未指定だとシングル/ダブルや長さ違いを含むので、caveats の『仕様違いを含む』に注意する。"
            "結果は groups（仕様ごとの束。単位価格の安い順）と cheapest_* と caveats。"
            "cheapest_* が null の理由は必ず caveats に書いてあるので、利用者へそのまま伝えること。"
            "keywords・ng_keyword・min_price/max_price・sort・pages は search_products と同じ。"
            "unit は数える単位（既定 ロール）。"),
    )
    def compare_offers(keywords: list[str], required_spec: dict[str, Any] | None = None,
                       desired_quantity: int | None = None, ng_keyword: str | None = None,
                       min_price: int | None = None, max_price: int | None = None,
                       sort: str = "standard", pages: int = 1,
                       unit: str = "ロール") -> dict[str, Any]:
        return service.compare_offers(keywords, required_spec, desired_quantity,
                                      ng_keyword=ng_keyword, min_price=min_price,
                                      max_price=max_price, sort=sort, pages=pages, unit=unit,
                                      adapter=service.make_adapter())

    @server.tool(
        name="find_regular_item",
        annotations=_READ_ONLY,
        description=(
            "登録済みの『いつもの定番品』を id で指定し、今どこが安いかを調べる。"
            "『いつものトイレットペーパー、今どこが安い？』の時に使う。"
            "定番品マスタ（id・検索語・必要仕様・希望数量）から検索語と条件を読み、"
            "compare_offers と同じ形の比較結果を返す（regular に登録内容、"
            "各候補の is_known_url で以前買ったURLかどうか）。"
            "価格・在庫は保存されておらず、呼ぶたびに取り直す。"
            "id が不明な時は、マスタに無い旨のエラー(regulars_not_found)が返る。"),
    )
    def find_regular_item(regular_id: str, pages: int = 1) -> dict[str, Any]:
        return service.find_regular_item(regular_id, pages=pages, adapter=service.make_adapter())

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
