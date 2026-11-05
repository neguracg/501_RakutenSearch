import json
from pathlib import Path

import pytest

from fakes import FakeAdapter, make_offer
from shopping import service
from shopping.adapters.base import AdapterError
from shopping.adapters.mock import MockAdapter
from shopping.config import RakutenCredentials
from shopping.regulars import RegularsError, get_regular, load_regulars

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "examples" / "regulars.sample.json"


def write(tmp_path, data, name="regulars.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


# --- regulars -------------------------------------------------------------------

def test_sample_file_loads():
    regs = load_regulars(SAMPLE)
    assert [r.id for r in regs] == ["detergent-refill", "aa-battery-40", "mineral-water-2l"]   # 3 カテゴリ
    assert regs[0].include_terms == ["詰め替え"] and regs[0].exclude_terms == ["本体"]
    assert regs[0].basis == "g" and regs[0].desired_quantity == 5000
    assert regs[2].basis is None and regs[2].include_terms == ["ミネラルウォーター"]
    assert get_regular("aa-battery-40", SAMPLE).keywords


def test_sample_has_no_price_or_stock_fields():
    raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
    for e in raw["regulars"]:
        assert not ({"price", "stock", "availability"} & set(e))


def test_top_level_list_also_accepted(tmp_path):
    p = write(tmp_path, [{"id": "a", "name": "A", "keywords": ["x"]}])
    assert load_regulars(p)[0].id == "a"


@pytest.mark.parametrize("bad", [
    {"regulars": [{"name": "A", "keywords": ["x"]}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": []}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": [1]}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": ["x"], "include_terms": "x"}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": ["x"], "exclude_terms": [1]}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": ["x"], "basis": "ふしぎ"}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": ["x"], "desired_quantity": True}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": ["x"], "desired_quantity": 0}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": ["x"], "known_urls": "u"}]},
    {"regulars": [{"id": "a", "name": "A", "keywords": ["x"]}, {"id": "a", "name": "B", "keywords": ["y"]}]},
    {"regulars": "nope"},
])
def test_invalid_format(tmp_path, bad):
    with pytest.raises(RegularsError) as e:
        load_regulars(write(tmp_path, bad))
    assert e.value.kind == "invalid_format"


def test_missing_and_bad_json_and_not_found(tmp_path):
    with pytest.raises(RegularsError) as e:
        load_regulars(tmp_path / "none.json")
    assert e.value.kind == "file_not_found"
    p = tmp_path / "x.json"
    p.write_text("{oops", encoding="utf-8")
    with pytest.raises(RegularsError) as e:
        load_regulars(p)
    assert e.value.kind == "invalid_json"
    with pytest.raises(RegularsError) as e:
        get_regular("zzz", SAMPLE)
    assert e.value.kind == "not_found"


def test_env_path_override(tmp_path, monkeypatch):
    p = write(tmp_path, [{"id": "envone", "name": "E", "keywords": ["x"]}])
    monkeypatch.setenv("SHOPPING_REGULARS_PATH", str(p))
    assert load_regulars()[0].id == "envone"


# --- mock adapter ---------------------------------------------------------------

def test_mock_adapter_filters_and_pages():
    m = MockAdapter()
    offers, count = m.search("洗濯洗剤 詰め替え")
    assert count == len(offers) >= 4
    assert all("架空" in o.item_name for o in offers)
    offers, _ = m.search("洗濯洗剤", min_price=2000, max_price=3000)
    assert offers and all(2000 <= o.price <= 3000 for o in offers)
    offers, _ = m.search("洗濯洗剤", ng_keyword="本体")
    assert all("本体" not in o.item_name for o in offers)
    p1, c = m.search("洗濯洗剤", hits=3, page=1)
    p2, _ = m.search("洗濯洗剤", hits=3, page=2)
    assert len(p1) == 3 and p2 and c > 3
    assert {o.mall_item_code for o in p1}.isdisjoint({o.mall_item_code for o in p2})
    assert m.search("存在しない商品xyz")[0] == []


