#!/usr/bin/env python3
"""
제안서 초안(버튼 실행 전용) - proposal_draft.yml(workflow_dispatch)에서만 돈다. 정기 배포에서는 실행하지 않는다.

  python proposal_draft.py <공고번호 또는 공고명 일부> <출력 폴더> [--ai]

  - 공고: 제안요청서 AI 분석(history/rfp_analysis.jsonl) → 없으면 연수 입찰 누적(history/training_bids.jsonl)
  - 참여 판단: bid_fit(자격·승부처) + 참여 권장 점수(경쟁 강도·자사 이력·강사 공급·작년 수주사)
  - 강사 구성: 강사풀 암호문(static_data/pool_people.enc.json)을 STRATEGY_KEY 로 풀어 공고 조건에 맞는 상위 5명(연락처 없음)
  - 수행 실적: 자사 계약(history/competitor_contracts.jsonl 의 비바샘 건) 최근 10건
  - 연계 단체: 교사단체 공개 집계(static_data/teacher_groups.json)
  --ai 를 준 경우에만 Gemini 로 '추진 전략' 문단을 다듬는다(그 외 AI 호출 없음 = 비용 없음).
출력은 비공개 저장소 proposals/ 에만 저장한다(강사 실명 포함).
"""
import json
import math
import os
import re
import sys
from datetime import date
from pathlib import Path

import bid_fit

HERE = Path(__file__).parent
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
SUBJ = ["수학", "영어", "과학", "국어", "사회", "정보", "미술", "음악", "체육", "특수", "진로", "기술", "가정", "역사", "상담", "한문"]


def _jsonl(p):
    p = HERE / p
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def find_bid(q):
    q = q.strip()
    no = q.split("-")[0]
    for src in ("history/rfp_analysis.jsonl", "history/training_bids.jsonl"):
        rows = _jsonl(src)[::-1]
        hit = next((r for r in rows if (r.get("k") or "").startswith(no)), None) if re.match(r"^R\d", no) else None
        hit = hit or next((r for r in rows if q and q in (r.get("t") or "")), None)
        if hit:
            if src.startswith("history/training") and not hit.get("ai"):  # 분석본이 따로 있으면 그쪽을 쓴다
                k = (hit.get("k") or "").split("-")[0]
                hit = next((r for r in _jsonl("history/rfp_analysis.jsonl")[::-1] if (r.get("k") or "").startswith(k)), hit)
            return hit
    return None


def parse(t):
    lv = [x for x, rx in (("초", r"초등|초교|유초"), ("중", r"중등|중학"), ("고", r"고등|고교")) if re.search(rx, t)]
    if "중등" in t and "고" not in lv:
        lv.append("고")
    return {"lv": lv, "subj": [s for s in SUBJ if s in t],
            "ai": bool(re.search(r"AI|인공지능|디지털|에듀테크|코딩|SW|소프트웨어|데이터|생성형", t, re.I)),
            "admin": bool(re.search(r"행정|직원|공무직|교육공무원|실무원|주무관", t))}


def match(people, bid, k=5):
    a = bid.get("ai") or {}
    q = parse(" ".join(str(x or "") for x in (bid.get("t"), bid.get("o"), a.get("target"), a.get("course"))))
    reg = bid.get("r")
    out = []
    for name, aff, tier, lvs, subs, sd, total, main, ai_f, y26 in people.get("all", []):
        s, why = 0, []
        if reg in sd:
            s += 30; why.append("지역")
        elif "*" in sd:
            s += 10; why.append("전국")
        if q["lv"]:
            if any(l in lvs for l in q["lv"]):
                s += 20; why.append("학교급")
            else:
                s -= 10
        if q["subj"]:
            if any(y in x for x in subs for y in q["subj"]):
                s += 40; why.append("과목")
            else:
                s -= 20
        if q["ai"] and (ai_f or any(re.search(r"정보|인공지능", x) for x in subs)):
            s += 20; why.append("AI 연수 경험")
        adm = any("행정" in x for x in subs)
        if q["admin"]:
            s += 30 if adm else -15
        elif adm and len(subs) == 1:
            s -= 25
        s += min(15, total / 3) + (10 if tier == "핵심강사" else 5 if tier == "활동강사" else 0) + min(5, y26 / 4)
        out.append({"name": name, "aff": aff, "tier": tier, "lv": lvs, "subj": subs, "sido": sd, "total": total, "main": main,
                    "score": round(s), "why": why})
    return sorted(out, key=lambda x: -x["score"])[:k]


