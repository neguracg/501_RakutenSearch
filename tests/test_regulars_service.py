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
    assert regs[0].id == "tp-double-30m" and regs[0].required_spec == {"ply": "double", "length_m": 30}
    assert regs[0].desired_quantity == 48 and regs[0].unit == "ロール"
    assert get_regular("tp-double-30m", SAMPLE).keywords


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
    {"regulars": [{"id": "a", "name": "A", "keywords": ["x"], "required_spec": []}]},
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
    offers, count = m.search("トイレットペーパー ダブル 30m")
    assert count == len(offers) >= 5
    assert all("架空" in o.item_name for o in offers)
    offers, _ = m.search("トイレットペーパー", min_price=2000, max_price=3000)
    assert offers and all(2000 <= o.price <= 3000 for o in offers)
    offers, _ = m.search("トイレットペーパー", ng_keyword="シングル")
    assert all("シングル" not in o.item_name for o in offers)
    p1, c = m.search("トイレットペーパー", hits=3, page=1)
    p2, _ = m.search("トイレットペーパー", hits=3, page=2)
    assert len(p1) == 3 and p2 and c > 3
    assert {o.mall_item_code for o in p1}.isdisjoint({o.mall_item_code for o in p2})
    assert m.search("存在しない商品xyz")[0] == []


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
    r = service.search_products(["トイレットペーパー ダブル 30m", "トイレットペーパー 12ロール"],
                                adapter=MockAdapter())
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
    ad = FakeAdapter({("a", 1): ([make_offer("1", caption="あ" * 500)], 1)})
    r = service.search_products(["a"], adapter=ad, sleep=lambda s: None)
    assert len(r["offers"][0]["caption"]) == 200


def test_search_products_max_results_truncates_and_says_so():
    r = service.search_products(["トイレットペーパー"], adapter=MockAdapter(), max_results=2)
    assert r["returned"] == 2 and any("max_results" in n for n in r["notes"])


def test_search_products_needs_review_noted():
    r = service.search_products(["トイレットペーパー ダブル 30m"], adapter=MockAdapter())
    assert any(o["url_status"] == "needs_review" for o in r["offers"])
    assert any("needs_review" in n for n in r["notes"])


@pytest.mark.parametrize("kw", [[], "", [""], None, [1], ["a", " "]])
def test_search_products_bad_keywords(kw):
    r = service.search_products(kw, adapter=MockAdapter())
    assert r["ok"] is False and r["error"]["kind"] == "invalid_request"


def test_search_products_over_limit_returns_error_not_exception():
    r = service.search_products([f"k{i}" for i in range(6)], adapter=MockAdapter())
    assert r["ok"] is False and r["error"]["kind"] == "invalid_request"
    r = service.search_products(["a"], pages=4, adapter=MockAdapter())
    assert r["ok"] is False


@pytest.mark.parametrize("kind", ["http_403", "http_429", "timeout"])
def test_all_failed_reports_kind(kind):
    ad = FakeAdapter({("a", 1): AdapterError(kind)})
    r = service.search_products(["a"], adapter=ad, sleep=lambda s: None)
    assert r["ok"] is False and r["error"]["kind"] == kind
    assert r["stats"]["per_keyword"][0]["error"] == kind


def test_partial_failure_still_ok_with_note():
    ad = FakeAdapter({("a", 1): AdapterError("timeout"), ("b", 1): ([make_offer("1")], 1)})
    r = service.search_products(["a", "b"], adapter=ad, sleep=lambda s: None)
    assert r["ok"] and r["returned"] == 1 and any("timeout" in n for n in r["notes"])


def test_429_partial_notes_rate_limit():
    ad = FakeAdapter({("a", 1): ([make_offer("1")], 1), ("b", 1): AdapterError("http_429")})
    r = service.search_products(["a", "b", "c"], adapter=ad, sleep=lambda s: None)
    assert r["ok"] and r["stats"]["stopped_reason"] == "rate_limited"
    assert any("429" in n for n in r["notes"])


def test_missing_credentials_surfaces_as_error(monkeypatch, tmp_path):
    monkeypatch.delenv("SHOPPING_MOCK", raising=False)
    ad = service.make_adapter(mock=False, credentials=RakutenCredentials("", ""))
    r = service.search_products(["a"], adapter=ad)
    assert r["ok"] is False and r["error"]["kind"] == "missing_credentials"


# --- service: compare_offers -----------------------------------------------------

def test_compare_offers_mock_end_to_end():
    r = service.compare_offers(["トイレットペーパー ダブル 30m", "トイレットペーパー 12ロール"],
                               required_spec={"ply": "double", "length_m": 30},
                               desired_quantity=48, adapter=MockAdapter())
    json.dumps(r, ensure_ascii=False)
    c = r["comparison"]
    assert r["ok"] and len(c["groups"]) == 1 and c["groups"][0]["key"] == "double|30m|ロール"
    assert c["cheapest_unit_price"]["item_code"] == "exshop-e:tp-96"
    assert c["cheapest_total"] is None                       # 送料不明が混在
    assert any("断定できない" in x for x in c["caveats"])
    assert c["cheapest_meeting_quantity"]["quantity"]["total"] >= 48
    prices = [o["unit_price"] for o in c["groups"][0]["offers"] if o["unit_price"] is not None]
    assert prices == sorted(prices)


def test_compare_offers_without_spec_flags_mixed_specs():
    r = service.compare_offers(["トイレットペーパー"], adapter=MockAdapter())
    assert len(r["comparison"]["groups"]) >= 3
    assert any("仕様違いを含む" in x for x in r["comparison"]["caveats"])


@pytest.mark.parametrize("kw", [dict(required_spec=["ply"]), dict(desired_quantity=0),
                                dict(desired_quantity="48"), dict(desired_quantity=True)])
def test_compare_offers_bad_args(kw):
    r = service.compare_offers(["a"], adapter=MockAdapter(), **kw)
    assert r["ok"] is False and r["error"]["kind"] == "invalid_request"


# --- service: find_regular_item --------------------------------------------------

def test_find_regular_item_mock_end_to_end():
    r = service.find_regular_item("tp-double-30m", regulars_path=SAMPLE, adapter=MockAdapter())
    assert r["ok"] and r["regular"]["id"] == "tp-double-30m"
    assert r["comparison"]["cheapest_unit_price"] is not None
    assert r["desired_quantity"] == 48 and r["required_spec"]["ply"] == "double"


def test_find_regular_item_known_url_flag(tmp_path):
    p = write(tmp_path, [{"id": "r", "name": "R", "keywords": ["トイレットペーパー ダブル 30m"],
                          "required_spec": {"ply": "double", "length_m": 30},
                          "known_urls": ["https://item.rakuten.co.jp/exshop-a/tp-48/"]}])
    r = service.find_regular_item("r", regulars_path=p, adapter=MockAdapter())
    flags = {o["item_code"]: o["is_known_url"] for g in r["comparison"]["groups"] for o in g["offers"]}
    assert flags["exshop-a:tp-48"] is True and flags["exshop-b:tp-72"] is False


def test_find_regular_item_errors(tmp_path):
    r = service.find_regular_item("tp-double-30m", regulars_path=tmp_path / "none.json",
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
    r = service.search_products(["a"], adapter=ad, sleep=lambda s: None)
    blob = json.dumps(r, ensure_ascii=False)
    assert fake_id not in blob and fake_key not in blob and "SECRET" not in blob
