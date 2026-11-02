from __future__ import annotations

import urllib.parse

from .http_client import HttpError, request
from .models import FileChange

API = "https://api.github.com"
ZERO_SHA = "0" * 40


class GitHubClient:
    def __init__(self, token: str):
        self._h = {"Authorization": f"Bearer {token}",
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}

    def _get(self, path: str):
        return request("GET", f"{API}{path}", headers=self._h)[1]

    @staticmethod
    def _files(raw: list[dict]) -> list[FileChange]:
        return [FileChange(path=f["filename"], status=f.get("status", "modified"),
                           patch=f.get("patch", ""), additions=f.get("additions", 0))
                for f in raw]

    def changed_files(self, repo: str, before: str, after: str):
        """Archivos y mensajes de commit de un push (maneja rama nueva y force-push)."""
        if before and before != ZERO_SHA:
            try:
                d = self._get(f"/repos/{repo}/compare/{before}...{after}")
                return self._files(d.get("files", [])), [c["commit"]["message"] for c in d["commits"]]
            except HttpError as e:
                if e.status != 404:      # 404: el «before» ya no existe (force-push)
                    raise
        d = self._get(f"/repos/{repo}/commits/{after}")
        return self._files(d.get("files", [])), [d["commit"]["message"]]

    def get_file(self, repo: str, path: str, ref: str) -> str | None:
        url = (f"{API}/repos/{repo}/contents/{urllib.parse.quote(path)}"
               f"?ref={urllib.parse.quote(ref)}")
        try:
            return request("GET", url, raw=True,
                           headers={**self._h, "Accept": "application/vnd.github.raw+json"})[1]
        except HttpError as e:
            if e.status == 404:
                return None
            raise

    def set_status(self, repo: str, sha: str, state: str, description: str,
                   context: str = "py-guardian", target_url: str | None = None) -> None:
        body = {"state": state, "description": description[:140], "context": context}
        if target_url:
            body["target_url"] = target_url
        request("POST", f"{API}/repos/{repo}/statuses/{sha}", headers=self._h, json_body=body)

    def comment_commit(self, repo: str, sha: str, body: str) -> None:
        request("POST", f"{API}/repos/{repo}/commits/{sha}/comments",
                headers=self._h, json_body={"body": body[:60000]})
