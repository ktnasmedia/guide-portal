#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
뉴스룸 상세 페이지 접근 테스트 (일회성)
GitHub Actions 서버 IP에서 넷플릭스 뉴스룸 상세 페이지가 열리는지 확인.
실제 수집은 하지 않고, 열렸는지/막혔는지만 출력.
"""
import sys
import re
import urllib.request
import urllib.error

TEST_URLS = [
    "https://about.netflix.com/ko/news/paper-man-wt-announcement",
    "https://about.netflix.com/ko/news/mission-cross-2-sequel-announcement",
    "https://about.netflix.com/ko/newsroom",  # 목록 페이지도 비교
]


def test_url(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36")
    req.add_header("Accept-Language", "ko-KR,ko;q=0.9")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
            status = r.status
            # 제목과 og:image가 잡히는지 확인
            title_m = re.search(r"meta-og:title:\s*([^\n]+)", html) or re.search(r"<title>([^<]+)</title>", html)
            img_m = re.search(r"meta-og:image:\s*(https?://[^\s\n]+)", html)
            work_m = re.search(r"<([^<>]{1,40})>", title_m.group(1)) if title_m else None
            return {
                "status": status,
                "size": len(html),
                "title": (title_m.group(1)[:60] if title_m else None),
                "work": (work_m.group(1) if work_m else None),
                "og_image": (img_m.group(1) if img_m else None),
                "blocked_hint": ("차단" in html or "Access Denied" in html or "captcha" in html.lower()),
            }
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 60)
    print("뉴스룸 상세 페이지 접근 테스트 (GitHub Actions 서버)")
    print("=" * 60)
    ok = 0
    for url in TEST_URLS:
        print(f"\n▶ {url}")
        result = test_url(url)
        if result.get("error"):
            print(f"  ✗ 실패: {result['error']}")
        else:
            print(f"  status: {result['status']} | size: {result['size']:,} bytes")
            print(f"  작품명: {result['work']}")
            print(f"  og:image: {result['og_image']}")
            print(f"  차단의심: {result['blocked_hint']}")
            if result["status"] == 200 and result["size"] > 5000 and not result["blocked_hint"]:
                print("  ✓ 정상 접근 가능")
                ok += 1
            else:
                print("  △ 접근됐으나 내용 불완전 (차단 가능성)")
    print(f"\n{'=' * 60}")
    print(f"결과: {len(TEST_URLS)}개 중 {ok}개 정상 접근")
    print("=" * 60)


if __name__ == "__main__":
    main()
