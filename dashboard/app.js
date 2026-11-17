// ArchiCheck 대시보드 (④ 담당: 분석 이력 · 리포트 상세)

// ===== 설정 =====
// true  : sample-data.js의 가짜 데이터로 화면을 그린다 (서버 없이 개발할 때)
// false : 서버 API(/api/reports ...)에서 데이터를 받는다
const USE_SAMPLE = true;
const API_BASE = "";          // 같은 서버에서 제공하면 빈 문자열 그대로
const POLL_MS = 5000;         // 분석 중일 때 다시 불러오는 간격

// ===== 데이터 불러오기 (API 연결은 여기만 고치면 된다) =====
const api = {
  async listReports() {
    if (USE_SAMPLE) return structuredClone(window.SAMPLE_REPORTS);
    return getJson(`${API_BASE}/api/reports`);
  },
  async getReport(id) {
    if (USE_SAMPLE) {
      const r = window.SAMPLE_REPORTS.find((x) => x.id === id);
      if (!r) throw new Error("리포트를 찾을 수 없습니다. 분석 이력에서 다시 선택하세요.");
      return structuredClone(r);
    }
    return getJson(`${API_BASE}/api/reports/${encodeURIComponent(id)}`);
  },
  async requestFix(reportId, issueId, direction) {
    if (USE_SAMPLE) return { direction, fix: null };   // 샘플 모드: 서버 호출 없이 선택만 반영
    return getJson(
      `${API_BASE}/api/reports/${encodeURIComponent(reportId)}/issues/${encodeURIComponent(issueId)}/fix`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ direction }) }
    );
  },
};

async function getJson(url, options = {}) {
  // 대시보드와 API가 같은 주소라 세션 쿠키는 브라우저가 자동으로 붙인다 (설계 문서 3.4)
  const res = await fetch(url, { credentials: "same-origin", ...options });
  if (res.status === 401) {               // 세션 없음 → 로그인 화면으로 (3.4 화면 ④)
    auth.goLogin();
    throw new Error("로그인이 필요합니다.");
  }
  if (!res.ok) throw new Error(`서버가 ${res.status} 오류를 돌려줬습니다.`);
  return res.json();
}

// ===== 로그인 (설계 문서 3.4 대시보드 인증: 로그인 API + 세션 쿠키) =====
// API 모드: POST /api/login { password } → 200이면 서버가 세션 쿠키를 준다. 이후 API가 401이면 로그인 화면으로 보낸다.
// 샘플 모드: 서버가 없으므로 아무 비밀번호나 통과시키고, 로그인 여부만 브라우저 탭에 기억한다.
const SAMPLE_LOGIN_KEY = "archicheck-sample-login";
const auth = {
  sampleLoggedIn() { try { return sessionStorage.getItem(SAMPLE_LOGIN_KEY) === "1"; } catch (_) { return true; } },
  async login(password) {
    if (USE_SAMPLE) {
      try { sessionStorage.setItem(SAMPLE_LOGIN_KEY, "1"); } catch (_) {}
      return;
    }
    let res;
    try {
      res = await fetch(`${API_BASE}/api/login`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
    } catch (_) {
      throw new Error("서버에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.");
    }
    if (res.status === 401) throw new Error("비밀번호가 맞지 않습니다. 다시 확인하세요.");
    if (!res.ok) throw new Error(`서버에 연결하지 못했습니다. (${res.status})`);
  },
  async logout() {
    if (USE_SAMPLE) {
      try { sessionStorage.removeItem(SAMPLE_LOGIN_KEY); } catch (_) {}
      return;
    }
    try {
      await fetch(`${API_BASE}/api/logout`, { method: "POST", credentials: "same-origin" });
    } catch (_) {}   // 서버에 닿지 않아도 로그인 화면으로는 보낸다
  },
  // 원래 보던 주소를 기억해 두고 로그인 화면으로 (로그인 후 그 주소로 돌아간다)
  goLogin() {
    const here = location.pathname.split("/").pop() + location.search;
    location.replace(`login.html?next=${encodeURIComponent(here)}`);
  },
};

// 샘플 모드에서만 화면을 열기 전에 로그인 여부를 확인한다.
// API 모드에서는 세션 쿠키를 화면에서 읽을 수 없으므로(HttpOnly), API가 401을 줄 때 로그인 화면으로 보낸다.
function requireLogin() {
  if (!USE_SAMPLE || auth.sampleLoggedIn()) return true;
  auth.goLogin();
  return false;
}

function addLogoutButton() {
  const bar = document.querySelector(".topbar");
  if (!bar) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "theme-btn";
  btn.textContent = "로그아웃";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    await auth.logout();
    location.href = "login.html";
  });
  bar.appendChild(btn);
}

