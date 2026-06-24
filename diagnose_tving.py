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
    checked = 0
    for tv_id, name in tving_all.items():
        provs = get_providers(tv_id)
        checked += 1
        if checked % 20 == 0:
            print(f"    ...{checked}/{len(tving_all)} 확인")
        # 티빙엔 있고, 다른 주요 OTT엔 없음 → 독점(Only)
        if PROV_TVING in provs and not (provs & OTHER_PROVIDERS):
            only[tv_id] = name
    print(f"    → TVING Only(독점) 작품 수: {len(only)}건")

    # ── 결과 요약 ──
    print("\n" + "=" * 60)
    print("결과 요약")
    print("=" * 60)
    print(f"  TVING Original (network 3897)      : {len(original):>4}건")
    print(f"  티빙 시청가능 전체 (provider 1883) : {len(tving_all):>4}건")
    print(f"  TVING Only (티빙 독점)             : {len(only):>4}건")

    # Original 중 Only에도 포함되는 교집합
    inter = set(original) & set(only)
    print(f"  Original ∩ Only (둘 다 해당)       : {len(inter):>4}건")
    only_not_original = set(only) - set(original)
    print(f"  Only 인데 Original 아님            : {len(only_not_original):>4}건")

    def preview(d, n=15):
        names = list(d.values())
        for nm in names[:n]:
            print(f"      - {nm}")
        if len(names) > n:
            print(f"      ... 외 {len(names)-n}건")

    print("\n[Original 목록 미리보기]")
    preview(original)
    print("\n[Only 목록 미리보기]")
    preview(only)
    print("\n[Only 인데 Original 아닌 작품 미리보기] (사올렸거나 독점계약 추정)")
    preview({k: only[k] for k in only_not_original})

    print("\n완료. 위 숫자/목록을 보고 수집 범위(Original만 vs Only 포함)를 결정하세요.")


if __name__ == "__main__":
    main()
