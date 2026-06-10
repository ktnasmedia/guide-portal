#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
network=넷플릭스(213) 조건 검증 (일회성)
- 맨 끝줄 소년이 network 조건으로 잡히는지
- provider 방식 vs network 방식 결과 규모 비교
- network 방식에 엉뚱한(비넷플릭스) 작품이 섞이지 않는지 샘플 확인
"""
import os
import sys
import json
import urllib.request
import urllib.parse

TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()
API_BASE = "https://api.themoviedb.org/3"
NETFLIX_NETWORK_ID = 213   # Netflix (제작/배급 network)
NETFLIX_PROVIDER_ID = 8    # Netflix (watch provider)
TARGET_ID = 286360         # 맨 끝줄 소년


def http_get(path, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API_BASE}{path}?{qs}")
    req.add_header("Authorization", f"Bearer {TMDB_TOKEN}")
    req.add_header("accept", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def collect_all(extra, max_pages=15):
    """조건에 맞는 2026년 작품 전체 수집 (id→name)"""
    found = {}
    page = 1
    while page <= max_pages:
        params = {
            "language": "ko-KR", "page": page,
            "first_air_date.gte": "2026-01-01",
            "first_air_date.lte": "2026-12-31",
            "sort_by": "first_air_date.desc",
        }
        params.update(extra)
        data = http_get("/discover/tv", params)
        results = data.get("results", [])
        if not results:
            break
        for it in results:
            found[it["id"]] = it.get("name")
        if page >= data.get("total_pages", 1):
            break
        page += 1
    return found


def main():
    if not TMDB_TOKEN:
        print("ERROR: TMDB_TOKEN 없음", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("network=넷플릭스(213) 조건 검증")
    print("=" * 60)

    # 1) 맨 끝줄 소년이 network 조건으로 잡히는가
    print("\n[1] 맨 끝줄 소년이 network=213 조건에 포함되는가")
    net = collect_all({"with_networks": NETFLIX_NETWORK_ID, "with_origin_country": "KR"})
    print(f"  network=213 + KR제작 결과: {len(net)}건")
    print(f"  맨 끝줄 소년(286360) 포함: {TARGET_ID in net}")

    # 2) provider 방식과 비교
    print("\n[2] provider 방식 vs network 방식 (2026, KR제작)")
    prov = collect_all({"with_watch_providers": NETFLIX_PROVIDER_ID, "watch_region": "KR", "with_origin_country": "KR"})
    print(f"  provider=8 방식: {len(prov)}건 (현재 우리 방식)")
    print(f"  network=213 방식: {len(net)}건")
    only_net = set(net) - set(prov)
    only_prov = set(prov) - set(net)
    print(f"  network에만 있음(신규 포착): {len(only_net)}건")
    print(f"  provider에만 있음: {len(only_prov)}건")

    # 3) network에만 있는 작품 샘플 (신작들이 잡히는지)
    print("\n[3] network 방식이 새로 잡는 작품 샘플 (최대 15개)")
    for tid in list(only_net)[:15]:
        print(f"  - {net[tid]} (id {tid})")

    # 4) provider에만 있는 작품 샘플 (network이 놓치는 게 있는지)
    print("\n[4] provider에만 있고 network엔 없는 작품 샘플 (최대 10개)")
    if only_prov:
        for tid in list(only_prov)[:10]:
            print(f"  - {prov[tid]} (id {tid})")
    else:
        print("  없음 (network이 provider를 모두 포함)")

    print("\n" + "=" * 60)
    print("판단 기준:")
    print(" - [1] 맨끝줄소년 포함 = True 면 network 조건이 신작을 잡음")
    print(" - [3]에 진짜 넷플릭스 신작들이 보이면 OK")
    print(" - [4]가 비어있거나 적으면 network로 바꿔도 손실 적음")
    print("=" * 60)


if __name__ == "__main__":
    main()