def pool():
    key = os.environ.get("STRATEGY_KEY", "")
    p = HERE / "static_data" / "pool_people.enc.json"
    if not key or not p.exists():
        return None
    import strategy_crypto
    try:
        return strategy_crypto.decrypt(json.loads(p.read_text(encoding="utf-8")), key)
    except Exception:
        return None


def ai_strategy(bid, a, go, inst):
    import gemini_client
    prompt = (f"비바샘원격교육연수원이 아래 공공 교원연수 입찰에 낼 제안서의 '추진 전략' 부분을 한국어 개조식 6~8줄로 써라. "
              f"공고·분석·자사 근거에 있는 사실만 쓰고 없는 수치·실적은 만들지 마라.\n공고: {bid.get('t')} / {bid.get('o')} / 예산 {bid.get('a')}\n"
              f"요구사항: {a.get('requirements')}\n평가: {a.get('evaluation')}\n제안 포인트(분석): {a.get('pitch')}\n"
              f"참여 판단: {go.get('label')} {go.get('reasons')}\n강사 후보 조건: {[i['why'] for i in inst]}")
    try:
        return gemini_client.generate_json(prompt, as_text=True, temperature=0.4)
    except Exception as e:
        return f"(AI 다듬기 실패: {type(e).__name__} - 아래 골격으로 작성)"


