---
name: archicheck-dev
description: ArchiCheck 작업 매뉴얼. NCP 서버에 반영할 때, 시험 PR로 분석 결과를 확인할 때(E2E), 리포트 JSON·대시보드 API를 바꿀 때, 팀원 PR을 리뷰·머지할 때 사용한다.
---

# ArchiCheck 작업 매뉴얼

공통 규칙(설계 문서 먼저, 담당 폴더, 커밋 형식, 허락 후 커밋)은 CLAUDE.md를 따른다.
아래는 작업별 순서다. 해당하는 절만 따른다.

## A. 리포트 JSON·API를 바꿀 때

1. docs/DESIGN.md를 먼저 고친다: 3.3(형식) 또는 3.4(API), 문서 이력 한 줄, 4.1 테스트 수.
2. 새 필드는 선택 필드로 추가한다. 없으면 기본값으로 보게 해서 기존 리포트가 깨지지 않게 한다.
3. 서버(`server/api/dashboard_api.py`)와 대시보드(`dashboard/app.js`)를 같은 규칙으로 고치고 양쪽에 테스트를 넣는다.
4. 대시보드 파일을 고쳤으면 HTML 3개(index·login·report)의 `style.css?v=N`, `app.js?v=N`을 올린다 (브라우저 캐시).
5. 다른 역할의 파일을 고쳤으면 알릴 팀원과 커밋 해시를 정리해 사용자에게 보고한다.

## B. 테스트

```bash
pytest
node --test dashboard/tests/app.test.js
node --test dashboard/tests/fix-panel.test.js
```

- node 테스트는 파일별로 돌린다 (폴더 지정은 Windows에서 실패).
- app.js 테스트는 vm 안에서 돌아서, 객체·배열을 비교할 때 `[...arr]`이나 `JSON.parse(JSON.stringify(x))`로 바꿔 비교한다.

## C. 서버 반영

1. main에 push된 상태인지 확인한다.
2. 서버에서 실행한다.

   ```bash
   cd /opt/archicheck && sudo -u archicheck git pull && systemctl restart archicheck
   ```

3. 확인한다: `/health`가 `ok`인지, 대시보드 HTML이 새 `app.js?v=N`을 내려주는지.

- git은 `sudo -u archicheck`로 실행한다 (root로 하면 dubious ownership 오류).
- `server/diagram/package-lock.json`이 바뀌었으면 `npm ci`를 다시 한다 (DESIGN.md 2.4).
- `.env` 값은 출력하지 않는다. 키는 사용자가 직접 넣는다.

## D. E2E 시험 PR

1. main에서 `test/<내용>` 브랜치를 만든다. 커밋 메시지는 실제 개발처럼 쓴다 (AI가 커밋 메시지도 읽는다).
2. push하고 사용자에게 PR 링크를 준다. PR 제목 끝에는 "(merge 금지)"를 붙인다.
3. 1분 뒤 PR 코멘트와 대시보드 리포트를 확인한다.
4. 프롬프트·모델을 바꾼 뒤에는 기존 시험 PR에 빈 커밋을 올려 다시 분석한다 (회귀 시험).
5. 결과는 DESIGN.md 4.2 표와 "발견한 문제"에 적는다.

| 시나리오 | 기대 결과 |
| --- | --- |
| 설계 원칙 위반 | 불일치 1건 이상 |
| 다이어그램에 없는 새 클래스 | 문서 개정안에 갱신된 Mermaid |
| 설계를 지킨 변경 | 불일치 0건 (오탐 확인) |
| 커밋 메시지와 다른 변경 | "커밋 메시지에 없는 변경" 경고 |
| 없는 설계 문서 지정 | `failed` / `no_design_doc` 안내 |

## E. 팀원 PR 리뷰·머지

1. PR 브랜치를 worktree로 받아 테스트를 돌린다.
2. `git merge-tree --write-tree main <브랜치>`로 충돌을 미리 본다.
3. 충돌, 설계 문서 반영 여부, 기존 규칙과 어긋나는 점을 정리해 보고한다.
4. 허락을 받으면 `git merge --no-ff -m "<PR 제목> (#번호)"`로 머지한 뒤 push하고, C 절차로 서버에 반영한다.
