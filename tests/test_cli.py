import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import cli

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = str(ROOT / "examples" / "regulars.sample.json")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("RAKUTEN_APPLICATION_ID", raising=False)
    monkeypatch.delenv("RAKUTEN_ACCESS_KEY", raising=False)
    monkeypatch.delenv("SHOPPING_MOCK", raising=False)


def test_search_mock_human_output(capsys):
    assert cli.run(["search", "洗濯洗剤 詰め替え", "--mock"]) == 0
    out = capsys.readouterr().out
    assert "https://item.rakuten.co.jp/" in out and "モック" in out and "出典" in out
    assert "[URL要確認]" in out and "送料込み" in out


def test_search_mock_json(capsys):
    assert cli.run(["search", "洗濯洗剤", "--mock", "--json", "--max-price", "2000"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] and data["offers"] and all(o["price"] <= 2000 for o in data["offers"])


def test_compare_mock_flags(capsys):
    code = cli.run(["compare", "洗濯洗剤 詰め替え", "--include", "詰め替え", "--exclude", "本体",
                    "--basis", "g", "--desired-quantity", "5000", "--mock"])
    out = capsys.readouterr().out
    assert code == 0 and "単位価格が最安" in out and "断定できない" in out
    assert "支払総額が最安: （断定できない／該当なし）" in out


def test_regular_mock(capsys):
    assert cli.run(["regular", "detergent-refill", "--regulars", SAMPLE, "--mock"]) == 0
    assert "定番品:" in capsys.readouterr().out


def test_regular_missing_returns_1_with_message_on_stderr(capsys, tmp_path):
    assert cli.run(["regular", "detergent-refill", "--regulars", str(tmp_path / "x.json"), "--mock"]) == 1
    cap = capsys.readouterr()
    assert "regulars_file_not_found" in cap.err and cap.out == ""


def test_limit_error_returns_1(capsys):
    assert cli.run(["search", "a", "b", "c", "d", "e", "f", "--mock"]) == 1
    assert "invalid_request" in capsys.readouterr().err


def test_cli_defaults_are_3_pages_start_1_no_max_results():
    ap = cli.build_parser()
    a = ap.parse_args(["search", "x"])
    assert a.pages == 3 and a.start_page == 1 and a.max_results is None
    for cmd, extra in (("compare", ["x"]), ("regular", ["r"])):
        b = ap.parse_args([cmd] + extra)
        assert b.pages == 3 and b.start_page == 1
    c = ap.parse_args(["search", "x", "--pages", "2", "--start-page", "4", "--max-results", "5"])
    assert (c.pages, c.start_page) == (2, 4)


def test_cli_search_default_returns_every_hit_in_the_mock(capsys):
    assert cli.run(["search", "洗濯洗剤", "--mock", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    st = d["stats"]["per_keyword"][0]
    assert d["returned"] == st["received"] == st["api_count"] and not st["truncated"] and st["next_page"] is None


def _many_mock(tmp_path, n=100):
    items = [{"itemName": f"テスト商品 {i} 100g", "itemCode": f"shop:i{i}", "itemPrice": 1000 + i,
              "itemUrl": f"https://item.rakuten.co.jp/shop/i{i}/", "shopName": "S", "availability": 1,
              "postageFlag": 0} for i in range(n)]
    p = tmp_path / "mock.json"
    p.write_text(json.dumps({"Items": items}, ensure_ascii=False), encoding="utf-8")
    return p


def test_cli_start_page_works_for_search_and_compare_and_prints_next(tmp_path, capsys, monkeypatch):
    from shopping.adapters.mock import MockAdapter
    path = _many_mock(tmp_path, 100)
    monkeypatch.setattr("shopping.service.make_adapter", lambda *a, **k: MockAdapter(data_path=path))
    assert cli.run(["search", "テスト商品", "--json", "--pages", "1", "--max-results", "0"]) == 0
    d = json.loads(capsys.readouterr().out)
    st = d["stats"]["per_keyword"][0]
    assert (st["api_count"], st["received"], st["next_page"], st["remaining"]) == (100, 30, 2, 70)
    assert cli.run(["search", "テスト商品", "--json", "--start-page", "2", "--pages", "2"]) == 0
    d = json.loads(capsys.readouterr().out)
    st = d["stats"]["per_keyword"][0]
    assert (st["start_page"], st["last_page"], st["received"], st["next_page"]) == (2, 3, 60, 4)
    assert cli.run(["compare", "テスト商品", "--json", "--start-page", "4"]) == 0
    d = json.loads(capsys.readouterr().out)
    st = d["stats"]["per_keyword"][0]
    assert (st["start_page"], st["received"], st["next_page"]) == (4, 10, None)
    assert cli.run(["search", "テスト商品", "--start-page", "2", "--pages", "1"]) == 0     # 人間向け表示に続きが出る
    out = capsys.readouterr().out
    assert "2〜2ページ目" in out and "--start-page 3" in out and "残り約 40 件" in out


def test_cli_start_page_range_over_100_is_invalid(capsys):
    assert cli.run(["search", "洗濯洗剤", "--mock", "--start-page", "99", "--pages", "3"]) == 1
    assert "invalid_request" in capsys.readouterr().err


def test_cli_pages_101_is_invalid(capsys):
    assert cli.run(["search", "洗濯洗剤", "--mock", "--pages", "101"]) == 1
    assert "invalid_request" in capsys.readouterr().err


def _no_credentials(monkeypatch):
    # .env を読ませない（実キーを使わない・通信もしない）: 認証情報が空なら adapter は通信前に止まる
    monkeypatch.setattr("shopping.service.load_credentials",
                        lambda *a, **k: __import__("shopping.config", fromlist=["x"]).RakutenCredentials("", ""))


def test_default_is_mock_and_never_calls_real_api(capsys, monkeypatch):
    # B4: フラグも環境変数も無ければモック。認証情報を読みにも行かない
    monkeypatch.setattr("shopping.service.load_credentials",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("実 API の認証情報を読んだ")))
    assert cli.run(["search", "洗濯洗剤"]) == 0
    assert "モック" in capsys.readouterr().out
    assert cli.run(["compare", "単3電池"]) == 0


def test_live_flag_uses_real_adapter_and_stops_safely_without_credentials(capsys, monkeypatch):
    _no_credentials(monkeypatch)
    assert cli.run(["search", "洗濯洗剤", "--live"]) == 1
    assert "missing_credentials" in capsys.readouterr().err


def test_live_env_uses_real_adapter(capsys, monkeypatch):
    _no_credentials(monkeypatch)
    monkeypatch.setenv("SHOPPING_LIVE", "1")
    assert cli.run(["search", "洗濯洗剤"]) == 1
    assert "missing_credentials" in capsys.readouterr().err
    assert cli.run(["search", "洗濯洗剤", "--mock"]) == 0          # 明示の --mock は常に勝つ


def test_mock_and_live_are_mutually_exclusive():
    with pytest.raises(SystemExit) as e:
        cli.run(["search", "a", "--mock", "--live"])
    assert e.value.code == 2


def test_subprocess_utf8_output_does_not_crash():
    env = {k: v for k, v in os.environ.items() if k not in ("RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY")}
    env["PYTHONIOENCODING"] = "cp932"  # 端末が cp932 でも reconfigure で落ちない
    p = subprocess.run([sys.executable, str(ROOT / "cli.py"), "search", "洗濯洗剤", "--mock"],
                       capture_output=True, env=env, timeout=60)
    assert p.returncode == 0
    assert "洗濯洗剤".encode("utf-8") in p.stdout


def test_no_args_is_usage_error():
    with pytest.raises(SystemExit) as e:
        cli.run([])
    assert e.value.code == 2
