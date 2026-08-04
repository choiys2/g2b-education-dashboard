#!/usr/bin/env python3
"""
2026-08-03 실측: data.go.kr(나라장터 API)가 4시간 넘게 타임아웃돼 입찰공고/
사전규격/낙찰정보가 전부 0건으로 수집됐는데, continue-on-error 때문에 그 빈
데이터가 그대로 배포돼 전날까지 멀쩡하던 사이트가 통째로 비어버렸다.

이 스크립트는 live/full_live.json의 수집 건수를 확인해 GitHub Actions의
GITHUB_OUTPUT에 healthy=true/false를 써준다. false면 워크플로가 배포 자체를
건너뛴다 - live/는 gitignore라 "어제 버전으로 롤백"할 파일이 없으므로,
배포를 안 하는 것 자체가 사실상의 롤백이다(어제까지의 GitHub Pages 콘텐츠가
그대로 남는다).
"""
import json
import os
import sys

MIN_TOTAL = 20


def main():
    try:
        with open("live/full_live.json", encoding="utf-8") as f:
            d = json.load(f)
        a = d["analytics"]
        total = len(a["입찰공고"]) + len(a["사전규격"]) + len(a["낙찰정보"])
    except Exception as e:
        print(f"건전성 체크 자체 실패: {e}", file=sys.stderr)
        total = 0

    healthy = total >= MIN_TOTAL
    print(f"수집 건수 합계: {total} (기준치 {MIN_TOTAL}) -> {'정상' if healthy else '비정상'}")
    if not healthy:
        print("::warning::G2B 수집 건수가 비정상적으로 적어 이번 실행은 배포를 건너뜁니다 - data.go.kr 장애 가능성")

    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"healthy={'true' if healthy else 'false'}\n")


if __name__ == "__main__":
    main()
