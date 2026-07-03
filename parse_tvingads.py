def extract_posters(html):
    """
    Framer 데이터 script에서 제목→포스터 URL 매핑.
    포스터가 든 script 위치가 개편으로 바뀔 수 있어 인덱스를 고정하지 않고
    포스터 URL이 가장 많은 script를 자동으로 찾는다.
    반환: {제목(공백제거): poster_url}
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    if not scripts:
        return {}
    poster_url_re = re.compile(
        r'https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png)'
    )
    best_idx, best_cnt = -1, 0
    for i, s in enumerate(scripts):
        c = len(poster_url_re.findall(s))
        if c > best_cnt:
            best_cnt, best_idx = c, i
    if best_idx < 0:
        return {}
    data = scripts[best_idx]
    posters = {}
    for m in re.finditer(
        r'"(https://framerusercontent\.com/images/[A-Za-z0-9]+\.(?:webp|jpg|png))\?[^"]*"',
        data,
    ):
        url = m.group(1)
        after = data[m.end():m.end() + 600]
        cands = []
        for cand in re.finditer(r'"([^"]{1,50})"', after):
            txt = cand.group(1)
            if txt.startswith("http") or "framerusercontent" in txt:
                continue
            if re.search(r'[:{}\[\]]', txt):
                continue
            if txt in ("type", "value", "src", "srcSet"):
                continue
            cands.append(txt)
            if len(cands) >= 6:
                break
        tm = None
        for i, txt in enumerate(cands):
            if re.search(r"[가-힣]", txt):
                if i > 0 and re.fullmatch(r"\d{2,4}", cands[i - 1].strip()):
                    tm = cands[i - 1].strip() + " " + txt
                else:
                    tm = txt
                break
        if tm:
            key = tm.replace(" ", "")
            posters.setdefault(key, url)
    return posters
