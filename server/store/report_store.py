"""SQLite 기반 리포트 저장소."""


class ReportStore:
    def save(self, report):
        raise NotImplementedError

    def get(self, report_id):
        raise NotImplementedError

    def list(self) -> list:
        raise NotImplementedError
