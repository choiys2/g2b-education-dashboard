# 비바샘 침투 전략 · 지역 채널 공략편 (강사 대시보드)

강사풀·17개 시도 연구회·대관 장소 통합 현황을 담은 내부 운영용 단일 HTML 대시보드.

- 원본: https://claude.ai/artifact/c1324e7a-db94-436d-b5a8-f3aff2b0efc5
- 접속 비밀번호: `9044` (강사 개인정보 포함으로 페이지 잠금)
- 구조: `index.html` 한 파일에 데이터(JSON, `<script type="application/json">`)와 로직(바닐라 JS IIFE)이 모두 포함된 정적 페이지. 별도 빌드 과정 없음.

## 로컬 확인
```bash
cd instructor-dashboard
python3 -m http.server 8000
# http://localhost:8000/index.html
```

## 탭 구성
1. 비바샘 침투작전 (세계관 홈 — 9개 전략 문서)
2. 요약
3. 지역별 강사단 선발
4. 강사 검색
5. 17개 시도 연구회
6. 나의 강사(즐겨찾기, localStorage)
7. 차원별 분석
8. 대관 장소
9. 데이터 노트

## 수정 후 아티팩트에 재배포
이 폴더의 `index.html`을 수정한 뒤, Artifact 도구로 같은 URL(`https://claude.ai/artifact/c1324e7a-db94-436d-b5a8-f3aff2b0efc5`)에 재배포해야 팀 공유 링크가 갱신됩니다.
