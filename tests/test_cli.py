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
    assert cli.run(["search", "トイレットペーパー ダブル 30m", "--mock"]) == 0
    out = capsys.readouterr().out
    assert "https://item.rakuten.co.jp/" in out and "モック" in out and "出典" in out
    assert "[URL要確認]" in out and "送料込み" in out


def test_search_mock_json(capsys):
    assert cli.run(["search", "トイレットペーパー", "--mock", "--json", "--max-price", "2000"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] and data["offers"] and all(o["price"] <= 2000 for o in data["offers"])


def test_compare_mock_flags(capsys):
    code = cli.run(["compare", "トイレットペーパー ダブル 30m", "--ply", "double", "--length-m", "30",
                    "--desired-quantity", "48", "--mock"])
    out = capsys.readouterr().out
    assert code == 0 and "単位価格が最安" in out and "断定できない" in out
    assert "支払総額が最安: （断定できない／該当なし）" in out


def test_regular_mock(capsys):
    assert cli.run(["regular", "tp-double-30m", "--regulars", SAMPLE, "--mock"]) == 0
    assert "定番品:" in capsys.readouterr().out


def test_regular_missing_returns_1_with_message_on_stderr(capsys, tmp_path):
    assert cli.run(["regular", "tp-double-30m", "--regulars", str(tmp_path / "x.json"), "--mock"]) == 1
    cap = capsys.readouterr()
    assert "regulars_file_not_found" in cap.err and cap.out == ""


def test_limit_error_returns_1(capsys):
    assert cli.run(["search", "a", "b", "c", "d", "e", "f", "--mock"]) == 1
    assert "invalid_request" in capsys.readouterr().err


def test_without_credentials_and_without_mock_stops_safely(capsys, monkeypatch):
    # .env を読ませない（実キーを使わない・通信もしない）: 認証情報が空なら adapter は通信前に止まる
    monkeypatch.setattr("shopping.service.load_credentials",
                        lambda *a, **k: __import__("shopping.config", fromlist=["x"]).RakutenCredentials("", ""))
    assert cli.run(["search", "トイレットペーパー"]) == 1
    assert "missing_credentials" in capsys.readouterr().err


def test_subprocess_utf8_output_does_not_crash():
    env = {k: v for k, v in os.environ.items() if k not in ("RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY")}
    env["PYTHONIOENCODING"] = "cp932"  # 端末が cp932 でも reconfigure で落ちない
    p = subprocess.run([sys.executable, str(ROOT / "cli.py"), "search", "トイレットペーパー", "--mock"],
                       capture_output=True, env=env, timeout=60)
    assert p.returncode == 0
    assert "トイレットペーパー".encode("utf-8") in p.stdout


def test_no_args_is_usage_error():
    with pytest.raises(SystemExit) as e:
        cli.run([])
    assert e.value.code == 2