// ===== 로그인 화면 =====
function renderLogin() {
  const form = document.getElementById("login-form");
  const input = document.getElementById("password");
  const error = document.getElementById("pw-error");
  const toggle = document.getElementById("toggle-pw");
  const submit = document.getElementById("login-btn");
  const next = new URLSearchParams(location.search).get("next") || "index.html";
  // 같은 폴더의 화면으로만 이동 (외부 주소로 튕기지 않게)
  const safeNext = /^(index|report)\.html(\?.*)?$/.test(next) ? next : "index.html";

  if (USE_SAMPLE) {
    document.getElementById("login-note").textContent = "샘플 모드에서는 아무 비밀번호나 통과합니다.";
  }

  toggle.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    toggle.textContent = show ? "숨기기" : "보기";
  });
  input.addEventListener("input", () => { error.textContent = ""; input.removeAttribute("aria-invalid"); });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const pw = input.value;
    if (!pw.trim()) {
      error.textContent = "비밀번호를 입력하세요.";
      input.setAttribute("aria-invalid", "true");
      input.focus();
      return;
    }
    submit.disabled = true;
    submit.textContent = "확인하는 중…";
    try {
      await auth.login(pw);
    } catch (err) {
      error.textContent = err.message;
      input.setAttribute("aria-invalid", "true");
      submit.disabled = false;
      submit.textContent = "접속하기";
      input.focus();
      return;
    }
    location.replace(safeNext);
  });
}

// ===== 공통 도우미 =====
const STATUS = {
  analyzing: { label: "분석 중", icon: "spinner" },
  done:      { label: "분석 완료", icon: "check" },
  resolved:  { label: "조치 완료", icon: "check" },
  failed:    { label: "실패", icon: "alert" },
};
const DIRECTION_LABEL = { code: "코드 수정", doc: "문서 개정" };

const ICONS = {
  spinner: `<path d="M8 2a6 6 0 1 0 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
  check:   `<path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`,
  checks:  `<path d="M1.5 8.5l3 3 6-7M7.5 11.5l1 0 6-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  alert:   `<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 4.5v4.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="11.3" r="1" fill="currentColor"/>`,
};
const icon = (name) => `<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">${ICONS[name]}</svg>`;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function statusBadge(status) {
  const s = STATUS[status] || { label: status, icon: "alert" };
  return `<span class="status ${esc(status)}">${icon(s.icon)}${esc(s.label)}</span>`;
}

function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `<time datetime="${esc(iso)}">${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}</time>`;
}

// 레포 파일 경로 → GitHub 링크 (designRef의 "#섹션"은 GitHub 제목 앵커로 변환)
function githubLink(repo, sha, ref) {
  if (!ref) return `<span class="muted">-</span>`;
  const [path, section] = ref.split("#");
  let url = `https://github.com/${repo}/blob/${sha}/${path}`;
  if (section) url += "#" + encodeURIComponent(section.trim().toLowerCase().replace(/\s+/g, "-"));
  return `<a href="${esc(url)}" target="_blank" rel="noopener" class="mono">${esc(ref)}</a>`;
}

// 리포트의 불일치 집계
function issueStats(r) {
  const issues = r.issues || [];
  const total = r.issueCount ?? issues.length;
  const pending = r.pendingCount ?? issues.filter((i) => !i.direction).length;
  const code = issues.filter((i) => i.direction === "code").length;
  const doc = issues.filter((i) => i.direction === "doc").length;
  return { total, pending, code, doc };
}

