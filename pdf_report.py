#!/usr/bin/env python3
"""
매일 파이프라인 실행 시 핵심 지표를 1~2페이지 PDF로 요약해 live/weekly_report.pdf에 저장.
"주간" 리포트라 부르지만 실제로는 매일 최신 데이터로 다시 만들어지는 "현재 시점 스냅샷"이다
- 대시보드 탭을 일일이 열어보지 않고 인쇄하거나 메일로 공유하기 위한 용도.

한글 출력은 TTF 폰트를 직접 임베드한다. 처음에는 reportlab의 Adobe 표준 CID 폰트
(HYGothic-Medium)를 썼는데, 이건 글리프를 PDF에 내장하지 않고 "뷰어가 알아서 갖고
있겠지" 하고 폰트 이름만 참조하는 방식이라 - 실제로 렌더링해보니 뷰어에 해당 CJK
폰트가 없으면 한글이 통째로 안 보이는(빈칸) 문제가 있었다(2026-08-02 실측 확인).
그래서 TTFont로 실제 폰트 파일을 찾아 글리프를 서브셋 임베드하는 방식으로 바꿨다 -
이러면 어떤 뷰어로 열어도 동일하게 보인다. 우분투(GitHub Actions)에서는
`sudo apt-get install -y fonts-nanum`으로 나눔고딕을 설치해서 쓰고, 로컬 윈도우
개발 시에는 맑은 고딕으로 자동 대체된다.
"""
import json
import os
import sys
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",   # ubuntu (apt install fonts-nanum)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:\\Windows\\Fonts\\malgun.ttf",                     # 로컬 윈도우
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",  # macOS
]


def _register_korean_font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("KoFont", path))
            return "KoFont"
    print("[경고] 한글 TTF 폰트를 찾지 못해 CID 폰트로 대체합니다(뷰어에 따라 글자가 안 보일 수 있음)",
          file=sys.stderr)
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    return "HYGothic-Medium"


FONT = _register_korean_font()

ACCENT = colors.HexColor("#2f6b4f")
ACCENT2 = colors.HexColor("#d99a3b")
ROW_ALT = colors.HexColor("#f5f6ef")
GRID = colors.HexColor("#dddddd")


def fmt_won(n):
    n = n or 0
    if n >= 100000000:
        return f"{n/100000000:.1f}억"
    return f"{round(n/10000):,}만" if n >= 10000 else f"{n:,}"


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else {}


_cell_style = None


def _wrap(text):
    """긴 한글 텍스트가 글자수 자르기 대신 셀 안에서 줄바꿈되도록 Paragraph로 감싼다."""
    global _cell_style
    if _cell_style is None:
        _cell_style = ParagraphStyle("KoCell", fontName=FONT, fontSize=7.5, leading=10)
    return Paragraph((text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), _cell_style)


