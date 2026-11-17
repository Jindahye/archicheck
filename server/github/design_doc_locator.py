"""설계 문서 탐색 (DESIGN.md 3.5)."""


class DesignDocLocator:
    def locate(self, repo, ref) -> list:
        """.archicheck.yml을 우선 사용하고, 없으면 자동 탐색한다."""
        raise NotImplementedError

    def _read_config(self, repo, ref):
        raise NotImplementedError

    def _auto_detect(self, repo, ref) -> list:
        raise NotImplementedError