// ===== 테마 전환 =====
function initTheme() {
  try {
    const saved = localStorage.getItem("archicheck-theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch (_) {}
  const btn = document.getElementById("theme-btn");
  if (!btn) return;
  const isDark = () =>
    document.documentElement.dataset.theme === "dark" ||
    (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  const sync = () => (btn.textContent = isDark() ? "밝은 테마로" : "어두운 테마로");
  sync();
  btn.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("archicheck-theme", next); } catch (_) {}
    sync();
  });
}

function showModeBadge() {
  const el = document.getElementById("mode-badge");
  if (el && USE_SAMPLE) el.textContent = "샘플 데이터";
}

// ===== 1. 분석 이력 화면 =====
const FILTERS = [
  { key: "all", label: "전체", test: () => true },
  { key: "pending", label: "결정 대기", test: (r) => r.status === "done" && issueStats(r).pending > 0 },
  { key: "analyzing", label: "분석 중", test: (r) => r.status === "analyzing" },
  { key: "failed", label: "실패", test: (r) => r.status === "failed" },
];
let allReports = [];
let currentFilter = "all";

let listTimer = null;
let lastLoaded = null;

async function renderList() {
  const rows = document.getElementById("report-rows");
  clearTimeout(listTimer);
  try {
    allReports = await api.listReports();
    lastLoaded = new Date();
  } catch (e) {
    if (!lastLoaded) {
      rows.innerHTML = `<p class="empty">목록을 불러오지 못했습니다. ${esc(e.message)}</p>`;
      return;
    }
    // 이미 화면이 있으면 그대로 두고, 다음 주기에 다시 시도한다
    setRefreshNote(`새로 고치지 못했습니다. ${POLL_MS / 1000}초 뒤 다시 시도합니다.`, true);
    listTimer = setTimeout(renderList, POLL_MS);
    return;
  }
  allReports.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  renderSummary();
  renderFilters();
  renderRows();
  scheduleListRefresh();
}

// 분석 중인 PR이 있으면 POLL_MS마다 목록을 다시 불러온다 (API 모드에서만)
function scheduleListRefresh() {
  const analyzing = allReports.filter((r) => r.status === "analyzing").length;
  if (USE_SAMPLE || analyzing === 0) {
    setRefreshNote(lastLoaded && !USE_SAMPLE ? `마지막 갱신 ${clock(lastLoaded)}` : "");
    return;
  }
  setRefreshNote(`분석 중인 PR ${analyzing}개 · ${POLL_MS / 1000}초마다 자동으로 새로 고칩니다 · 마지막 갱신 ${clock(lastLoaded)}`);
  listTimer = setTimeout(() => {
    if (document.hidden) {
      // 탭을 안 보고 있으면 쉬었다가, 다시 보면 바로 갱신
      document.addEventListener("visibilitychange", renderList, { once: true });
    } else {
      renderList();
    }
  }, POLL_MS);
}

function setRefreshNote(text, isError = false) {
  const el = document.getElementById("refresh-note");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("error", isError);
}

