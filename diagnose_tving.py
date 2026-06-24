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

# TMDB TV 장르 ID → 한글 이름
TV_GENRES = {
    10759: "액션&어드벤처", 16: "애니메이션", 35: "코미디", 80: "범죄",
    99: "다큐멘터리", 18: "드라마", 10751: "가족", 10762: "키즈",
    9648: "미스터리", 10763: "뉴스", 10764: "리얼리티", 10765: "SF&판타지",
    10766: "연속극", 10767: "토크", 10768: "전쟁&정치", 37: "서부",
}

def get_detail(tv_id):
    """작품 상세: 장르 + 원산지 + 에피소드길이 + 제작사 (숏폼 추정 포함)"""
    data = get(f"{BASE}/tv/{tv_id}", {"language": "ko-KR"})
    if not data:
        return [], [], None, [], False
    genres = [g.get("name", "") for g in data.get("genres", [])]
    origin = data.get("origin_country", []) or []
    runtimes = data.get("episode_run_time", []) or []
    runtime = runtimes[0] if runtimes else None
    companies = [c.get("name", "") for c in data.get("production_companies", [])]
    # 숏폼 추정: 회차 15분 이하 OR 제작사에 숏폼 키워드
    SHORT_COMPANIES = ["shortcha", "shortime", "lezhin snack", "vigloo", "vlending", "kanta", "alwayz", "shortcha", "playlist", "와이낫미디어", "shorts"]
    is_short = False
    if runtime is not None and runtime <= 15:
        is_short = True
    comp_low = " ".join(companies).lower()
    if any(k in comp_low for k in SHORT_COMPANIES):
        is_short = True
    return genres, origin, runtime, companies, is_short

def get_detail_full(tv_id):
    """작품 상세: 공개일 + network 목록 (정보없음 작품 분석용)"""
    data = get(f"{BASE}/tv/{tv_id}", {"language": "ko-KR"})
    if not data:
        return "", []
    air = data.get("first_air_date", "") or ""
    networks = [n.get("name", "") for n in data.get("networks", [])]
    return air, networks

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


