// 수정안 패널 단위 테스트 (⑤ dashboard/fix-panel.js, DESIGN.md 3.3 issues[].fix)
//
// 실행 (레포 루트에서):  node --test dashboard/tests/fix-panel.test.js
// 필요: Node.js 18 이상. 추가 패키지 없음 (node:test, node:assert, node:vm 만 사용)
//
// fix-panel.js는 브라우저용 스크립트라서 가짜 window 안에서 실행한 뒤 함수들을 꺼내 검사한다.
// CDN(diff2html, mermaid)은 부르지 않는다. 가짜 환경에는 document가 없어서 대체 화면이 쓰인다.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const DASHBOARD = path.join(__dirname, "..");
const PANEL_JS = fs.readFileSync(path.join(DASHBOARD, "fix-panel.js"), "utf8");
const SAMPLE_JS = fs.readFileSync(path.join(DASHBOARD, "sample-data.js"), "utf8");

// vm 안에서 만든 배열은 프로토타입이 달라 deepEqual이 실패하므로 이쪽 배열로 옮긴다
const plain = (v) => JSON.parse(JSON.stringify(v));

function load() {
  const window = {};
  const ctx = vm.createContext({ window, URL, console });
  vm.runInContext(PANEL_JS, ctx);
  return window;
}

// innerHTML만 받는 가짜 요소
function fakeEl() {
  return { innerHTML: "" };
}

const CODE_DIFF = [
  "--- a/src/user/service.py",
  "+++ b/src/user/service.py",
  "@@ -1,4 +1,4 @@",
  " def get_user(user_id):",
  "-    return db.query(User).get(user_id)",
  "+    return UserRepository().find(user_id)",
  " ",
  " # end",
  "--- /dev/null",
  "+++ b/src/user/repository.py",
  "@@ -0,0 +1,2 @@",
  "+class UserRepository:",
  "+    pass",
].join("\n");

test("window.renderFixPanel 을 app.js가 찾을 수 있게 등록한다", () => {
  const w = load();
  assert.equal(typeof w.renderFixPanel, "function");
  assert.equal(typeof w.ArchiCheckFixPanel.lineDiff, "function");
});

