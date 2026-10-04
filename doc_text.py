#!/usr/bin/env python3
"""첨부 문서(HWP·HWPX·PDF) -> Gemini 입력. PDF는 파일 그대로, 한글 문서는 본문 텍스트로 바꾼다.

HWP(5.x)는 OLE 복합문서: BodyText/SectionN 스트림(압축 시 raw deflate)의 레코드 중
HWPTAG_PARA_TEXT(67)가 UTF-16LE 문단 텍스트다. 인라인·확장 컨트롤 문자는 8 wchar 를 차지하므로 건너뛴다.
"""
import io
import re
import struct
import zipfile
import zlib

PARA_TEXT = 67
_SKIP8 = set(range(1, 10)) | {11, 12} | set(range(14, 24))


def _hwp5_text(data):
    import olefile  # CI 에서 pip install olefile
    ole = olefile.OleFileIO(io.BytesIO(data))
    header = ole.openstream("FileHeader").read()
    compressed = bool(struct.unpack_from("<I", header, 36)[0] & 1)
    out = []
    secs = sorted([e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"], key=lambda e: int(re.sub(r"\D", "", e[1]) or 0))
    for e in secs:
        raw = ole.openstream(e).read()
        if compressed:
            raw = zlib.decompress(raw, -15)
        i = 0
        while i + 4 <= len(raw):
            h = struct.unpack_from("<I", raw, i)[0]
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            i += 4
            if size == 0xFFF:
                size = struct.unpack_from("<I", raw, i)[0]
                i += 4
            if tag == PARA_TEXT:
                buf = raw[i:i + size]
                chars, j = [], 0
                while j + 2 <= len(buf):
                    c = struct.unpack_from("<H", buf, j)[0]
                    if c in _SKIP8:
                        j += 16
                        continue
                    if c >= 32:
                        chars.append(chr(c))
                    elif c in (10, 13):
                        chars.append("\n")
                    j += 2
                out.append("".join(chars))
            i += size
    return "\n".join(t for t in out if t.strip())


def _hwpx_text(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    parts = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
    texts = []
    for n in parts:
        xml = z.read(n).decode("utf-8", "replace")
        texts += re.findall(r"<hp:t[^>]*>([^<]*)</hp:t>", xml)
    return "\n".join(texts)


def to_gemini_input(data, name=""):
    """-> ('file', mime, bytes) | ('text', None, str) | (None, None, 사유)"""
    head = data[:8]
    nm = (name or "").lower()
    try:
        if head.startswith(b"%PDF"):
            return ("file", "application/pdf", data) if len(data) < 15_000_000 else (None, None, "PDF 용량 초과")
        if head.startswith(b"\xd0\xcf\x11\xe0") or nm.endswith(".hwp"):
            t = _hwp5_text(data)
            return ("text", None, t) if len(t) > 200 else (None, None, "HWP 본문 추출 실패")
        if head.startswith(b"PK") and (nm.endswith(".hwpx") or b"Contents/" in data[:4000] or True):
            t = _hwpx_text(data)
            return ("text", None, t) if len(t) > 200 else (None, None, "압축 문서 본문 없음")
    except Exception as e:
        return (None, None, f"추출 오류: {str(e)[:80]}")
    return (None, None, "지원하지 않는 형식")
