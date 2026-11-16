# ArchiCheck (아키체크)

> 코드가 바뀌면 설계 문서·다이어그램과 어긋난 부분을 찾아, 코드 수정 또는 문서 개정안을 제안하는 AI 에이전트

🚧 개발 중 (2026.11.16 ~ 11.20)

## 왜 필요한가

코드는 계속 바뀌지만 설계 문서와 다이어그램은 사람이 직접 고쳐야 해서 금방 낡습니다.
ArchiCheck는 PR이 올라올 때마다 **설계 문서를 기준으로 코드 변경을 검사**하고,
어긋난 부분을 **코드를 고칠지, 문서를 고칠지** 개발자가 선택하게 합니다.

## 주요 기능

- **설계 정합성 검사:** PR의 변경 코드와 설계 문서를 비교해 불일치 항목을 찾습니다.
- **PR 코멘트:** 검사 결과 요약과 대시보드 링크를 PR에 자동으로 남깁니다.
- **수정 방향 선택:** 불일치 항목마다 [코드 수정] 또는 [문서 개정]을 고를 수 있습니다.
- **수정안 생성:** 코드 수정안(diff) 또는 문서 개정안(수정 문구 + 갱신된 Mermaid 다이어그램)을 만듭니다.
- **대시보드:** 분석 이력, 리포트 상세, 수정안을 웹에서 확인합니다.

## 동작 방식

```mermaid
flowchart LR
    Dev([개발자]) -->|PR| GH[GitHub]
    GH -->|Webhook| S[ArchiCheck 서버]
    S -->|정합성 분석| AI[Claude API]
    S -->|리포트 코멘트| GH
    Dev -->|수정 방향 선택| D[대시보드]
    D --> S
```

## 기술 스택

| 구분 | 기술 |
|---|---|
| 서버 | Python, FastAPI |
| 저장소 | SQLite |
| 대시보드 | HTML/JS, mermaid.js, diff2html |
| AI | Claude API |
| 인프라 | 네이버 클라우드 플랫폼(NCP) |
| 연동 | GitHub Webhook, GitHub REST API |

## 문서

- [설계 문서](docs/DESIGN.md)

## 실행 방법

추후 작성 예정

## 협업 규칙

- `main`에 직접 push하지 않고, 브랜치에서 작업한 뒤 PR로 합친다.
- 브랜치 이름은 `종류/작업내용` 형식으로 짓는다. (예: `feat/dashboard`, `fix/webhook`, `docs/design`)
- 커밋 메시지는 `종류: 내용` 형식의 한 줄로 쓴다. (종류: `feat`, `fix`, `docs`, `refactor`)
- 작업 전 `git pull`로 최신 코드를 받는다.
- `.env` 파일은 올리지 않는다.
- 설계와 다르게 구현할 때는 [설계 문서](docs/DESIGN.md)를 먼저 고친다.

## 팀원

| 이름 | 역할 | GitHub |
|---|---|---|
| 진다혜 | 팀장 | [Jindahye](https://github.com/Jindahye) |
| 신유찬 | | [a01050508080-blip](https://github.com/a01050508080-blip) |
| 장경호 | | [OVenrswrll](https://github.com/OVenrswrll) |
| 주성빈 | | [AP6258](https://github.com/AP6258) |
| 윤정은 | | [wjdsl](https://github.com/wjdsl) |
