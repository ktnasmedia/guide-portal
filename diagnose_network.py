#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
network=넷플릭스(213) 조건 + 오리지널 판별 검증 (일회성)
1) 맨 끝줄 소년이 network 조건으로 잡히는가 (신작 누락 해결 확인)
2) provider방식 / network방식 / OR합집합 결과 규모 비교
3) 오리지널 판별: 샘플 작품들의 network에 넷플릭스(213)가 박혀있는지 확인
"""
import os, sys, json, urllib.request, urllib.parse

TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()
API_BASE = "https://api.themoviedb.org/3"
NET_ID = 213   # Netflix network (오리지널 제작/배급)
PROV_ID = 8    # Netflix watch provider (볼 수 있음)
TARGET_ID = 286360  # 맨 끝줄 소년

def http_get(path, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API_BASE}{path}?{qs}")
    req.add_header("Authorization", f"Bearer {TMDB_TOKEN}")
    req.add_header("accept", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def collect_all(extra, max_pages=20):
    found = {}
    page = 1
    while page <= max_pages:
        params = {"language":"ko-KR","page":page,
                  "first_air_date.gte":"2026-01-01","first_air_date.lte":"2026-12-31",
                  "sort_by":"first_air_date.desc"}
        params.update(extra)
        data = http_get("/discover/tv", params)
        results = data.get("results", [])
        if not results: break
        for it in results: found[it["id"]] = it.get("name")
        if page >= data.get("total_pages", 1): break
        page += 1
    return found

def is_original(tv_id):
    """작품 상세의 networks에 넷플릭스(213)가 있으면 오리지널로 판단"""
    try:
        d = http_get(f"/tv/{tv_id}", {"language":"ko-KR"})
        net_ids = [n.get("id") for n in d.get("networks", [])]
        return NET_ID in net_ids, [n.get("name") for n in d.get("networks", [])]
    except Exception as e:
        return None, str(e)

def main():
    if not TMDB_TOKEN:
        print("ERROR: TMDB_TOKEN 없음", file=sys.stderr); sys.exit(1)

    print("="*60)
    print("network 조건 + 오리지널 판별 검증")
    print("="*60)

    net = collect_all({"with_networks":NET_ID, "with_origin_country":"KR"})
    prov = collect_all({"with_watch_providers":PROV_ID, "watch_region":"KR", "with_origin_country":"KR"})
    union = dict(prov); union.update(net)

    print(f"\n[1] 맨 끝줄 소년(286360) 포함 여부")
    print(f"  provider 방식: {TARGET_ID in prov}")
    print(f"  network 방식:  {TARGET_ID in net}")
    print(f"  OR 합집합:     {TARGET_ID in union}")

    print(f"\n[2] 방식별 결과 규모 (2026, KR제작)")
    print(f"  provider=8:        {len(prov)}건")
    print(f"  network=213:       {len(net)}건")
    print(f"  OR 합집합:         {len(union)}건")
    print(f"  network에만 있음:  {len(set(net)-set(prov))}건 (provider가 놓친 신작 후보)")
    print(f"  provider에만 있음: {len(set(prov)-set(net))}건 (오리지널 아닐 가능성)")

    print(f"\n[3] 오리지널 판별 정확도 — network에만 있는 작품 샘플 8개")
    print(f"    (network에 잡혔으니 오리지널이어야 함)")
    for tid in list(set(net)-set(prov))[:8]:
        orig, names = is_original(tid)
        mark = "✓오리지널" if orig else ("✗아님" if orig is False else "?")
        print(f"  [{mark}] {net[tid]} — networks: {names}")

    print(f"\n[4] provider에만 있는 작품 샘플 6개")
    print(f"    (볼 순 있지만 오리지널 아닐 수 있음 → 배지 안 붙음)")
    for tid in list(set(prov)-set(net))[:6]:
        orig, names = is_original(tid)
        mark = "✓오리지널" if orig else ("✗아님" if orig is False else "?")
        print(f"  [{mark}] {prov[tid]} — networks: {names}")

    print("\n"+"="*60)
    print("판단: [3]이 대부분 ✓면 network=오리지널 판별이 정확.")
    print("      OR합집합으로 수집하면 전부 가져오면서 신작도 안 놓침.")
    print("="*60)

if __name__ == "__main__":
    main()
