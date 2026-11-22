#!/usr/bin/env python3
"""
관리 탭 '👩‍🏫 교사 세그먼트 전략' 칸(사용자 요청 2026-11-22) — 신입·저경력·경력·고경력 × 성별·지역·연령·학교급 입체 분석과 B2C 방향.
- 사실·틀·전략: 비공개 저장소 strategy_room/teacher_segments.json (출처·기준일 포함, 수동 갱신) - 공개 저장소에는 전략 내용이 없다
- 살아 있는 근거(배포 때마다 다시 계산): 경쟁 3사 강좌 카탈로그의 세그먼트 주제별 공급량, 교사 크리에이터 상위 채널 구독자
- 결과 HTML 은 관리 탭 암호문 안에만(ADMIN_PASSWORD). 외부 텍스트는 모두 escape, 링크는 https 만.
"""
import json
import re
from collections import Counter
from html import escape as h
from pathlib import Path

HERE = Path(__file__).parent
THEMES = {
    "신규·저경력": r"신규|초임|새내기|저경력|첫 ?해",
    "교권·민원·법": r"교권|민원|아동학대|법률|소송|분쟁",
    "생활지도·학급경영": r"생활지도|학급 ?경영|학급운영|상담",
    "마음·회복": r"마음|힐링|회복|번아웃|스트레스|명상|웰빙|심리",
    "퍼스널브랜딩·크리에이터": r"브랜딩|유튜브|크리에이터|콘텐츠 제작|영상 제작|SNS|인플루언서|책 쓰기|출판|글쓰기",
    "재테크·경제": r"재테크|투자|경제|주식|부동산|연금",
    "AI·디지털": r"AI|인공지능|에듀테크|디지털|챗GPT|ChatGPT|코딩",
    "승진·자격(1정·교감)": r"1급 정교사|1정|자격연수|승진|교감|수석|관리자|리더십",
    "고경력·은퇴설계": r"은퇴|퇴직|인생 ?2막|노후|원로",
}
SEG_COL = {"new": "#10b981", "low": "#0ea5e9", "mid": "#8b5cf6", "senior": "#f59e0b"}


