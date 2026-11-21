// 대시보드 단위 테스트 (DESIGN.md 4장: 각 담당자 자기 모듈 단위 테스트, ④ dashboard/)
//
// 실행 (레포 루트에서):  node --test dashboard/tests/app.test.js
// 필요: Node.js 18 이상. 추가 패키지 없음 (Node 내장 node:test, node:assert, node:vm 만 사용)
//
// app.js는 브라우저용 스크립트라서, 브라우저 대신 쓰는 가짜 location·document·fetch·sessionStorage를
// 만들어 그 안에서 app.js를 실행한 뒤 함수들을 꺼내 검사한다. 실제 서버나 네트워크는 쓰지 않는다.

process.env.TZ = "Asia/Seoul"; // formatDate가 한국 시간 기준으로 나오는지 보려고 고정

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const DASHBOARD = path.join(__dirname, "..");
const APP_JS = fs.readFileSync(path.join(DASHBOARD, "app.js"), "utf8");
const SAMPLE_JS = fs.readFileSync(path.join(DASHBOARD, "sample-data.js"), "utf8");

const EXPORTS = [
  "USE_SAMPLE", "api", "auth", "ApiError", "getJson", "reportErrorMessage", "fixErrorMessage",
  "requireLogin", "safeNextPage", "esc", "statusBadge", "formatDate", "githubLink", "issueStats",
  "bindIssueButtons",
];

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    _data: data,
  };
}

/**
 * 가짜 브라우저에서 app.js를 실행한다.
 * url: 화면 주소 (file:// 이면 샘플 모드, http:// 이면 API 모드)
 * fetch: 가짜 fetch (요청 기록은 env.requests에 남는다)
 */
