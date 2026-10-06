#!/usr/bin/env python3
"""
경영 종합 '지표 스토리라인' 해석 - 시장 → 경쟁 → 자사 → 기회 4단계 수치를 Gemini가 읽고 단계별 해석을 쓴다.

- 입력: live/_exec_inputs.json (combine_dashboard.py 가 exec_summary.build 결과를 저장). 공개·집계 수치만.
- 출력: live/exec_story.json, 실패하면 history/exec_story_last.json(마지막 성공본)을 날짜와 함께 쓴다.
- 하루 1회 호출(무료 한도 영향 작음).
"""
import json
import sys
from datetime import date
from pathlib import Path

import gemini_client as gc

HERE = Path(__file__).parent
LAST = HERE / "history" / "exec_story_last.json"

PROMPT = """너는 (주)비상교육 비바샘원격교육연수원 사업총괄의 전략 참모다. 아래 JSON은 오늘 기준 교원연수 시장·경쟁·자사 지표다.
2027 목표: B2G 매출 비중 80%→40%, B2C+B2S 60%, 샘몰 2026 H2 출시. 데이터에 있는 수치만 인용하고, 없는 수치는 만들지 마라.
시장(market)·경쟁(competition)·자사(self)·기회(opportunity) 4단계로 '이 숫자가 말하는 것'을 한국어로 써라. 반드시 아래 JSON 형식:
{"market": {"say": "해석 2문장(수치 인용)", "so": "그래서 해야 할 일 1문장"},
 "competition": {"say": "...", "so": "..."}, "self": {"say": "...", "so": "..."}, "opportunity": {"say": "...", "so": "..."},
 "bottom_line": "경영진에게 한 줄 결론(50자 이내)"}
데이터:
"""


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/exec_story.json")
    try:
        data = json.loads((HERE / "live" / "_exec_inputs.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("[경고] _exec_inputs.json 없음 - 스토리라인 건너뜀", file=sys.stderr)
        return
    data.pop("sources", None)
    res = None
    if gc.key():
        try:
            r = gc.generate_json(PROMPT + json.dumps(data, ensure_ascii=False))
            res = {k: {"say": str((r.get(k) or {}).get("say", ""))[:300], "so": str((r.get(k) or {}).get("so", ""))[:160]}
                   for k in ("market", "competition", "self", "opportunity")}
            res["bottom_line"] = str(r.get("bottom_line", ""))[:120]
            res["date"] = date.today().isoformat()
            res["model"] = gc.model().split("/")[-1]
            LAST.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[경고] 스토리라인 해석 실패: {gc.mask(e)[:200]}", file=sys.stderr)
    if res is None and LAST.exists():
        res = json.loads(LAST.read_text(encoding="utf-8"))
        res["stale"] = True
    if res:
        out.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(f"스토리라인: {res.get('date')} {'(이전본)' if res.get('stale') else ''}")


if __name__ == "__main__":
    main()
