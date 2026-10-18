"""교육청 결과보고 — 청구서(xls 양식) 채우기.

청구서 양식은 .xls(직인 이미지·병합 서식 포함)라 LibreOffice(UNO)로 열어 값만 바꾸고
같은 .xls로 저장한다. 과정 수가 양식 줄 수(12)와 다르면 줄을 넣거나 빼고,
학점별로 '학점' 칸과 '단가' 칸을 묶는다(1학점 묶음 → 2학점 묶음).
"""

import contextlib
import datetime as dt
import os
import shutil
import socket
import subprocess
import tempfile
import time

# 양식 좌표(1-based 행, 열 문자). 공문 양식이 바뀌면 여기만 고친다.
CELLS = {"사업명": "G7", "수신처": "G9", "수신 담당자": "G10", "청구일자": "G11",
         "등록번호": "G13", "대표자명": "M14", "공급자 담당자": "M15", "공급자 주소": "G16",
         "공급자 전화": "G18", "공급자 이메일": "M18"}
FIRST_LINE_ROW = 22
TEMPLATE_LINES = 12          # 양식의 과정 줄 수(22~33행)
ROW_MERGES = [("D", "I"), ("J", "K"), ("N", "O")]


@contextlib.contextmanager
def office():
    import uno  # LibreOffice 파이썬 브리지
    from com.sun.star.connection import NoConnectException

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    profile = tempfile.mkdtemp(prefix="rr_lo_")
    proc = subprocess.Popen(
        ["soffice", "--headless", "--invisible", "--nologo", "--norestore",
         f"-env:UserInstallation=file://{profile}",
         f"--accept=socket,host=127.0.0.1,port={port};urp;"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    ctx = None
    for _ in range(60):
        try:
            ctx = resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
            break
        except NoConnectException:
            time.sleep(0.5)
    if ctx is None:
        proc.kill()
        raise RuntimeError("LibreOffice 연결 실패(soffice 설치 확인)")
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    try:
        yield desktop
    finally:
        with contextlib.suppress(Exception):
            desktop.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=10)
        if proc.poll() is None:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def _props(**kw):
    import uno
    from com.sun.star.beans import PropertyValue
    out = []
    for k, v in kw.items():
        p = PropertyValue()
        p.Name, p.Value = k, v
        out.append(p)
    return tuple(out)


def _url(path):
    import uno
    return uno.systemPathToFileUrl(os.path.abspath(path))


def _serial(d):
    return (d - dt.date(1899, 12, 30)).days


def fill(desktop, template_path, out_xls, out_pdf, basic, inv):
    doc = desktop.loadComponentFromURL(_url(template_path), "_blank", 0, _props(Hidden=True))
    try:
        sh = doc.Sheets.getByIndex(0)
        rng = sh.getCellRangeByName

        for key, ref in CELLS.items():
            v = basic.get(key)
            if v in (None, ""):
                continue
            if key == "청구일자":
                rng(ref).setValue(_serial(v))
            else:
                rng(ref).setString(str(v))

        lines = inv["내역"]
        n = max(len(lines), 1)
        last_tpl = FIRST_LINE_ROW + TEMPLATE_LINES - 1
        for ref in (f"C{FIRST_LINE_ROW}:C{last_tpl}", f"L{FIRST_LINE_ROW}:M{last_tpl}"):
            rng(ref).merge(False)
        if n > TEMPLATE_LINES:
            sh.Rows.insertByIndex(last_tpl - 1, n - TEMPLATE_LINES)   # 마지막 줄 앞에 끼워 서식 상속
        elif n < TEMPLATE_LINES:
            sh.Rows.removeByIndex(FIRST_LINE_ROW - 1 + n, TEMPLATE_LINES - n)
        last = FIRST_LINE_ROW + n - 1
        don_row, total_row, note_row = last + 1, last + 2, last + 3

        rng(f"B{FIRST_LINE_ROW}:O{last}").clearContents(1 | 2 | 4 | 16)  # 값·날짜·문자·수식
        group_start = {}
        for i, l in enumerate(lines):
            r = FIRST_LINE_ROW + i
            for a, b in ROW_MERGES:
                rng(f"{a}{r}:{b}{r}").merge(False)
                rng(f"{a}{r}:{b}{r}").merge(True)
            gs = group_start.setdefault(l["학점"], r)
            rng(f"B{r}").setValue(i + 1)
            rng(f"D{r}").setString(l["과정명"])
            rng(f"J{r}").setValue(l["인원"])
            rng(f"N{r}").setFormula(f"=J{r}*$L${gs}")
        groups = sorted(group_start.items(), key=lambda x: x[1])
        for k, (credit, start) in enumerate(groups):
            end = groups[k + 1][1] - 1 if k + 1 < len(groups) else last
            rng(f"C{start}").setString(f"{credit}학점")
            rng(f"L{start}").setValue(next(l["단가"] for l in lines if l["학점"] == credit))
            rng(f"L{start}:M{end}").merge(True)
            if end > start:
                rng(f"C{start}:C{end}").merge(True)

        rng(f"N{don_row}").setValue(inv["교육기부"])
        rng(f"N{total_row}").setFormula(f"=SUM(N{FIRST_LINE_ROW}:N{last})+N{don_row}")
        note = [" ※ 이수정보", f" - 총 이수 : {inv['총이수']:,}건"]
        if inv["교육기부"] < 0:
            note.append(" - 초과비용 기부처리")
        rng(f"B{note_row}").setString("\n".join(note))

        doc.calculateAll()
        got = rng(f"N{total_row}").getValue()
        if round(got) != inv["청구금액"]:
            raise RuntimeError(f"청구서 합계 불일치: 양식 {got:,.0f} ≠ 계산 {inv['청구금액']:,}")
        doc.storeToURL(_url(out_xls), _props(FilterName="MS Excel 97", Overwrite=True))
        if out_pdf:
            doc.storeToURL(_url(out_pdf), _props(FilterName="calc_pdf_Export", Overwrite=True))
    finally:
        doc.close(True)


def to_pdf(desktop, path, out_pdf, filter_name="calc_pdf_Export"):
    doc = desktop.loadComponentFromURL(_url(path), "_blank", 0, _props(Hidden=True))
    try:
        doc.storeToURL(_url(out_pdf), _props(FilterName=filter_name, Overwrite=True))
    finally:
        doc.close(True)
