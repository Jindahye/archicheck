// ArchiCheck 수정안 패널 (⑤ 담당, DESIGN.md 3.3 issues[].fix, 3.7)
//
// app.js의 showFix()가 window.renderFixPanel(issue, element)를 호출하면 수정안을 그린다.
//   - 코드 수정안  fix = { diff }                     → diff 화면 (빨강 = 지운 줄, 초록 = 추가한 줄)
//   - 문서 개정안  fix = { before, after, mermaid }   → 기존 문구 | 수정 문구 나란히 비교 + 다이어그램 그림
//
// 그림 도구는 CDN에서 필요할 때만 불러온다 (설계 문서 2장 기술 스택: diff2html, mermaid.js).
//   - diff2html 3.4.56: 코드 diff 화면
//   - mermaid 12.3.0:   다이어그램. 서버 DiagramValidator(server/diagram/package.json)와 같은 버전
// CDN을 못 불러오면(인터넷 차단 등) 이 파일에 있는 간단한 화면으로 대신 보여 준다.
(function () {
  "use strict";

  const LIBS = {
    diff2htmlJs: "https://cdn.jsdelivr.net/npm/diff2html@3.4.56/bundles/js/diff2html.min.js",
    diff2htmlCss: "https://cdn.jsdelivr.net/npm/diff2html@3.4.56/bundles/css/diff2html.min.css",
    mermaidJs: "https://cdn.jsdelivr.net/npm/mermaid@12.3.0/dist/mermaid.min.js",
  };

  // 이 파일과 같은 폴더의 fix-panel.css를 불러온다 (report.html은 script 한 줄만 추가하면 되도록)
  const SELF_SRC = (typeof document !== "undefined" && document.currentScript && document.currentScript.src) || "";
  const CSS_URL = SELF_SRC ? new URL("fix-panel.css", SELF_SRC).href : "fix-panel.css";

  // ---------- 작은 도구 ----------
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  }

  function splitLines(text) {
    const s = String(text ?? "").replace(/\r\n?/g, "\n");
    if (s === "") return [];
    return s.endsWith("\n") ? s.slice(0, -1).split("\n") : s.split("\n");
  }

  // 줄 단위 비교 (LCS). 결과: [{ type: "same" | "del" | "add", text }]
  function lineDiff(beforeText, afterText) {
    const a = splitLines(beforeText);
    const b = splitLines(afterText);
    const n = a.length, m = b.length;
    // 문서 문구는 짧다. 너무 길면(표 전체 등) 계산량을 막기 위해 통째로 지움/추가로 본다.
    if (n * m > 400000) {
      return a.map((t) => ({ type: "del", text: t })).concat(b.map((t) => ({ type: "add", text: t })));
    }
    const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    const out = [];
    let i = 0, j = 0;
    while (i < n && j < m) {
      if (a[i] === b[j]) { out.push({ type: "same", text: a[i] }); i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: "del", text: a[i++] }); }
      else { out.push({ type: "add", text: b[j++] }); }
    }
    while (i < n) out.push({ type: "del", text: a[i++] });
    while (j < m) out.push({ type: "add", text: b[j++] });
    return out;
  }

  // unified diff 텍스트 → 파일별 줄 목록 (CDN 없이 보여 주는 대체 화면용)
  function parseUnifiedDiff(diffText) {
    const files = [];
    let file = null, oldNo = 0, newNo = 0;
    const startFile = () => { file = { oldPath: "", newPath: "", lines: [] }; files.push(file); };
    for (const line of splitLines(diffText)) {
      if (line.startsWith("diff --git ")) { startFile(); continue; }
      if (line.startsWith("--- ")) {
        if (!file || file.lines.length || file.oldPath) startFile();
        file.oldPath = line.slice(4).replace(/^a\//, "").trim();
        continue;
      }
      if (line.startsWith("+++ ")) {
        if (!file) startFile();
        file.newPath = line.slice(4).replace(/^b\//, "").trim();
        continue;
      }
      if (!file) startFile();
      const h = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/.exec(line);
      if (h) {
        oldNo = +h[1]; newNo = +h[2];
        file.lines.push({ type: "hunk", text: line });
      } else if (line.startsWith("+")) {
        file.lines.push({ type: "add", text: line.slice(1), newNo: newNo++ });
      } else if (line.startsWith("-")) {
        file.lines.push({ type: "del", text: line.slice(1), oldNo: oldNo++ });
      } else if (line.startsWith("\\")) {
        file.lines.push({ type: "meta", text: line });          // "\ No newline at end of file"
      } else if (/^(index |new file mode|deleted file mode|similarity |rename )/.test(line)) {
        continue;
      } else {
        file.lines.push({ type: "same", text: line.startsWith(" ") ? line.slice(1) : line, oldNo: oldNo++, newNo: newNo++ });
      }
    }
    return files.filter((f) => f.oldPath || f.newPath || f.lines.length);
  }

  function filePathLabel(f) {
    if (f.oldPath === "/dev/null") return `${f.newPath} (새 파일)`;
    if (f.newPath === "/dev/null") return `${f.oldPath} (삭제)`;
    if (f.oldPath && f.newPath && f.oldPath !== f.newPath) return `${f.oldPath} → ${f.newPath}`;
    return f.newPath || f.oldPath || "변경 내용";
  }

  function diffStats(files) {
    let add = 0, del = 0;
    files.forEach((f) => f.lines.forEach((l) => { if (l.type === "add") add++; if (l.type === "del") del++; }));
    return { add, del };
  }

  // ---------- 화면 조각 (HTML 문자열) ----------
  function statsHtml(add, del) {
    return `<span class="fp-stat add">+${add}</span><span class="fp-stat del">−${del}</span>`;
  }

  function copyButton(label, key) {
    return `<button type="button" class="fp-copy" data-copy="${key}">${esc(label)}</button>`;
  }

  // CDN 없이 쓰는 diff 화면
  function codeDiffFallbackHtml(diffText) {
    const files = parseUnifiedDiff(diffText);
    if (!files.length) return `<p class="fp-note">diff 내용이 비어 있습니다.</p>`;
    return files.map((f) => {
      const s = diffStats([f]);
      const rows = f.lines.map((l) => {
        if (l.type === "hunk") return `<tr class="fp-hunk"><td colspan="3">${esc(l.text)}</td></tr>`;
        if (l.type === "meta") return `<tr class="fp-meta"><td colspan="3">${esc(l.text)}</td></tr>`;
        const sign = l.type === "add" ? "+" : l.type === "del" ? "−" : " ";
        return `<tr class="fp-${l.type}"><td class="fp-no">${l.oldNo ?? ""}</td><td class="fp-no">${l.newNo ?? ""}</td>` +
          `<td class="fp-code"><span class="fp-sign" aria-hidden="true">${sign}</span>${esc(l.text)}</td></tr>`;
      }).join("");
      return `<div class="fp-file"><div class="fp-file-head"><span class="fp-path">${esc(filePathLabel(f))}</span>${statsHtml(s.add, s.del)}</div>` +
        `<div class="fp-scroll"><table class="fp-diff">${rows}</table></div></div>`;
    }).join("");
  }

  function codeFixHtml(fix) {
    const files = parseUnifiedDiff(fix.diff);
    const s = diffStats(files);
    return `
      <section class="fp fp-code-fix">
        <header class="fp-head">
          <h4>코드 수정안</h4>
          <span class="fp-sub">파일 ${files.length}개 · ${statsHtml(s.add, s.del)}</span>
          <span class="fp-spacer"></span>
          ${copyButton("diff 복사", "diff")}
        </header>
        <p class="fp-legend"><span class="fp-key del">빨강</span> 지운 줄 <span class="fp-key add">초록</span> 추가한 줄 · 코드는 자동으로 바뀌지 않습니다. 확인 후 직접 반영하세요.</p>
        <div class="fp-diff-host" data-role="diff">${codeDiffFallbackHtml(fix.diff)}</div>
      </section>`;
  }

  function sideHtml(rows, kind) {
    const keep = kind === "before" ? "del" : "add";
    const lines = rows.filter((r) => r.type === "same" || r.type === keep);
    if (!lines.length) return `<div class="fp-side-empty">(내용 없음)</div>`;
    return `<pre class="fp-text">${lines.map((r) =>
      `<span class="fp-line ${r.type === "same" ? "" : "fp-" + r.type}">${esc(r.text) || " "}</span>`).join("")}</pre>`;
  }

  function docFixHtml(fix) {
    const rows = lineDiff(fix.before, fix.after);
    const add = rows.filter((r) => r.type === "add").length;
    const del = rows.filter((r) => r.type === "del").length;
    const hasDiagram = typeof fix.mermaid === "string" && fix.mermaid.trim() !== "";
    return `
      <section class="fp fp-doc-fix">
        <header class="fp-head">
          <h4>문서 개정안</h4>
          <span class="fp-sub">${statsHtml(add, del)}</span>
          <span class="fp-spacer"></span>
          ${copyButton("수정 문구 복사", "after")}
        </header>
        <p class="fp-legend">설계 문서에서 <b>기존 문구</b>를 찾아 <b>수정 문구</b>로 바꾸면 됩니다. <span class="fp-key del">빨강</span> 바뀌는 줄 <span class="fp-key add">초록</span> 새 줄</p>
        <div class="fp-sbs">
          <div class="fp-side fp-before"><div class="fp-side-title">기존 문구</div>${sideHtml(rows, "before")}</div>
          <div class="fp-side fp-after"><div class="fp-side-title">수정 문구</div>${sideHtml(rows, "after")}</div>
        </div>
        ${hasDiagram ? `
        <div class="fp-diagram">
          <div class="fp-diagram-head">
            <span class="fp-side-title">갱신된 다이어그램</span>
            <span class="fp-spacer"></span>
            ${copyButton("Mermaid 코드 복사", "mermaid")}
          </div>
          <div class="fp-diagram-view" data-role="mermaid"><p class="fp-note">다이어그램을 그리는 중…</p></div>
          <details class="fp-src"><summary>Mermaid 코드 보기</summary><pre>${esc(fix.mermaid)}</pre></details>
        </div>` : ""}
      </section>`;
  }

  function emptyHtml(iss) {
    const label = iss && iss.direction === "code" ? "코드 수정안" : "문서 개정안";
    return `<div class="fp fp-empty"><b>${label}</b>을 아직 받지 못했습니다. ` +
      `샘플 모드에서는 서버를 부르지 않아 수정안이 비어 있습니다.</div>`;
  }

  function unknownHtml(fix) {
    return `<div class="fp fp-empty">알 수 없는 수정안 형식입니다. 원본 데이터를 그대로 보여 줍니다.` +
      `<pre>${esc(JSON.stringify(fix, null, 2))}</pre></div>`;
  }

  // fix 모양으로 판단한다 (direction보다 실제 데이터가 우선)
  function fixKind(iss) {
    const fix = iss && iss.fix;
    if (!fix || typeof fix !== "object") return "empty";
    if (typeof fix.diff === "string") return "code";
    if (typeof fix.before === "string" || typeof fix.after === "string") return "doc";
    return "unknown";
  }

  function panelHtml(iss) {
    const kind = fixKind(iss);
    if (kind === "code") return codeFixHtml(iss.fix);
    if (kind === "doc") return docFixHtml(iss.fix);
    if (kind === "unknown") return unknownHtml(iss.fix);
    return emptyHtml(iss);
  }

  // ---------- 외부 라이브러리 (필요할 때 한 번만 불러옴) ----------
  const loading = {};
  function loadOnce(url, kind) {
    if (loading[url]) return loading[url];
    loading[url] = new Promise((resolve, reject) => {
      if (typeof document === "undefined" || !document.head) return reject(new Error("no document"));
      const node = document.createElement(kind === "css" ? "link" : "script");
      if (kind === "css") { node.rel = "stylesheet"; node.href = url; }
      else { node.src = url; node.async = true; }
      node.onload = () => resolve();
      node.onerror = () => { delete loading[url]; reject(new Error("load failed: " + url)); };
      document.head.appendChild(node);
    });
    return loading[url];
  }

  function isDark() {
    const t = document.documentElement.dataset.theme;
    if (t) return t === "dark";
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  async function enhanceDiff(host, diffText) {
    try {
      await Promise.all([loadOnce(LIBS.diff2htmlJs, "js"), loadOnce(LIBS.diff2htmlCss, "css")]);
      if (!window.Diff2Html || !host.isConnected) return;
      // AI diff에는 "diff --git"·"new file mode" 줄이 없어서, 새 파일이 RENAMED로 표시된다 → 직접 표시를 고친다
      const files = window.Diff2Html.parse(diffText);
      files.forEach((f) => {
        if (f.oldName === "/dev/null") { f.isNew = true; f.isRename = false; }
        if (f.newName === "/dev/null") { f.isDeleted = true; f.isRename = false; }
      });
      host.innerHTML = window.Diff2Html.html(files, {
        drawFileList: false,
        outputFormat: "line-by-line",
        matching: "lines",
        colorScheme: isDark() ? "dark" : "light",
      });
      host.classList.add("fp-d2h");
    } catch (_) {
      // CDN 실패: 이미 그려 둔 대체 화면을 그대로 둔다
    }
  }

  let mermaidSeq = 0;
  async function enhanceMermaid(host, code) {
    try {
      await loadOnce(LIBS.mermaidJs, "js");
      const m = window.mermaid;
      if (!m) throw new Error("mermaid 없음");
      m.initialize({ startOnLoad: false, securityLevel: "strict", theme: isDark() ? "dark" : "default" });
      const { svg } = await m.render(`fp-mmd-${Date.now()}-${++mermaidSeq}`, code);
      if (host.isConnected) host.innerHTML = svg;
    } catch (e) {
      const msg = String((e && e.message) || "");
      const why = msg.startsWith("load failed") || msg === "no document"
        ? "다이어그램 도구(mermaid.js)를 불러오지 못했습니다 (인터넷 연결 확인)"
        : `다이어그램을 그림으로 그리지 못했습니다${msg ? `: ${esc(msg.split("\n")[0])}` : ""}`;
      host.innerHTML = `<p class="fp-note fp-warn">${why}. 아래 Mermaid 코드를 확인하세요.</p>`;
    }
  }

  function bindCopy(el, fix) {
    el.querySelectorAll(".fp-copy").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const text = fix[btn.dataset.copy] ?? "";
        const old = btn.textContent;
        try {
          await navigator.clipboard.writeText(text);
          btn.textContent = "복사했습니다";
        } catch (_) {
          btn.textContent = "복사 실패";
        }
        setTimeout(() => { btn.textContent = old; }, 1500);
      });
    });
  }

  // ---------- 진입점 ----------
  function renderFixPanel(iss, el) {
    if (!el) return;
    if (typeof document !== "undefined" && document.head) loadOnce(CSS_URL, "css").catch(() => {});
    el.innerHTML = panelHtml(iss);
    const kind = fixKind(iss);
    if (kind !== "code" && kind !== "doc") return;
    if (typeof el.querySelector !== "function") return;   // 테스트용 가짜 요소
    bindCopy(el, iss.fix);
    if (kind === "code") {
      const host = el.querySelector('[data-role="diff"]');
      if (host && iss.fix.diff.trim()) enhanceDiff(host, iss.fix.diff);
    } else {
      const host = el.querySelector('[data-role="mermaid"]');
      if (host) enhanceMermaid(host, iss.fix.mermaid);
    }
  }

  window.renderFixPanel = renderFixPanel;
  // 단위 테스트용 (dashboard/tests/fix-panel.test.js)
  window.ArchiCheckFixPanel = { esc, splitLines, lineDiff, parseUnifiedDiff, panelHtml, fixKind, LIBS };
})();
