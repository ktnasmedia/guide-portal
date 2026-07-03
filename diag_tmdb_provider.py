#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TMDB 특정 작품(도깨비 10주년 여행, tv/325828)의 provider(제공처) 진단.
우리 수집이 이 작품을 왜 netflix로 분류했는지 확인.

- watch/providers 로 실제 제공처 조회 (한국 KR 기준)
- discover 로 넷플릭스(provider 8) 목록에 이 작품이 포함되는지 확인
환경변수: TMDB_TOKEN (API Read Access Token)
"""
import os
import sys
import json
import urllib.request
import urllib.parse

TOKEN = os.environ.get("TMDB_TOKEN", "").strip()
BASE = "https://api.themoviedb.org/3"
TV_ID = 325828


def api_get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("accept", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if not TOKEN:
        print("TMDB_TOKEN 없음")
        sys.exit(1)

    # 1) 작품 기본 정보
    info = api_get("/tv/%d" % TV_ID)
    print("제목:", info.get("name"), "/", info.get("original_name"))
    print("첫 방영:", info.get("first_air_date"))
    print()

    # 2) watch/providers (KR)
    print("=== watch/providers (KR) ===")
    wp = api_get("/tv/%d/watch/providers" % TV_ID)
    kr = wp.get("results", {}).get("KR", {})
    if not kr:
        print("  한국(KR) 제공처 정보 없음")
    else:
        for kind in ("flatrate", "free", "ads", "rent", "buy"):
            provs = kr.get(kind, [])
            if provs:
                names = ", ".join(p.get("provider_name", "") for p in provs)
                print("  [%s] %s" % (kind, names))
    print()

    # 3) 넷플릭스(provider 8) discover 목록에 이 작품이 포함되는지
    print("=== 넷플릭스(provider 8) discover 포함 여부 ===")
    found = False
    for year in (2025, 2026, 2027):
        for page in range(1, 6):
            data = api_get("/discover/tv", {
                "with_watch_providers": "8",
                "watch_region": "KR",
                "first_air_date_year": str(year),
                "page": str(page),
            })
            ids = [x.get("id") for x in data.get("results", [])]
            if TV_ID in ids:
                found = True
                print("  %d년 %d페이지에서 발견됨!" % (year, page))
            if page >= data.get("total_pages", 1):
                break
    if not found:
        print("  넷플릭스 provider 목록에서 찾을 수 없음")

    # 4) 티빙(provider 1883) 포함 여부도 참고로
    print()
    print("=== 티빙(provider 1883) discover 포함 여부 ===")
    found_tv = False
    for year in (2025, 2026, 2027):
        for page in range(1, 6):
            data = api_get("/discover/tv", {
                "with_watch_providers": "1883",
                "watch_region": "KR",
                "first_air_date_year": str(year),
                "page": str(page),
            })
            ids = [x.get("id") for x in data.get("results", [])]
            if TV_ID in ids:
                found_tv = True
                print("  %d년 %d페이지에서 발견됨!" % (year, page))
            if page >= data.get("total_pages", 1):
                break
    if not found_tv:
        print("  티빙 provider 목록에서 찾을 수 없음")


if __name__ == "__main__":
    main()
