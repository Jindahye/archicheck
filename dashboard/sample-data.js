// 개발용 가짜 데이터 (설계 문서 3.3 형식)
// 첫 번째 항목은 samples/report.json 그대로이고, 나머지는 상태별 화면 확인용으로 만든 변형이다.
// 실제 API에 연결하면 (app.js의 USE_SAMPLE = false) 이 파일은 쓰이지 않는다.
window.SAMPLE_REPORTS = [
  {
    "id": "rpt_12_a1b2c3",
    "repo": "owner/archicheck-demo",
    "pr": 12,
    "headSha": "a1b2c3d",
    "title": "로그인 버그 수정",
    "createdAt": "2026-11-18T14:20:00+09:00",
    "status": "done",
    "designDocs": ["docs/architecture.md"],
    "summary": {
      "commitMessage": "로그인 버그 수정",
      "actualChanges": ["로그인 실패 처리 수정", "세션 저장 방식 변경(메모리 → DB)"],
      "unmentionedChanges": 1
    },
    "impact": [
      { "file": "src/auth/AuthController.java", "symbol": "refresh()", "reason": "변경된 세션 로직과 맞지 않음" }
    ],
    "issues": [
      {
        "id": "iss_1",
        "title": "인증 흐름 문서에 세션 DB 저장 단계 없음",
        "designRef": "docs/architecture.md#인증 흐름",
        "codeRef": "src/auth/SessionStore.java",
        "detail": "코드는 세션을 DB에 저장하지만 시퀀스 다이어그램에는 해당 단계가 없음",
        "direction": null,
        "fix": null
      }
    ]
  },
  {
    "id": "rpt_14_d4e5f6",
    "repo": "owner/archicheck-demo",
    "pr": 14,
    "headSha": "d4e5f6a",
    "title": "사용자 조회 성능 개선",
    "createdAt": "2026-11-18T16:05:00+09:00",
    "status": "done",
    "designDocs": ["docs/architecture.md", "docs/설계서.md"],
    "summary": {
      "commitMessage": "사용자 조회 성능 개선",
      "actualChanges": ["UserService에서 DB 직접 조회 추가"],
      "unmentionedChanges": 0
    },
    "impact": [],
    "issues": [
      {
        "id": "iss_1",
        "title": "Service가 Repository를 거치지 않고 DB를 직접 조회함",
        "designRef": "docs/설계서.md#계층 구조",
        "codeRef": "src/user/UserService.java",
        "detail": "설계상 Service는 Repository를 통해서만 DB에 접근해야 하지만, UserService.findActiveUsers()가 JDBC로 직접 쿼리함",
        "direction": null,
        "fix": null
      },
      {
        "id": "iss_2",
        "title": "클래스 다이어그램에 UserCache 없음",
        "designRef": "docs/architecture.md#서버 모듈 구조",
        "codeRef": "src/user/UserCache.java",
        "detail": "새로 추가된 UserCache 클래스가 클래스 다이어그램에 없음",
        "direction": null,
        "fix": null
      }
    ]
  },
  {
    "id": "rpt_15_0a9b8c",
    "repo": "owner/archicheck-demo",
    "pr": 15,
    "headSha": "0a9b8c7",
    "title": "주문 API 추가",
    "createdAt": "2026-11-18T16:40:00+09:00",
    "status": "analyzing",
    "designDocs": [],
    "summary": null,
    "impact": [],
    "issues": []
  },
  {
    "id": "rpt_11_77aa21",
    "repo": "owner/archicheck-demo",
    "pr": 11,
    "headSha": "77aa21b",
    "title": "로그아웃 기능 추가",
    "createdAt": "2026-11-17T20:10:00+09:00",
    "status": "resolved",
    "designDocs": ["docs/architecture.md"],
    "summary": {
      "commitMessage": "로그아웃 기능 추가",
      "actualChanges": ["로그아웃 API 추가"],
      "unmentionedChanges": 0
    },
    "impact": [],
    "issues": [
      {
        "id": "iss_1",
        "title": "API 목록에 로그아웃 엔드포인트 없음",
        "designRef": "docs/architecture.md#서버 API",
        "codeRef": "src/auth/AuthController.java",
        "detail": "POST /auth/logout 이 추가되었지만 설계 문서의 API 표에는 없음",
        "direction": "doc",
        "fix": {
          "before": "| POST | /auth/login | 로그인 |",
          "after": "| POST | /auth/login | 로그인 |\n| POST | /auth/logout | 로그아웃 |",
          "mermaid": null
        }
      }
    ]
  },
  {
    "id": "rpt_10_c3c3c3",
    "repo": "owner/archicheck-demo",
    "pr": 10,
    "headSha": "c3c3c3d",
    "title": "README 오타 수정",
    "createdAt": "2026-11-17T18:30:00+09:00",
    "status": "done",
    "designDocs": ["docs/architecture.md"],
    "summary": null,
    "impact": [],
    "issues": []
  },
  {
    "id": "rpt_9_ff0011",
    "repo": "owner/archicheck-demo",
    "pr": 9,
    "headSha": "ff00112",
    "title": "빌드 설정 변경",
    "createdAt": "2026-11-17T15:00:00+09:00",
    "status": "failed",
    "designDocs": [],
    "summary": null,
    "impact": [],
    "issues": []
  }
];
