"""GitHub Webhook 수신 (POST /webhook/github)."""


class WebhookHandler:
    def receive(self, request):
        """pull_request 이벤트를 받아 분석을 시작한다."""
        raise NotImplementedError

    def _verify_signature(self, request) -> bool:
        """X-Hub-Signature-256 서명을 검증한다."""
        raise NotImplementedError
