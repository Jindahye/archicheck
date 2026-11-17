"""대시보드용 API (GET /api/reports, GET /api/reports/{id}, POST .../fix)."""


class DashboardAPI:
    def list_reports(self):
        raise NotImplementedError

    def get_report(self, id):
        raise NotImplementedError

    def request_fix(self, issue_id, direction):
        """direction: "code" 또는 "doc"."""
        raise NotImplementedError
