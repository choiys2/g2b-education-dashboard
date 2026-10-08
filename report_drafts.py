#!/usr/bin/env python3
"""
B2G 결과보고서 초안(Gemini, CI 전용): 최근 끝난 운영DT 사업의 결과보고서 골격과 장학사 보고 요지.
- 입력: live/own_pipeline_export.json 의 사업명·기관·지역·분야·기간·목표/신청 인원만(개인정보·소통 원문 없음)
- 출력: live/report_drafts.json {사업명: {"summary", "report", "next"}} — history 에 저장하지 않는다(사업명 포함).
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

import gemini_client as gc
from ops_insights import num, parse_date

HERE = Path(__file__).parent
MAX = 4
PROMPT = """너는 교원 원격연수 기관(비바샘원격교육연수원)의 B2G 사업 담당자다. 아래는 최근 끝난 교육청 위탁 연수 사업이다.
사업마다 교육청 제출용 결과보고서 초안과 장학사 구두 보고 요지를 한국어로 써라. 데이터에 없는 수치(만족도·이수율 등)는 만들지 말고
'[확인 필요: 이수 인원]'처럼 빈칸으로 둬라. 반드시 아래 JSON:
{"items": [{"summary": "장학사 보고 요지 2문장", "report": "결과보고서 초안(1. 사업 개요 2. 운영 결과 3. 성과 4. 개선·차기 제안, 각 2~3문장, 줄바꿈 \\n)",
            "next": "차년도 재계약 제안 포인트 1문장"}]}
사업 목록:
"""


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/report_drafts.json")
    try:
        recs = json.loads((HERE / "live" / "own_pipeline_export.json").read_text(encoding="utf-8")).get("records", [])
    except FileNotFoundError:
        return
    today = date.today()
    done = []
    for r in recs:
        end = parse_date(r.get("trainEnd"))
        if end and 0 <= (today - end).days <= 75 and (re.search(r"완료|종료|정산", str(r.get("status") or "")) or (today - end).days >= 3):
            done.append((end, r))
    done = [r for _, r in sorted(done, key=lambda x: x[0], reverse=True)[:MAX]]
    if not done or not gc.key():
        print(f"결과보고 초안: 대상 {len(done)}건 - 건너뜀")
        return
    brief = [{"사업명": r.get("courseName"), "발주기관": r.get("org"), "지역": r.get("region"), "분야": r.get("field"),
              "모집기간": f"{r.get('recruitStart', '')}~{r.get('recruitEnd', '')}", "연수기간": f"{r.get('trainStart', '')}~{r.get('trainEnd', '')}",
              "목표인원": num(r.get("targetCount")), "신청인원": num(r.get("appliedCount"))} for r in done]
    try:
        res = gc.generate_json(PROMPT + json.dumps(brief, ensure_ascii=False), temperature=0.4)
        items = res.get("items") if isinstance(res, dict) else res
        outd = {}
        for r, it in zip(done, items or []):
            if isinstance(it, dict):
                outd[r.get("courseName", "")] = {"summary": str(it.get("summary", ""))[:300], "report": str(it.get("report", ""))[:1500],
                                                 "next": str(it.get("next", ""))[:200], "org": r.get("org", ""), "end": r.get("trainEnd", "")}
        out.write_text(json.dumps({"date": today.isoformat(), "items": outd}, ensure_ascii=False), encoding="utf-8")
        print(f"결과보고 초안: {len(outd)}건")
    except Exception as e:
        print(f"[경고] 결과보고 초안 실패: {gc.mask(e)[:200]}", file=sys.stderr)


if __name__ == "__main__":
    main()
