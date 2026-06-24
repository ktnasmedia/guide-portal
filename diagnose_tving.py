#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
티빙 콘텐츠 수집 범위 비교 진단 스크립트 (일회성 테스트용)

목적:
  - TVING Original (network 3897 기준): 티빙 자체 제작/오리지널
  - TVING Only (provider 1883 중 타 OTT provider에 없는 작품): 티빙 디지털 독점 공개
  두 방식이 각각 몇 건이고 어떤 작품인지 비교 출력.

사용법 (GitHub Actions 또는 로컬):
  - 환경변수 TMDB_TOKEN 에 TMDB v4 Bearer 토큰 설정
  - python diagnose_tving.py
  - 결과는 콘솔(로그)로 출력. 파일도 안 만들고 기존 데이터도 안 건드림.

주의:
  - provider(시청 가능 플랫폼) 정보는 한국(KR) 기준, 조회 시점에 따라 달라질 수 있음.
  - TMDB의 한국 OTT provider 정보는 누락이 있을 수 있어 Only 판별은 참고용.
"""

import os
import sys
import time
import requests

TOKEN = os.environ.get("TMDB_TOKEN", "").strip()
if not TOKEN:
    print("ERROR: 환경변수 TMDB_TOKEN 이 설정되지 않았습니다.")
    sys.exit(1)

BASE = "https://api.themoviedb.org/3"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "accept": "application/json"}
REGION = "KR"

# ── OTT provider ID (한국 기준, TMDB watch provider) ──
PROV_TVING   = 1883
PROV_NETFLIX = 8
PROV_WAVVE   = 356
PROV_DISNEY  = 337
PROV_COUPANG = 1796   # 쿠팡플레이
PROV_WATCHA  = 97
PROV_APPLE   = 350
# 티빙 Only 판별 시 "다른 OTT" 목록 (여기 중 하나라도 있으면 독점 아님)
OTHER_PROVIDERS = {PROV_NETFLIX, PROV_WAVVE, PROV_DISNEY, PROV_COUPANG, PROV_WATCHA, PROV_APPLE}

# provider ID → 이름 (로그 출력용)
PROV_NAMES = {
    PROV_TVING: "티빙", PROV_NETFLIX: "넷플릭스", PROV_WAVVE: "웨이브",
    PROV_DISNEY: "디즈니+", PROV_COUPANG: "쿠팡플레이", PROV_WATCHA: "왓챠",
    PROV_APPLE: "애플TV+",
}
def prov_label(ids):
    if not ids:
        return "(어디에도 없음/정보없음)"
    return ", ".join(PROV_NAMES.get(i, f"ID{i}") for i in sorted(ids))

# ── 티빙 network ID (자체 제작/오리지널) ──
NETWORK_TVING = 3897

# 수집 연도 범위 (전년·올해·내년)
import datetime
Y = datetime.date.today().year
YEARS = [Y - 1, Y, Y + 1]


def get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2)
                continue
            print(f"  [warn] {r.status_code} {url} {params}")
            return None
        except Exception as e:
            print(f"  [err] {e}")
            time.sleep(1)
    return None


def discover_by_network(network_id):
    """network 기준 TV 작품 수집 (TVING Original 근사)"""
    found = {}
    for year in YEARS:
        page = 1
        while True:
            data = get(f"{BASE}/discover/tv", {
                "with_networks": network_id,
                "first_air_date_year": year,
                "language": "ko-KR",
                "page": page,
                "sort_by": "first_air_date.desc",
            })
            if not data:
                break
            for it in data.get("results", []):
                found[it["id"]] = it.get("name", "")
            if page >= data.get("total_pages", 1) or page >= 20:
                break
            page += 1
    return found


def discover_by_provider(provider_id):
    """watch provider 기준 TV 작품 수집 (티빙에서 볼 수 있는 작품)"""
    found = {}
    for year in YEARS:
        page = 1
        while True:
            data = get(f"{BASE}/discover/tv", {
                "with_watch_providers": provider_id,
                "watch_region": REGION,
                "first_air_date_year": year,
                "language": "ko-KR",
                "page": page,
                "sort_by": "first_air_date.desc",
            })
            if not data:
                break
            for it in data.get("results", []):
                found[it["id"]] = it.get("name", "")
            if page >= data.get("total_pages", 1) or page >= 20:
                break
            page += 1
    return found


def get_providers(tv_id):
    """특정 작품의 한국(KR) flatrate(정액제) provider ID 집합"""
    data = get(f"{BASE}/tv/{tv_id}/watch/providers")
    if not data:
        return set()
    kr = data.get("results", {}).get(REGION, {})
    ids = set()
    for kind in ("flatrate", "free", "ads"):
        for p in kr.get(kind, []):
            ids.add(p.get("provider_id"))
    return ids


def main():
    print("=" * 60)
    print(f"티빙 콘텐츠 수집 범위 비교  (연도: {YEARS}, 지역: {REGION})")
    print("=" * 60)

    # 1) TVING Original (network 3897)
    print("\n[1] TVING Original — network 3897 기준 수집 중...")
    original = discover_by_network(NETWORK_TVING)
    print(f"    → Original 작품 수: {len(original)}건")

    # 2) 티빙 provider(1883)로 볼 수 있는 작품 전체
    print("\n[2] 티빙 provider 1883 기준 수집 중...")
    tving_all = discover_by_provider(PROV_TVING)
    print(f"    → 티빙에서 볼 수 있는 작품 수: {len(tving_all)}건")

    # 3) TVING Only = 티빙 provider에 있으나 타 OTT provider엔 없는 작품
    print("\n[3] TVING Only 판별 중 (각 작품의 provider 교차 확인)...")
    only = {}
    prov_cache = {}   # tv_id → provider 집합 (재사용)
    checked = 0
    for tv_id, name in tving_all.items():
        provs = get_providers(tv_id)
        prov_cache[tv_id] = provs
        checked += 1
        if checked % 20 == 0:
            print(f"    ...{checked}/{len(tving_all)} 확인")
        # 티빙엔 있고, 다른 주요 OTT엔 없음 → 독점(Only)
        if PROV_TVING in provs and not (provs & OTHER_PROVIDERS):
            only[tv_id] = name
    print(f"    → TVING Only(독점) 작품 수: {len(only)}건")

    # 4) Original 인데 Only에 안 잡힌 작품의 provider 조회 (다른 OTT 확인용)
    print("\n[4] Original 중 Only에 없는 작품의 provider 조회 중...")
    only_not_orig = set(only) - set(original)
    orig_not_only = set(original) - set(only)
    orig_prov = {}
    for tv_id in orig_not_only:
        if tv_id in prov_cache:
            orig_prov[tv_id] = prov_cache[tv_id]
        else:
            orig_prov[tv_id] = get_providers(tv_id)

    # ── 결과 요약 ──
    print("\n" + "=" * 60)
    print("결과 요약")
    print("=" * 60)
    print(f"  TVING Original (network 3897)      : {len(original):>4}건")
    print(f"  티빙 시청가능 전체 (provider 1883) : {len(tving_all):>4}건")
    print(f"  TVING Only (티빙 독점)             : {len(only):>4}건")
    print(f"  Original ∩ Only (둘 다 해당)       : {len(set(original)&set(only)):>4}건")
    print(f"  Only 인데 Original 아님            : {len(only_not_orig):>4}건")
    print(f"  Original 인데 Only 아님            : {len(orig_not_only):>4}건")

    # ── TVING Only 전체 목록 ──
    print("\n" + "=" * 60)
    print(f"[A] TVING Only 전체 목록 ({len(only)}건)")
    print("=" * 60)
    for i, (tv_id, name) in enumerate(sorted(only.items(), key=lambda x: x[1]), 1):
        print(f"  {i:>3}. {name}")

    # ── Original 인데 Only 아닌 작품 + 어디서 보이는지 ──
    print("\n" + "=" * 60)
    print(f"[B] Original 인데 Only 아닌 작품 ({len(orig_not_only)}건) — 다른 OTT 확인")
    print("=" * 60)
    for i, tv_id in enumerate(sorted(orig_not_only, key=lambda x: original.get(x, "")), 1):
        name = original.get(tv_id, "")
        provs = orig_prov.get(tv_id, set())
        print(f"  {i:>3}. {name}")
        print(f"        시청가능: {prov_label(provs)}")

    print("\n완료. [A] Only 전체 목록과 [B] 35건의 다른 OTT 여부를 보고 결정하세요.")


if __name__ == "__main__":
    main()
