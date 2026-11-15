#!/usr/bin/env python3
"""
A5 교육청 2027 정책 신호 누적 - 에듀테크 레이더 수집본(history/edutech_radar.json, 최근 7일)의 교육청 기사를
시도 × 연수 주제(training_topics)로 분류해 history/edu_office_signals.jsonl 에 쌓는다(주소 기준 중복 제거, 최근 400일).

  - 추가 수집·외부 호출 없음(레이더가 이미 모은 공개 기사 제목·원문 주소만 사용). 비용 0.
  - '2027'·'내년'·'시행계획'·'정책연구'·'예산' 이 들어간 기사는 plan=true 로 표시(다음 해 발주 선행 신호).
  - 각 교육청 '2027 주요업무계획' 원문은 보통 1~2월에 공개된다 - 공개되면 같은 표에 원문 주제를 덧붙인다(Firecrawl, 월 상한 안에서).
관리 탭 '교육청 인사이트' 칸에서만 보인다(관리 비밀번호 암호화).
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "history" / "edutech_radar.json"
OUT = HERE / "history" / "edu_office_signals.jsonl"
SIDO = [("서울", r"서울"), ("부산", r"부산"), ("대구", r"대구"), ("인천", r"인천"), ("전남광주", r"전남광주|광주"), ("대전", r"대전"),
        ("울산", r"울산"), ("세종", r"세종"), ("경기", r"경기"), ("강원", r"강원"), ("충북", r"충북|충청북"), ("충남", r"충남|충청남"),
        ("전북", r"전북|전라북"), ("전남", r"(?<!광주)전남(?!광주)|전라남"), ("경북", r"경북|경상북"), ("경남", r"경남|경상남"), ("제주", r"제주")]
EDU_RE = re.compile(r"교육청|교육감|교육지원청|교육연구정보원|교육원")
PLAN_RE = re.compile(r"2027|내년|시행계획|업무계획|정책연구|예산|중장기|대전환|로드맵")


def sido_of(t):
    for name, rx in SIDO:
        if re.search(rx, t):
            return name
    return ""


def main():
    try:
        import training_topics as tt
    except Exception:  # noqa: BLE001
        tt = None
    d = json.loads(SRC.read_text(encoding="utf-8")) if SRC.exists() else {}
    seen, rows = set(), []
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows.append(r)
                seen.add(r.get("u") or r.get("t"))
    add = 0
    for it in d.get("items") or []:
        t = (it.get("title") or "").strip()
        if not t or not EDU_RE.search(t):
            continue
        s = sido_of(t)
        if not s:
            continue
        u = it.get("orig") or it.get("url") or ""
        if not u.startswith("https://") and not u.startswith("http://"):
            u = ""
        key = u or t
        if key in seen:
            continue
        seen.add(key)
        day = (it.get("orig_date") or it.get("date") or "")[:10]
        tops = tt.classify_topics(t) if tt else []
        rows.append({"d": day, "s": s, "tp": tops, "plan": bool(PLAN_RE.search(t)), "t": t[:120], "u": u, "src": (it.get("src") or it.get("source") or "")[:20]})
        add += 1
    cut = (date.today() - timedelta(days=400)).isoformat()
    rows = sorted((r for r in rows if (r.get("d") or "9") >= cut), key=lambda r: r.get("d") or "")
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"교육청 정책 신호: 신규 {add}건 · 누적 {len(rows)}건 · 레이더 {d.get('collected_at', '-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
