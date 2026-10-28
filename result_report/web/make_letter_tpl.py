"""결과보고 공문(HWPX) 양식 만들기 — 그룹웨어 공문 PDF(VS-2026-965 형식)를 본떠 자리표시(【…】)를 둔다.

머리 배너(로고·슬로건·청록 선)와 직인 문구(주식회사 비상교육 / 대표이사 양태회)는 공문 PDF에서 그림으로 뽑아 쓴다.
브라우저(app.html)가 【문서번호】 같은 자리표시를 실제 값으로 바꾼다.

1쪽 고정: 원본 PDF(A4)의 세로 위치를 재서 모든 문단을 '고정 줄간격'으로 만든다. 내용 길이와 상관없이 줄 높이가
같고, 길이가 바뀌는 칸(사업명·연수대상)이 2줄이 되면 브라우저가 【여백】 문단을 하나씩 지워 아래쪽 위치를 유지한다.
제목·연수과정처럼 칸이 정해진 곳은 브라우저가 글자 크기를 줄여 맞춘다.
  python make_letter_tpl.py 공문.pdf 출력.hwpx
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import warnings
import zipfile

from PIL import Image
from hwpx import HwpxDocument

warnings.filterwarnings("ignore", category=DeprecationWarning)

MM = 283.465   # HWPUNIT / mm
PT = 100       # HWPUNIT / pt
TEXT_MM = 189  # A4 210 - 왼쪽 11 - 오른쪽 10
FONT = "맑은 고딕"
# 고정 줄간격(pt) — 문단 서식을 만들 때 표시용 퍼센트 값(500+pt)으로 넣고 저장 뒤 FIXED로 바꾼다
FIX = lambda pt: 500 + pt
SPACERS = 5    # 【여백】 문단 수(사업명·연수대상이 2줄이 되면 하나씩 지움)
SIZES = (8, 8.5, 9, 9.5, 10, 10.5, 11)


def pdf_images(pdf):
    """공문 PDF의 그림 2개(머리 배너, 직인 문구)를 투명 마스크까지 합쳐 PNG 바이트로."""
    d = tempfile.mkdtemp()
    subprocess.run(["pdfimages", "-all", pdf, os.path.join(d, "im")], check=True)
    files = sorted(os.listdir(d))
    imgs, i = [], 0
    while i < len(files):
        base = Image.open(os.path.join(d, files[i])).convert("RGB")
        if i + 1 < len(files) and Image.open(os.path.join(d, files[i + 1])).mode == "L":
            mask = Image.open(os.path.join(d, files[i + 1])).convert("L")
            bg = Image.new("RGB", base.size, "white")
            bg.paste(base, mask=mask)
            base, i = bg, i + 2
        else:
            i += 1
        buf = io.BytesIO()
        base.save(buf, "PNG")
        imgs.append((buf.getvalue(), base.size))
    return imgs


def build(pdf, out):
    imgs = pdf_images(pdf)
    head, sign = imgs[0], imgs[1]
    d = HwpxDocument.new()
    st = d.styles
    d.set_page_margins(left=int(11 * MM), right=int(10 * MM), top=int(14 * MM), bottom=int(8 * MM), header=0, footer=0)
    for s in SIZES:                       # 브라우저가 글자 크기를 줄일 때 고를 수 있게 미리 만들어 둔다
        st.ensure_run(size=s, font=FONT)
        st.ensure_run(size=s, bold=True, font=FONT)
    body = st.ensure_run(size=11, font=FONT)
    bold = st.ensure_run(size=11, bold=True, font=FONT)
    fld = st.ensure_run(size=10, font=FONT)
    fld_b = st.ensure_run(size=10, bold=True, font=FONT)
    cell = st.ensure_run(size=10, font=FONT)
    cell_b = st.ensure_run(size=10, bold=True, font=FONT)
    foot = st.ensure_run(size=9.5, font=FONT)

    def para(text="", run=body, **fmt):
        p = d.add_paragraph(text, para_pr_id_ref=0, char_pr_id_ref=run)
        if fmt:
            st.apply_paragraph_format(paragraph_index=len(d.paragraphs) - 1, **fmt)
        return p

    def runs(parts, **fmt):
        p = para(parts[0][0], parts[0][1], **fmt)
        for t, r in parts[1:]:
            p.add_run(t, char_pr_id_ref=r)
        return p

    # 머리 배너(로고·슬로건·청록 선) — 글 너비 꽉 차게
    w, h = head[1]
    pic = d.add_picture(head[0], "png", width_mm=TEXT_MM, height_mm=TEXT_MM * h / w, para_pr_id_ref=0)
    para("", spacing_after_pt=0, line_spacing_percent=FIX(7))
    for label, key in [("문 서 번 호 : ", "문서번호"), ("발 행 일 자 : ", "발행일자"), ("수          신 : ", "수신"),
                       ("참          조 : ", "참조"), ("제          목 : ", "제목")]:
        runs([(label, fld_b), (f"【{key}】", fld)], indent_left_mm=1.4, line_spacing_percent=FIX(21))
    para("", bottom_border=True, border_color="#000000", border_width="0.4 mm", line_spacing_percent=FIX(6))
    para("", line_spacing_percent=FIX(10))
    for t in ["1. 귀 기관의 무궁한 발전을 기원합니다.",
              "2. ㈜비상교육은 「교원 등의 연수에 관한 규정」 제2조에 의거, 인가번호 제02-9호 비바샘 원격교육연수원을 인가 받아 교원직무연수를 실시하고 있습니다.",
              "3. 추진하신 위탁사업에 관한 결과를 아래와 같이 보고 드립니다."]:
        para(t, indent_left_mm=14.1, first_line_indent_mm=-6.3, line_spacing_percent=FIX(19))
    para("", line_spacing_percent=FIX(20))
    for label, key in [("가. 사 업 명", "사업명"), ("나. 연수기간", "연수기간"), ("다. 연수종별", "연수종별"), ("라. 연수대상", "연수대상")]:
        runs([(label, bold), (f" : 【{key}】", body)], indent_left_mm=9.9, line_spacing_percent=FIX(17))
    runs([("마. 연수결과 및 청구금액", bold)], indent_left_mm=9.9, line_spacing_percent=FIX(17))
    para("", line_spacing_percent=FIX(14))

    # 연수결과 표(머리 31pt, 내용 63pt — 연수과정은 2줄까지)
    head_fill = st.ensure_border_fill(border_color="#000000", fill_color="#C6D9F1")
    cell_fill = st.ensure_border_fill(border_color="#000000")
    t = d.add_table(2, 7, width=int(TEXT_MM * MM), char_pr_id_ref=cell)
    t.set_column_widths([30, 183, 63, 63, 59, 55, 82])
    for j, v in enumerate(["순", "연수과정", "신청인원", "이수인원", "이수율", "만족도", "청구금액"]):
        t.set_cell_text(0, j, v)
        t.set_cell_border_fill(0, j, head_fill)
    for j, v in enumerate(["1", "【대표과정】", "【신청인원】", "【이수인원】", "【이수율】", "【만족도】", "【청구금액】"]):
        t.set_cell_text(1, j, v)
        t.set_cell_border_fill(1, j, cell_fill)
    p = para("", alignment="CENTER", line_spacing_percent=FIX(15))
    centre = p.para_pr_id_ref
    p2 = para("", line_spacing_percent=FIX(14))
    left14 = p2.para_pr_id_ref
    for i in range(2):
        for j in range(7):
            for cp in t.cell(i, j).paragraphs:
                cp.para_pr_id_ref = left14 if (i == 1 and j == 1) else centre
                for r in cp.runs:
                    r.char_pr_id_ref = cell if (i == 1 and j == 1) else cell_b

    para("", line_spacing_percent=FIX(12))
    runs([("붙임) 1. 결과보고서", body)], indent_left_mm=9.9, line_spacing_percent=FIX(14))
    for x in ["2. 이수자 명단", "3. 청구서", "4. 사업자등록증", "5. 통장사본"]:
        para(x, indent_left_mm=22.3, line_spacing_percent=FIX(14))
    for _ in range(SPACERS):
        para("【여백】", line_spacing_percent=FIX(17))
    sw, sh = sign[1]
    d.add_picture(sign[0], "png", width_mm=48, height_mm=48 * sh / sw, para_pr_id_ref=centre)
    para("", line_spacing_percent=FIX(16))

    # 아래 정보: 테두리 없는 표(주관부서·담당자·E-mail·Tel / 결재라인)
    para("", bottom_border=True, border_color="#000000", border_width="0.2 mm", line_spacing_percent=FIX(4))
    none = st.ensure_border_fill(border_color="#FFFFFF", active_borders=[])
    ft = d.add_table(2, 4, width=int(TEXT_MM * MM), char_pr_id_ref=foot, border_fill_id_ref=none)
    ft.set_column_widths([150, 118, 165, 102])
    vals = [["주관부서 : 【주관부서】", "담당자 : 【담당자】", "E-mail : 【이메일】", "Tel : 【전화】"],
            ["결재라인 :", "【결재1】", "【결재2】", "【결재3】"]]
    p3 = para("", line_spacing_percent=FIX(13))
    foot_p = p3.para_pr_id_ref
    for i in range(2):
        for j in range(4):
            ft.set_cell_text(i, j, vals[i][j])
            ft.set_cell_border_fill(i, j, none)
            for cp in ft.cell(i, j).paragraphs:
                cp.para_pr_id_ref = foot_p
                for r in cp.runs:
                    r.char_pr_id_ref = foot
    para("", bottom_border=True, border_color="#000000", border_width="0.2 mm", line_spacing_percent=FIX(4))
    para("", line_spacing_percent=FIX(5))
    runs([("13824 경기 과천시 과천대로2길 54 (갈현동) 그라운드브이 14층", foot)], line_spacing_percent=FIX(14))
    d.save_to_path(out)
    _fix_layout(out)


def _fix_layout(path):
    """표시용 퍼센트 줄간격(500+pt)을 고정 줄간격으로, 표 줄 높이·세로 가운데 맞춤, 빈 문단 정리."""
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
        order = z.namelist()
    hdr = files["Contents/header.xml"].decode()
    hdr = re.sub(r'<hh:lineSpacing type="PERCENT" value="5(\d\d)" unit="HWPUNIT"/>',
                 lambda m: f'<hh:lineSpacing type="FIXED" value="{int(m.group(1)) * PT}" unit="HWPUNIT"/>', hdr)
    hdr = hdr.replace('breakNonLatinWord="BREAK_WORD"', 'breakNonLatinWord="KEEP_WORD"')  # 어절 단위 줄바꿈
    files["Contents/header.xml"] = hdr.encode()

    sec = files["Contents/section0.xml"].decode()
    tbls = list(re.finditer(r"<hp:tbl\b.*?</hp:tbl>", sec, re.S))
    heights = [[31, 63], [26, 15]]          # 결과표, 아래 정보표(pt)
    for k in reversed(range(len(tbls))):
        m = tbls[k]
        x = m.group(0)
        rows = re.findall(r"<hp:tr>.*?</hp:tr>", x, re.S)
        for i, row in enumerate(rows):
            h = heights[k][i] * PT
            new = re.sub(r'(<hp:cellSz width="\d+" height=")\d+(")', rf"\g<1>{h}\g<2>", row)
            new = new.replace('vertAlign="TOP"', 'vertAlign="CENTER"')
            if k == 1:   # 아래 정보표는 칸 여백을 없애 글이 왼쪽 선에 맞게
                new = re.sub(r'<hp:cellMargin left="\d+" right="\d+" top="\d+" bottom="\d+"/>',
                             '<hp:cellMargin left="0" right="0" top="0" bottom="0"/>', new)
            x = x.replace(row, new, 1)
        x = re.sub(r'(<hp:sz width="\d+" widthRelTo="ABSOLUTE" height=")\d+(")', rf"\g<1>{sum(heights[k]) * PT}\g<2>", x, 1)
        if k == 1:
            x = re.sub(r'<hp:inMargin left="\d+" right="\d+" top="\d+" bottom="\d+"/>',
                       '<hp:inMargin left="0" right="0" top="0" bottom="0"/>', x)
        sec = sec[:m.start()] + x + sec[m.end():]
    files["Contents/section0.xml"] = sec.encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in order:
            z.writestr(n, files[n], compress_type=zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
    print("ok", sys.argv[2])
