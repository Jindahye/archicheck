"""GitHub REST API 클라이언트. GitHub API 호출은 이 모듈에서만 한다."""


class GitHubClient:
    def get_diff(self, pr):
        raise NotImplementedError

    def get_commit_messages(self, pr) -> list[str]:
        raise NotImplementedError

    def get_file(self, repo, ref, path) -> str:
        raise NotImplementedError

    def list_files(self, repo, ref) -> list[str]:
        raise NotImplementedError

    def post_comment(self, pr, body):
        raise NotImplementedError
