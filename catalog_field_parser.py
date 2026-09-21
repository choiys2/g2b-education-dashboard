#!/usr/bin/env python3
"""
경쟁사 연수과정 카탈로그(competitor_course_catalog_scrape.py)가 모은 title/context
원문 텍스트에서 실제 강좌명·가격·학점(차시)·카테고리를 정규식으로 뽑아낸다.

세 사이트가 카드 텍스트를 완전히 다른 형식으로 이어붙여놓기 때문에(2026-09-05
실측), 사이트별로 별도 정규식을 쓴다. 매칭에 실패하면 원본 title을 그대로 두고
나머지 필드는 None으로 둔다 - 사이트 레이아웃이 바뀌어도 조용히 깨지기만 하고
잘못된 값을 만들어내지는 않게 하기 위함.

- 아이스크림 context 예: "미리보기 상세보기 15차시(1학점) 교수학습 50,000원
  연수·상품SET 신규 2022 개정 교육과정에 딱 맞는 디지털 드로잉 수업 디자인"
  -> 카드의 <a>가 '상세보기' 버튼 자체라 title이 항상 '상세보기'로만 잡힌다.
- 비바샘 title 예: "구글 제미나이를 활용한 실질적인 수업 및 업무 혁신 방법!
  직무/15차시(1학점) 미리보기 상세보기 신규 질문이 답이 되는 제미나이 수업
  솔루션 20% 60,000원 48,000원" -> 앞부분은 홍보 카피(teaser)이고 실제 강좌명은
  '미리보기 상세보기' 뒤, 가격 앞에 온다.
- 티처빌 title은 data-tv-label 속성이라 이미 깨끗하다 - context에서 가격/학점만
  보조로 뽑는다.
"""
import re

_ISCREAM_RE = re.compile(
    r"^(?:미리보기\s*)?(?:상세보기\s*)?"
    r"(?P<credit>\d+차시(?:\(\d+학점\))?)\s*"
    r"(?P<category>\S+)\s*"
    r"(?P<price1>[\d,]+원)\s*(?:(?P<price2>[\d,]+원)\s*)?"
    r"(?:할인중\s*)?"
    r"(?:(?:연수.\S*SET|신규|베스트|교재|할인중)\s*)*"
    r"(?P<title>.+)$"
)

_VIVASAM_RE = re.compile(
    r"^(?P<teaser>.*?)\s*직무/(?P<credit>\d+차시(?:\([^)]*\))?)\s*"
    r"미리보기\s*상세보기\s*"
    r"(?:(?:신규|베스트|샘크리에이티브연수|인기|MD추천|이벤트)\s*)*"
    r"(?P<title>.+?)\s*"
    r"(?:\d+%\s*)?"
    r"(?P<price1>[\d,]+원)(?:\s*(?P<price2>[\d,]+원))?\s*$"
)

_TEACHERVILLE_RE = re.compile(
    r"^\[(?P<format>[^\]]+)\]\s*(?P<category>\S+)\s*.+?"
    r"(?P<price>[\d,]+원)\s*(?:강의체험\s*)?연수신청\s*$"
)


def _price_int(s):
    if not s:
        return None
    try:
        return int(s.replace(",", "").replace("원", ""))
    except ValueError:
        return None


def parse_fields(site, title, context):
    """반환: dict(title, category, credit, price, orig_price) - 매칭 실패 시
    title=원본, 나머지는 None."""
    out = {"title": title, "category": None, "credit": None, "price": None, "orig_price": None}

    if site == "아이스크림":
        m = _ISCREAM_RE.match(context or "")
        if m:
            out["title"] = m.group("title").strip()
            out["category"] = m.group("category")
            out["credit"] = m.group("credit")
            p1, p2 = _price_int(m.group("price1")), _price_int(m.group("price2"))
            out["price"] = p2 if p2 is not None else p1
            out["orig_price"] = p1 if p2 is not None else None
        return out

    if site == "비바샘":
        # title이 아니라 context에서 파싱한다 - scrape_site가 title을 이미 정제된
        # 값으로 덮어쓴 뒤에도(예: 재처리) context는 원본 그대로 남아있어 안전하다.
        m = _VIVASAM_RE.match(context or title or "")
        if m:
            out["title"] = m.group("title").strip()
            out["credit"] = m.group("credit")
            p1, p2 = _price_int(m.group("price1")), _price_int(m.group("price2"))
            out["price"] = p2 if p2 is not None else p1
            out["orig_price"] = p1 if p2 is not None else None
        return out

    if site == "티처빌":
        m = _TEACHERVILLE_RE.match(context or "")
        if m:
            out["category"] = m.group("category")
            out["credit"] = m.group("format")
            out["price"] = _price_int(m.group("price"))
        return out

    return out