function loadApp({ url = "http://localhost:8000/dashboard/index.html", fetch, session } = {}) {
  const u = new URL(url);
  const env = { requests: [], replaced: [] };
  const location = {
    protocol: u.protocol,
    pathname: u.pathname,
    search: u.search,
    href: u.href,
    replace: (to) => env.replaced.push(to),
  };
  const document = {
    documentElement: { dataset: {} },
    body: { dataset: { page: "test" } },      // 화면을 그리지 않게 "test"로 둔다
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  const context = {
    location,
    document,
    sessionStorage: session || memoryStorage(),
    localStorage: memoryStorage(),
    matchMedia: () => ({ matches: false }),
    fetch: async (reqUrl, options = {}) => {
      env.requests.push({ url: reqUrl, ...options });
      if (!fetch) throw new Error("fetch가 준비되지 않았습니다");
      return fetch(reqUrl, options);
    },
    URLSearchParams, URL, TextEncoder, structuredClone, setTimeout, clearTimeout, console,
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(SAMPLE_JS, context, { filename: "sample-data.js" });
  const app = vm.runInContext(`${APP_JS}\n;({ ${EXPORTS.join(", ")} })`, context, { filename: "app.js" });
  env.replaced.length = 0;                     // app.js가 시작하면서 한 이동은 지운다
  return { app, env, context };
}

/** 가짜 서버 응답 */
function response(status, body = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

// ---------------------------------------------------------------------------
// 샘플/API 모드 자동 전환
// ---------------------------------------------------------------------------
test.describe("샘플/API 모드 자동 전환", () => {
  test.it("파일로 열면(file://) 샘플 모드", () => {
    const { app } = loadApp({ url: "file:///C:/archicheck/dashboard/index.html" });
    assert.equal(app.USE_SAMPLE, true);
  });

  test.it("서버 주소(http://)로 열면 API 모드", () => {
    const { app } = loadApp({ url: "http://localhost:8000/dashboard/index.html" });
    assert.equal(app.USE_SAMPLE, false);
  });

  test.it("?sample=1을 붙이면 샘플 모드이고, 다른 화면으로 옮겨도 유지된다", () => {
    const session = memoryStorage();
    const first = loadApp({ url: "http://127.0.0.1:5500/dashboard/login.html?sample=1", session });
    assert.equal(first.app.USE_SAMPLE, true);
    const next = loadApp({ url: "http://127.0.0.1:5500/dashboard/index.html", session });
    assert.equal(next.app.USE_SAMPLE, true);
  });
});

// ---------------------------------------------------------------------------
// 화면에 보여 주는 값
// ---------------------------------------------------------------------------
test.describe("화면 표시 도우미", () => {
  const { app } = loadApp();

  test.it("issueStats: 불일치 전체·결정 대기·코드 수정·문서 개정 개수를 센다", () => {
    const report = {
      issues: [
        { id: "iss_1", direction: null },
        { id: "iss_2", direction: "code" },
        { id: "iss_3", direction: "doc" },
        { id: "iss_4", direction: "doc" },
      ],
    };
    assert.deepEqual({ ...app.issueStats(report) }, { total: 4, pending: 1, code: 1, doc: 2, resolved: 0 });
  });

  test.it("issueStats: issues가 없으면 모두 0 (3.3 형식에 없는 필드는 쓰지 않는다)", () => {
    assert.deepEqual({ ...app.issueStats({ issueCount: 9 }) }, { total: 0, pending: 0, code: 0, doc: 0, resolved: 0 });
  });

  test.it("statusBadge: 3.3의 status 4가지를 한국어로 보여 준다", () => {
    assert.match(app.statusBadge("analyzing"), /분석 중/);
    assert.match(app.statusBadge("done"), /분석 완료/);
    assert.match(app.statusBadge("resolved"), /조치 완료/);
    assert.match(app.statusBadge("failed"), /실패/);
  });

  test.it("esc: HTML 특수 문자를 바꿔서 화면에 그대로 끼워 넣어도 안전하다", () => {
    assert.equal(app.esc(`<img src=x onerror="a">&'`), "&lt;img src=x onerror=&quot;a&quot;&gt;&amp;&#39;");
    assert.equal(app.esc(null), "");
  });

  test.it("statusBadge: 모르는 status 값도 HTML로 해석되지 않는다", () => {
    assert.ok(!app.statusBadge("<script>").includes("<script>"));
  });

  test.it("formatDate: 분 단위 한국 시간으로 보여 주고, 형식이 틀리면 원래 값을 보여 준다", () => {
    assert.match(app.formatDate("2026-11-18T14:20:00+09:00"), />2026-11-18 14:20</);
    assert.equal(app.formatDate("어제"), "어제");
  });

  test.it("githubLink: 레포·커밋·경로로 GitHub 파일 링크를 만들고, #섹션은 GitHub 제목 앵커로 바꾼다", () => {
    const html = app.githubLink("owner/target-repo", "a1b2c3d", "docs/architecture.md#인증 흐름");
    const href = html.match(/href="([^"]+)"/)[1];
    assert.equal(
      href,
      "https://github.com/owner/target-repo/blob/a1b2c3d/docs/architecture.md#" + encodeURIComponent("인증-흐름"),
    );
    assert.match(html, />docs\/architecture\.md#인증 흐름</);
  });

  test.it("githubLink: 경로가 없으면 '-'를 보여 준다", () => {
    assert.match(app.githubLink("owner/repo", "abc", null), />-</);
  });
});

// ---------------------------------------------------------------------------
// 로그인과 401 처리 (DESIGN.md 3.4 화면 ④)
// ---------------------------------------------------------------------------
test.describe("로그인과 401 처리", () => {
  test.it("API가 401이면 로그인 화면으로 보내고, 원래 보던 주소를 next로 넘긴다", async () => {
    const { app, env } = loadApp({
      url: "http://localhost:8000/dashboard/report.html?id=rpt_12_a1b2c3",
      fetch: async () => response(401, { detail: "Login required" }),
    });
    await assert.rejects(app.api.getReport("rpt_12_a1b2c3"), (e) => e.status === 401);
    assert.deepEqual(env.replaced, ["login.html?next=" + encodeURIComponent("report.html?id=rpt_12_a1b2c3")]);
  });

  test.it("로그인 후 돌아갈 주소는 대시보드 화면만 허용한다", () => {
    const { app } = loadApp();
    assert.equal(app.safeNextPage("report.html?id=rpt_12_a1b2c3"), "report.html?id=rpt_12_a1b2c3");
    assert.equal(app.safeNextPage("index.html"), "index.html");
    assert.equal(app.safeNextPage("https://evil.example/phish"), "index.html");
    assert.equal(app.safeNextPage("//evil.example"), "index.html");
    assert.equal(app.safeNextPage(null), "index.html");
  });

  test.it("API 모드 로그인: POST /api/login에 { password }를 JSON으로 보낸다", async () => {
    const { app, env } = loadApp({ fetch: async () => response(200, { status: "ok" }) });
    await app.auth.login("naver1234");
    assert.equal(env.requests[0].url, "/api/login");
    assert.equal(env.requests[0].method, "POST");
    assert.equal(env.requests[0].credentials, "same-origin");
    assert.deepEqual(JSON.parse(env.requests[0].body), { password: "naver1234" });
  });

  test.it("API 모드 로그인: 비밀번호가 틀리면(401) 안내 문구로 실패한다", async () => {
    const { app } = loadApp({ fetch: async () => response(401, { detail: "Invalid password" }) });
    await assert.rejects(app.auth.login("wrong"), /비밀번호가 맞지 않습니다/);
  });

  test.it("API 모드 로그인: 서버에 닿지 않으면 연결 실패 안내", async () => {
    const { app } = loadApp({ fetch: async () => { throw new TypeError("Failed to fetch"); } });
    await assert.rejects(app.auth.login("x"), /서버에 연결하지 못했습니다/);
  });

  test.it("API 모드 로그아웃: POST /api/logout을 부른다", async () => {
    const { app, env } = loadApp({ fetch: async () => response(200, { status: "ok" }) });
    await app.auth.logout();
    assert.equal(env.requests[0].url, "/api/logout");
    assert.equal(env.requests[0].method, "POST");
  });

  test.it("샘플 모드 로그인: 서버를 부르지 않고 아무 비밀번호나 통과한다", async () => {
    const { app, env, context } = loadApp({ url: "file:///C:/archicheck/dashboard/login.html" });
    await app.auth.login("아무거나");
    assert.equal(env.requests.length, 0);
    assert.equal(context.sessionStorage.getItem("archicheck-sample-login"), "1");
  });

  test.it("샘플 모드: 로그인 전에 화면을 열면 로그인 화면으로 보낸다", () => {
    const { app, env } = loadApp({ url: "file:///C:/archicheck/dashboard/index.html" });
    assert.equal(app.requireLogin(), false);
    assert.equal(env.replaced.length, 1);
  });

  test.it("API 모드: 화면에서 막지 않고 서버의 401에 맡긴다 (세션 쿠키는 HttpOnly라 화면에서 읽을 수 없음)", () => {
    const { app, env } = loadApp();
    assert.equal(app.requireLogin(), true);
    assert.equal(env.replaced.length, 0);
  });
});

// ---------------------------------------------------------------------------
// 서버 API 연결 (DESIGN.md 3.4)
// ---------------------------------------------------------------------------
test.describe("서버 API 연결", () => {
  test.it("목록·상세를 3.4의 주소로 요청한다", async () => {
    const { app, env } = loadApp({ fetch: async () => response(200, []) });
    await app.api.listReports();
    await app.api.getReport("rpt 1/2");
    assert.equal(env.requests[0].url, "/api/reports");
    assert.equal(env.requests[1].url, "/api/reports/" + encodeURIComponent("rpt 1/2"));
  });

  test.it("수정안 요청에 방향을 보내고 수정안과 리포트 상태를 받는다", async () => {
    const fix = { diff: "--- a\n+++ b" };
    const payload = { direction: "code", fix, status: "done" };
    const { app, env } = loadApp({ fetch: async () => response(200, payload) });
    const result = await app.api.requestFix("rpt_14_d4e5f6", "iss_1", "code");
    assert.equal(env.requests[0].url, "/api/reports/rpt_14_d4e5f6/issues/iss_1/fix");
    assert.equal(env.requests[0].method, "POST");
    assert.deepEqual(JSON.parse(env.requests[0].body), { direction: "code" });
    assert.deepEqual(result, payload);
  });

  test.it("서버 오류는 상태 코드를 담은 ApiError로 알려 준다", async () => {
    const { app } = loadApp({ fetch: async () => response(500) });
    await assert.rejects(app.api.listReports(), (e) => e instanceof app.ApiError && e.status === 500);
  });

  test.it("샘플 모드: sample-data.js의 리포트를 복사해서 돌려준다 (원본이 바뀌지 않게)", async () => {
    const { app, context } = loadApp({ url: "file:///C:/archicheck/dashboard/index.html" });
    const list = await app.api.listReports();
    assert.equal(list.length, context.SAMPLE_REPORTS.length);
    list[0].title = "바뀜";
    assert.notEqual(context.SAMPLE_REPORTS[0].title, "바뀜");
  });

  test.it("샘플 모드: 없는 리포트는 오류로 알려 준다", async () => {
    const { app } = loadApp({ url: "file:///C:/archicheck/dashboard/index.html" });
    await assert.rejects(app.api.getReport("없는 id"), /찾을 수 없습니다/);
  });
});

// ---------------------------------------------------------------------------
// 오류 안내 문구
// ---------------------------------------------------------------------------
test.describe("오류 안내 문구", () => {
  const { app } = loadApp();
  const err = (status) => new app.ApiError(status, `서버가 ${status} 오류를 돌려줬습니다.`);

  test.it("수정안 요청 실패: 서버 오류 코드마다 무슨 일인지 알려 준다", () => {
    assert.match(app.fixErrorMessage(err(404)), /파일을 찾지 못했습니다/);
    assert.match(app.fixErrorMessage(err(409)), /분석 중이거나 분석에 실패한/);
    assert.match(app.fixErrorMessage(err(422)), /위치가 없어/);
    assert.match(app.fixErrorMessage(err(502)), /AI가 수정안을 만들지 못했습니다/);
    assert.match(app.fixErrorMessage(err(503)), /수정안 기능을 쓸 수 없습니다/);
  });

  test.it("수정안 요청 실패: 정해지지 않은 코드는 원래 메시지를 보여 준다", () => {
    assert.equal(app.fixErrorMessage(err(500)), "서버가 500 오류를 돌려줬습니다.");
  });

  test.it("리포트 조회 실패: 404면 리포트를 찾을 수 없다고 알려 준다", () => {
    assert.match(app.reportErrorMessage(err(404)), /리포트를 찾을 수 없습니다/);
    assert.equal(app.reportErrorMessage(err(500)), "서버가 500 오류를 돌려줬습니다.");
  });
});

// ---------------------------------------------------------------------------
// 조치 완료 반영
// ---------------------------------------------------------------------------
test.describe("조치 완료와 취소", () => {
  function reportWithControls({ resolutionStatus = 200, alreadyResolved = false } = {}) {
    const fix = { diff: "x" };
    const loaded = loadApp({
      fetch: async (url, options) => {
        if (url.endsWith("/fix")) return response(200, { direction: "code", fix, status: "done" });
        const { resolved } = JSON.parse(options.body);
        return response(resolutionStatus, {
          status: resolved ? "resolved" : "done",
          resolutions: { iss_1: resolved },
        });
      },
    });
    const issue = { id: "iss_1", direction: alreadyResolved ? "code" : null, fix: alreadyResolved ? fix : null };
    const report = { id: "rpt", status: alreadyResolved ? "resolved" : "done", issues: [issue] };
    const listeners = {};
    const button = (name, dataset) => ({
      dataset,
      classList: { toggle: (key, value) => { resolve[key] = value; } },
      addEventListener: (event, fn) => { listeners[name] = fn; },
      setAttribute: () => {},
    });
    const resolve = button("resolve");
    const code = button("code", { dir: "code" });
    const badge = { outerHTML: loaded.app.statusBadge(report.status) };
    const progress = {};
    const note = { classList: { add() {}, remove() {} } };
    const panel = {};
    const card = {
      dataset: { issue: "iss_1" },
      querySelector: (sel) => ({
        ".fix-panel": panel, ".choice": note, "[data-resolution]": resolve, "[data-resolution-note]": note,
      })[sel],
      querySelectorAll: () => [code],
    };
    const doc = loaded.context.document;
    doc.querySelector = (sel) => ({
      ".report-head .status": badge, ".report-head .progress": progress,
    })[sel];
    doc.querySelectorAll = () => [card];
    loaded.app.bindIssueButtons(report);
    return { ...loaded, report, issue, listeners, resolve, badge, progress, note, panel };
  }

  test.it("수정안 생성, 완료, 취소, 재완료 시 버튼과 배지 및 진행도가 갱신된다", async () => {
    const { report, issue, listeners, resolve, badge, progress, panel, env } = reportWithControls();
    assert.equal(resolve.disabled, true);
    assert.equal(resolve.textContent, "조치 완료");

    await listeners.code();
    assert.equal(report.status, "done");
    assert.equal(resolve.disabled, false);
    assert.equal(env.requests.length, 1);
    const proposal = panel.innerHTML;

    const saving = listeners.resolve();
    assert.equal(resolve.disabled, true);
    await listeners.resolve();
    await saving;
    assert.equal(env.requests.length, 2);
    assert.equal(env.requests[1].url, "/api/reports/rpt/issues/iss_1/resolution");
    assert.equal(env.requests[1].method, "PUT");
    assert.deepEqual(JSON.parse(env.requests[1].body), {
      resolved: true, reviewed: { direction: "code", fix: { diff: "x" } },
    });
    assert.equal(resolve.textContent, "조치 완료 취소");
    assert.equal(resolve.primary, false);
    assert.match(badge.outerHTML, /조치 완료/);
    assert.match(progress.outerHTML, /aria-valuenow="1"/);

    await listeners.resolve();
    assert.deepEqual(JSON.parse(env.requests[2].body), { resolved: false });
    assert.equal(resolve.textContent, "조치 완료");
    assert.equal(resolve.primary, true);
    assert.match(badge.outerHTML, /분석 완료/);
    assert.match(progress.outerHTML, /aria-valuenow="0"/);
    assert.deepEqual(issue.fix, { diff: "x" });
    assert.equal(panel.innerHTML, proposal);

    await listeners.resolve();
    assert.equal(report.status, "resolved");
    assert.equal(resolve.textContent, "조치 완료 취소");
  });

  test.it("취소 요청 실패 시 완료 상태와 수정안을 유지하고 재시도를 안내한다", async () => {
    const { report, issue, listeners, resolve, note } = reportWithControls({
      resolutionStatus: 500, alreadyResolved: true,
    });
    assert.equal(resolve.textContent, "조치 완료 취소");
    await listeners.resolve();
    assert.equal(report.status, "resolved");
    assert.equal(resolve.textContent, "조치 완료 취소");
    assert.equal(resolve.disabled, false);
    assert.deepEqual(issue.fix, { diff: "x" });
    assert.match(note.textContent, /다시 시도/);
  });

  test.it("샘플의 완료 취소도 같은 탭에서 다시 불러오면 유지된다", async () => {
    const url = "file:///C:/archicheck/dashboard/index.html";
    const session = memoryStorage();
    const { app } = loadApp({ url, session });
    const report = (await app.api.listReports()).find((item) => item.status === "resolved");
    await app.api.setIssueResolution(report.id, report.issues[0], false);
    const { app: reloaded } = loadApp({ url, session });
    const reopened = await reloaded.api.getReport(report.id);
    assert.equal(reopened.status, "done");
    assert.equal(reopened.issues[0].resolved, false);
    assert.equal(reopened.issues[0].fix.after, report.issues[0].fix.after);
  });
});