def test_mock_data_covers_three_or_more_categories():
    names = " ".join(o.item_name for o in MockAdapter().search("架空", hits=30)[0])
    for word in ("洗濯洗剤", "単3電池", "ミネラルウォーター", "ソーラーパネル"):
        assert word in names


def test_mock_data_has_no_real_shop_marks():
    raw = json.loads((ROOT / "src" / "shopping" / "mock_data.json").read_text(encoding="utf-8"))
    assert all("架空" in i["itemName"] and "架空" in i["shopName"] for i in raw["Items"])


# --- make_adapter ---------------------------------------------------------------

def test_make_adapter_mock_env(monkeypatch):
    monkeypatch.setenv("SHOPPING_MOCK", "1")
    assert isinstance(service.make_adapter(), MockAdapter)
    monkeypatch.setenv("SHOPPING_MOCK", "0")
    assert not isinstance(service.make_adapter(credentials=RakutenCredentials("a", "b")), MockAdapter)
    monkeypatch.delenv("SHOPPING_MOCK")
    assert isinstance(service.make_adapter(mock=True), MockAdapter)


# --- service: search_products ----------------------------------------------------

def test_search_products_with_mock_returns_json_ready_dict():
    r = service.search_products(["洗濯洗剤 詰め替え", "洗濯洗剤 900g"], adapter=MockAdapter())
    json.dumps(r, ensure_ascii=False)  # JSON 化できる
    assert r["ok"] and r["mock"] is True and r["returned"] == len(r["offers"]) > 0
    assert r["stats"]["duplicates_removed"] > 0 and r["stats"]["unique_offers"] == r["returned"]
    o = r["offers"][0]
    for k in ("name", "price", "url", "url_status", "shipping_status", "quantity", "unit_price",
              "matched_keywords", "fetched_at", "shop_name"):
        assert k in o
    assert any("モック" in n for n in r["notes"])
    assert any("出典" in n for n in r["notes"])
    # 生レスポンスのキーは出さない
    assert "itemCode" not in o and "Items" not in r


def test_search_products_caption_truncated():
    ad = FakeAdapter({("aa", 1): ([make_offer("1", caption="あ" * 500)], 1)})
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None)
    assert len(r["offers"][0]["caption"]) == 200


def test_search_products_max_results_truncates_and_says_so():
    r = service.search_products(["洗濯洗剤"], adapter=MockAdapter(), max_results=2)
    assert r["returned"] == 2 and any("max_results" in n for n in r["notes"])


def test_search_products_needs_review_noted():
    r = service.search_products(["洗濯洗剤 詰め替え"], adapter=MockAdapter())
    assert any(o["url_status"] == "needs_review" for o in r["offers"])
    assert any("needs_review" in n for n in r["notes"])


@pytest.mark.parametrize("kw", [[], "", [""], None, [1], ["a", " "]])
def test_search_products_bad_keywords(kw):
    r = service.search_products(kw, adapter=MockAdapter())
    assert r["ok"] is False and r["error"]["kind"] == "invalid_request"


def test_search_products_over_limit_returns_error_not_exception():
    r = service.search_products([f"k{i}" for i in range(6)], adapter=MockAdapter())
    assert r["ok"] is False and r["error"]["kind"] == "invalid_request"
    r = service.search_products(["aa"], pages=101, adapter=MockAdapter())     # 楽天の page 上限(100)超え
    assert r["ok"] is False and r["error"]["kind"] == "invalid_request"


@pytest.mark.parametrize("kind", ["http_403", "http_429", "timeout"])
def test_all_failed_reports_kind(kind):
    ad = FakeAdapter({("aa", 1): AdapterError(kind)})
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None)
    assert r["ok"] is False and r["error"]["kind"] == kind
    assert r["stats"]["per_keyword"][0]["error"] == kind


