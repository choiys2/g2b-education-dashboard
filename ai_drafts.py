#!/usr/bin/env python3
"""
2027 연수 개발 추천 상위 주제의 '기획서 초안'을 Gemini로 고도화한다.

- 입력: live/_weekly_inputs.json 의 topics(공고 표본·정책 근거·경쟁 과정·가격) + history/rfp_analysis.jsonl
  (같은 주제 공고의 제안요청서 요구사항). 모두 공개 데이터.
- 출력: live/ai_drafts.json {topic_id: {md, date, model}}. 대시보드 기획서 대화상자에서 'AI 초안'으로 보인다.
- 무료 등급 절약: 주제별 결과를 history/ai_drafts_cache.json 에 보관하고 7일이 지났거나 공고 수가 바뀐 주제만 새로 만든다.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import gemini_client as gc
import training_topics as tt

HERE = Path(__file__).parent
CACHE = HERE / "history" / "ai_drafts_cache.json"
TOP_N = 6

PROMPT = """너는 (주)비상교육 비바샘원격교육연수원의 교원연수 과정 기획자다.
아래 JSON(최근 12개월 교원 연수 입찰공고 분석, 2027 정책 근거, 경쟁사 유사 과정과 가격, 실제 제안요청서 요구사항)만 근거로
'{name}' 주제의 2027년 신규 과정 기획서 초안을 한국어 마크다운으로 써라. 데이터에 없는 수치·기관명은 만들지 마라.
구성(제목 그대로):
# [AI 기획서 초안] 과정명
- 대상 / 운영 형태 / 학점·차시
## 1. 개발 배경(공고·정책 근거 3줄 이내, 수치 인용)
## 2. 학습 목표(3개)
## 3. 차시 구성(표: 차시 | 주제 | 학습 활동 | 산출물, 15차시)
## 4. 경쟁 과정 대비 차별화(3개, 경쟁 과정명 인용)
## 5. B2G 제안 대응(제안요청서 요구사항과 매칭되는 포인트, 없으면 공고명 기반)
## 6. 가격·판매 채널
## 7. 성과 지표
데이터:
"""


def compact(t, rfps):
    c = t.get("coverage", {})
    return {
        "주제": t["name"], "공고수": t["n"], "증감": t.get("growth"), "예산합계": t.get("amount"),
        "학교급": t.get("levels"), "운영형태": t.get("modes"), "추천형태": t.get("format"), "형태근거": t.get("format_reason"),
        "정책근거": t.get("policy_note"), "채널": t.get("channel"),
        "공고표본": [f"{s['d']} {s['o']} · {s['t']}" for s in t.get("samples", [])[:6]],
        "기본과정안": [{"학교급": p["level"], "과정": p["title"], "내용": p["content"]} for p in t.get("proposals", [])],
        "자사강좌수": c.get("own"), "경쟁사평균": c.get("comp_avg"), "15차시환산_중앙가": c.get("price15_median"),
        "경쟁과정": c.get("comp_examples", []),
        "제안요청서_요구사항": rfps[:4],
    }


def rfps_by_topic():
    out = {}
    p = HERE / "history" / "rfp_analysis.jsonl"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not r.get("ai"):
            continue
        a = r["ai"]
        brief = {"공고": r["t"], "기관": r["o"], "요구사항": a.get("requirements", []), "평가": a.get("evaluation", ""),
                 "형태": a.get("format", ""), "차시": a.get("hours", "")}
        for tid in tt.classify_topics(r["t"]):
            out.setdefault(tid, []).append(brief)
    return out


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "live/ai_drafts.json")
    if not gc.key():
        print("[경고] GEMINI_API_KEY 없음 - AI 기획서 초안 건너뜀", file=sys.stderr)
        return
    topics = json.loads((HERE / "live" / "_weekly_inputs.json").read_text(encoding="utf-8")).get("topics", [])
    topics = [t for t in topics if t.get("n")][:TOP_N]
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    rf = rfps_by_topic()
    stale = (date.today() - timedelta(days=7)).isoformat()
    made = 0
    for t in topics:
        old = cache.get(t["id"])
        if old and old.get("date", "") > stale and old.get("n") == t["n"] and old.get("rfp") == len(rf.get(t["id"], [])):
            continue
        try:
            md = gc.generate_json(PROMPT.replace("{name}", t["name"]) + json.dumps(compact(t, rf.get(t["id"], [])), ensure_ascii=False),
                                  as_text=True)
        except Exception as e:
            print(f"[경고] {t['name']} 초안 실패: {gc.mask(e)[:160]}", file=sys.stderr)
            continue
        cache[t["id"]] = {"md": md.strip()[:12000], "date": date.today().isoformat(), "n": t["n"],
                          "rfp": len(rf.get(t["id"], [])), "model": gc.model().split("/")[-1]}
        made += 1
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    keep = {t["id"] for t in topics}
    out.write_text(json.dumps({k: v for k, v in cache.items() if k in keep}, ensure_ascii=False), encoding="utf-8")
    print(f"AI 기획서 초안: 새로 {made}건, 게시 {len(keep & set(cache))}건")


if __name__ == "__main__":
    main()
