#!/usr/bin/env python3
"""
나라장터 공고 스코어링 엔진
입력: listings.json (아래 스키마) — G2B 고급검색 CSV 내보내기를 변환하거나
      data.go.kr '나라장터 입찰공고정보서비스' OpenAPI 응답을 매핑해서 생성
출력: scored.json (점수 내림차순 정렬)

listings.json 스키마 (배열):
[
  {
    "공고명": str,
    "발주기관": str,
    "지역": str,          # 시도명
    "예산": int,           # 원 단위, 모르면 0
    "마감일": "YYYY-MM-DD",
    "공고일": "YYYY-MM-DD",
    "url": str
  }, ...
]
"""
import sys, json
from datetime import date, datetime

# ── 회사 프로필 설정 (변경 시 이 블록만 수정) ──────────────────────
KEYWORDS_HIGH = ["교원연수", "원격연수", "AI 활용", "AIDT", "인공지능", "디지털교과서", "선도교사"]
KEYWORDS_MID = ["위탁교육", "역량강화", "직무연수", "컨소시엄", "교원 역량"]
STRONG_REGIONS = ["대구", "강원", "경북", "광주", "전북", "전남", "경기", "충남", "세종", "충북"]
BUDGET_SWEET_MIN = 100_000_000   # 1억
BUDGET_SWEET_MAX = 2_000_000_000  # 20억
LEAD_TIME_MIN_DAYS = 7   # 이보다 급하면 준비 리스크 ↑
LEAD_TIME_MAX_DAYS = 30  # 이보다 여유 있으면 우선순위 약간 ↓
# ──────────────────────────────────────────────────────────

def score_keyword(title):
    s = 0
    for k in KEYWORDS_HIGH:
        if k in title:
            s += 10
    for k in KEYWORDS_MID:
        if k in title:
            s += 5
    return min(s, 40)  # cap 40


def score_budget(amount):
    if not amount:
        return 10  # 예산 미상 → 중립 점수
    if BUDGET_SWEET_MIN <= amount <= BUDGET_SWEET_MAX:
        return 25
    if amount < BUDGET_SWEET_MIN:
        return 12
    return 15  # 초대형 사업 - 컨소시엄 지분 참여 가능성


def score_region(region):
    return 20 if any(r in region for r in STRONG_REGIONS) else 8


def score_deadline(deadline_str, today=None):
    today = today or date.today()
    try:
        d = datetime.strptime(deadline_str, "%Y-%m-%d").date()
    except Exception:
        return 5
    days_left = (d - today).days
    if days_left < 0:
        return 0
    if days_left < LEAD_TIME_MIN_DAYS:
        return 5   # 너무 급함
    if days_left <= LEAD_TIME_MAX_DAYS:
        return 15  # 최적 준비기간
    return 8       # 여유는 있으나 아직 먼 일정


def score_listing(item):
    kw = score_keyword(item.get("공고명", ""))
    bg = score_budget(item.get("예산", 0))
    rg = score_region(item.get("지역", ""))
    dl = score_deadline(item.get("마감일", ""))
    total = kw + bg + rg + dl
    return {
        **item,
        "점수": total,
        "점수상세": {"키워드": kw, "예산": bg, "지역": rg, "마감임박도": dl},
    }


def main(in_path, out_path):
    with open(in_path, encoding="utf-8") as f:
        listings = json.load(f)
    scored = [score_listing(x) for x in listings]
    scored.sort(key=lambda x: x["점수"], reverse=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)
    print(f"scored {len(scored)} listings -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
