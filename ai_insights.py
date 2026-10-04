#!/usr/bin/env python3
"""
Gemini로 '오늘의 AI 브리핑'(나라장터 종합 탭 AI 인사이트 상단)을 만든다.

- 입력: combine_dashboard.py 가 남긴 live/_weekly_inputs.json(입찰공고·조기경보·2027 추천·경쟁사 신규과정·계약 점유)
  + 최신 조간 브리핑 헤드라인. 모두 공개 데이터이고 자사 영업 파이프라인은 넣지 않는다.
- 키: GitHub Secret GEMINI_API_KEY. 배포 과정에서만 호출하고 브라우저에는 결과(JSON)만 싣는다.
- 모델: 사용 가능한 모델 목록에서 최신 flash 계열을 고른다(모델명이 바뀌어도 동작하도록).
  python ai_insights.py [out_json]
"""
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import gemini_client as gc

HERE = Path(__file__).parent
STATUS = HERE / "history" / "ai_insights_status.json"


def compact_inputs():
    inp = json.loads((HERE / "live" / "_weekly_inputs.json").read_text(encoding="utf-8"))
    today = date.today()
    wk = (today - timedelta(days=7)).isoformat()
    bids = sorted([b for b in inp.get("bids", []) if (b.get("공고일") or "") >= wk],
                  key=lambda b: -(b.get("예산") or 0))[:25]
    due = sorted([b for b in inp.get("bids", []) if today.isoformat() <= (b.get("마감일") or "") <= (today + timedelta(days=10)).isoformat()],
                 key=lambda b: b.get("마감일"))[:15]
    brief = sorted((HERE / "briefings").glob("????-??-??.json"))
    head = []
    for f in brief[-3:]:
        d = json.loads(f.read_text(encoding="utf-8"))
        head.append(f"{d['date']} {re.sub('<[^>]+>', '', d.get('lead', {}).get('headline', ''))}")
    return {
        "기준일": today.isoformat(),
        "최근7일_입찰공고": [{"기관": b.get("발주기관"), "지역": b.get("지역"), "공고명": b.get("공고명"),
                          "예산": b.get("예산"), "마감": b.get("마감일")} for b in bids],
        "10일내_마감": [{"기관": b.get("발주기관"), "공고명": b.get("공고명"), "마감": b.get("마감일"), "예산": b.get("예산")} for b in due],
        "조기경보": [{"단계": e["stage"], "기관": e["o"], "사업": e["t"], "예산": e["a"], "기한": e["due"], "대응": e["ready"]}
                  for e in (inp.get("early") or {}).get("items", [])[:15]],
        "2027_추천주제": [{"주제": t["name"], "점수": t["score"], "공고수": t["n"], "증감": t.get("growth"),
                        "자사강좌": t.get("coverage", {}).get("own"), "경쟁사평균": t.get("coverage", {}).get("comp_avg")}
                       for t in inp.get("topics", [])[:5]],
        "경쟁사_신규과정_7일": [f"{r.get('company')}: {r.get('title')}" for r in inp.get("new_courses", []) if (r.get("first_seen") or "") >= wk][:10],
        "계약점유": inp.get("contracts", [])[:5],
        "최근_브리핑_헤드라인": head,
    }


PROMPT = """너는 (주)비상교육 비바샘원격교육연수원 B2G(교육청·학교 대상 교원연수) 영업 전략가다.
아래 JSON은 오늘 기준 나라장터 공고, 발주 조기 경보, 2027 연수 개발 추천, 경쟁사 동향, 조간 브리핑 헤드라인이다.
데이터에 있는 사실만 근거로, 영업·기획 담당자가 오늘 바로 할 일을 한국어로 제시하라. 데이터에 없는 수치는 만들지 마라.
반드시 아래 JSON 형식으로만 답하라:
{"summary": "오늘 상황 2문장", "actions": [{"title": "할 일(20자 이내)", "why": "근거(공고명·기관·수치 인용, 60자 이내)", "owner": "영업|기획|경영"}], "watch": ["주시할 점 1문장", "..."]}
actions는 정확히 3개, watch는 2개.
데이터:
"""


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/ai_insights.json")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("[경고] GEMINI_API_KEY 없음 - AI 브리핑 건너뜀", file=sys.stderr)
        return
    status = {"date": date.today().isoformat()}
    try:
        data = compact_inputs()
        model = gc.model()
        status["model"] = model
        ai = gc.generate_json(PROMPT + json.dumps(data, ensure_ascii=False))
        ai = {"summary": str(ai.get("summary", ""))[:400],
              "actions": [{k: str(a.get(k, ""))[:160] for k in ("title", "why", "owner")} for a in ai.get("actions", [])[:3]],
              "watch": [str(w)[:200] for w in ai.get("watch", [])[:3]],
              "model": model.split("/")[-1], "date": date.today().isoformat()}
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(ai, ensure_ascii=False), encoding="utf-8")
        status["ok"] = True
        print(f"AI 브리핑 생성: {model}")
    except Exception as e:
        status["ok"] = False
        status["error"] = gc.mask(e)[:300]
        print(f"[경고] AI 브리핑 실패: {status['error']}", file=sys.stderr)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
