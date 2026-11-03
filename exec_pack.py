#!/usr/bin/env python3
"""
경영 브리프 팩 - 대시보드가 매일 만든 경영 정보를 '채팅에서 읽기 좋은 Markdown' 한 장으로 묶어
비공개 저장소(vs-insight-private)의 exec_pack/ 에 저장한다(양방향 연동의 '대시보드 → 대표님' 방향).

- 입력: live/owner_pack.json(combine_dashboard.py 가 대표 전용 데이터로 남김), history/exec_story_last.json,
        history/daily_stats.jsonl, Secret MGMT_JSON(경영 실적), 비공개 저장소 weekly_data/(주간보고)
- 출력: <out>/latest.md(항상 최신) + <out>/YYYY-MM-DD.md(날짜별 보관)
- 이 파일은 공개 저장소·사이트에는 절대 쓰지 않는다. deploy.yml 이 _private/exec_pack 으로만 넘긴다.
  python exec_pack.py _private/exec_pack
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent


def _j(p, default=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _jsonl(p, n=None):
    try:
        rows = [json.loads(x) for x in (HERE / p).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []
    return rows[-n:] if n else rows


def _won(v):
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return str(v)
    return f"{v / 1e8:,.1f}억" if abs(v) >= 1e8 else f"{v / 1e4:,.0f}만"


def _today():
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


def sec_ai(owner):
    a = (owner or {}).get("ai_brief") or {}
    if not a.get("summary"):
        return []
    out = ["## 오늘의 AI 브리핑", f"_기준 {a.get('date', '-')}_", "", a["summary"], ""]
    if a.get("actions"):
        out += ["**오늘 할 일**"] + [f"- [{x.get('owner', '-')}] **{x.get('title', '')}** — {x.get('why', '')}" for x in a["actions"]] + [""]
    if a.get("watch"):
        out += ["**주시할 점**"] + [f"- {x}" for x in a["watch"]] + [""]
    return out


def sec_story():
    s = _j("history/exec_story_last.json", {}) or {}
    lab = {"market": "시장(나라장터)", "competition": "경쟁", "self": "자사", "opportunity": "기회(B2S·샘몰)"}
    rows = [(lab.get(k, k), v) for k, v in s.items() if isinstance(v, dict) and v.get("say")]
    if not rows:
        return []
    out = ["## 경영 종합 해석 (시장 → 경쟁 → 자사)", ""]
    for name, v in rows:
        out += [f"### {name}", v["say"], "", f"→ **So what:** {v.get('so', '')}", ""]
    return out


def sec_metrics(owner):
    e = (owner or {}).get("exec") or {}
    if not e:
        return []
    m, c, p, r = e.get("market") or {}, e.get("contracts") or {}, e.get("pipeline") or {}, e.get("rfp") or {}
    out = ["## 핵심 지표", "", "| 구분 | 지표 | 값 |", "|---|---|---|"]
    out += [f"| 시장 | 진행 중 입찰공고 / 사전규격 / 낙찰 | {m.get('open_bids', 0)} / {m.get('prespec', 0)} / {m.get('wins', 0)}건 |",
            f"| 시장 | 연수 입찰 12개월 | {m.get('bids_12m', 0)}건 |",
            f"| 시장 | 조기 경보 | {m.get('early', 0)}건 |"]
    if c.get("total_n"):
        out.append(f"| 경쟁 | 계약 전체(수의 비중) | {c['total_n']}건 · {_won(c.get('total_amt'))} (수의 {c.get('sui_share')}%) |")
        if c.get("own"):
            o = c["own"]
            out.append(f"| 자사 | 계약 점유율 | {o.get('share')}% · {o.get('n')}건 · {_won(o.get('amount'))} (평균 {_won(o.get('avg'))}) |")
        for x in c.get("rivals") or []:
            out.append(f"| 경쟁 | {x['name']} | 점유 {x.get('share')}% · {x.get('n')}건 · {_won(x.get('amount'))} (평균 {_won(x.get('avg'))}) |")
    if p.get("n"):
        st = ", ".join(f"{k} {v}" for k, v in (p.get("status") or {}).items())
        out.append(f"| 자사 | 영업 파이프라인 | {p['n']}건 · 목표 {_won(p.get('target_sum'))} ({st}) |")
    if r.get("n"):
        out.append(f"| 자사 | 제안요청서 AI 적합 판정 | {r['n']}건 중 " + ", ".join(f"{k} {v}" for k, v in (r.get("fit") or {}).items() if k) + " |")
    b = e.get("b2s") or {}
    if b:
        out.append(f"| B2S | 학교 시장 | 학교 {b.get('schools', 0):,} · 교사 {b.get('teachers', 0):,} · 미진출 큰 지역 {', '.join(b.get('white_regions') or [])} |")
    tops = m.get("top_topics") or []
    if tops:
        out += ["", "**수요 상위 연수 주제 (12개월)**", "", "| 주제 | 건수 | 성장률 | 자사 강좌 | 경쟁사 평균 |", "|---|---|---|---|---|"]
        out += [f"| {t.get('name')} | {t.get('n')} | {t.get('growth')}% | {t.get('own')} | {t.get('comp')} |" for t in tops]
    return out + [""]


def sec_daily():
    rows = _jsonl("history/daily_stats.jsonl", 14)
    if not rows:
        return []
    out = ["## 일일 지표 추이 (최근 14일)", "", "| 날짜 | 연수 관련 공고 | 공고 금액 합 | 자사 파이프라인 | 목표액 | 1위 경쟁사 |", "|---|---|---|---|---|---|"]
    out += [f"| {r.get('date')} | {r.get('ai_rows_count', '-')} | {_won(r.get('ai_rows_amount_sum'))} | {r.get('own_pipeline_total', '-')} | "
            f"{_won(r.get('own_pipeline_target'))} | {r.get('top_competitor', '-')} {r.get('top_competitor_amount', '')} |" for r in rows]
    return out + [""]


def sec_comp(owner):
    c = (owner or {}).get("comp") or {}
    if not c:
        return []
    out = [f"## 경쟁사 변화 감지 (최근 {c.get('days', 30)}일 {c.get('total', 0)}건, 이번 주 {c.get('week', 0)}건)", ""]
    if c.get("by_co"):
        out.append("- 회사별: " + ", ".join(f"{k} {v}" for k, v in c["by_co"].items()))
    for s in c.get("signals") or []:
        out.append(f"- **[{s.get('lv')}] {s.get('t')}** → {s.get('do')}")
    items = (c.get("items") or [])[:15]
    if items:
        out += ["", "| 날짜 | 회사 | 유형 | 내용 | 비고 |", "|---|---|---|---|---|"]
        out += [f"| {x.get('d')} | {x.get('co')} | {x.get('type')} | {str(x.get('title', '')).replace('|', '/')} | {str(x.get('note', '')).replace('|', '/')} |" for x in items]
    return out + [""]


def sec_mgmt():
    try:
        M = __import__("mgmt_owner").load()
    except Exception:
        M = None
    if not M:
        return []
    out = [f"## 경영 실적 (기준 {M.get('asof', '-')}, 단위 억 원)", "",
           "| 연도 | 총매출 | 개인·학교(B2C·B2S) | 교육청 단체 | 위탁 용역 | B2G 비중 |", "|---|---|---|---|---|---|"]
    for r in M.get("years") or []:
        tot = r.get("tot") or 0
        g = ((r.get("b2s") or 0) + (r.get("b2g") or 0)) / tot * 100 if tot else 0
        out.append(f"| {r.get('y')}{'E' if r.get('y') == 2026 else ''} | {tot:,.1f} | {r.get('b2c', 0):,.1f} | {r.get('b2s', 0):,.1f} | {r.get('b2g', 0):,.1f} | {g:.0f}% |")
    t = M.get("target") or {}
    if t:
        out += ["", f"- 목표 {t.get('y')}: B2G {t.get('b2g')} : B2C+B2S {t.get('b2cs')}",
                "- B2G = 교육청 단체 + 위탁 용역 (2027 경영계획 공식 기준)"]
    return out + [""]


def sec_weekly():
    try:
        ow = __import__("owner_weekly")
        weeks = ow.load_weeks()
        if not weeks:
            return []
        tr, _ = ow.project_trend(weeks)
        return ["## 콘텐츠Company 주간보고", "", "```", ow.brief_text(weeks, tr, ow.flags(tr, weeks)), "```", ""]
    except Exception as e:
        print(f"[경고] 주간보고 요약 실패: {type(e).__name__}")
        return []


def sec_schedule():
    try:
        return __import__("owner_schedule").pack_md()
    except Exception as e:
        print(f"[경고] 내 일정 요약 실패: {type(e).__name__}")
        return []


def build():
    owner = _j("live/owner_pack.json", {}) or {}
    today = _today()
    parts = [sec_ai(owner), sec_story(), sec_metrics(owner), sec_daily(), sec_comp(owner), sec_mgmt(), sec_weekly(), sec_schedule()]
    body = [x for p in parts for x in p]
    head = [f"# 경영 브리프 팩 — {today.isoformat()}", "",
            "> 비바샘원격교육연수원 대표 전용 · 대시보드(vs-insight.pages.dev)가 매일 06시에 자동 생성 · 외부 공유 금지",
            "> 채팅 활용 예: \"이 파일 기준으로 경영회의 1장 요약\", \"B2G 비중 추이로 2027 전략 옵션 3개\"", ""]
    if not body:
        body = ["_오늘은 수집된 경영 데이터가 없습니다(수집 실패 또는 시크릿 미설정)._"]
    return "\n".join(head + body) + "\n"


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "_private/exec_pack")
    md = build()
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.md").write_text(md, encoding="utf-8")
    (out / f"{_today().isoformat()}.md").write_text(md, encoding="utf-8")
    print(f"경영 브리프 팩 {len(md):,}자 → {out}/latest.md")
