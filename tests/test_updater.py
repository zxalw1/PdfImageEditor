# -*- coding: utf-8 -*-
import hashlib
import http.server
import json
import os
import threading

import pytest

from app.core import updater as up


def test_versions():
    assert up.parse_version("1.10.0") > up.parse_version("1.9.9")
    assert up.parse_version("v2") == (2, 0, 0, 0)
    assert up.is_newer("1.9.0", "1.8.0") and not up.is_newer("1.8.0", "1.8.0") and not up.is_newer("1.7", "1.8.0")


def make_release(tmp_path, ver="9.9.0", payload=b"MZ fake installer" * 1000, sha=None, url=None):
    exe = tmp_path / f"PdfImageEditor_Setup_v{ver}.exe"
    exe.write_bytes(payload)
    info = {"version": ver, "downloadUrl": url or exe.name, "sha256": sha or hashlib.sha256(payload).hexdigest(),
            "mandatory": False, "releaseNotes": "새 기능"}
    j = tmp_path / "update.json"
    j.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return j, exe


def test_parse_info_errors():
    with pytest.raises(up.UpdateError):
        up.parse_info(b"not json")
    with pytest.raises(up.UpdateError):
        up.parse_info(json.dumps({"version": "1", "downloadUrl": "x", "sha256": "abc"}))
    with pytest.raises(up.UpdateError):
        up.parse_info(json.dumps({"version": "1"}))


def test_local_share_check_and_download(tmp_path):
    j, exe = make_release(tmp_path)
    info = up.check(str(j), "1.8.0")                       # 사내 공유폴더·로컬 경로
    assert info and info.version == "9.9.0" and info.url == str(exe) and info.notes == "새 기능"
    assert up.check(str(j), "9.9.0") is None
    seen = []

    class T:
        def report(self, v, label=None):
            seen.append(v)

        def cancelled(self):
            return False
    out = up.download(info, str(tmp_path / "dl"), T())
    assert open(out, "rb").read() == exe.read_bytes() and seen[-1] == 100


def test_sha_mismatch_not_kept(tmp_path):
    j, exe = make_release(tmp_path, sha="0" * 64)
    info = up.check(str(j), "1.0")
    with pytest.raises(up.UpdateError, match="sha256"):
        up.download(info, str(tmp_path / "dl"))
    assert not os.listdir(tmp_path / "dl")                 # 잘못된 파일은 남기지 않음


def test_cancel(tmp_path):
    j, _ = make_release(tmp_path, payload=b"x" * (3 * 1024 * 1024))
    info = up.check(str(j), "1.0")

    class C:
        def report(self, *a):
            pass

        def cancelled(self):
            return True
    with pytest.raises(up.UpdateError, match="취소"):
        up.download(info, str(tmp_path / "dl"), C())


def test_http(tmp_path):
    j, exe = make_release(tmp_path)
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path), **k)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}/update.json"
        info = up.check(base, "1.0.0")
        assert info.url.endswith("/" + exe.name)            # 상대 주소 → JSON 기준
        out = up.download(info, str(tmp_path / "dl"))
        assert up.sha256_file(out) == info.sha256
        with pytest.raises(up.UpdateError):
            up.fetch_info(base.replace("update.json", "none.json"))
    finally:
        srv.shutdown()


def test_unreachable_and_empty():
    with pytest.raises(up.UpdateError):
        up.fetch_info("")
    with pytest.raises(up.UpdateError):
        up.fetch_info(r"Z:\없는\경로\update.json")


def test_configured_url(tmp_path, monkeypatch):
    monkeypatch.setattr(up, "LOG_DIR", str(tmp_path / "user"))
    appd = tmp_path / "app"
    appd.mkdir()
    assert up.configured_url("http://default", str(appd)) == "http://default"
    (appd / up.CONFIG_NAME).write_text(r"\\server\share\update.json", encoding="utf-8")
    assert up.configured_url("http://default", str(appd)) == r"\\server\share\update.json"
    (tmp_path / "user").mkdir()
    (tmp_path / "user" / up.CONFIG_NAME).write_text("https://user/update.json\n", encoding="utf-8")
    assert up.configured_url("http://default", str(appd)) == "https://user/update.json"
