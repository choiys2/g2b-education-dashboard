#!/usr/bin/env python3
"""
GitHub Pages(공개 주소)에 올릴 최소 사이트를 만든다.

대시보드 본체는 이메일 로그인(Cloudflare Access) 뒤의 https://<프로젝트>.pages.dev 에만 올리고,
누구나 열 수 있는 GitHub 주소에는 외부 연동용 공개 자료만 남긴다.
- 남김: news/(조간 지면) · api/news(뉴스 JSON, 비상 영업앱·채팅 루틴용) · widget/ · full/calendar.ics(입찰 마감 구독)
- 대시보드 주소(/, /full/, /full/weekly.html)는 로그인 주소로 넘기는 안내 페이지만 둔다.

  python gh_public_site.py <출력폴더> <news폴더> <api폴더> <widget폴더> [calendar.ics]
"""
import os
import shutil
import sys

PROJECT = os.environ.get("CF_PAGES_PROJECT") or "vs-insight"
DEST = f"https://{PROJECT}.pages.dev/full/"

MOVED = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
<meta name="referrer" content="no-referrer">
<meta http-equiv="refresh" content="0; url={DEST}">
<title>대시보드 주소 이전</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;background:#f6f7f9;color:#1a1f2b;padding:16px}}
@media (prefers-color-scheme: dark){{body{{background:#0f141c;color:#e8ecf2}}a{{color:#4f8cff}}}}
.c{{max-width:360px;text-align:center;font-size:14px;line-height:1.6}}a{{color:#0075de}}</style>
</head><body><div class="c"><b>대시보드 주소가 바뀌었습니다</b><br>
회사 이메일 확인 후 열리는 주소로 이동합니다.<br><a href="{DEST}">{DEST}</a></div>
<script>location.replace({DEST!r});</script></body></html>
"""


def main():
    dst, news, api, widget = sys.argv[1:5]
    ics = sys.argv[5] if len(sys.argv) > 5 else ""
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.join(dst, "full"))
    for src, name in ((news, "news"), (api, "api"), (widget, "widget")):
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, name))
    if ics and os.path.isfile(ics) and os.path.getsize(ics):
        shutil.copy(ics, os.path.join(dst, "full", "calendar.ics"))
    for p in ("index.html", "full/index.html", "full/weekly.html"):
        with open(os.path.join(dst, p), "w", encoding="utf-8") as f:
            f.write(MOVED)
    files = sorted(os.path.relpath(os.path.join(r, n), dst) for r, _, ns in os.walk(dst) for n in ns)
    print(f"GitHub 공개 사이트 {len(files)}개 파일 (대시보드 → {DEST})")
    for x in files:
        if not x.startswith(("news/", "api/")):
            print(" ", x)


if __name__ == "__main__":
    main()
