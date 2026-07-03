#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
티빙(framer) 포스터 이미지 영구 보존.
티빙이 콘텐츠를 내리면 framerusercontent.com 이미지도 사라져 대시보드에서 깨진다.
이미지 파일을 저장소 posters/ 에 내려받아 보관하고, content_lineup.json 의
poster_url 을 로컬 경로로 교체한다.
- 대상: poster_url 이 framerusercontent.com 인 항목만 (TMDB 는 그대로)
- 이미 저장된 항목은 건너뜀
- 다운로드 실패해도 기존 값 유지
콘텐츠 수집(collect_lineup.py) 이후에 실행.
"""
import json
import os
import re
import sys
import hashlib
import urllib.request

LINEUP_FILE = "content_lineup.json"
POSTER_DIR = "posters"
FRAMER_HOST = "framerusercontent.com"


def safe_name(content_id, url):
    ext = ".webp"
    m = re.search(r"\.(webp|jpg|jpeg|png)", url, re.IGNORECASE)
    if m:
        ext = "." + m.group(1).lower()
    base = re.sub(r"[^0-9A-Za-z가-힣_-]", "_", str(content_id))[:60]
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return "%s_%s%s" % (base, h, ext)


def download(url, path):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 guide-portal-poster-archiver/1.0")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    if not data or len(data) < 100:
        raise RuntimeError("빈 이미지")
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def main():
    if not os.path.exists(LINEUP_FILE):
        print("%s 없음" % LINEUP_FILE)
        sys.exit(1)

    with open(LINEUP_FILE, encoding="utf-8") as f:
        doc = json.load(f)
    items = doc.get("items", [])

    os.makedirs(POSTER_DIR, exist_ok=True)

    saved, skipped, failed, untouched = 0, 0, 0, 0
    for it in items:
        url = it.get("poster_url") or ""
        cid = it.get("content_id") or "unknown"

        if url.startswith(POSTER_DIR + "/"):
            if os.path.exists(url):
                skipped += 1
            else:
                failed += 1
            continue

        if FRAMER_HOST not in url:
            untouched += 1
            continue

        fname = safe_name(cid, url)
        fpath = os.path.join(POSTER_DIR, fname)

        if os.path.exists(fpath):
            it["poster_url"] = fpath
            skipped += 1
            continue

        try:
            size = download(url, fpath)
            it["poster_url"] = fpath
            saved += 1
            print("  저장: %s (%d bytes) ← %s" % (fname, size, cid))
        except Exception as e:
            failed += 1
            print("  실패: %s (%s)" % (cid, e))

    with open(LINEUP_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print()
    print("완료 — 신규저장 %d · 기존유지 %d · 실패 %d · 대상아님(TMDB등) %d"
          % (saved, skipped, failed, untouched))


if __name__ == "__main__":
    main()
