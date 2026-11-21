"""PR 코멘트 본문 생성.

⑤가 prompts/에 PR 코멘트 템플릿을 만들면 이 모듈을 그 템플릿으로 교체한다.
그 전까지 쓰는 기본 형식이다 (DESIGN.md 3.1: 요약 + 사용한 설계 문서 + 대시보드 링크).
"""
from __future__ import annotations

DASHBOARD_PATH = "/dashboard/report.html?id="  # TODO: ④와 실제 리포트 상세 경로 확인


def report_url(base_url: str, report_id: str) -> str | None:
    """대시보드 링크. PUBLIC_BASE_URL이 없거나 http(s) 주소가 아니면 None (깨진 링크 방지)."""
    if not base_url or not base_url.startswith(("http://", "https://")):
        return None
    return f"{base_url.rstrip('/')}{DASHBOARD_PATH}{report_id}"


def format_report_comment(report: dict, base_url: str) -> str:
    """리포트 → 코멘트. 분석기 결과에 필드가 빠져 있어도 예외 없이 만든다."""
    lines = [f"🤖 **변경 분석 리포트** (PR #{report.get('pr', '?')})", ""]

    docs = report.get("designDocs") or []
    if docs:
        lines.append("사용한 설계 문서: " + ", ".join(f"`{d}`" for d in docs))
    else:
        lines.append("⚠ 설계 문서를 찾지 못함, `.archicheck.yml`로 지정 필요")
    lines.append("")

    summary = report.get("summary") or {}
    changes = summary.get("actualChanges") or []
    if changes:
        lines.append("**① 변경 설명**")
        lines += [f"- {c}" for c in changes]
        if summary.get("unmentionedChanges"):
            lines.append(f"- ⚠ 커밋 메시지에 없는 변경 {summary['unmentionedChanges']}건 포함")
        lines.append("")

    impact = [i for i in (report.get("impact") or []) if isinstance(i, dict)]
    if impact:
        lines.append("**② 영향 범위**")
        for i in impact:
            target = " ".join(x for x in (f"`{i['file']}`" if i.get("file") else "", i.get("symbol") or "") if x)
            reason = i.get("reason") or ""
            lines.append(f"- {target}: {reason}" if target and reason else f"- {target or reason or '(내용 없음)'}")
        lines.append("")

    issues = [i for i in (report.get("issues") or []) if isinstance(i, dict)]
    lines.append(f"**③ 설계 정합성** 불일치 {len(issues)}건")
    lines += [f"- {i.get('title') or i.get('detail') or '(제목 없음)'}" for i in issues]

    url = report_url(base_url, report.get("id", ""))
    if url:
        lines += ["", f"👉 수정 방향 선택: {url}"]
    return "\n".join(lines)


# 실패 종류(리포트 error, DESIGN.md 3.3)별 안내. 예외 원문은 공개 PR에 쓰지 않는다.
FAILURE_GUIDE = {
    "no_design_doc": "설계 문서를 찾지 못했습니다. 레포 루트에 `.archicheck.yml`을 두고 `design_docs:`에 "
                     "설계 문서 경로를 적어 주세요 (경로가 실제 파일과 맞는지도 확인하세요). 커밋을 다시 올리면 새로 분석합니다.",
    "github_error": "GitHub에서 PR 정보나 파일을 가져오지 못했습니다. 잠시 뒤 커밋을 다시 올리면 새로 분석합니다.",
    "ai_error": "AI 분석 중 오류가 났습니다 (응답 지연, 사용량 초과 등). 잠시 뒤 커밋을 다시 올리면 새로 분석합니다.",
}


def format_failure_comment(report_id: str = "", error: str | None = None) -> str:
    """실패 안내. 실패 종류별 정해진 문구만 쓰고, 오류 원문은 서버 로그에만 남긴다."""
    ref = f" (리포트 `{report_id}`)" if report_id else ""
    guide = FAILURE_GUIDE.get(error or "", "분석 중 오류가 발생했습니다. 자세한 원인은 서버 로그에서 확인할 수 있습니다.")
    return f"🤖 **변경 분석 실패**{ref}\n\n{guide}"