function clock(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function renderSummary() {
  const pendingIssues = allReports
    .filter((r) => r.status === "done")
    .reduce((n, r) => n + issueStats(r).pending, 0);
  const analyzing = allReports.filter((r) => r.status === "analyzing").length;
  const failed = allReports.filter((r) => r.status === "failed").length;
  document.getElementById("summary").innerHTML = `
    <div class="stat ${pendingIssues ? "attention" : ""}">
      <span class="label">결정 대기 불일치</span>
      <span class="value">${pendingIssues}<small>건</small></span>
    </div>
    <div class="stat"><span class="label">분석 중</span><span class="value">${analyzing}<small>PR</small></span></div>
    <div class="stat"><span class="label">분석 실패</span><span class="value">${failed}<small>PR</small></span></div>
    <div class="stat"><span class="label">분석한 PR</span><span class="value">${allReports.length}<small>개</small></span></div>`;
}

function renderFilters() {
  const box = document.getElementById("filters");
  box.innerHTML = FILTERS.map((f) => {
    const n = allReports.filter(f.test).length;
    return `<button type="button" class="filter" data-key="${f.key}" aria-pressed="${f.key === currentFilter}">
      ${f.label}<span class="n">${n}</span></button>`;
  }).join("");
  box.querySelectorAll(".filter").forEach((b) =>
    b.addEventListener("click", () => {
      currentFilter = b.dataset.key;
      box.querySelectorAll(".filter").forEach((x) => x.setAttribute("aria-pressed", x === b));
      renderRows();
    })
  );
}

function renderRows() {
  const rows = document.getElementById("report-rows");
  const f = FILTERS.find((x) => x.key === currentFilter);
  const list = allReports.filter(f.test);
  if (!list.length) {
    rows.innerHTML = `<p class="empty">${currentFilter === "all" ? "아직 분석한 PR이 없습니다." : "해당하는 PR이 없습니다."}</p>`;
    return;
  }
  rows.innerHTML = list.map((r) => {
    const s = issueStats(r);
    let issuesCell, attention = "";
    if (r.status === "analyzing" || r.status === "failed") {
      issuesCell = `<span class="muted">-</span>`;
      if (r.status === "failed") attention = "crit";
    } else if (s.total === 0) {
      issuesCell = `<span class="muted">없음 · 설계와 일치</span>`;
    } else if (s.pending > 0) {
      issuesCell = `<span class="pending-chip">결정 대기 ${s.pending}</span><span class="muted">/ 전체 ${s.total}건</span>`;
      attention = "crit";
    } else {
      issuesCell = `<span class="muted">${s.total}건 모두 결정</span>`;
    }
    if (r.status === "analyzing") attention = "warn";
    return `
      <a class="report-row" href="report.html?id=${encodeURIComponent(r.id)}" data-attention="${attention}">
        <span class="stripe" aria-hidden="true"></span>
        <span class="pr-no">#${esc(r.pr)}</span>
        <span class="row-title"><strong>${esc(r.title)}</strong><span>${esc(r.repo)} · ${esc(r.headSha)}</span></span>
        <span class="status-cell">${statusBadge(r.status)}</span>
        <span class="issues-cell">${issuesCell}</span>
        <span class="time-cell">${formatDate(r.createdAt)}</span>
      </a>`;
  }).join("");
}

// ===== 2. 리포트 상세 화면 =====
let pollTimer = null;

async function renderReport() {
  const root = document.getElementById("report-root");
  const id = new URLSearchParams(location.search).get("id");
  if (!id) {
    root.innerHTML = `<p class="empty">리포트 ID가 없습니다. <a href="index.html">분석 이력</a>에서 PR을 선택하세요.</p>`;
    return;
  }

  let r;
  try {
    r = await api.getReport(id);
  } catch (e) {
    root.innerHTML = `<a href="index.html" class="back">← 분석 이력</a>
      <div class="notice failed">${icon("alert")}<div><strong>리포트를 불러오지 못했습니다</strong><p>${esc(e.message)}</p></div></div>`;
    return;
  }

  document.title = `ArchiCheck PR #${r.pr} ${r.title}`;
  const finished = r.status !== "analyzing" && r.status !== "failed";
  root.innerHTML =
    `<a href="index.html" class="back">← 분석 이력</a>` +
    headSection(r) +
    statusNotice(r) +
    (finished ? bodySection(r) : "");

  if (finished) bindIssueButtons(r);

  // 분석 중이면 주기적으로 다시 불러온다 (API 모드에서만)
  clearTimeout(pollTimer);
  if (r.status === "analyzing" && !USE_SAMPLE) pollTimer = setTimeout(renderReport, POLL_MS);
}

function headSection(r) {
  return `
    <section class="card report-head">
      <div class="title-row">
        <h1>${esc(r.title)}<span class="pr">#${esc(r.pr)}</span></h1>
        ${statusBadge(r.status)}
      </div>
      <dl class="meta">
        <div><dt>레포</dt><dd><a href="https://github.com/${esc(r.repo)}/pull/${esc(r.pr)}" target="_blank" rel="noopener">${esc(r.repo)} PR 열기</a></dd></div>
        <div><dt>커밋</dt><dd class="mono">${esc(r.headSha)}</dd></div>
        <div><dt>분석 시각</dt><dd>${formatDate(r.createdAt)}</dd></div>
      </dl>
      ${progressBlock(r)}
    </section>`;
}

// 결정 진행도: 얇은 분할 막대 (코드 수정 / 문서 개정 / 결정 대기)
function progressBlock(r) {
  const s = issueStats(r);
  if (r.status === "analyzing" || r.status === "failed" || s.total === 0) return "";
  const decided = s.code + s.doc;
  const parts = [
    ["seg-code", s.code, "코드 수정"],
    ["seg-doc", s.doc, "문서 개정"],
    ["seg-pending", s.pending, "결정 대기"],
  ].filter((p) => p[1] > 0);
  const aria = parts.map((p) => `${p[2]} ${p[1]}건`).join(", ");
  return `
    <div class="progress">
      <div class="progress-text">불일치 <b>${s.total}건</b> 중 <b>${decided}건</b> 수정 방향을 정했습니다.</div>
      <div class="segbar" role="img" aria-label="${aria}">
        ${parts.map((p) => `<span class="${p[0]}" style="flex:${p[1]}" title="${p[2]} ${p[1]}건"></span>`).join("")}
      </div>
      <div class="legend">
        <span><i class="seg-code"></i>코드 수정 ${s.code}</span>
        <span><i class="seg-doc"></i>문서 개정 ${s.doc}</span>
        <span><i class="seg-pending"></i>결정 대기 ${s.pending}</span>
      </div>
    </div>`;
}

function statusNotice(r) {
  if (r.status === "analyzing") {
    return `<div class="notice analyzing">${icon("spinner")}<div><strong>분석 중입니다</strong>
      <p>설계 문서와 코드 변경을 비교하고 있습니다. 보통 1분 안에 끝나며, 끝나면 이 화면이 자동으로 바뀝니다.</p></div></div>`;
  }
  if (r.status === "failed") {
    return `<div class="notice failed">${icon("alert")}<div><strong>분석하지 못했습니다</strong>
      <p>설계 문서를 찾지 못했거나 분석 중 오류가 났습니다. 레포 루트의 <code>.archicheck.yml</code>에 설계 문서 경로를 적은 뒤 PR에 커밋을 다시 올려 주세요.</p></div></div>`;
  }
  if (!r.issues || r.issues.length === 0) {
    return `<div class="notice ok">${icon("check")}<div><strong>설계와 일치합니다</strong>
      <p>이번 변경에서 설계 문서와 어긋난 부분을 찾지 못했습니다.</p></div></div>`;
  }
  return "";
}

function bodySection(r) {
  const issues = r.issues || [];
  const left = issues.length
    ? `<h2 class="section-title">불일치 항목 <span class="count-chip">${issues.length}</span></h2>` +
      issues.map((iss, i) => issueCard(r, iss, i)).join("")
    : "";
  const right = designDocsCard(r) + summaryCard(r) + impactCard(r);
  return `<div class="detail-grid"><div class="col">${left}</div><aside class="col">${right}</aside></div>`;
}

function issueCard(r, iss, i) {
  const dir = iss.direction || "";
  return `
    <article class="issue" data-issue="${esc(iss.id)}" data-direction="${esc(dir)}">
      <div class="issue-head">
        <span class="issue-no">불일치 ${i + 1} · ${esc(iss.id)}</span>
        <h3>${esc(iss.title)}</h3>
        <p class="detail">${esc(iss.detail)}</p>
      </div>
      <div class="compare">
        <div><span class="k">설계 문서</span>${githubLink(r.repo, r.headSha, iss.designRef)}</div>
        <div class="neq" aria-label="어긋남">≠</div>
        <div><span class="k">코드</span>${githubLink(r.repo, r.headSha, iss.codeRef)}</div>
      </div>
      <div class="actions">
        <button type="button" class="btn code" data-dir="code" aria-pressed="${dir === "code"}">코드 수정안 받기</button>
        <button type="button" class="btn doc" data-dir="doc" aria-pressed="${dir === "doc"}">문서 개정안 받기</button>
        <span class="choice">${dir ? `${DIRECTION_LABEL[dir]}으로 정했습니다` : "코드를 고칠지, 설계 문서를 고칠지 골라 주세요"}</span>
      </div>
      <div class="fix-panel"></div>
    </article>`;
}

function designDocsCard(r) {
  const docs = r.designDocs || [];
  return `
    <section class="card">
      <h2 class="card-title">비교에 쓴 설계 문서 <span class="count-chip">${docs.length}</span></h2>
      <div class="card-body">
        ${docs.length
          ? `<ul class="ref-list">${docs.map((d) => `<li>${githubLink(r.repo, r.headSha, d)}</li>`).join("")}</ul>`
          : `<span class="muted">사용한 설계 문서가 없습니다.</span>`}
      </div>
    </section>`;
}

function summaryCard(r) {
  const s = r.summary;
  if (!s || (!s.commitMessage && !(s.actualChanges || []).length)) return "";   // 보조 기능: 없으면 숨김
  const warn = s.unmentionedChanges > 0
    ? `<span class="warn-tag">${icon("alert")}커밋 메시지에 없는 변경 ${esc(s.unmentionedChanges)}건</span>` : "";
  return `
    <section class="card">
      <h2 class="card-title">변경 요약</h2>
      <dl class="card-body kv">
        <div><dt>커밋 메시지</dt><dd>${esc(s.commitMessage)}</dd></div>
        <div><dt>실제 변경</dt><dd><ul class="change-list">${(s.actualChanges || []).map((c) => `<li>${esc(c)}</li>`).join("")}</ul>${warn}</dd></div>
      </dl>
    </section>`;
}

function impactCard(r) {
  const list = r.impact || [];
  if (!list.length) return "";   // 보조 기능: 없으면 숨김
  return `
    <section class="card">
      <h2 class="card-title">영향 범위 <span class="count-chip">${list.length}</span></h2>
      <ul class="impact">
        ${list.map((i) => `
          <li>
            ${githubLink(r.repo, r.headSha, i.file)}
            <span class="sym">${esc(i.symbol)}</span>
            <span class="why">${esc(i.reason)}</span>
          </li>`).join("")}
      </ul>
    </section>`;
}

function bindIssueButtons(r) {
  document.querySelectorAll(".issue").forEach((card) => {
    const iss = r.issues.find((x) => x.id === card.dataset.issue);
    const panel = card.querySelector(".fix-panel");
    const choice = card.querySelector(".choice");
    const buttons = card.querySelectorAll(".btn");
    if (iss.direction) showFix(iss, panel);

    buttons.forEach((btn) => {
      btn.addEventListener("click", async () => {
        const direction = btn.dataset.dir;
        buttons.forEach((b) => (b.disabled = true));
        choice.textContent = `${DIRECTION_LABEL[direction]}안을 만드는 중입니다…`;
        try {
          const result = await api.requestFix(r.id, iss.id, direction);
          iss.direction = result.direction ?? direction;
          iss.fix = result.fix ?? null;
          card.dataset.direction = iss.direction;
          buttons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.dir === iss.direction));
          choice.textContent = `${DIRECTION_LABEL[iss.direction]}으로 정했습니다`;
          showFix(iss, panel);
          refreshProgress(r);
        } catch (e) {
          choice.textContent = `수정안을 만들지 못했습니다. ${e.message}`;
        } finally {
          buttons.forEach((b) => (b.disabled = false));
        }
      });
    });
  });
}

function refreshProgress(r) {
  const old = document.querySelector(".report-head .progress");
  if (old) old.outerHTML = progressBlock(r);
}

// 수정안 패널: ⑤가 window.renderFixPanel(issue, element)를 만들면 그걸 사용한다.
function showFix(iss, panel) {
  if (typeof window.renderFixPanel === "function") {
    window.renderFixPanel(iss, panel);
    return;
  }
  const label = iss.direction === "code" ? "코드 수정안" : "문서 개정안";
  panel.innerHTML = `
    <div class="fix-placeholder">
      <b>${label}</b> 패널 자리 (⑤ 담당: diff 표시, 다이어그램 전후 비교)
      ${iss.fix ? `<pre>${esc(JSON.stringify(iss.fix, null, 2))}</pre>` : `<div>아직 수정안 데이터가 없습니다.</div>`}
    </div>`;
}

// ===== 시작 =====
initTheme();
const PAGE = document.body.dataset.page;
if (PAGE === "login") {
  renderLogin();
} else if (requireLogin()) {
  showModeBadge();
  addLogoutButton();
  if (PAGE === "list") renderList();
  if (PAGE === "report") renderReport();
}