def _load(p, d=None):
    try:
        return json.loads((HERE / p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def supply():
    """경쟁 3사(자사 포함) 강좌 제목을 세그먼트 주제로 센다."""
    C = _load("history/competitor_course_catalog.json", {}) or {}
    titles = []
    for comp, v in (C.get("companies") or {}).items():
        for x in (v.get("courses") if isinstance(v, dict) else v) or []:
            titles.append((comp, str(x.get("title") or x.get("t") or x.get("name") or "")))
    out = {}
    for k, rx in THEMES.items():
        out[k] = Counter(c for c, t in titles if re.search(rx, t))
    return out, len(titles), C.get("captured_date")


def creators(n=8):
    Y = ((_load("history/teacher_creator_trends.json", {}) or {}).get("youtube") or {})
    ch = sorted(Y.get("channels") or [], key=lambda x: -(x.get("subs") or 0))[:n]
    return [(x.get("name") or x.get("title") or "", int(x.get("subs") or 0)) for x in ch], Y.get("captured_date")


def _a(url, t):
    return f'<a href="{h(url)}" target="_blank" rel="noopener noreferrer">{h(t)}</a>' if str(url or "").startswith("https://") else h(t)


def build(sec=None):
    D = None
    try:
        from strategy_room import _private
        d = _private()
        f = d / "strategy_room" / "teacher_segments.json" if d else None
        D = json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None
    except Exception:  # noqa: BLE001
        D = None
    if not D:
        return '<div class="cpv-wrap"><p class="cpv-note">데이터 준비 중</p></div>'
    S, total, cap = supply()
    own = "비바샘연수원"
    seg = D["segments"]
    # ① 핵심요약
    gap = sorted(((k, sum(c.values())) for k, c in S.items()), key=lambda x: x[1])
    summary = [
        f"경쟁 3사 강좌 {total:,}개 중 <b>신규·저경력 전용 {sum(S['신규·저경력'].values())}개, 은퇴·인생 2막 {sum(S['고경력·은퇴설계'].values())}개</b> — 교사 생애의 처음과 끝이 비어 있다.",
        "저연차 중도퇴직 +31%(2020→2024), 교원 49%가 자부심 하락: <b>'버티게 해 주는 연수'</b>가 B2C 1순위 수요.",
        "겸직 교원의 47%가 서울·경기, 유튜브 겸직 796명 — 공직+개인 브랜드 이중 정체성은 <b>수도권·저경력~경력</b>에서 가장 강하다.",
        "권장: <b>A 생존 키트(신입) → B 크리에이터 아카데미(저경력·경력) → D 인생 2막·강사 데뷔(고경력)</b>를 한 줄의 '평생 교사 여정'으로 묶어 신입을 고경력 강사까지 데려간다.",
    ]
    sum_html = "".join(f"<li>{x}</li>" for x in summary)
    # ② 세그먼트 카드
    mx = max(s["share_est"] for s in seg) or 1
    seg_html = "".join(
        f'<div class="ts-seg" style="--c:{SEG_COL.get(s["key"], "#64748b")}"><div class="ts-h"><b>{h(s["name"])}</b><small>{h(s["years"])} · {h(s["age"])}</small>'
        f'<span class="ts-sh"><i style="width:{s["share_est"] / mx * 100:.0f}%"></i></span><em>추정 {s["share_est"]}%</em></div>'
        f'<dl><dt>정체성</dt><dd>{h(s["identity"])}</dd><dt>고통</dt><dd>{h(s["pain"])}</dd><dt>자산</dt><dd>{h(s["assets"])}</dd>'
        f'<dt>공직×개인</dt><dd>{h(s["dual"])}</dd><dt>핵심 욕구</dt><dd><b>{h(s["need"])}</b></dd></dl></div>' for s in seg)
    # 주제 공급 대비(세그먼트 매핑)
    smax = max((sum(c.values()) for c in S.values()), default=1) or 1
    rows = ""
    for k, c in sorted(S.items(), key=lambda kv: sum(kv[1].values())):
        n = sum(c.values())
        tag = '<b style="color:#dc2626">공백</b>' if n <= 5 else ("경쟁 적음" if n <= 30 else "")
        who = " ".join(f'<span class="ts-chip" style="background:{SEG_COL[s["key"]]}">{h(s["name"])}</span>' for s in seg if k in s["theme"])
        rows += (f'<tr><td>{h(k)}</td><td>{who}</td><td><span class="ts-bar"><i style="width:{max(2, n / smax * 100):.0f}%"></i></span></td>'
                 f'<td class="num">{n}</td><td class="num">{c.get(own, 0)}</td><td>{tag}</td></tr>')
    # 겹쳐 보기
    ov = "".join(f'<tr><td><b>{h(o["axis"])}</b></td><td>{h(o["fact"])}</td><td>{h(o["so"])}</td></tr>' for o in D["overlays"])
    era = "".join(f'<div class="ts-era"><small>{h(e["years"])}</small><b>{h(e["era"])}</b><p>{h(e["core"])}</p><p class="ts-now">→ {h(e["now"])}</p></div>' for e in D["eras"])
    mb = "".join(f'<tr><td><b>{h(m["type"])}</b></td><td>{h(m["fit"])}</td><td>{h(m["msg"])}</td></tr>' for m in D["mbti_lens"])
    cr, ccap = creators()
    cr_html = "".join(f'<li>{h(n)} <small>{s:,}명</small></li>' for n, s in cr)
    opt = "".join(f'<tr><td><b>{h(o["id"])}. {h(o["name"])}</b><div class="ts-s">{h(o["what"])}</div></td><td>{h(o["why"])}</td><td>{h(o["rev"])}</td><td>{h(o["fame"])}</td><td>{h(o["risk"])}</td></tr>' for o in D["options"])
    rm = "".join(f'<tr><td>{h(r["when"])}</td><td>{h(r["what"])}</td><td>{h(r["who"])}</td></tr>' for r in D["roadmap"])
    kp = "".join(f'<tr><td>{h(k["k"])}</td><td>{h(k["base"])}</td><td><b>{h(k["target"])}</b></td></tr>' for k in D["kpis"])
    rk = "".join(f"<li>{h(r)}</li>" for r in D["risks"])
    facts = "".join(f'<li><span class="ts-k">{h(f["k"])}</span> {h(f["t"])} <small>({h(f["d"])} · {_a(f.get("url"), f["src"])})</small></li>' for f in D["facts"])
    card = lambda ic, t, sub, body: f'<section class="cpv-card"><header><span class="cpv-ic">{ic}</span><div><b>{t}</b><small>{sub}</small></div></header>{body}</section>'
    tbl = lambda head, body: f'<div class="tbl-wrap"><table class="data"><thead><tr>{"".join(f"<th>{x}</th>" for x in head)}</tr></thead><tbody>{body}</tbody></table></div>'
    return ('<div class="cpv-wrap ts"><div class="cpv-grid">'
            + card("①", "핵심 요약", f"기준 {h(D['as_of'])} · 근거는 맨 아래 출처", f'<ul class="ts-sum">{sum_html}</ul>')
            + card("②", "경력 단계별 교사 — 정체성·고통·자산·공직×개인", h(D["share_note"]), f'<div class="ts-segs">{seg_html}</div>')
            + card("📊", "시장 공급 vs 세그먼트 — 경쟁 3사 강좌 주제 분포", f"강좌 {total:,}개 · {h(cap or '')} 수집 · 제목 키워드 분류(검수 전)",
                   tbl(["주제", "주 대상", "공급량", "강좌", "자사", ""], rows))
            + card("🧭", "겹쳐 보기 — 성별·지역·연령·학교급", "같은 경력이라도 다른 상품이 필요한 이유", tbl(["축", "사실", "그래서"], ov))
            + card("📜", "인문학 렌즈 — 한국 교사상의 다섯 겹", "시대마다 쌓인 정체성이 지금 한 교사 안에 공존한다", f'<div class="ts-eras">{era}</div>')
            + card("🎭", "성향 렌즈(MBTI) — 보조용", h(D["mbti_note"]), tbl(["성향", "맞는 상품", "메시지 톤"], mb))
            + card("🎥", "교사 크리에이터 상위 채널", f"구독자 · {h(ccap or '')} 기준 — 개인 브랜드 경제의 크기", f'<ol class="ts-cr">{cr_html}</ol>')
            + card("③", "전략 옵션 — 매출·명성", "B2C 개인 교사 우선(사용자 선택)", tbl(["옵션", "근거", "매출", "명성", "리스크"], opt))
            + card("④", "실행 로드맵", "기능 단위 담당", tbl(["시기", "할 일", "담당"], rm))
            + card("⑤", "KPI", "세그먼트별 추적", tbl(["지표", "현재", "목표"], kp))
            + card("⑥", "리스크·조직 제언", "", f'<ul class="ts-sum">{rk}</ul>')
            + card("🔎", "근거 자료", "신문·통계 보도(원문 링크) — 수치는 보도 기준일 그대로", f'<ul class="ts-facts">{facts}</ul>')
            + "</div></div>")


if __name__ == "__main__":
    print(len(build()))
