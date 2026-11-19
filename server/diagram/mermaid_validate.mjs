// Mermaid 문법 검사기. diagram_validator.py(DiagramValidator)가 실행한다.
// 사용법: node mermaid_validate.mjs < 다이어그램.mmd
// 종료 코드: 0 = 문법 정상, 1 = 문법 오류(오류 메시지를 표준출력에 씀), 2 = 검사기 자체 오류
// mermaid.parse는 브라우저 화면(DOM)이 필요해서 jsdom으로 가짜 화면을 만든다. (크롬 불필요)
let mermaid;
try {
  const { JSDOM } = await import("jsdom");
  const dom = new JSDOM("<!DOCTYPE html><body></body>");
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  ({ default: mermaid } = await import("mermaid"));
  mermaid.initialize({ startOnLoad: false });
} catch (e) {
  process.stderr.write(`검사기 준비 실패: ${e?.message || e}\n`);
  process.exit(2);
}

let code = "";
for await (const chunk of process.stdin) code += chunk;

try {
  await mermaid.parse(code);
  process.exit(0);
} catch (e) {
  process.stdout.write(String(e?.message || e));
  process.exit(1);
}
