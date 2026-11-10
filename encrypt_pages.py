#!/usr/bin/env python3
"""
배포본 대시보드 HTML을 비밀번호로 암호화한다(처음 열 때 비밀번호 입력, 이후 이 브라우저에선 기억).

- 비밀번호는 GitHub Secret DASHBOARD_PASSWORD 에서만 읽는다(공개 저장소라 코드에 적지 않는다).
- PBKDF2-SHA256(25만 회)로 키를 만들고 AES-256-GCM 으로 페이지 전체를 암호화해, 비밀번호 없이는
  페이지 소스를 봐도 내용이 보이지 않는다. 복호화는 브라우저 WebCrypto 로 한다.
- 대상: 대시보드(index.html, full/index.html), 주간 보고(full/weekly.html).
  뉴스 위젯·뉴스 API(외부 앱 연동)와 조간 지면은 대상이 아니다.
  python encrypt_pages.py _site
"""
import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

TARGETS = ["index.html", "full/index.html", "full/weekly.html"]
ITER = 250_000
MARK = "data-gate=\"v1\""

GATE = """<!doctype html>
<html lang="ko" __MARK__><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
<meta name="googlebot" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<title>(주)비상교육 B2G 대시보드</title>
<style>
  /* 비상 브랜드 잠금 화면: 흰 바탕 + visang/VIVA샘 로고 + 비상 하늘색(#00B5E2)·남색(#041A72) */
  :root{color-scheme:light;--bg:#ffffff;--ink:#222;--muted:#666;--line:#dddddd;--accent:#00B5E2;--navy:#041A72;--bad:#d33;}
  *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif;padding:16px;}
  body::before{content:"";position:fixed;left:0;right:0;top:0;height:4px;background:var(--accent);}
  .card{width:100%;max-width:380px;background:#fff;text-align:center;padding:8px 8px 0;}
  .logos{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:26px;}
  .logos img.v{height:36px}.logos img.s{height:40px}.logos .bar{width:1px;height:28px;background:#cccccc}
  h1{font-size:18px;margin:0 0 6px;color:var(--navy)}p{font-size:13px;color:var(--muted);margin:0 0 20px}
  input{width:100%;font:inherit;font-size:22px;letter-spacing:8px;text-align:center;padding:12px;border:1px solid #cccccc;border-radius:4px;background:#fff;color:var(--ink);}
  input:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent)}
  button{width:100%;margin-top:12px;font:inherit;font-weight:700;padding:13px;border:0;border-radius:4px;background:var(--navy);color:#fff;cursor:pointer}
  button:hover{background:var(--accent)}
  label.keep{display:flex;gap:6px;justify-content:center;align-items:center;font-size:12px;color:var(--muted);margin-top:12px}
  .err{color:var(--bad);font-size:13px;min-height:18px;margin-top:10px}
  .foot{margin-top:28px;font-size:11px;color:#999}
</style></head><body>
<form class="card" id="gate" autocomplete="off">
  <div class="logos">__LOGO_V__<span class="bar"></span>__LOGO_S__</div>
  <h1>B2G 시장 전략 대시보드</h1>
  <p>비밀번호를 입력하세요.</p>
  <input id="pw" type="password" inputmode="numeric" autocomplete="current-password" aria-label="비밀번호" autofocus>
  <button type="submit" id="go">열기</button>
  <label class="keep"><input type="checkbox" id="keep" checked style="width:auto;margin:0">이 브라우저에서 기억</label>
  <div class="err" id="err" role="alert"></div>
  <div class="foot">(주)비상교육 · 비바샘 원격교육연수원 내부용</div>
</form>
<script>
(function(){
  var P = {s: "__SALT__", i: "__IV__", c: "__CT__", n: __ITER__};
  var KEY = "g2bdash.pw";
  var b64 = function(s){ var b = atob(s), u = new Uint8Array(b.length); for (var k = 0; k < b.length; k++) u[k] = b.charCodeAt(k); return u; };
  async function open(pw){
    var base = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveKey"]);
    var key = await crypto.subtle.deriveKey({name: "PBKDF2", salt: b64(P.s), iterations: P.n, hash: "SHA-256"}, base, {name: "AES-GCM", length: 256}, false, ["decrypt"]);
    var plain = await crypto.subtle.decrypt({name: "AES-GCM", iv: b64(P.i)}, key, b64(P.c));
    return new TextDecoder().decode(plain);
  }
  function show(html){ document.open(); document.write(html); document.close(); }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (saved) open(saved).then(show).catch(function(){ try { localStorage.removeItem(KEY); } catch (e) {} });
  document.getElementById("gate").addEventListener("submit", function(ev){
    ev.preventDefault();
    var pw = document.getElementById("pw").value.trim(), err = document.getElementById("err"), go = document.getElementById("go");
    if (!pw) return;
    go.disabled = true; go.textContent = "확인 중…"; err.textContent = "";
    open(pw).then(function(html){
      if (document.getElementById("keep").checked) { try { localStorage.setItem(KEY, pw); } catch (e) {} }
      show(html);
    }).catch(function(){
      err.textContent = "비밀번호가 맞지 않습니다."; go.disabled = false; go.textContent = "열기";
      document.getElementById("pw").select();
    });
  });
})();
</script></body></html>
"""


def _logo(k, cls, alt):
    """잠금 화면 로고(static_data/brand). 없으면 글자로."""
    f = Path(__file__).parent / "static_data" / "brand" / f"{k}_logo.png"
    if not f.exists():
        return f'<b style="font-size:22px;color:#00B5E2">{alt}</b>'
    return f'<img class="{cls}" alt="{alt}" src="data:image/png;base64,{base64.b64encode(f.read_bytes()).decode()}">'


def encrypt(html, pw):
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode())
    ct = AESGCM(key).encrypt(iv, html.encode("utf-8"), None)
    e = lambda b: base64.b64encode(b).decode()
    return (GATE.replace("__LOGO_V__", _logo("visang", "v", "visang")).replace("__LOGO_S__", _logo("vivasam", "s", "비바샘 원격교육연수원"))
            .replace("__MARK__", MARK).replace("__SALT__", e(salt)).replace("__IV__", e(iv))
            .replace("__ITER__", str(ITER)).replace("__CT__", e(ct)))


def main(root):
    pw = os.environ.get("DASHBOARD_PASSWORD", "").strip()
    if not pw:
        print("::warning::DASHBOARD_PASSWORD 시크릿이 없어 대시보드를 암호화하지 않았습니다(비밀번호 화면 없음).")
        return
    n = 0
    for rel in TARGETS:
        p = Path(root) / rel
        if not p.exists():
            continue
        html = p.read_text(encoding="utf-8")
        if MARK in html[:400]:  # 이미 잠긴 페이지(뉴스 워크플로가 배포본을 다시 받아 올릴 때)
            continue
        p.write_text(encrypt(html, pw), encoding="utf-8")
        n += 1
    print(f"비밀번호 보호: {n}개 페이지 암호화")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_site")