def _styled_table(data, col_widths, header_bg):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def build_pdf(out_path="live/weekly_report.pdf"):
    ai_rows = load("live/_ai_rows_count.json", [])
    g2b_full = load("live/g2b_full_export.json", {})
    pipeline = load("live/own_pipeline_export.json", {})
    # EDSS 학교회계 계약현황(2025)은 매일 자동 수집되는 live/ 데이터가 아니라
    # 사용자가 수동으로 내려받아 넣어준 스냅샷이라 static_data/에 고정 보관한다.
    school_contract = load("static_data/school_contract_national_2025.json", {})

    title_style = ParagraphStyle("KoTitle", fontName=FONT, fontSize=18, leading=22)
    h2_style = ParagraphStyle("KoH2", fontName=FONT, fontSize=12.5, leading=16,
                               spaceBefore=14, spaceAfter=6, textColor=ACCENT)
    small_style = ParagraphStyle("KoSmall", fontName=FONT, fontSize=8, leading=11,
                                  textColor=colors.HexColor("#666666"))

    doc = SimpleDocTemplate(out_path, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                             leftMargin=16 * mm, rightMargin=16 * mm)
    story = [
        Paragraph("비바샘 B2G 시장 리포트", title_style),
        Paragraph(f"생성일: {date.today().isoformat()} (매일 자동 갱신 - 이 시점 스냅샷)", small_style),
        Spacer(1, 10),
    ]

    ai_total_amount = sum(r.get("amount", 0) for r in ai_rows)
    pipe_kpi = pipeline.get("kpi", {})
    kpi_data = [
        ["AI·에듀테크 공고", f"{len(ai_rows)}건", f"총 {fmt_won(ai_total_amount)}"],
        ["자사 파이프라인", f"{pipe_kpi.get('total', 0)}건", f"목표 {fmt_won(pipe_kpi.get('totalTarget', 0))}"],
    ]
    kpi_table = Table(kpi_data, colWidths=[45 * mm, 30 * mm, 60 * mm])
    kpi_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#ecefe1")),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)

    story.append(Paragraph("AI·에듀테크 상위 공고 (금액순 10건)", h2_style))
    top_ai = sorted(ai_rows, key=lambda r: -(r.get("amount") or 0))[:10]
    ai_data = [["공고명", "기관", "지역", "금액", "상태"]]
    for r in top_ai:
        ai_data.append([
            _wrap(r.get("title")), _wrap(r.get("org")),
            r.get("region", ""), fmt_won(r.get("amount", 0)), r.get("status", ""),
        ])
    if len(ai_data) > 1:
        story.append(_styled_table(ai_data, [62 * mm, 40 * mm, 14 * mm, 20 * mm, 20 * mm], ACCENT))
    else:
        story.append(Paragraph("해당 데이터 없음", small_style))

    story.append(Paragraph("경쟁사 랭킹 (낙찰금액순 5건)", h2_style))
    top_comp = (g2b_full.get("competitor") or [])[:5]
    comp_data = [["순위", "낙찰업체", "건수", "총낙찰금액", "평균낙찰률"]]
    for c in top_comp:
        comp_data.append([
            str(c.get("순위", "")), _wrap(c.get("낙찰업체")),
            str(c.get("낙찰건수", "")), c.get("총낙찰금액", ""), c.get("평균낙찰률", ""),
        ])
    if len(comp_data) > 1:
        story.append(_styled_table(comp_data, [12 * mm, 60 * mm, 15 * mm, 30 * mm, 25 * mm], ACCENT2))
    else:
        story.append(Paragraph("해당 데이터 없음", small_style))

    story.append(Paragraph("학교회계 계약현황 시도 랭킹 (물품+용역, 2025 · 상위 10개)", h2_style))
    top_sido = (school_contract.get("by_sido") or [])[:10]
    sido_data = [["순위", "시도", "계약금액", "학교 수", "학교당 평균"]]
    for i, s in enumerate(top_sido, 1):
        n = s.get("n") or 1
        sido_data.append([
            str(i), s.get("sido", ""), fmt_won(s.get("amt", 0)),
            f"{s.get('n', 0)}교", fmt_won(round(s.get("amt", 0) / n)),
        ])
    if len(sido_data) > 1:
        story.append(_styled_table(sido_data, [12 * mm, 30 * mm, 30 * mm, 20 * mm, 30 * mm], ACCENT))
        story.append(Paragraph(
            "※ 학교명은 EDSS(에듀데이터서비스) 공개데이터 특성상 익명 식별자로만 제공되어 표시하지 않습니다. "
            "상세 학교 랭킹(시도·시군구 필터)은 대시보드 ‘학교단위 발주’ 탭에서 확인하세요.",
            small_style))
    else:
        story.append(Paragraph("해당 데이터 없음", small_style))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "자동 생성 리포트 · 전체 데이터는 대시보드(choiys2.github.io/g2b-education-dashboard/full/)에서 확인하세요.",
        small_style))

    doc.build(story)
    print(f"saved {out_path}")


if __name__ == "__main__":
    build_pdf(sys.argv[1] if len(sys.argv) > 1 else "live/weekly_report.pdf")