def diagnose_titles(titles):
    """특정 제목들을 TMDB에서 검색해 존재·provider·network·공개일 확인"""
    print("\n" + "=" * 60)
    print("[C] 빠진 작품 개별 진단 (왜 Only에 안 잡혔는지)")
    print("=" * 60)
    for q in titles:
        print(f"\n● '{q}'")
        data = get(f"{BASE}/search/tv", {"query": q, "language": "ko-KR"})
        results = (data or {}).get("results", [])
        if not results:
            # 영화로도 검색
            mdata = get(f"{BASE}/search/movie", {"query": q, "language": "ko-KR"})
            mres = (mdata or {}).get("results", [])
            if mres:
                print(f"    TV로는 없음. 영화로 검색됨: {mres[0].get('title','')} (TMDB는 movie로 등록)")
            else:
                print("    ✗ TMDB에 검색 결과 없음 (작품 미등록 또는 제목 상이)")
            continue
        # 가장 유사한 첫 결과
        top = results[0]
        tv_id = top["id"]
        name = top.get("name", "")
        air = top.get("first_air_date", "") or "미정"
        # network
        detail = get(f"{BASE}/tv/{tv_id}", {"language": "ko-KR"})
        networks = [n.get("name","") for n in (detail or {}).get("networks", [])] if detail else []
        # provider
        provs = get_providers(tv_id)
        has_tving_net = any("tving" in n.lower() for n in networks)
        print(f"    ✓ TMDB 존재: '{name}' (id={tv_id}) | 공개일: {air}")
        print(f"      network(제작/방영): {', '.join(networks) if networks else '없음'}{'  ← 티빙 network 있음' if has_tving_net else ''}")
        print(f"      provider(시청처): {prov_label(provs)}")
        # 왜 Only에 안 잡혔는지 판정
        if PROV_TVING not in provs:
            print(f"      → Only 누락 원인: TMDB provider에 티빙 없음 (provider 데이터 누락)")
        elif provs & OTHER_PROVIDERS:
            print(f"      → Only 제외 원인: 티빙 외 다른 OTT에도 있음")
        if results and len(results) > 1:
            print(f"      (검색 결과 {len(results)}건 중 첫 번째 기준)")


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

    # ── TVING Only 전체 목록 (장르·원산지·숏폼 포함) ──
    print("\n[5] Only 작품들의 장르·원산지·숏폼 조회 중...")
    only_detail = {}   # tv_id → (genres, origin, runtime, companies, is_short)
    cnt = 0
    for tv_id in only:
        only_detail[tv_id] = get_detail(tv_id)
        cnt += 1
        if cnt % 20 == 0:
            print(f"    ...{cnt}/{len(only)} 확인")

    # 장르별 집계
    from collections import Counter
    genre_counter = Counter()
    origin_counter = Counter()
    anime_ids = []
    short_ids = []   # 숏폼 추정 작품
    for tv_id, (genres, origin, runtime, companies, is_short) in only_detail.items():
        for g in genres:
            genre_counter[g] += 1
        for o in origin:
            origin_counter[o] += 1
        if "애니메이션" in genres:
            anime_ids.append(tv_id)
        if is_short:
            short_ids.append(tv_id)

    print("\n" + "=" * 60)
    print(f"[A] TVING Only 전체 목록 ({len(only)}건) — 원산지 · 장르 · 숏폼 · 회차길이")
    print("=" * 60)
    for i, (tv_id, name) in enumerate(sorted(only.items(), key=lambda x: x[1]), 1):
        genres, origin, runtime, companies, is_short = only_detail.get(tv_id, ([], [], None, [], False))
        g = ", ".join(genres) if genres else "장르정보없음"
        o = "/".join(origin) if origin else "?"
        rt = f"{runtime}분" if runtime else "?"
        short_mark = " [숏폼추정]" if is_short else ""
        print(f"  {i:>3}. {name}{short_mark}")
        print(f"        [{o}] {g} | 회차 {rt}")

    # ── 장르 통계 ──
    print("\n" + "=" * 60)
    print("[A-1] Only 장르별 작품 수 (한 작품이 여러 장르일 수 있음)")
    print("=" * 60)
    for g, c in genre_counter.most_common():
        print(f"  {g:<14}: {c:>3}건")

    print("\n[A-2] Only 원산지 국가별 작품 수")
    print("=" * 60)
    KOR = {"KR": "한국", "JP": "일본", "CN": "중국", "US": "미국"}
    for o, c in origin_counter.most_common():
        print(f"  {KOR.get(o, o):<6}: {c:>3}건")

    print(f"\n[A-3] 애니메이션 장르 포함 작품: {len(anime_ids)}건")
    for tv_id in anime_ids:
        print(f"      - {only.get(tv_id,'')}")

    print(f"\n[A-4] 숏폼 추정 작품: {len(short_ids)}건 (회차 15분 이하 또는 숏폼 제작사)")
    for tv_id in short_ids:
        g, o, rt, comp, _ = only_detail.get(tv_id, ([], [], None, [], False))
        rt_s = f"{rt}분" if rt else "회차길이?"
        comp_s = ", ".join(comp[:3]) if comp else ""
        print(f"      - {only.get(tv_id,'')} ({rt_s}) {comp_s}")

    # ── Original 인데 Only 아닌 작품 + 어디서 보이는지 + 공개일/network ──
    print("\n" + "=" * 60)
    print(f"[B] Original 인데 Only 아닌 작품 ({len(orig_not_only)}건) — 다른 OTT · 공개일")
    print("=" * 60)
    import datetime as _dt
    today_str = _dt.date.today().isoformat()
    for i, tv_id in enumerate(sorted(orig_not_only, key=lambda x: original.get(x, "")), 1):
        name = original.get(tv_id, "")
        provs = orig_prov.get(tv_id, set())
        air, networks = get_detail_full(tv_id)
        # 숏폼 추정 (회차 길이 + 제작사)
        _, _, runtime, companies, is_short = get_detail(tv_id)
        net = ", ".join(networks) if networks else "?"
        rt = f"{runtime}분" if runtime else "?"
        short_mark = " [숏폼추정]" if is_short else ""
        note = ""
        if not provs:
            if air and air <= today_str:
                note = "  ← 이미 공개됨(TMDB provider 누락 추정)"
            elif air and air > today_str:
                note = "  ← 공개 예정작"
            else:
                note = "  ← 공개일 미상"
        print(f"  {i:>3}. {name}{short_mark}")
        print(f"        공개일: {air or '미정'} | 회차: {rt} | 제작/방영사: {net}")
        print(f"        시청가능: {prov_label(provs)}{note}")

    print("\n완료. [A] Only 전체 목록과 [B] 35건의 공개일·OTT 여부를 보고 결정하세요.")

    # [C] 누락 의심 작품 개별 진단
    MISSING_CHECK = [
        "스크릿 레스토랑 파이터", "콩콩팜팜", "내일도 출근",
        "도깨비 10주년 여행", "샤먼: 미신전", "도굴왕",
    ]
    diagnose_titles(MISSING_CHECK)


if __name__ == "__main__":
    main()