test("CDN은 버전을 고정하고, mermaid는 서버 DiagramValidator와 같은 버전이다", () => {
  const { LIBS } = load().ArchiCheckFixPanel;
  assert.match(LIBS.diff2htmlJs, /diff2html@\d+\.\d+\.\d+\//);
  const pkg = JSON.parse(fs.readFileSync(path.join(DASHBOARD, "..", "server", "diagram", "package-lock.json"), "utf8"));
  const serverMermaid = pkg.packages["node_modules/mermaid"].version;
  assert.ok(LIBS.mermaidJs.includes(`mermaid@${serverMermaid}/`), `서버 mermaid ${serverMermaid}와 다름: ${LIBS.mermaidJs}`);
});

test("lineDiff: 같은 줄·지운 줄·추가한 줄을 구분한다", () => {
  const { lineDiff } = load().ArchiCheckFixPanel;
  const rows = lineDiff("a\nb\nc", "a\nB\nc\nd");
  assert.deepEqual(plain(rows.map((r) => r.type + ":" + r.text)), ["same:a", "del:b", "add:B", "same:c", "add:d"]);
  assert.deepEqual(plain(lineDiff("", "x").map((r) => r.type)), ["add"]);
  assert.deepEqual(plain(lineDiff("x\r\ny", "x\ny").map((r) => r.type)), ["same", "same"]); // Windows 줄바꿈
});

test("parseUnifiedDiff: 파일별로 나누고 줄 번호를 매긴다", () => {
  const { parseUnifiedDiff } = load().ArchiCheckFixPanel;
  const files = parseUnifiedDiff(CODE_DIFF);
  assert.equal(files.length, 2);
  assert.equal(files[0].newPath, "src/user/service.py");
  assert.equal(files[1].oldPath, "/dev/null");
  const del = files[0].lines.find((l) => l.type === "del");
  const add = files[0].lines.find((l) => l.type === "add");
  assert.equal(del.oldNo, 2);
  assert.equal(add.newNo, 2);
  assert.equal(files[1].lines.filter((l) => l.type === "add").length, 2);
});

test("코드 수정안: diff 화면(빨강·초록 줄)과 파일 이름·통계를 그린다", () => {
  const w = load();
  const el = fakeEl();
  w.renderFixPanel({ direction: "code", fix: { diff: CODE_DIFF } }, el);
  assert.match(el.innerHTML, /코드 수정안/);
  assert.match(el.innerHTML, /class="fp-del"/);
  assert.match(el.innerHTML, /class="fp-add"/);
  assert.match(el.innerHTML, /src\/user\/repository\.py \(새 파일\)/);
  assert.match(el.innerHTML, /\+3<\/span><span class="fp-stat del">−1/);
  assert.doesNotMatch(el.innerHTML, /"diff":/); // JSON 글자로 보이지 않는다
});

test("문서 개정안: 기존 문구와 수정 문구를 나란히 놓고 바뀐 줄을 표시한다", () => {
  const w = load();
  // sample-data.js의 실제 예시(rpt_11, 로그아웃 API 추가)를 그대로 쓴다
  const sctx = vm.createContext({ window: {} });
  vm.runInContext(SAMPLE_JS + "\n;window.__r = typeof SAMPLE_REPORTS !== 'undefined' ? SAMPLE_REPORTS : window.SAMPLE_REPORTS;", sctx);
  const reports = sctx.window.__r;
  const iss = reports.flatMap((r) => r.issues).find((i) => i.fix && i.direction === "doc");
  assert.ok(iss, "sample-data.js에 문서 개정안 예시가 있어야 한다");

  const el = fakeEl();
  w.renderFixPanel(iss, el);
  assert.match(el.innerHTML, /문서 개정안/);
  assert.match(el.innerHTML, /기존 문구/);
  assert.match(el.innerHTML, /수정 문구/);
  assert.match(el.innerHTML, /fp-line fp-add">\| POST \| \/auth\/logout \| 로그아웃 \|/);
  assert.doesNotMatch(el.innerHTML, /갱신된 다이어그램/); // mermaid가 null이면 그림 칸 없음
});

test("문서 개정안에 mermaid가 있으면 다이어그램 칸과 코드 보기를 만든다", () => {
  const w = load();
  const el = fakeEl();
  w.renderFixPanel({
    direction: "doc",
    fix: { before: "로그인", after: "로그인\n로그아웃", mermaid: "sequenceDiagram\n  C->>S: logout" },
  }, el);
  assert.match(el.innerHTML, /갱신된 다이어그램/);
  assert.match(el.innerHTML, /data-role="mermaid"/);
  assert.match(el.innerHTML, /C-&gt;&gt;S: logout/); // 코드는 이스케이프되어 들어간다
});

test("AI가 만든 글자에 HTML이 섞여 있어도 태그로 실행되지 않는다", () => {
  const w = load();
  const el = fakeEl();
  w.renderFixPanel({ direction: "doc", fix: { before: "<b>x</b>", after: "<img src=x onerror=alert(1)>", mermaid: null } }, el);
  assert.doesNotMatch(el.innerHTML, /<img/);
  assert.match(el.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);

  const el2 = fakeEl();
  w.renderFixPanel({ direction: "code", fix: { diff: "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-<script>a()</script>\n+ok" } }, el2);
  assert.doesNotMatch(el2.innerHTML, /<script>/);
});

test("수정안이 아직 없으면(샘플 모드 등) 안내 문구를 보여 준다", () => {
  const w = load();
  const el = fakeEl();
  w.renderFixPanel({ direction: "code", fix: null }, el);
  assert.match(el.innerHTML, /코드 수정안<\/b>을 아직 받지 못했습니다/);
});

test("모르는 형식이면 원본 데이터를 그대로 보여 준다", () => {
  const w = load();
  const el = fakeEl();
  w.renderFixPanel({ direction: "doc", fix: { foo: 1 } }, el);
  assert.match(el.innerHTML, /알 수 없는 수정안 형식/);
  assert.match(el.innerHTML, /&quot;foo&quot;: 1/);
});

test("report.html이 app.js보다 먼저 fix-panel.js를 불러온다", () => {
  const html = fs.readFileSync(path.join(DASHBOARD, "report.html"), "utf8");
  const panel = html.indexOf('src="fix-panel.js');
  const app = html.indexOf('src="app.js');
  assert.ok(panel !== -1, "report.html에 fix-panel.js script 태그가 없다");
  assert.ok(panel < app, "fix-panel.js가 app.js보다 먼저 와야 한다");
});
