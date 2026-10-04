#!/usr/bin/env python3
"""
Gemini API 공용 호출부(배포 과정 전용, 키: 환경변수 GEMINI_API_KEY).

- 최신 flash 계열 모델을 자동 선택(모델명이 바뀌어도 동작)
- JSON 응답 강제(responseMimeType), 파일(PDF 등)은 inline_data 로 첨부
- 무료 등급 분당 호출 제한을 넘지 않게 호출 사이 간격을 둔다(MIN_INTERVAL)
"""
import base64
import json
import os
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API = "https://generativelanguage.googleapis.com/v1beta"
MIN_INTERVAL = 6.5  # 초. 무료 등급(분당 약 10회) 여유
_last = [0.0]
_model = [None]
_fallbacks = []  # 과부하(503) 때 차례로 넘어갈 다른 flash 모델


def key():
    return os.environ.get("GEMINI_API_KEY")


def mask(s):
    return re.sub(r"key=[^&\s]+", "key=***", str(s))


def _http(url, body=None, timeout=120):
    req = Request(url, data=json.dumps(body).encode() if body is not None else None,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def model():
    if _model[0]:
        return _model[0]
    name = "models/gemini-2.5-flash"
    try:
        ms = _http(f"{API}/models?key={key()}&pageSize=200").get("models", [])
        cands = [m["name"] for m in ms if "generateContent" in m.get("supportedGenerationMethods", [])
                 and "flash" in m["name"] and not re.search(r"lite|image|tts|live|exp|preview|thinking|audio", m["name"])]
        ver = lambda n: float((re.search(r"gemini-(\d+(?:\.\d+)?)", n) or [0, 0])[1] or 0)
        if cands:
            ranked = sorted(set(cands), key=ver, reverse=True)
            name = ranked[0]
            _fallbacks[:] = ranked[1:4]
    except Exception:
        pass
    _model[0] = name
    return name


def generate_json(prompt, files=None, temperature=0.3, retries=3, as_text=False):
    """prompt(문자열) + files[(mime, bytes)] -> 파싱된 JSON(as_text=True 면 마크다운 등 원문). 실패 시 예외."""
    parts = [{"text": prompt}]
    for mime, data in files or []:
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "text/plain" if as_text else "application/json"}}
    for attempt in range(retries + 1):
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            res = _http(f"{API}/{model()}:generateContent?key={key()}", body)
            text = "".join(p.get("text", "") for p in res["candidates"][0]["content"]["parts"] if not p.get("thought"))
            return text if as_text else json.loads(text)
        except HTTPError as e:
            if e.code == 429 and attempt < retries:  # 분당 한도 - 잠시 쉬고 재시도
                time.sleep(30)
                continue
            if e.code in (500, 503) and attempt < retries:  # 일시 과부하 - 잠시 뒤 재시도, 마지막엔 다른 모델로
                time.sleep(15 * (attempt + 1))
                if attempt == retries - 1 and _fallbacks:
                    _model[0] = _fallbacks.pop(0)
                continue
            raise RuntimeError(mask(f"HTTP {e.code}: {e.read()[:200]!r}"))
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            if attempt < retries:
                continue
            raise RuntimeError(f"응답 해석 실패: {e}")
