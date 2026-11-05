# @owns 検索条件の検査（公開面の Web・MCP と、service・pricing・楽天アダプタが共有）: 語数・1語の長さ・1文字の語・価格・sort・basis・必要量の許可範囲
"""入力検査の単一の実装。Web と MCP は guard.Gate.admit() を通してここに来る（ロック取得・
最小間隔のスリープより前）。弾いた入力は楽天 API の枠を消費しない。

長さは楽天の上限（半角 128 文字）を安全側に解釈し、UTF-8 で 128 バイト以内（全角はおよそ 42 文字。S8）。
Gate と楽天アダプタは同じ fits_limit() で判定する。メッセージは利用者に見せてよい文言だけ（入力値そのものは入れない）。

1 文字だけの語（WP8-2）: 楽天は keyword・NGKeyword の空白区切りの語が「半角 2 文字以上、または全角 1 文字」を
求める（公式: https://webservice.rakuten.co.jp/documentation/ichiba-item-search。ただし全角のひらがな・カタカナ・記号は
2 文字以上）。2026-11-06 の実測では、半角 1 文字（a・2）、全角の数字・英字・かな・カタカナ・長音・記号 1 文字
（２・Ａ・の・ア・ー・！）は HTTP 400、漢字 1 文字（力）と 2 文字の語は通る。keyword・除外語（NGKeyword）とも同じ。
全角空白（U+3000）も区切りとして働く。送る前に弾き、語を勝手につなげたり捨てたりはしない（意味が変わる）。
"""
from __future__ import annotations

import math

from .quantity import basis_choices, resolve_basis

MAX_KEYWORDS = 5                 # 検索語・含む語・除く語・楽天側の除外語、いずれも 1〜5 語
MAX_BYTES = 128                  # 1 語の長さ（UTF-8 で 128 バイト = 半角 128 文字 = 全角 42 文字）
MAX_PRICE = 10_000_000
MAX_QUANTITY = 1e12
MAX_PAGES = 3                    # 語ごとに取るページ数（1 ページ 30 件）
MAX_FETCHES = 9                  # 検索語の数 × ページ数の上限（API は 1 秒 1 回直列なので 1 呼び出し最大約 9 秒）
# 楽天 IchibaItem Search の sort（公式の値）
SORTS = frozenset({"standard", "+affiliateRate", "-affiliateRate", "+reviewCount", "-reviewCount",
                   "+reviewAverage", "-reviewAverage", "+itemPrice", "-itemPrice",
                   "+updateTimestamp", "-updateTimestamp"})

WIDTH_TEXT = f"全角{MAX_BYTES // 3}文字（半角{MAX_BYTES}文字）"


class InvalidInput(ValueError):
    """利用者に見せてよい理由を str(exc) に持つ。kind は結果の error.kind に使う機械可読の種類。"""

    kind = "invalid_request"


class KeywordTermTooShort(InvalidInput):
    kind = "keyword_term_too_short"


def fits_limit(text: str) -> bool:
    """検索語・除外語 1 つが楽天に渡せる長さ（UTF-8 で 128 バイト以内）か。エンコードできない文字列は不可。"""
    try:
        return len(text.encode("utf-8")) <= MAX_BYTES
    except UnicodeEncodeError:
        return False


def _is_ideograph(ch: str) -> bool:
    """漢字（CJK 統合漢字とその拡張・互換）か。楽天が 1 文字で受け付けるのは漢字だけ（実測）。"""
    cp = ord(ch)
    return (0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF
            or 0x20000 <= cp <= 0x3FFFF)


def has_too_short_term(text: str) -> bool:
    """空白（半角・全角）区切りの語に、楽天が受け付けない 1 文字の語（漢字以外の 1 文字）があるか。"""
    return any(len(t) == 1 and not _is_ideograph(t) for t in text.split())


def check_term_lengths(texts, label: str) -> None:
    """楽天に渡す語（検索語・除外語）の 1 文字だけの語の検査。不正なら KeywordTermTooShort。
    service・楽天アダプタもここを呼ぶ（公開面の Gate と同じ判定）。texts は文字列または文字列のリスト。"""
    items = [texts] if isinstance(texts, str) else list(texts or [])
    if any(isinstance(t, str) and has_too_short_term(t) for t in items):
        raise KeywordTermTooShort(
            f"{label}に、楽天で検索できない 1 文字だけの語があります（半角 1 文字、全角の数字・英字・かな・記号 1 文字。"
            "漢字 1 文字は可）。『DELTA 2』は『DELTA2』のように前の語とつなげるか、語を 2 文字以上にしてください。")


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
    """語ごとに取るページ数の検査（int の 1〜MAX_PAGES）。不正なら InvalidInput。"""
    if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= MAX_PAGES:
        raise InvalidInput(f"pages は 1〜{MAX_PAGES} の整数で指定してください（1 ページ 30 件）。")
    return pages


def validate(*, keywords, ng_keyword=None, min_price=None, max_price=None, sort="standard",
             include_terms=None, exclude_terms=None, basis=None, desired_quantity=None,
             pages=1) -> None:
    """不正なら InvalidInput。正規化後の値は返さない（service が自分で正規化する）。"""
    kws = _terms(keywords, "検索語", allow_empty=False)
    check_term_lengths(kws, "検索語")
    pages = check_pages(pages)
    if len(kws) * pages > MAX_FETCHES:
        raise InvalidInput(f"検索語の数×ページ数は {MAX_FETCHES} まで（検索語 {len(kws)} 語 × {pages} ページ"
                           "は多すぎます。語かページ数を減らしてください）。")
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
        check_term_lengths(ng_keyword, "除外語（楽天側）")
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
