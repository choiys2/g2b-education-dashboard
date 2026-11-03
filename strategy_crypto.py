#!/usr/bin/env python3
"""
전략 브리핑 암호화 저장(공개 저장소용).

  - 비밀값은 GitHub Secret STRATEGY_KEY 에만 있다(누구에게도 보여주지 않음).
  - 공개키 strategy_pubkey.txt = X25519(sha256(STRATEGY_KEY)) 의 공개키 - strategy_key.yml 이 만들어 커밋한다.
  - 07:00 브리핑 세션은 공개키로만 암호화(비밀값을 몰라도 됨) -> strategy_briefings/YYYY-MM-DD.enc.json
  - 대시보드 조합(combine_dashboard.py)만 STRATEGY_KEY 로 복호화해 로그인 뒤 화면에 싣는다.
암호: 임시 X25519 키 교환 -> HKDF-SHA256 -> AES-256-GCM.

  python strategy_crypto.py pubkey                  # (러너) STRATEGY_KEY -> strategy_pubkey.txt
  python strategy_crypto.py encrypt in.json out.enc.json   # (세션) 공개키로 암호화
"""
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

HERE = Path(__file__).parent
PUB = HERE / "strategy_pubkey.txt"
DIR = HERE / "strategy_briefings"
INFO = b"vivasam-strategy-briefing-v1"
b64 = lambda b: base64.b64encode(b).decode()
unb64 = base64.b64decode


def _priv(secret):
    return X25519PrivateKey.from_private_bytes(hashlib.sha256(secret.encode()).digest())


def _raw(pub):
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _key(shared, epk, rpk):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=epk + rpk, info=INFO).derive(shared)


def encrypt(obj, pub_b64=None):
    rpk = unb64(pub_b64 or PUB.read_text().strip())
    eph = X25519PrivateKey.generate()
    epk = _raw(eph.public_key())
    key = _key(eph.exchange(X25519PublicKey.from_public_bytes(rpk)), epk, rpk)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, json.dumps(obj, ensure_ascii=False).encode(), None)
    return {"v": 1, "epk": b64(epk), "n": b64(nonce), "c": b64(ct)}


def decrypt(blob, secret):
    priv = _priv(secret)
    epk, rpk = unb64(blob["epk"]), _raw(priv.public_key())
    key = _key(priv.exchange(X25519PublicKey.from_public_bytes(epk)), epk, rpk)
    return json.loads(AESGCM(key).decrypt(unb64(blob["n"]), unb64(blob["c"]), None))


def load_all(secret=None, limit=30):
    """대시보드용: 최근 limit 개 호를 복호화. 키가 없거나 실패하면 상태만 알린다."""
    secret = secret if secret is not None else os.environ.get("STRATEGY_KEY", "")
    files = sorted(DIR.glob("????-??-??.enc.json"))[-limit:] if DIR.exists() else []
    if not secret:
        return {"available": False, "reason": "STRATEGY_KEY 미설정", "n_files": len(files)}
    out, bad = [], 0
    for f in reversed(files):
        try:
            out.append(decrypt(json.loads(f.read_text(encoding="utf-8")), secret))
        except Exception:
            bad += 1
    return {"available": bool(out), "issues": out, "undecryptable": bad, "n_files": len(files),
            "reason": "" if out else ("복호화 실패(키 불일치)" if bad else "브리핑 없음")}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "pubkey":
        secret = os.environ.get("STRATEGY_KEY", "")
        if len(secret) < 16:
            print("STRATEGY_KEY 가 없거나 너무 짧습니다(16자 이상).", file=sys.stderr)
            return 1
        PUB.write_text(b64(_raw(_priv(secret).public_key())) + "\n")
        print("공개키 갱신:", PUB)
        return 0
    if cmd == "encrypt":
        src, dst = Path(sys.argv[2]), Path(sys.argv[3])
        blob = encrypt(json.loads(src.read_text(encoding="utf-8")))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(blob), encoding="utf-8")
        print("암호화 저장:", dst)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