def test_partial_failure_still_ok_with_note():
    ad = FakeAdapter({("aa", 1): AdapterError("timeout"), ("bb", 1): ([make_offer("1")], 1)})
    r = service.search_products(["aa", "bb"], adapter=ad, sleep=lambda s: None)
    assert r["ok"] and r["returned"] == 1 and any("timeout" in n for n in r["notes"])


def test_429_partial_notes_rate_limit():
    ad = FakeAdapter({("aa", 1): ([make_offer("1")], 1), ("bb", 1): AdapterError("http_429")})
    r = service.search_products(["aa", "bb", "cc"], adapter=ad, sleep=lambda s: None)
    assert r["ok"] and r["stats"]["stopped_reason"] == "rate_limited"
    assert any("429" in n for n in r["notes"])


def test_missing_credentials_surfaces_as_error(monkeypatch, tmp_path):
    monkeypatch.delenv("SHOPPING_MOCK", raising=False)
    ad = service.make_adapter(mock=False, credentials=RakutenCredentials("", ""))
    r = service.search_products(["aa"], adapter=ad)
    assert r["ok"] is False and r["error"]["kind"] == "missing_credentials"


# --- service: compare_offers -----------------------------------------------------

def test_compare_offers_mock_end_to_end():
    r = service.compare_offers(["洗濯洗剤 詰め替え", "洗濯洗剤 900g"], ["詰め替え"], ["本体"], 5000, "g",
                               adapter=MockAdapter())
    json.dumps(r, ensure_ascii=False)
    c = r["comparison"]
    assert r["ok"] and r["basis"] == "g" and c["basis"] == "g" and c["basis_label"] == "100gあたり"
    assert r["include_terms"] == ["詰め替え"] and r["exclude_terms"] == ["本体"]
    assert len(c["groups"]) == 1 and c["groups"][0]["dimension"] == "mass"
    assert c["cheapest_unit_price"]["item_code"] == "exshop-a:det-6"
    assert c["cheapest_unit_price"]["unit_price_label"] == "100gあたり"
    assert c["cheapest_total"] is None                       # 送料不明が混在
    assert any("送料" in x for x in c["caveats"])
    assert c["cheapest_for_quantity"]["quantity"]["measure_total"] >= 5000
    prices = [o["unit_price"] for o in c["groups"][0]["offers"] if o["unit_price"] is not None]
    assert prices == sorted(prices)
    assert "含む語で除外: 1件" in c["notes"] and "含む語で除外: 1件" in r["notes"]


def test_compare_offers_result_shape_and_quantity_fields():
    r = service.compare_offers(["単3電池"], adapter=MockAdapter())
    c = r["comparison"]
    for k in ("basis", "basis_label", "groups", "unknown_offers", "cheapest_price", "cheapest_unit_price",
              "cheapest_total", "cheapest_for_quantity", "caveats", "notes"):
        assert k in c
    assert c["basis"] == "個" and c["groups"][0]["dimension"] == "count"
    o = c["cheapest_unit_price"]
    assert o["quantity"]["count_unit"] == "本" and o["unit_price_label"] == "1個あたり"
    for k in ("count_total", "content_amount", "content_dimension", "content_unit", "measure_total",
              "confidence", "evidence"):
        assert k in o["quantity"]
    assert "ply" not in o["quantity"] and "length_label" not in o["quantity"]


@pytest.mark.parametrize("query,basis", [("洗濯洗剤 詰め替え", "g"), ("ミネラルウォーター", "ml"),
                                         ("単3電池", "個"), ("ソーラーパネル", "W")])
def test_compare_offers_auto_basis_per_category(query, basis):
    r = service.compare_offers([query], adapter=MockAdapter())
    assert r["ok"] and r["comparison"]["basis"] == basis and r["comparison"]["groups"]


def test_compare_offers_unreadable_goes_to_unknown_and_says_so():
    r = service.compare_offers(["ソーラーパネル"], adapter=MockAdapter())
    c = r["comparison"]
    assert c["unknown_count"] == 1 and c["unknown_offers"][0]["unit_price"] is None
    assert any("単価を出せない候補: 1件" in x for x in c["caveats"])


