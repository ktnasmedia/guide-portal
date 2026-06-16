#!/usr/bin/env python3
"""
티빙(TVING) 수집 진단 스크립트 (일회성 점검용)
- 목적: 티빙 provider(1883) / network(3897)로 한국 콘텐츠가 TMDB에서 몇 개나, 어떻게 잡히는지 확인
- 넷플릭스 수집(collect_lineup.py)과 완전히 분리됨. 이 파일은 진단만 하고 아무것도 저장하지 않음.
- 결과는 화면(stdout)에 출력 → GitHub Actions 로그에서 확인
"""
import os
import json
import urllib.request
import urllib.parse

TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()
API_BASE = "https://api.themoviedb.org/3"
TVING_PROVIDER_ID = 1883   # 티빙 watch provider
TVING_NETWORK_ID = 3897    # 티빙 network
REGION = "KR"
ORIGIN_COUNTRY = "KR"
LANG = "ko-KR"


def http_get(path, params):
    qs = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}?{qs}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {TMDB_TOKEN}")
    req.add_header("accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def discover_pages(media_type, params, label):
    """여러 페이지를 모아 (id, 제목, 방송사networks) 목록 반환"""
    results = {}
    page = 1
    while page <= 5:  # 최대 5페이지(100건)까지만 진단
        p = dict(params)
        p["page"] = page
        try:
            data = http_get(f"/discover/{media_type}", p)
        except Exception as e:
            print(f"    [오류] {label} {media_type} page{page}: {e}")
            break
        items = data.get("results", [])
        if not items:
            break
        for it in items:
            tid = it.get("id")
            title = it.get("name") or it.get("title") or "(제목없음)"
            date = it.get("first_air_date") or it.get("release_date") or ""
            results[tid] = {"title": title, "date": date}
        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1
    return results


def main():
    if not TMDB_TOKEN:
        print("[중단] TMDB_TOKEN 환경변수가 없습니다. GitHub Secrets 확인 필요.")
        return

    print("=" * 60)
    print("티빙(TVING) 수집 진단")
    print(f"  provider_id={TVING_PROVIDER_ID}, network_id={TVING_NETWORK_ID}")
    print(f"  region={REGION}, origin_country={ORIGIN_COUNTRY}")
    print("=" * 60)

    for year in [2025, 2026]:
        print(f"\n■ {year}년 기준")

        # ── 방법1: provider(볼 수 있는 곳)로 티빙 TV 수집 ──
        prov_params = {
            "language": LANG,
            "sort_by": "first_air_date.desc",
            "first_air_date.gte": f"{year}-01-01",
            "first_air_date.lte": f"{year}-12-31",
            "watch_region": REGION,
            "with_watch_providers": TVING_PROVIDER_ID,
            "with_origin_country": ORIGIN_COUNTRY,
        }
        prov = discover_pages("tv", prov_params, "provider")
        print(f"\n  [방법1] provider={TVING_PROVIDER_ID}로 잡힌 TV: {len(prov)}건")
        for tid, info in list(prov.items())[:15]:
            print(f"      - {info['title']} ({info['date']}) [id={tid}]")

        # ── 방법2: network(제작/배급)로 티빙 TV 수집 ──
        net_params = {
            "language": LANG,
            "sort_by": "first_air_date.desc",
            "first_air_date.gte": f"{year}-01-01",
            "first_air_date.lte": f"{year}-12-31",
            "with_networks": TVING_NETWORK_ID,
        }
        net = discover_pages("tv", net_params, "network")
        print(f"\n  [방법2] network={TVING_NETWORK_ID}로 잡힌 TV: {len(net)}건")
        for tid, info in list(net.items())[:15]:
            print(f"      - {info['title']} ({info['date']}) [id={tid}]")

        # ── 겹침 분석 ──
        prov_ids = set(prov.keys())
        net_ids = set(net.keys())
        both = prov_ids & net_ids
        print(f"\n  [분석] provider만: {len(prov_ids - net_ids)}건 / "
              f"network만: {len(net_ids - prov_ids)}건 / 둘 다: {len(both)}건")

    print("\n" + "=" * 60)
    print("진단 끝. 위 결과로 티빙 수집 전략을 정합니다.")
    print("  - provider/network로 충분한 티빙 작품이 잡히는지")
    print("  - 잡힌 작품이 실제 티빙 콘텐츠가 맞는지(엉뚱한 게 섞였는지)")
    print("=" * 60)


if __name__ == "__main__":
    main()
