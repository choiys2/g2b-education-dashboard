#!/usr/bin/env python3
"""배포본(_site)의 모든 HTML에 검색엔진 비노출 메타를 넣는다(링크를 받은 사람만 보도록).

GitHub Pages(프로젝트 사이트)는 응답 헤더(X-Robots-Tag)나 사이트 루트 robots.txt 를 둘 수 없어서,
페이지마다 <meta name="robots" content="noindex, nofollow, noarchive, nosnippet"> 를 넣는 것이 유일한 방법이다.
이미 들어 있으면 건너뛴다.   python add_noindex.py _site
"""
import re
import sys
from pathlib import Path

META = '<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">\n<meta name="googlebot" content="noindex, nofollow">\n<meta name="referrer" content="no-referrer">'


def main(root):
    n = 0
    for p in Path(root).rglob("*.html"):
        s = p.read_text(encoding="utf-8", errors="replace")
        if 'name="robots"' in s:
            continue
        s2, k = re.subn(r"(<head[^>]*>)", r"\1\n" + META, s, count=1, flags=re.I)
        if k:
            p.write_text(s2, encoding="utf-8")
            n += 1
    print(f"noindex: {n}개 HTML에 비노출 메타 추가")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_site")