def test_compare_offers_always_carries_the_standing_caveat():
    r = service.compare_offers(["洗濯洗剤"], adapter=MockAdapter())
    assert "仕様の違い（濃縮・層数・型番・色など）は判定していません。商品名で確認してください。" in r["comparison"]["caveats"]


@pytest.mark.parametrize("kw", [dict(include_terms="x1", exclude_terms=[1]), dict(desired_quantity=0),
                                dict(desired_quantity="48"), dict(desired_quantity=True),
                                dict(basis="ふしぎ"), dict(include_terms={"a": 1})])
def test_compare_offers_bad_args(kw):
    r = service.compare_offers(["a"], adapter=MockAdapter(), **kw)
    assert r["ok"] is False and r["error"]["kind"] == "invalid_request"


def test_compare_offers_accepts_alias_basis_and_single_string_terms():
    r = service.compare_offers(["ミネラルウォーター"], include_terms="2L", basis="L",
                               adapter=MockAdapter())
    assert r["ok"] and r["comparison"]["basis"] == "ml" and r["include_terms"] == ["2L"]


# --- service: find_regular_item --------------------------------------------------

def test_find_regular_item_mock_end_to_end():
    r = service.find_regular_item("detergent-refill", regulars_path=SAMPLE, adapter=MockAdapter())
    assert r["ok"] and r["regular"]["id"] == "detergent-refill"
    assert r["comparison"]["cheapest_unit_price"] is not None
    assert r["desired_quantity"] == 5000 and r["include_terms"] == ["詰め替え"] and r["basis"] == "g"
    assert r["regular"]["basis"] == "g" and "required_spec" not in r["regular"]


def test_find_regular_item_known_url_flag(tmp_path):
    p = write(tmp_path, [{"id": "r", "name": "R", "keywords": ["洗濯洗剤 詰め替え"],
                          "include_terms": ["詰め替え"],
                          "known_urls": ["https://item.rakuten.co.jp/exshop-a/det-6/"]}])
    r = service.find_regular_item("r", regulars_path=p, adapter=MockAdapter())
    flags = {o["item_code"]: o["is_known_url"] for g in r["comparison"]["groups"] for o in g["offers"]}
    assert flags["exshop-a:det-6"] is True and flags["exshop-b:det-4"] is False


def test_find_regular_item_errors(tmp_path):
    r = service.find_regular_item("detergent-refill", regulars_path=tmp_path / "none.json",
                                  adapter=MockAdapter())
    assert r["ok"] is False and r["error"]["kind"] == "regulars_file_not_found"
    r = service.find_regular_item("nope", regulars_path=SAMPLE, adapter=MockAdapter())
    assert r["error"]["kind"] == "regulars_not_found"
    r = service.find_regular_item("", regulars_path=SAMPLE, adapter=MockAdapter())
    assert r["error"]["kind"] == "invalid_request"
    p = tmp_path / "bad.json"
    p.write_text("{x", encoding="utf-8")
    assert service.find_regular_item("a", regulars_path=p)["error"]["kind"] == "regulars_invalid_json"


def test_no_credentials_in_any_output(monkeypatch):
    fake_id, fake_key = "FAKEAPPID_ZZZ", "FAKEKEY_ZZZ"
    from fakes import FakeOpener, http_error
    from shopping.adapters.rakuten import RakutenAdapter
    ad = RakutenAdapter(fake_id, fake_key, opener=FakeOpener(http_error(403)))
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None)
    blob = json.dumps(r, ensure_ascii=False)
    assert fake_id not in blob and fake_key not in blob and "SECRET" not in blob


