#!/usr/bin/env python3
"""
조간 브리핑 AI 보조 - 최신 브리핑을 Gemini로 3줄 요약·영업 한마디·키워드로 정리한다.

- 입력: briefings/YYYY-MM-DD.json (평문만 추려 보낸다)
- 출력: history/news_ai.jsonl {date, summary[3], sales_brief, keywords[], model} - 같은 날짜는 다시 호출하지 않는다.
  news_api_export.py 가 issue["ai"] 로 실어 위젯·외부 앱이 쓴다.
- 최근 MAX_DAYS 개 호 중 결과가 없는 것만 처리(배포가 하루 2~3번 돌아도 호출은 호당 1회).
"""
import json
import re
import sys
from html import unescape
from pathlib import Path

import gemini_client as gc

HERE = Path(__file__).parent
CACHE = HERE / "history" / "news_ai.jsonl"
MAX_DAYS = 3

PROMPT = """너는 (주)비상교육 비바샘원격교육연수원 영업팀을 돕는 브리핑 편집자다.
아래 오늘자 교육 조간 브리핑(평문)만 근거로 한국어 JSON을 만들어라. 브리핑에 없는 사실은 쓰지 마라.
{"summary": ["오늘의 핵심 3줄(각 60자 이내)"], "sales_brief": "교육청·학교 담당자와 통화할 때 쓸 오늘의 영업 한마디(80자 이내)",
 "keywords": ["키워드 5개 이내"], "risk": "주의할 점 1문장(없으면 빈 문자열)"}
브리핑:
"""


def plain(s):
    return unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def flatten(d):
    lead = d.get("lead") or {}
    lines = [f"[헤드라인] {plain(lead.get('headline'))}", plain(lead.get("sub")), plain(lead.get("lede"))]
    lines += [f"- {plain(f.get('label'))}: {plain(f.get('text'))}" for f in lead.get("facts") or []]
    for sec in d.get("sections") or []:
        lines.append(f"[{sec.get('name')}]")
        lines += [f"- {plain(it.get('title'))}: {plain(it.get('body'))[:300]}" for it in sec.get("items") or []]
    lines += [f"[시사점] {plain(im.get('news'))} -> {plain(im.get('impact'))}" for im in d.get("implications") or []]
    return "\n".join(x for x in lines if x)[:20000]


def load():
    out = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                out[r["date"]] = r
            except (json.JSONDecodeError, KeyError):
                pass
    return out


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "briefings")
    if not gc.key():
        print("[경고] GEMINI_API_KEY 없음 - 브리핑 AI 요약 건너뜀", file=sys.stderr)
        return
    cache = load()
    made = 0
    for f in sorted(src.glob("????-??-??.json"))[-MAX_DAYS:]:
        if f.stem in cache:
            continue
        try:
            r = gc.generate_json(PROMPT + flatten(json.loads(f.read_text(encoding="utf-8"))))
        except Exception as e:
            print(f"[경고] {f.stem} 요약 실패: {gc.mask(e)[:160]}", file=sys.stderr)
            continue
        cache[f.stem] = {"date": f.stem, "summary": [str(x)[:120] for x in r.get("summary", [])[:3]],
                         "sales_brief": str(r.get("sales_brief", ""))[:200],
                         "keywords": [str(x)[:20] for x in r.get("keywords", [])[:5]],
                         "risk": str(r.get("risk", ""))[:200], "model": gc.model().split("/")[-1]}
        made += 1
    CACHE.write_text("".join(json.dumps(cache[k], ensure_ascii=False) + "\n" for k in sorted(cache)), encoding="utf-8")
    print(f"브리핑 AI 요약: 새로 {made}건, 누적 {len(cache)}건")


if __name__ == "__main__":
    main()
