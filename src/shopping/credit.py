# @owns 楽天ウェブサービス規約から来る表示文言（クレジット・運営者の責任表示・価格在庫の注意）。Web と MCP が同じ文言を使う
"""公式テキスト版クレジット（https://webservice.rakuten.co.jp/guide/credit）は改変しない。"""
from __future__ import annotations

import os

CREDIT_HTML = (
    '<!-- Rakuten Web Services Attribution Snippet FROM HERE -->\n'
    '<a href="https://developers.rakuten.com/" target="_blank">Supported by Rakuten Developers</a>\n'
    '<!-- Rakuten Web Services Attribution Snippet TO HERE -->'
)
CREDIT_TEXT = "Supported by Rakuten Developers"
CREDIT_URL = "https://developers.rakuten.com/"
OPERATOR_TEXT = ("このサイトは個人開発者 negura が作成・運営しており、内容の責任は運営者にあります。"
                 "楽天グループとは関係ありません。")
OPERATOR_SHORT = "個人開発者 negura が運営（楽天グループとは無関係）"
FRESHNESS_TEXT = "価格・在庫は検索時点のもの。購入前に楽天市場の商品ページで確認してください。"
DEFAULT_PUBLIC_BASE_URL = "https://app.negura.website/kaimono/"


def public_base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL


def mcp_credit_fields() -> dict:
    """リモートMCP のツール結果に必ず入れる項目。"""
    return {"credit": CREDIT_TEXT, "credit_url": CREDIT_URL, "operator": OPERATOR_SHORT,
            "web": public_base_url()}