def test_search_products_default_max_results_returns_everything_fetched():
    # 既定（None）は取得した全件。30 件で黙って切らない
    pages = {("aa", p): ([make_offer(f"a{p}-{i}") for i in range(30)], 90) for p in (1, 2, 3)}
    r = service.search_products(["aa"], adapter=FakeAdapter(pages), pages=3, sleep=lambda s: None)
    assert r["returned"] == 90 and not any("max_results" in n for n in r["notes"])
    r = service.search_products(["aa"], adapter=FakeAdapter(pages), pages=3, max_results=0,
                                sleep=lambda s: None)
    assert r["returned"] == 0 and any("max_results" in n for n in r["notes"])


def _hits_table(total, per_page=30, keyword="aa", upto=None):
    upto = upto or -(-total // per_page)
    return {(keyword, p): ([make_offer(f"{keyword}{p}-{i}", f"商品 {p}-{i} 100g")
                            for i in range(max(0, min(per_page, total - (p - 1) * per_page)))], total)
            for p in range(1, upto + 1)}


def test_search_products_default_is_3_pages_90_hits_and_tells_the_total_and_next_page():
    ad = FakeAdapter(_hits_table(144))
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None)
    st = r["stats"]["per_keyword"][0]
    assert r["returned"] == 90 and [kw["page"] for _, kw in ad.calls] == [1, 2, 3]
    assert (st["api_count"], st["received"], st["pages_fetched"]) == (144, 90, 3)
    assert (st["start_page"], st["last_page"], st["next_page"], st["remaining"], st["truncated"]) == (1, 3, 4, 54, True)
    assert isinstance(r["stats"]["elapsed_sec"], float)
    note = next(n for n in r["notes"] if "start_page=4" in n)
    assert "144" in note and "1〜3" in note and "54" in note


def test_search_products_start_page_4_pages_2_gets_the_rest_up_to_the_144th_hit():
    ad = FakeAdapter(_hits_table(144))
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None, start_page=4, pages=2)
    st = r["stats"]["per_keyword"][0]
    assert [kw["page"] for _, kw in ad.calls] == [4, 5] and r["returned"] == 54
    assert (st["api_count"], st["start_page"], st["last_page"], st["next_page"], st["remaining"],
            st["truncated"]) == (144, 4, 5, None, 0, False)
    assert not any("start_page=" in n for n in r["notes"])


def test_search_products_pages_none_means_the_default_3():
    ad = FakeAdapter(_hits_table(144))
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None, pages=None)
    assert r["returned"] == 90


@pytest.mark.parametrize("kw", [dict(start_page=99, pages=3), dict(start_page=101), dict(start_page=0),
                                dict(pages=0), dict(start_page=100, pages=2)])
def test_search_products_and_compare_offers_reject_out_of_range_and_say_the_ceiling(kw):
    for fn in (service.search_products, service.compare_offers):
        ad = FakeAdapter(_hits_table(144))
        r = fn(["aa"], adapter=ad, sleep=lambda s: None, **kw)
        assert r["ok"] is False and r["error"]["kind"] == "invalid_request" and ad.calls == []
    r = service.search_products(["aa"], adapter=FakeAdapter({}), start_page=99, pages=3)
    assert "100 ページ目までしか返しません" in r["error"]["message"]


def test_search_products_over_3000_hits_notes_the_rakuten_ceiling():
    ad = FakeAdapter(_hits_table(5000, upto=101))
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None, start_page=98, pages=3)
    st = r["stats"]["per_keyword"][0]
    assert (st["api_count"], st["next_page"], st["remaining"], st["truncated"]) == (5000, None, 0, False)
    assert any("5000" in n and "3000" in n for n in r["notes"])


def test_paging_notes_time_limit_message_and_multi_keyword_hint():
    pages = {**_hits_table(144, keyword="aa"), **_hits_table(144, keyword="bb")}
    r = service.search_products(["aa", "bb"], adapter=FakeAdapter(pages), sleep=lambda s: None)
    assert sum("start_page=4" in n for n in r["notes"]) == 2
    assert any("続きが要る語だけ" in n for n in r["notes"])


