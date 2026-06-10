#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
특정 작품이 수집 조건에서 왜 누락되는지 단계별 진단 (일회성)
대상: 맨 끝줄 소년 (TMDB TV id 286360)
각 조건을 하나씩 풀어가며 어디서 걸러지는지 확인.
"""
import os
import sys
import json
import urllib.request
import urllib.parse

TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()
API_BASE = "https://api.themoviedb.org/3"
TARGET_ID = 286360  # 맨 끝줄 소년
TARGET_NAME = "맨 끝줄 소년"


def http_get(path, params):
    qs = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{qs}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {TMDB_TOKEN}")
    req.add_header("accept", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    if not TMDB_TOKEN:
        print("ERROR: TMDB_TOKEN 환경변수 없음", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print(f"진단 대상: {TARGET_NAME} (TMDB TV {TARGET_ID})")
    print("=" * 60)

    # 1) 작품 자체 상세 정보
    print("\n[1] 작품 상세 정보")
    d = http_get(f"/tv/{TARGET_ID}", {"language": "ko-KR"})
    print(f"  제목: {d.get('name')}")
    print(f"  첫 공개일(first_air_date): {d.get('first_air_date')}")
    print(f"  제작국(origin_country): {d.get('origin_country')}")
    print(f"  원어(original_language): {d.get('original_language')}")
    print(f"  상태(status): {d.get('status')}")

    # 2) watch provider (넷플릭스에 걸리는지)
    print("\n[2] 한국(KR) watch provider")
    wp = http_get(f"/tv/{TARGET_ID}/watch/providers", {})
    kr = wp.get("results", {}).get("KR", {})
    if kr:
        flatrate = kr.get("flatrate", [])
        names = [p.get("provider_name") for p in flatrate]
        ids = [p.get("provider_id") for p in flatrate]
        print(f"  KR 제공처: {names}")
        print(f"  provider_id: {ids}")
        print(f"  넷플릭스(8) 포함: {8 in ids}")
    else:
        print("  ⚠️ KR watch provider 정보 없음 (← 누락 원인일 수 있음)")

    # 3) discover 조건별 포함 여부 단계 테스트
    print("\n[3] discover 조건별 포함 여부 (2026년)")
    def in_discover(extra, label):
        params = {
            "language": "ko-KR", "page": 1,
            "first_air_date.gte": "2026-01-01",
            "first_air_date.lte": "2026-12-31",
            "sort_by": "first_air_date.desc",
        }
        params.update(extra)
        try:
            data = http_get("/discover/tv", params)
            ids = [it["id"] for it in data.get("results", [])]
            total = data.get("total_results", 0)
            found = TARGET_ID in ids
            # 여러 페이지일 수 있으니 전체에서 검색
            pages = min(data.get("total_pages", 1), 5)
            if not found and pages > 1:
                for p in range(2, pages + 1):
                    params["page"] = p
                    dd = http_get("/discover/tv", params)
                    if TARGET_ID in [it["id"] for it in dd.get("results", [])]:
                        found = True
                        break
            print(f"  [{ '포함O' if found else '누락X' }] {label} (총 {total}건)")
            return found
        except Exception as e:
            print(f"  [오류] {label}: {e}")
            return False

    in_discover({"with_watch_providers": 8, "watch_region": "KR", "with_origin_country": "KR"},
                "넷플릭스+KR지역+KR제작 (현재 우리 조건)")
    in_discover({"with_watch_providers": 8, "watch_region": "KR"},
                "넷플릭스+KR지역 (제작국 조건 제거)")
    in_discover({"with_origin_country": "KR"},
                "KR제작만 (provider 조건 제거)")
    in_discover({"with_original_language": "ko"},
                "한국어 작품만")

    print("\n" + "=" * 60)
    print("해석: '현재 우리 조건'에서 누락인데 다른 조건에서 포함이면,")
    print("      그 빠진 조건이 누락 원인입니다.")
    print("=" * 60)


if __name__ == "__main__":
    main()
