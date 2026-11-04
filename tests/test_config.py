from shopping.config import (ACCESS_KEY_VAR, APP_ID_VAR, load_credentials,
                             parse_env_file)

FAKE_ID = "FAKEAPPID_123"
FAKE_KEY = "FAKEKEY_456"


def _clear(monkeypatch):
    monkeypatch.delenv(APP_ID_VAR, raising=False)
    monkeypatch.delenv(ACCESS_KEY_VAR, raising=False)


def test_load_from_env_file(tmp_path, monkeypatch):
    _clear(monkeypatch)
    p = tmp_path / ".env"
    p.write_text(f"# comment\n\n{APP_ID_VAR}={FAKE_ID}\nexport {ACCESS_KEY_VAR}=\"{FAKE_KEY}\"\n",
                 encoding="utf-8")
    c = load_credentials(p)
    assert c.app_id == FAKE_ID and c.access_key == FAKE_KEY and c.present


def test_env_var_overrides_file(tmp_path, monkeypatch):
    _clear(monkeypatch)
    p = tmp_path / ".env"
    p.write_text(f"{APP_ID_VAR}=fromfile\n{ACCESS_KEY_VAR}=fromfile2\n", encoding="utf-8")
    monkeypatch.setenv(APP_ID_VAR, FAKE_ID)
    c = load_credentials(p)
    assert c.app_id == FAKE_ID and c.access_key == "fromfile2"


def test_missing_file_gives_not_present(tmp_path, monkeypatch):
    _clear(monkeypatch)
    c = load_credentials(tmp_path / "nope.env")
    assert not c.present and c.app_id == ""


def test_repr_and_str_do_not_leak(tmp_path, monkeypatch):
    _clear(monkeypatch)
    p = tmp_path / ".env"
    p.write_text(f"{APP_ID_VAR}={FAKE_ID}\n{ACCESS_KEY_VAR}={FAKE_KEY}\n", encoding="utf-8")
    c = load_credentials(p)
    for s in (repr(c), str(c), f"{c}", f"{c!r}"):
        assert FAKE_ID not in s and FAKE_KEY not in s


def test_bom_and_garbage_lines(tmp_path):
    p = tmp_path / ".env"
    p.write_bytes("﻿A=1\nnot a pair\n=x\nB='two'\n".encode("utf-8"))
    assert parse_env_file(p) == {"A": "1", "B": "two"}
