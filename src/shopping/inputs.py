# @owns 検索条件の検査（公開面の Web・MCP と、service・pricing・楽天アダプタが共有）: 語数・1語の長さ・価格・sort・basis・必要量の許可範囲
"""入力検査の単一の実装。Web と MCP は guard.Gate.admit() を通してここに来る（ロック取得・
最小間隔のスリープより前）。弾いた入力は楽天 API の枠を消費しない。

長さは楽天の上限（半角 128 文字）を安全側に解釈し、UTF-8 で 128 バイト以内（全角はおよそ 42 文字。S8）。
Gate と楽天アダプタは同じ fits_limit() で判定する。メッセージは利用者に見せてよい文言だけ（入力値そのものは入れない）。
"""
from __future__ import annotations

import math

from .quantity import basis_choices, resolve_basis

MAX_KEYWORDS = 5                 # 検索語・含む語・除く語・楽天側の除外語、いずれも 1〜5 語
MAX_BYTES = 128                  # 出典: 楽天 keyword の上限（半角 128 文字）を安全側に解釈。1 語の長さ（UTF-8 で 128 バイト = 半角 128 文字 = 全角 42 文字）
MAX_PRICE = 10_000_000
MAX_QUANTITY = 1e12
# 楽天 IchibaItem Search の仕様（出典: 楽天ウェブサービス API 仕様 page は 1〜100、hits は 1〜30）。
# 1 語あたり最大 100 ページ × 30 件 = 3000 件。これ以外の上限は置かない（語数×ページ数の上限も置かない）
MAX_PAGES = 100
DEFAULT_PAGES = 3                # 腱さんの決定（2026-11-06 #931）: 既定は語ごと 3 ページ（90 件）。続きは start_page で取る
MAX_HITS = 30
# 楽天 IchibaItem Search の sort（公式の値）
SORTS = frozenset({"standard", "+affiliateRate", "-affiliateRate", "+reviewCount", "-reviewCount",
                   "+reviewAverage", "-reviewAverage", "+itemPrice", "-itemPrice",
                   "+updateTimestamp", "-updateTimestamp"})

WIDTH_TEXT = f"全角{MAX_BYTES // 3}文字（半角{MAX_BYTES}文字）"


class InvalidInput(ValueError):
    """利用者に見せてよい理由を str(exc) に持つ。"""


def fits_limit(text: str) -> bool:
    """検索語・除外語 1 つが楽天に渡せる長さ（UTF-8 で 128 バイト以内）か。エンコードできない文字列は不可。"""
    try:
        return len(text.encode("utf-8")) <= MAX_BYTES
    except UnicodeEncodeError:
        return False


def _terms(value, label: str, *, allow_empty: bool) -> list[str]:
    if value is None:
        items: list = []
    elif isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise InvalidInput(f"{label}は文字列のリストで指定してください。")
    if not all(isinstance(t, str) for t in items):
        raise InvalidInput(f"{label}は文字列のリストで指定してください。")
    terms = [t.strip() for t in items if t.strip()]
    if not terms and not allow_empty:
        raise InvalidInput("検索したい言葉を入力してください。")
    if len(terms) > MAX_KEYWORDS:
        raise InvalidInput(f"{label}は {MAX_KEYWORDS} 語までです（{len(terms)} 語指定されています）。")
    if not all(fits_limit(t) for t in terms):
        raise InvalidInput(f"{label}は 1 語あたり{WIDTH_TEXT}までです。")
    return terms


def _price(value, label: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_PRICE:
        raise InvalidInput(f"{label}は 0〜{MAX_PRICE:,} の整数で指定してください。")


def check_pages(pages) -> int:
    """語ごとに取るページ数の検査。None＝省略＝DEFAULT_PAGES、指定する時は int の 1〜MAX_PAGES。
    検査後の値を返す。不正なら InvalidInput。"""
    if pages is None:
        return DEFAULT_PAGES
    if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= MAX_PAGES:
        raise InvalidInput(f"pages は 1〜{MAX_PAGES} の整数で指定してください（省略すると {DEFAULT_PAGES} ページ）。")
    return pages


def check_start_page(start_page) -> int:
    """取り始めるページ番号の検査。None＝省略＝1、指定する時は int の 1〜MAX_PAGES。検査後の値を返す。"""
    if start_page is None:
        return 1
    if isinstance(start_page, bool) or not isinstance(start_page, int) or not 1 <= start_page <= MAX_PAGES:
        raise InvalidInput(f"start_page は 1〜{MAX_PAGES} の整数で指定してください（省略すると 1）。")
    return start_page


def check_page_range(start_page, pages) -> tuple[int, int]:
    """start_page〜start_page+pages-1 が楽天の天井（MAX_PAGES ページ目）に収まるか。(start_page, pages) を返す。"""
    s, n = check_start_page(start_page), check_pages(pages)
    if s + n - 1 > MAX_PAGES:
        raise InvalidInput(f"楽天は {MAX_PAGES} ページ目までしか返しません。start_page + pages - 1 が "
                           f"{MAX_PAGES} 以下になるように指定してください（最大で {MAX_PAGES - s + 1} ページ）。")
    return s, n


def validate(*, keywords, ng_keyword=None, min_price=None, max_price=None, sort="standard",
             include_terms=None, exclude_terms=None, basis=None, desired_quantity=None,
             pages=None, start_page=None) -> None:
    """不正なら InvalidInput。正規化後の値は返さない（service が自分で正規化する）。"""
    kws = _terms(keywords, "検索語", allow_empty=False)
    check_page_range(start_page, pages)
    _terms(include_terms, "含む語", allow_empty=True)
    _terms(exclude_terms, "除く語", allow_empty=True)
    if ng_keyword is not None:
        if not isinstance(ng_keyword, str):
            raise InvalidInput("除外語は文字列で指定してください。")
        ng = ng_keyword.split()
        if len(ng) > MAX_KEYWORDS:
            raise InvalidInput(f"除外語は空白区切りで {MAX_KEYWORDS} 語までです。")
        if not fits_limit(ng_keyword.strip()):
            raise InvalidInput(f"除外語は全体で{WIDTH_TEXT}までです。")
    _price(min_price, "価格の下限")
    _price(max_price, "価格の上限")
    if sort not in SORTS:
        raise InvalidInput("sort は " + " / ".join(sorted(SORTS)) + " のいずれかで指定してください。")
    check_basis(basis)
    check_desired_quantity(desired_quantity)


def check_basis(basis) -> None:
    """比べる単位の検査（None・空は自動）。不正なら InvalidInput。service・pricing もここを呼ぶ。"""
    if basis in (None, ""):
        return
    try:
        resolve_basis(basis)
    except ValueError:
        raise InvalidInput("比べる単位は " + " / ".join(basis_choices())
                           + "（または L・kg 等の別名）で指定してください。") from None


def check_desired_quantity(value) -> None:
    """必要な量の検査（None は未指定）。不正なら InvalidInput。service・pricing もここを呼ぶ。"""
    if value is None:
        return
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 < value <= MAX_QUANTITY):
        raise InvalidInput("必要な量は正の数（比べる単位あたり）で指定してください。")
