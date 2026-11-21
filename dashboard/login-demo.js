// 로그인 화면 왼쪽 예시 화면 (④ dashboard/)
//
// 가상의 저장소(example/shop-api) 데이터로 대시보드 사용 흐름을 혼자 재생한다.
//   1 분석 이력(분석 중 → 분석 완료) → 2 리포트 상세 → 3 코드 수정안(스피너 → diff) → 4 조치 완료
// 실제 팀 데이터는 쓰지 않는다. 로그인 전 화면이라 서버 API도 부르지 않는다.
// 화면 조각은 실제 대시보드와 같은 클래스와 함수로 그린다:
//   statusBadge(), esc()  → app.js    /    renderFixPanel() → fix-panel.js (⑤)
// 오른쪽 "이용 순서"의 단계를 누르면 그 장면으로 이동해서 이어서 재생한다.
// 움직임 줄이기 설정이면 마지막 장면만 보여 주고 반복하지 않는다.

(function () {
  const body = document.getElementById("demo-body");
  if (!body) return;
  const $ = (id) => document.getElementById(id);

  // ---------- 예시 데이터 ----------
  const REPO = "example/shop-api";
  const TARGET = { pr: 42, title: "feat: 주문 조회 API 추가", sha: "a1b2c3d" };   // 재생 중 분석이 끝나는 PR
  const HISTORY = [   // 이미 분석이 끝난 PR들 (목록을 채우는 용도)
    { pr: 41, title: "fix: 장바구니 수량 0 이하 입력 막기", sha: "7e8f9a0", status: "done", issues: "없음 · 설계와 일치", time: "어제" },
    { pr: 40, title: "feat: 회원 탈퇴와 개인정보 삭제", sha: "4d5e6f7", status: "resolved", issues: "2건 모두 결정", time: "3일 전" },
    { pr: 39, title: "feat: 상품 검색에 가격대 필터 추가", sha: "0b1c2d3", status: "resolved", issues: "1건 모두 결정", time: "5일 전" },
    { pr: 38, title: "feat: 상품 리뷰 작성 API", sha: "8c9d0e1", status: "resolved", issues: "3건 모두 결정", time: "1주 전" },
    { pr: 37, title: "refactor: 배송지 주소 저장 로직 분리", sha: "2f3a4b5", status: "done", issues: "없음 · 설계와 일치", time: "1주 전" },
  ];
  const ISSUE = {
    id: "iss_demo",
    title: "주문 서비스는 Repository를 거쳐 DB에 접근해야 함",
    detail: "OrderService에서 SQL을 직접 실행하고 있습니다.",
    designRef: "docs/DESIGN.md#2.1 계층 구조",
    codeRef: "app/order/service.py",
    direction: "code",
    fix: { diff: [
      "--- a/app/order/service.py",
      "+++ b/app/order/service.py",
      "@@ -1,5 +1,4 @@",
      "-import sqlite3",
      "+from app.order.repository import OrderRepository",
      "",
      " def get_order(order_id):",
      '-    conn = sqlite3.connect("shop.db")',
      '-    return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()',
      "+    return OrderRepository().find_by_id(order_id)",
      "",
    ].join("\n") },
  };

  // ---------- 화면 뼈대 (실제 index.html / report.html과 같은 클래스) ----------
  const row = (r, id = "") => `
    <div class="report-row" ${id ? `id="${id}"` : ""} data-attention="${r.attention || ""}">
      <span class="stripe"></span>
      <span class="pr-no">#${r.pr}</span>
      <span class="row-title"><strong>${esc(r.title)}</strong><span>${REPO} · ${r.sha}</span></span>
      <span class="status-cell" ${id ? `id="${id}-status"` : ""}>${statusBadge(r.status)}</span>
      <span class="issues-cell" ${id ? `id="${id}-issues"` : ""}><span class="muted">${esc(r.issues)}</span></span>
      <span class="time-cell">${r.time}</span>
    </div>`;

  body.innerHTML = `
    <div id="demo-list">
      <div class="demo-list-head"><b>분석 이력</b><span>${REPO}</span></div>
      ${row({ ...TARGET, status: "analyzing", issues: "-", time: "방금" }, "demo-row")}
      ${HISTORY.map((r) => row(r)).join("")}
    </div>
    <section class="card report-head demo-hidden" id="demo-head">
      <div class="title-row"><h1>${esc(TARGET.title)}<span class="pr">#${TARGET.pr}</span></h1><span id="demo-head-status"></span></div>
      <div class="progress"><div class="progress-text" id="demo-progress"></div><div class="segbar" id="demo-seg"></div></div>
    </section>
    <article class="issue demo-hidden" id="demo-issue">
      <div class="issue-head">
        <span class="issue-no">불일치 1</span>
        <h3>${esc(ISSUE.title)}</h3>
        <p class="detail">${esc(ISSUE.detail)}</p>
      </div>
      <div class="compare">
        <div class="side-doc" style="background: var(--accent-soft)"><span class="k">설계 문서</span><span class="mono" style="color: var(--accent)">${esc(ISSUE.designRef)}</span></div>
        <div class="neq">≠</div>
        <div style="background: var(--crit-bg)"><span class="k">코드</span><span class="mono" style="color: var(--accent)">${esc(ISSUE.codeRef)}</span></div>
      </div>
      <div class="actions">
        <button type="button" class="btn code" id="demo-btn-code" aria-pressed="false">코드 수정안 받기</button>
        <button type="button" class="btn doc" aria-pressed="false">문서 개정안 받기</button>
        <span class="choice" id="demo-choice"></span>
      </div>
      <div class="fix-panel" id="demo-panel"></div>
    </article>`;
  // 목록은 한 덩어리로 숨기고 보이기 위해 감싼 div를 grid 흐름에 그대로 둔다
  $("demo-list").style.display = "contents";

  // ---------- 재생 ----------
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const SCENE = { 1: 0, 2: 2600, 3: 4400, 4: 8200 };   // 단계별 시작 시각(ms)
  const LOOP_MS = 12000;                                  // 마지막 장면을 잠시 보여 준 뒤 처음부터
  let timers = [], from = 0;
  // from 이전 장면은 바로 적용하고, 이후 장면은 남은 시간만큼 기다렸다 실행
  const at = (ms, fn) => { if (reduce || ms <= from) fn(); else timers.push(setTimeout(fn, ms - from)); };
  const show = (el) => { el.classList.remove("demo-hidden", "demo-in"); void el.offsetWidth; el.classList.add("demo-in"); };
  const hide = (el) => el.classList.add("demo-hidden");
  const scrollBody = (top) => body.scrollTo({ top, behavior: reduce || from ? "auto" : "smooth" });
  const step = (n) => document.querySelectorAll("#demo-steps li").forEach((li) => {
    const s = Number(li.dataset.step);
    li.classList.toggle("on", s === n);
    li.classList.toggle("done", s < n);
  });

  function reset() {
    timers.forEach(clearTimeout);
    timers = [];
    $("demo-list").style.display = "contents";
    hide($("demo-head")); hide($("demo-issue"));
    $("demo-url").textContent = "/dashboard/";
    $("demo-row").dataset.attention = "warn";
    $("demo-row-status").innerHTML = statusBadge("analyzing");
    $("demo-row-issues").innerHTML = `<span class="muted">-</span>`;
    $("demo-head-status").innerHTML = statusBadge("done");
    $("demo-progress").innerHTML = "불일치 <b>1건</b> 중 <b>0건</b> 수정 방향을 정했습니다.";
    $("demo-seg").innerHTML = `<span class="seg-pending" style="flex:1"></span>`;
    $("demo-btn-code").setAttribute("aria-pressed", "false");
    $("demo-choice").textContent = "코드를 고칠지, 설계 문서를 고칠지 골라 주세요";
    $("demo-panel").innerHTML = "";
    body.scrollTop = 0;
  }

  function play(start = 0) {
    from = start;
    reset();
    at(0, () => step(1));
    // 1. 분석 중 → 분석 완료 (이력 화면이 상태를 다시 불러온 모습)
    at(1400, () => {
      $("demo-row").dataset.attention = "crit";
      $("demo-row-status").innerHTML = statusBadge("done");
      $("demo-row-issues").innerHTML = `<span class="pending-chip">결정 대기 1</span><span class="muted">/ 전체 1건</span>`;
      show($("demo-row-status"));
    });
    // 2. 리포트 상세로 이동
    at(SCENE[2], () => {
      step(2);
      $("demo-list").style.display = "none";
      $("demo-url").textContent = "/dashboard/report.html?id=example_42";
      show($("demo-head")); show($("demo-issue"));
    });
    // 3. 코드 수정안 받기 → 스피너 (app.js의 .fix-loading과 같은 모양)
    at(SCENE[3], () => {
      step(3);
      const b = $("demo-btn-code");
      b.classList.remove("demo-press"); void b.offsetWidth; b.classList.add("demo-press");
      $("demo-choice").textContent = "코드 수정안을 만드는 중입니다…";
      $("demo-panel").innerHTML = `<div class="fix-loading" role="status">${icon("spinner")}<span>AI가 코드 수정안을 만드는 중입니다. 10~30초 정도 걸릴 수 있습니다.</span></div>`;
    });
    // 3-2. 수정안 도착 → ⑤의 renderFixPanel로 diff 표시
    at(6000, () => {
      $("demo-btn-code").setAttribute("aria-pressed", "true");
      $("demo-choice").textContent = "코드 수정으로 정했습니다";
      if (typeof window.renderFixPanel === "function") window.renderFixPanel(ISSUE, $("demo-panel"));
      show($("demo-panel"));
      scrollBody($("demo-issue").offsetTop - body.offsetTop - 8);
    });
    // 4. 조치 완료
    at(SCENE[4], () => {
      step(4);
      scrollBody(0);
      $("demo-head-status").innerHTML = statusBadge("resolved");
      show($("demo-head-status"));
      $("demo-progress").innerHTML = "불일치 <b>1건</b> 중 <b>1건</b> 수정 방향을 정했습니다.";
      $("demo-seg").innerHTML = `<span class="seg-code" style="flex:1"></span>`;
    });
    if (!reduce) at(LOOP_MS, () => play(0));
  }

  // 이용 순서 단계 버튼: 그 장면으로 이동해서 이어서 재생
  document.querySelectorAll("[data-jump]").forEach((b) => {
    b.addEventListener("click", () => play(SCENE[b.dataset.jump]));
  });
  // 다른 탭을 보는 동안은 멈추고, 돌아오면 처음부터
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { timers.forEach(clearTimeout); timers = []; } else play(0);
  });

  play(0);
})();