def build(q, use_ai=False):
    bid = find_bid(q)
    if not bid:
        return None, f"공고를 찾지 못했습니다: {q}"
    a = bid.get("ai") or {}
    fit = bid_fit.judge(a) if a else None
    go = bid_fit.go_score(bid, fit, bid_fit.go_context())
    P = pool()
    inst = match(P, bid) if P else []
    own = [c for c in _jsonl("history/competitor_contracts.jsonl") if "비바샘" in (c.get("competitor") or "")]
    own = sorted(own, key=lambda c: c.get("date") or "", reverse=True)[:10]
    try:
        G = json.loads((HERE / "static_data" / "teacher_groups.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        G = {}
    tp = set(__import__("training_topics").classify_topics(bid.get("t") or ""))
    groups = [g for g in (G.get("groups") or []) + (G.get("national") or []) if (g.get("sido") in (bid.get("r"), "전국", None)) and tp & set(g.get("topics") or [])][:5]
    won = lambda v: f"{v / 1e8:.1f}억 원" if (v or 0) >= 1e8 else f"{round((v or 0) / 1e4):,}만 원"
    L = [f"# 제안서 초안 — {bid.get('t')}", "",
         f"> 생성 {date.today().isoformat()} · 버튼 실행(proposal_draft) · 비공개 · 강사 실명 포함, 외부 공유 금지 · AI 다듬기 {'사용' if use_ai else '미사용'}", "",
         "## 1. 사업 개요", "",
         f"- 발주기관: {bid.get('o')} ({bid.get('r')})", f"- 공고번호: {bid.get('k')} · 공고일 {bid.get('d')}" + (f" · [공고 보기]({bid.get('u')})" if bid.get("u") else ""),
         f"- 예산: {won(bid.get('a'))}" + (f" · 기간: {a.get('period')}" if a.get("period") else "")]
    for k, lab in (("target", "대상"), ("headcount", "인원"), ("format", "운영 방식"), ("hours", "시간"), ("evaluation", "평가 방식")):
        if a.get(k):
            L.append(f"- {lab}: {a[k]}")
    if a.get("requirements"):
        L += ["", "**과업 핵심 요구사항(제안요청서 분석)**", ""] + [f"- {x}" for x in a["requirements"]]
    if a.get("qualifications"):
        L += ["", "**참가 자격·실적 요건**", ""] + [f"- {x}" for x in a["qualifications"]]
    L += ["", "## 2. 참여 판단", "", f"- 판정: **{go['label']} ({go['score']}점)** · 자격 {fit['verdict'] if fit else '분석본 없음'}",
          *[f"- {x}" for x in go["reasons"] if not x.startswith("자격 ")]]
    if fit and fit.get("reasons"):
        L += [f"- 확인 필요: {x}" for x in fit["reasons"]]
    L += ["", "## 3. 추진 전략", ""]
    if use_ai and os.environ.get("GEMINI_API_KEY"):
        L += [ai_strategy(bid, a, go, inst), ""]
    L += ["**골격(작성자가 채움)**", "", *[f"- {x}" for x in (a.get("pitch") or [])],
          "- 비바샘 교과서·교사몰 자료와 연계한 현장 적용형 과정(차시별 수업 적용 과제)",
          "- 지역 교사 연구회·현장 교사 강사진으로 지역화(아래 4·6장 근거)",
          "- 이수율·만족도 관리: 원격/집합 혼합 시 출결·과제 관리 방식 명시", ""]
    L += ["## 4. 강사 구성(후보, 공고 조건 매칭 상위 5명 — 섭외 확인 전)", ""]
    if inst:
        L += ["| 강사 | 소속 | 등급 | 학교급·과목 | 활동 권역 | 강의 실적 | 맞는 조건 |", "|---|---|---|---|---|---|---|"]
        L += [f"| {i['name']} | {i['aff']} | {i['tier']} | {i['lv']} / {'·'.join(i['subj'])} | {'·'.join(i['sido']).replace('*', '전국')} | {i['total']}회(주강사 {i['main']}) | {' · '.join(i['why'])} |" for i in inst]
        L += ["", "_연락처는 강사풀에서 확인. 강사 동의 전에는 제안서에 실명 기재 금지._"]
    else:
        L.append("_강사풀 복호화 키(STRATEGY_KEY)가 없어 후보를 넣지 못했습니다._")
    L += ["", "## 5. 수행 실적(자사 계약 최근 10건)", ""]
    L += [f"- {c.get('date')} · {c.get('org')} · {c.get('course')} · {won(c.get('amount'))} ({c.get('method', '')})" for c in own] or ["- (누적 계약 기록 없음)"]
    L += ["", "## 6. 연계 가능 교사 단체(공개 조사)", ""]
    L += [f"- {g['name']}" + (f" ({g.get('sido')})" if g.get("sido") else "") + (f" — {g.get('theme') or g.get('focus') or ''}") for g in groups] or ["- (주제·지역에 맞는 단체 없음)"]
    if a.get("deliverables"):
        L += ["", "## 7. 산출물", ""] + [f"- {x}" for x in a["deliverables"]]
    L += ["", "## 8. 작성 체크리스트", "", "- [ ] 참가 자격(업종·지역·실적) 증빙 확인", "- [ ] 평가표 항목별 목차 맞춤", "- [ ] 강사 섭외 동의·이력서 확보",
          "- [ ] 예산 산출 내역(인건비·운영비) 검토", "- [ ] 유사 실적 증명서 발급", ""]
    return "\n".join(L), bid.get("k") or "draft"


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    use_ai = "--ai" in sys.argv
    if len(args) < 2:
        print(__doc__)
        return 1
    md, key = build(args[0], use_ai)
    if md is None:
        print(key)
        return 1
    out = Path(args[1])
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{date.today().isoformat()}_{re.sub(r'[^A-Za-z0-9-]', '', key)[:24] or 'draft'}.md"
    f.write_text(md, encoding="utf-8")
    print(f"제안서 초안 저장: {f} ({len(md):,}자)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