def test_search_products_time_limit_returns_partial_with_next_page_and_note(monkeypatch):
    from shopping.orchestrator import Limits
    t = [0.0]

    class Slow(FakeAdapter):
        def search(self, keyword, **kw):
            t[0] += 1.0
            return super().search(keyword, **kw)
    monkeypatch.setattr("shopping.orchestrator.time.monotonic", lambda: t[0])
    ad = Slow(_hits_table(3000))
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None, pages=100,
                                limits=Limits(time_budget_sec=10.0))
    st = r["stats"]["per_keyword"][0]
    assert r["ok"] and r["stats"]["stopped_reason"] == "time_limit" and len(ad.calls) == 10
    assert st["next_page"] == 11 and st["truncated"] is True and r["returned"] == 300
    assert any("時間の上限で途中まで" in n for n in r["notes"]) and any("start_page=11" in n for n in r["notes"])


def test_compare_offers_start_page_and_default_paging():
    ad = FakeAdapter(_hits_table(144))
    r = service.compare_offers(["aa"], adapter=ad, sleep=lambda s: None)
    st = r["stats"]["per_keyword"][0]
    assert [kw["page"] for _, kw in ad.calls] == [1, 2, 3] and st["next_page"] == 4 and st["api_count"] == 144
    assert any("start_page=4" in n for n in r["notes"])
    ad = FakeAdapter(_hits_table(144))
    r = service.compare_offers(["aa"], adapter=ad, sleep=lambda s: None, start_page=4, pages=2)
    assert [kw["page"] for _, kw in ad.calls] == [4, 5] and r["stats"]["per_keyword"][0]["next_page"] is None
    assert r["comparison"]["groups"][0]["count"] == 54


def test_paging_notes_can_be_turned_off_for_the_web_screen():
    ad = FakeAdapter(_hits_table(144))
    r = service.search_products(["aa"], adapter=ad, sleep=lambda s: None, pages=1, paging_notes=False)
    assert not any("start_page" in n for n in r["notes"])
    r = service.compare_offers(["aa"], adapter=FakeAdapter(_hits_table(144)), sleep=lambda s: None, pages=1,
                               paging_notes=False)
    assert not any("start_page" in n for n in r["notes"])


def test_find_regular_item_passes_start_page(tmp_path):
    reg = write(tmp_path, [{"id": "r1", "name": "洗剤", "keywords": ["aa"], "include_terms": [], "exclude_terms": []}])
    ad = FakeAdapter(_hits_table(144))
    r = service.find_regular_item("r1", regulars_path=reg, adapter=ad, sleep=lambda s: None, start_page=4, pages=2)
    assert r["ok"] and [kw["page"] for _, kw in ad.calls] == [4, 5]


def test_compare_offers_does_not_cut_groups_by_default_but_group_offers_max_cuts():
    pages = {("aa", 1): ([make_offer(f"x{i}", f"洗剤 {i} 900g", 1000 + i, shipping_status="included")
                         for i in range(25)], 25)}
    r = service.compare_offers(["aa"], adapter=FakeAdapter(pages), sleep=lambda s: None)
    g = r["comparison"]["groups"][0]
    assert g["count"] == 25 and len(g["offers"]) == 25                     # MCP・CLI は切らない
    r = service.compare_offers(["aa"], adapter=FakeAdapter(pages), sleep=lambda s: None,
                               group_offers_max=10)                          # Web 画面だけ 10 件表示
    g = r["comparison"]["groups"][0]
    assert g["count"] == 25 and len(g["offers"]) == 10


def test_compare_offers_does_not_cut_unknown_offers_by_default():
    pages = {("aa", 1): ([make_offer(f"u{i}", f"量の分からない商品 {i}") for i in range(25)], 25)}
    r = service.compare_offers(["aa"], adapter=FakeAdapter(pages), sleep=lambda s: None)
    c = r["comparison"]
    assert c["unknown_count"] == 25 and len(c["unknown_offers"]) == 25
    r = service.compare_offers(["aa"], adapter=FakeAdapter(pages), sleep=lambda s: None, group_offers_max=10)
    assert len(r["comparison"]["unknown_offers"]) == 10
