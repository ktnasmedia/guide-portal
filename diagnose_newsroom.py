#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
뉴스룸 상세 페이지 원본 HTML 진단 (일회성)
서버가 받은 진짜 HTML에서 og:title, og:image가 어떤 형식으로 들어있는지 그대로 출력.
이걸 보고 정확한 추출 패턴을 정한다.
"""
import re
import urllib.request

URL = "https://about.netflix.com/ko/news/paper-man-wt-announcement"


def main():
    req = urllib.request.Request(URL)
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
    req.add_header("Accept-Language", "ko-KR,ko;q=0.9")
    with urllib.request.urlopen(req, timeout=20) as r:
        html = r.read().decode("utf-8", errors="ignore")

    print("총 길이:", len(html))
    print("=" * 60)

    # 1) 'og:' 또는 'og-' 가 들어간 줄/부분 모두 출력
    print("[og 관련 문자열 주변 추출]")
    for m in re.finditer(r'.{0,80}og[:\-]?(?:title|image).{0,160}', html, re.IGNORECASE):
        snippet = m.group(0).replace("\n", " ")
        print("  ...", snippet[:240])
    print("=" * 60)

    # 2) <title> 태그
    print("[<title> 태그]")
    tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    print("  ", (tm.group(1).strip()[:120] if tm else "없음"))
    print("=" * 60)

    # 3) <meta property=...> 형태 샘플 (앞쪽 몇 개)
    print("[meta 태그 샘플 (property/content 포함, 앞 10개)]")
    count = 0
    for m in re.finditer(r'<meta[^>]*(?:property|name)=["\']([^"\']+)["\'][^>]*content=["\']([^"\']*)["\']', html, re.IGNORECASE):
        key, val = m.group(1), m.group(2)
        if "og" in key.lower() or "title" in key.lower() or "image" in key.lower() or "desc" in key.lower():
            print(f"  {key} = {val[:100]}")
            count += 1
        if count >= 10:
            break
    if count == 0:
        print("  (property/content 형식 meta 태그를 못 찾음)")
    print("=" * 60)

    # 4) ctfassets 이미지 URL 직접 탐색
    print("[ctfassets 이미지 URL 탐색]")
    imgs = re.findall(r'https://images\.ctfassets\.net/[^\s"\'<>]+', html)
    for u in imgs[:5]:
        print("  ", u)
    if not imgs:
        print("  (없음)")
    print("=" * 60)

    # 5) '차단' 단어가 어떤 맥락인지
    print("['차단' 단어 맥락]")
    for m in re.finditer(r'.{0,40}차단.{0,40}', html):
        print("  ...", m.group(0).replace("\n", " "))


if __name__ == "__main__":
    main()
