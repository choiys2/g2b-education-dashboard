#!/usr/bin/env python3
"""
live/*.json(오늘자 파이프라인 산출물) -> briefings/YYYY-MM-DD.json

build_news_briefing.py가 그대로 읽는 신문 지면 스키마를, 이미 계산된 값들만
재구성해서 채운다(LLM 미사용 - 대시보드의 다른 "AI 인사이트"들과 같은 원칙).
경제 뉴스가 아니라 비바샘 B2G 경쟁 동향(나라장터·경쟁사·자사 파이프라인)이
그날의 "지면"이 된다.

데이터가 부실한 날(핵심 파일이 없거나 기사 하나도 못 만든 날)은 아무것도
쓰지 않고 조용히 종료한다 - 빈 지면을 발행하는 것보다 안 만드는 게 낫다.
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


def load(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_history_deltas(path="history/daily_stats.jsonl"):
    p = Path(path)
    if not p.exists():
        return None, None
    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return None, None
    today_row = json.loads(lines[-1])
    prev_row = json.loads(lines[-2]) if len(lines) >= 2 else None
    return today_row, prev_row


def idx(label, today_v, prev_v, unit=""):
    if today_v is None:
        return None
    if prev_v is None:
        return {"label": label, "value": f"{today_v:,}{unit}", "delta": "-", "dir": "flat"}
    d = today_v - prev_v
    dir_ = "up" if d > 0 else ("down" if d < 0 else "flat")
    sign = "+" if d > 0 else ""
    return {"label": label, "value": f"{today_v:,}{unit}", "delta": f"{sign}{d:,}{unit}", "dir": dir_}


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "briefings")
    today = date.today()
    weekday = ["월", "화", "수", "목", "금", "토", "일"][today.weekday()]

    full_live = load("live/full_live.json")
    g2b_full = load("live/g2b_full_export.json")
    comp_g2b = load("live/competitor_g2b_export.json")
    comp_content = load("live/competitor_content_export.json")
    comp_finance = load("live/competitor_finance_export.json")
    own_pipe = load("live/own_pipeline_export.json")

    if not g2b_full:
        print("g2b_full_export.json 없음 - 브리핑 생성 건너뜀", file=sys.stderr)
        return 0

    today_row, prev_row = load_history_deltas()

    # ---------- 지수 스트립 ----------
    indices = []
    if today_row:
        indices.append(idx("AI·에듀테크 발주", today_row.get("ai_rows_count"), (prev_row or {}).get("ai_rows_count"), "건"))
        indices.append(idx("나라장터 상세건수", today_row.get("g2b_total_detail"), (prev_row or {}).get("g2b_total_detail"), "건"))
        indices.append(idx("자사 파이프라인", today_row.get("own_pipeline_total"), (prev_row or {}).get("own_pipeline_total"), "건"))
    if comp_g2b:
        indices.append({"label": "경쟁사 누적 낙찰", "value": f"{comp_g2b.get('totals', {}).get('deal_count', 0):,}건", "delta": "누적", "dir": "flat"})
    indices = [i for i in indices if i]

    # ---------- 경쟁사 재무 이상치(전년 대비 ±30%) ----------
    finance_anomalies = []
    if comp_finance:
        for name, c in (comp_finance.get("companies") or {}).items():
            hist = [h for h in (c.get("history") or []) if h.get("sales") is not None or h.get("operating_profit") is not None]
            if len(hist) < 2:
                continue
            prev, cur = hist[-2], hist[-1]
            for metric, label in [("sales", "매출"), ("operating_profit", "영업이익"), ("net_profit", "순이익")]:
                p, v = prev.get(metric), cur.get(metric)
                if p in (None, 0) or v is None:
                    continue
                change = (v - p) / abs(p)
                if abs(change) >= 0.30:
                    finance_anomalies.append({
                        "name": name, "year": cur["biz_year"], "metric": label,
                        "change": change, "dir": "up" if change > 0 else "down",
                    })

    # ---------- 놓친 기회(당일 신규 - 최근 3일 이내 낙찰) ----------
    recent_missed = []
    if g2b_full:
        cutoff = (today - timedelta(days=3)).isoformat()
        known_orgs = {r.get("기관", "").strip() for r in (own_pipe or {}).get("records", []) if r.get("기관")}
        for r in g2b_full.get("detail", []):
            if r.get("구분") != "낙찰정보" or not r.get("낙찰업체"):
                continue
            if (r.get("날짜") or "") < cutoff:
                continue
            # AI_ROWS 필터와 무관하게 g2b_full.detail 전체에서 보므로, 우리 관심사(교육청/연수원) 위주로 자연히 걸러짐
            if r.get("기관", "").strip() not in known_orgs:
                recent_missed.append(r)

    # ---------- 오늘의 톱기사 선정 (우선순위: 재무 이상치 > 대형 신규 낙찰 > 파이프라인 요약) ----------
    lead = None
    if finance_anomalies:
        top = max(finance_anomalies, key=lambda a: abs(a["change"]))
        verb = "급증" if top["dir"] == "up" else "급감"
        lead = {
            "kicker": "경쟁사 재무 동향",
            "headline": f'{top["name"]} {top["year"]}년 {top["metric"]} 전년 대비 {verb}',
            "sub": f'({top["change"]*100:+.0f}%) — 금융위원회 공시 재무정보 기준',
            "lede": f'{top["name"]}의 {top["year"]}년 결산 {top["metric"]}이 전년 대비 {top["change"]*100:+.0f}% {verb}한 것으로 확인됐다. '
                    f'재무 프로파일 탭에서 부채비율·낙찰률과 함께 맥락을 확인할 수 있다.',
            "facts": [{"label": "회사", "text": top["name"]}, {"label": "지표", "text": f'{top["metric"]} {top["change"]*100:+.0f}%'}],
        }
    elif recent_missed:
        big = max(recent_missed, key=lambda r: r.get("예산") or 0)
        lead = {
            "kicker": "놓친 기회",
            "headline": f'{big.get("기관","")} 최근 낙찰 — 자사 파이프라인 기록 없음',
            "sub": big.get("공고명", "")[:60],
            "lede": f'{big.get("기관","")}이(가) 최근 3일 내 "{big.get("공고명","")}" 건을 {big.get("낙찰업체","")}에 낙찰했다. '
                    f'자사 파이프라인에는 이 기관과의 접점 기록이 없어 확인이 필요하다.',
            "facts": [{"label": "발주기관", "text": big.get("기관", "")}, {"label": "낙찰업체", "text": big.get("낙찰업체", "")}],
        }
    elif today_row:
        lead = {
            "kicker": "오늘의 파이프라인",
            "headline": f'AI·에듀테크 발주 {today_row.get("ai_rows_count",0)}건 · 자사 파이프라인 {today_row.get("own_pipeline_total",0)}건 진행 중',
            "sub": "특이 신호 없음 — 평시 지표",
            "lede": "오늘은 재무 이상치나 놓친 기회 신호가 감지되지 않았다. 아래 지면에서 평시 지표를 확인할 수 있다.",
            "facts": [],
        }

    if lead is None:
        print("브리핑 리드 기사를 구성할 데이터가 없음 - 건너뜀", file=sys.stderr)
        return 0

    # ---------- 섹션: 나라장터 ----------
    g2b_items = []
    for insight in (g2b_full.get("insights") or [])[:4]:
        g2b_items.append({"title": insight, "body": "규칙 기반 자동 요약 · 나라장터 종합 탭 참고.", "tags": ["나라장터"]})
    if g2b_items:
        sections_g2b = {"id": "g2b", "name": "나라장터", "tone": "slate", "items": g2b_items}
    else:
        sections_g2b = None

    # ---------- 섹션: 경쟁사 ----------
    comp_items = []
    for a in finance_anomalies[:4]:
        verb = "급증" if a["dir"] == "up" else "급감"
        comp_items.append({
            "title": f'{a["name"]} {a["year"]}년 {a["metric"]} {verb}({a["change"]*100:+.0f}%)',
            "body": "금융위원회 공시 재무정보 기준. 경쟁사 연수 탭의 재무 프로파일에서 5개년 추이를 확인하세요.",
            "tags": ["재무"],
        })
    if comp_content:
        for name, c in (comp_content.get("companies") or {}).items():
            n = c.get("event_count") or 0
            if n:
                comp_items.append({
                    "title": f'{name} 진행중 이벤트 {n}건',
                    "body": "비로그인 공개 화면 기준 스냅샷. 경쟁사 연수 탭에서 개별 이벤트를 확인할 수 있습니다.",
                    "tags": ["마케팅"],
                })
    if comp_items:
        sections_comp = {"id": "competitor", "name": "경쟁사", "tone": "carmine", "items": comp_items}
    else:
        sections_comp = None

    # ---------- 섹션: 파이프라인 ----------
    pipe_items = []
    if own_pipe:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            import beta_features as bf
            momentum = bf.pipeline_momentum(own_pipe.get("records", []))
            for m in momentum[:4]:
                if m["단계"] != "임박":
                    continue
                pipe_items.append({
                    "title": f'{m.get("org","")} — {m.get("courseName","")[:30]}',
                    "body": f'모집 마감 {m.get("recruitEnd","-")} · 모멘텀 스코어 {m["모멘텀점수"]} · 담당 {m.get("salesRep") or "-"}',
                    "tags": ["임박"], "priority": True,
                })
        except Exception as e:
            print(f"[경고] 파이프라인 모멘텀 계산 실패: {e}", file=sys.stderr)
    if pipe_items:
        sections_pipe = {"id": "pipeline", "name": "파이프라인", "tone": "forest", "items": pipe_items}
    else:
        sections_pipe = None

    sections = [s for s in (sections_g2b, sections_comp, sections_pipe) if s]

    # ---------- 시사점 ----------
    implications = []
    for a in finance_anomalies[:2]:
        verb = "저가 수주 방어 여부" if a["dir"] == "down" else "공격적 확장 여부"
        implications.append({
            "news": f'{a["name"]} {a["metric"]} {a["change"]*100:+.0f}%',
            "impact": f'{verb}를 낙찰률·신규 채용 동향과 함께 살펴볼 만합니다.',
        })
    for r in recent_missed[:2]:
        implications.append({
            "news": f'{r.get("기관","")} 낙찰 → {r.get("낙찰업체","")}',
            "impact": "해당 기관과의 접점이 파이프라인에 없다면, 다음 사업연도 영업 대상으로 등록을 검토하세요.",
        })

    data = {
        "date": today.isoformat(),
        "weekday": weekday,
        "indices": indices,
        "lead": lead,
        "sections": sections,
        "implications": implications,
        "sources": "나라장터 공공데이터포털 · 금융위원회 공시 재무정보 · 자사 영업 파이프라인 · 경쟁사 홈페이지 공개 화면 기준 자동 생성",
    }

    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{today.isoformat()}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out_path}: 섹션 {len(sections)}개, 재무이상치 {len(finance_anomalies)}, 놓친기회 {len(recent_missed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
