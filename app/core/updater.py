# -*- coding: utf-8 -*-
"""자동 업데이트 (Qt 의존 없음)

업데이트 정보 JSON (Shorts Recorder 와 동일 구조):
    {"version": "1.9.0", "downloadUrl": "https://.../PdfImageEditor_Setup_v1.9.0.exe",
     "sha256": "…64자리…", "mandatory": false, "releaseNotes": "변경 내용"}

주소(UPDATE_URL)는 http(s) 뿐 아니라 사내 공유폴더(\\\\서버\\배포\\update.json)·로컬 경로도 가능.
downloadUrl 도 마찬가지. 받은 파일은 sha256 이 일치할 때만 실행한다.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .utils import LOG_DIR, task_or_null

USER_AGENT = "PdfImageEditor-Updater"
TIMEOUT = 8
CONFIG_NAME = "update_url.txt"      # 설치 폴더 또는 %LOCALAPPDATA%\PdfImageEditor 에 두면 주소를 바꿀 수 있음


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str
    url: str
    sha256: str
    mandatory: bool = False
    notes: str = ""


# ── 버전 ──
def parse_version(v):
    nums = [int(x) for x in re.findall(r"\d+", str(v))[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


def is_newer(remote, current):
    return parse_version(remote) > parse_version(current)


# ── 주소 ──
def configured_url(default="", app_dir=None):
    """우선순위: %LOCALAPPDATA%\\PdfImageEditor\\update_url.txt > 설치 폴더\\update_url.txt > 기본값"""
    cands = [os.path.join(LOG_DIR, CONFIG_NAME)]
    if app_dir:
        cands.append(os.path.join(app_dir, CONFIG_NAME))
    for p in cands:
        try:
            with open(p, encoding="utf-8-sig") as f:
                u = f.read().strip()
            if u:
                return u
        except OSError:
            pass
    return default


def _is_remote(url):
    return urllib.parse.urlparse(url).scheme in ("http", "https")


def _local_path(url):
    if url.lower().startswith("file:"):
        return urllib.request.url2pathname(urllib.parse.urlparse(url).path)
    return url


def _open(url, timeout=TIMEOUT):
    if _is_remote(url):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
        return urllib.request.urlopen(req, timeout=timeout)
    return open(_local_path(url), "rb")


def resolve(base, ref):
    """downloadUrl 이 상대 경로면 JSON 위치 기준으로"""
    if _is_remote(ref) or os.path.isabs(_local_path(ref)) or ref.startswith("\\\\"):
        return ref
    if _is_remote(base):
        return urllib.parse.urljoin(base, ref)
    return os.path.join(os.path.dirname(_local_path(base)), ref)


# ── 정보 확인 ──
def parse_info(data, base_url=""):
    try:
        d = json.loads(data.decode("utf-8-sig") if isinstance(data, bytes) else data)
        ver, url, sha = str(d["version"]).strip(), str(d["downloadUrl"]).strip(), str(d["sha256"]).strip().lower()
    except (ValueError, KeyError, TypeError) as ex:
        raise UpdateError(f"업데이트 정보 형식이 올바르지 않습니다 ({ex})")
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise UpdateError("업데이트 정보의 sha256 값이 올바르지 않습니다")
    if not url:
        raise UpdateError("업데이트 정보에 다운로드 주소가 없습니다")
    return UpdateInfo(ver, resolve(base_url, url), sha, bool(d.get("mandatory", False)), str(d.get("releaseNotes", "")))


def fetch_info(url, timeout=TIMEOUT):
    if not url:
        raise UpdateError("업데이트 주소가 설정되지 않았습니다")
    try:
        with _open(url, timeout) as r:
            data = r.read(1024 * 1024)
    except OSError as ex:
        raise UpdateError(f"업데이트 정보를 가져오지 못했습니다\n{ex}")
    return parse_info(data, url)


def check(url, current):
    """새 버전이 있으면 UpdateInfo, 없으면 None"""
    info = fetch_info(url)
    return info if is_newer(info.version, current) else None


# ── 다운로드·검증 ──
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(info: UpdateInfo, dest_dir=None, task=None):
    """설치파일을 받아 sha256 확인 후 경로 반환. 진행률은 task.report(0~100, 글자)"""
    task = task_or_null(task)
    dest_dir = dest_dir or os.path.join(tempfile.gettempdir(), "PdfImageEditor_update")
    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(urllib.parse.urlparse(info.url).path if _is_remote(info.url) else _local_path(info.url))
    if not name.lower().endswith(".exe"):
        name = f"PdfImageEditor_Setup_v{info.version}.exe"
    dst = os.path.join(dest_dir, name)
    part = dst + ".part"
    h = hashlib.sha256()
    try:
        with _open(info.url, timeout=30) as r, open(part, "wb") as out:
            total = int(getattr(r, "headers", {}).get("Content-Length", 0) or 0) if _is_remote(info.url) \
                else os.path.getsize(_local_path(info.url))
            got = 0
            while True:
                if task.cancelled():
                    raise UpdateError("다운로드를 취소했습니다")
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                got += len(chunk)
                pct = int(got * 100 / total) if total else 0
                task.report(min(pct, 100), f"새 버전 받는 중... {got // (1024 * 1024)}MB"
                            + (f" / {total // (1024 * 1024)}MB" if total else ""))
    except UpdateError:
        _silent_remove(part)
        raise
    except OSError as ex:
        _silent_remove(part)
        raise UpdateError(f"다운로드 실패\n{ex}")
    if h.hexdigest() != info.sha256:
        _silent_remove(part)
        raise UpdateError("받은 파일의 sha256 이 일치하지 않습니다. 파일이 손상됐거나 바뀌었을 수 있어 실행하지 않습니다.")
    _silent_remove(dst)
    shutil.move(part, dst)
    return dst


def _silent_remove(p):
    try:
        os.remove(p)
    except OSError:
        pass


# ── 설치 실행 ──
INSTALL_ARGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/AUTOUPDATE=1"]


def launch_installer(path, verify_sha=None):
    """설치파일 실행(조용히 덮어 설치 → 설치 끝나면 프로그램 다시 실행). 호출 후 앱은 바로 종료해야 함"""
    if verify_sha and sha256_file(path) != verify_sha:
        raise UpdateError("설치파일 sha256 이 일치하지 않습니다")
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen([path] + INSTALL_ARGS, creationflags=flags, close_fds=True)
