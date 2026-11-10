#!/usr/bin/env python3
"""
보안 점검(연결·배포 때마다) - 실패하면 배포를 멈춘다.

  python security_check.py repo          저장소 추적 파일에 비밀값(키·토큰)·휴대폰 번호가 없는지
  python security_check.py site _site    암호화 직전 배포본에 비밀값이 없고, 바깥 링크가 허용 목록 주소인지

  - 값은 절대 출력하지 않는다(파일·줄 번호와 종류만)
  - 바깥 링크 버튼(a.tablink)·window.open 대상은 https 이고 허용 도메인만(피싱·하이재킹 방지)
"""
import re
import subprocess
import sys
from pathlib import Path

SECRET = {
    "Google API 키": r"AIza[0-9A-Za-z_\-]{30,}",
    "GitHub 토큰": r"(?:gh[pousr]_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{40,})",
    "OpenAI/Anthropic 키": r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{30,}",
    "Slack 토큰": r"xox[abpr]-[0-9A-Za-z\-]{20,}",
    "개인키": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "공공데이터 서비스키": r"serviceKey=(?!\*\*\*)[A-Za-z0-9%+/=]{40,}",
    "Cloudflare 토큰": r"\bCF[_-]?API[_-]?TOKEN\s*[:=]\s*['\"][A-Za-z0-9_\-]{30,}",
}
MOBILE = r"(?<![\d-])01[016789]-?\d{3,4}-?\d{4}(?![\d-])"
LINK_OK = ("https://claude.ai/", "https://www.g2b.go.kr/", "https://")  # 버튼형 바깥 링크는 https 만
SKIP = re.compile(r"(^history/|\.enc\.json$|^static_data/brand/|\.(png|jpg|jpeg|webp|gif|pdf|xlsx|ico)$)")


def scan(text, name, bad, warn, mobile=True):
    for kind, pat in SECRET.items():
        for m in re.finditer(pat, text):
            bad.append(f"{name}:{text.count(chr(10), 0, m.start()) + 1} {kind}")
    if mobile:
        n = len(re.findall(MOBILE, text))
        if n:
            warn.append(f"{name}: 휴대폰 번호 형식 {n}개")


def repo():
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    bad, warn = [], []
    for f in files:
        if SKIP.search(f) or f == "security_check.py":
            continue
        try:
            scan(Path(f).read_text(encoding="utf-8"), f, bad, warn)
        except (UnicodeDecodeError, OSError):
            continue
    return bad, warn


def site(root):
    bad, warn = [], []
    for p in Path(root).rglob("*"):
        if p.suffix.lower() not in (".html", ".json", ".js", ".txt", ".csv", ".ics") or not p.is_file():
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        scan(t, str(p.relative_to(root)), bad, warn, mobile=False)  # 공개 조달 데이터의 기관 번호는 경고 대상 아님
        if p.suffix == ".html":
            for m in re.finditer(r'<a[^>]*class="[^"]*tablink[^"]*"[^>]*href="([^"]*)"', t):
                u = m.group(1)
                if u not in ("#", "") and not u.startswith("https://"):
                    bad.append(f"{p.relative_to(root)}: 바깥 링크가 https 가 아님")
            for m in re.finditer(r'target="_blank"(?![^>]*rel="[^"]*noopener)', t):
                warn.append(f"{p.relative_to(root)}: 새 창 링크에 noopener 없음(1건 이상)")
                break
    return bad, warn


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "repo"
    bad, warn = repo() if mode == "repo" else site(sys.argv[2] if len(sys.argv) > 2 else "_site")
    for w in sorted(set(warn))[:30]:
        print("::warning::" + w)
    for b in sorted(set(bad))[:50]:
        print("::error::" + b)
    print(f"보안 점검({mode}): 차단 {len(set(bad))} · 경고 {len(set(warn))}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
