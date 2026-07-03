from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "LocalWikipediaSaver/0.1 (local personal archive)"


class WikiSaverError(RuntimeError):
    """Raised for user-facing saver errors."""


@dataclass(frozen=True)
class WikipediaPageRef:
    host: str
    title: str
    original_url: str

    @property
    def canonical_url(self) -> str:
        return f"https://{self.host}/wiki/{quote(self.title.replace(' ', '_'), safe='()!:$@,;')}"


def default_repo_path() -> Path:
    return Path(__file__).resolve().parents[2] / "local-wiki"


def parse_wikipedia_url(url: str) -> WikipediaPageRef:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if parsed.scheme not in {"http", "https"}:
        raise WikiSaverError("Only http/https Wikipedia URLs can be saved.")
    if not host.endswith(".wikipedia.org"):
        raise WikiSaverError("This does not look like a Wikipedia article URL.")
    if not parsed.path.startswith("/wiki/"):
        raise WikiSaverError("Only /wiki/ Wikipedia pages can be saved.")

    raw_title = parsed.path[len("/wiki/") :]
    if not raw_title:
        raise WikiSaverError("Could not find a page title in the URL.")

    title = unquote(raw_title).replace("_", " ")
    return WikipediaPageRef(host=host, title=title, original_url=url)


def page_slug(title: str) -> str:
    normalized = title.replace(" ", "_")
    slug = quote(normalized, safe="")
    return slug[:180] or "untitled"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class WikipediaClient:
    def __init__(self, host: str):
        self.host = host
        self.api_url = f"https://{host}/w/api.php"

    def fetch_page(self, title: str) -> dict[str, Any]:
        query = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "info|revisions",
            "inprop": "url",
            "rvprop": "ids|timestamp|user|comment|content",
            "rvslots": "main",
            "redirects": "1",
            "titles": title,
        }
        data = self._get(query)
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            raise WikiSaverError(f"Wikipedia did not return a page for {title!r}.")

        page = pages[0]
        if page.get("missing"):
            raise WikiSaverError(f"Wikipedia page not found: {title}")

        revision = (page.get("revisions") or [{}])[0]
        slot = (revision.get("slots") or {}).get("main") or {}
        content = slot.get("content") or revision.get("content") or revision.get("*") or ""
        html = self.fetch_rendered_html(page["pageid"])

        return {
            "title": page.get("title", title),
            "pageid": page.get("pageid"),
            "canonical_url": page.get("fullurl"),
            "revision": revision,
            "wikitext": content,
            "html": html,
        }

    def fetch_rendered_html(self, pageid: int) -> str:
        query = {
            "action": "parse",
            "format": "json",
            "formatversion": "2",
            "pageid": str(pageid),
            "prop": "text",
        }
        data = self._get(query)
        return data.get("parse", {}).get("text", "")

    def _get(self, query: dict[str, str]) -> dict[str, Any]:
        url = f"{self.api_url}?{urlencode(query)}"
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=30) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset))
        except HTTPError as exc:
            raise WikiSaverError(f"Wikipedia returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise WikiSaverError(f"Could not reach Wikipedia: {exc.reason}") from exc
        except TimeoutError as exc:
            raise WikiSaverError("Timed out while contacting Wikipedia.") from exc


class GitBackedWikiArchive:
    def __init__(self, repo_path: Path | str | None = None):
        self.repo_path = Path(repo_path or default_repo_path()).expanduser().resolve()

    def save_url(self, url: str, *, commit: bool = True) -> dict[str, Any]:
        page_ref = parse_wikipedia_url(url)
        self.ensure_repo()

        client = WikipediaClient(page_ref.host)
        fetched = client.fetch_page(page_ref.title)
        revision = fetched["revision"]
        title = fetched["title"]
        slug = page_slug(title)

        page_dir = self.repo_path / "pages" / page_ref.host / slug
        page_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "title": title,
            "site": page_ref.host,
            "pageid": fetched["pageid"],
            "canonical_url": fetched["canonical_url"] or page_ref.canonical_url,
            "original_url": page_ref.original_url,
            "revision_id": revision.get("revid"),
            "parent_id": revision.get("parentid"),
            "revision_timestamp": revision.get("timestamp"),
            "revision_user": revision.get("user"),
            "revision_comment": revision.get("comment"),
            "saved_at": utc_now(),
        }

        self._write_text(page_dir / "article.wikitext", fetched["wikitext"])
        self._write_text(page_dir / "article.html", fetched["html"])
        self._write_json(page_dir / "metadata.json", metadata)
        self._update_index(page_ref.host, slug, metadata)

        commit_hash = None
        changed = self.has_staged_or_unstaged_changes()
        if commit and changed:
            commit_hash = self.commit(f"Save {page_ref.host} / {title}")

        return {
            "ok": True,
            "title": title,
            "site": page_ref.host,
            "revision_id": revision.get("revid"),
            "path": str(page_dir),
            "repo": str(self.repo_path),
            "changed": changed,
            "commit": commit_hash,
        }

    def init_archive(self) -> dict[str, Any]:
        self.ensure_repo()
        commit_hash = None
        changed = self.has_staged_or_unstaged_changes()
        if changed:
            commit_hash = self.commit("Initialize local Wikipedia archive")
        return {
            "ok": True,
            "repo": str(self.repo_path),
            "changed": changed,
            "commit": commit_hash,
        }

    def update_all(self) -> dict[str, Any]:
        self.ensure_repo()
        index_path = self.repo_path / "index.json"
        if not index_path.exists():
            return {"ok": True, "updated": [], "count": 0, "message": "No saved pages yet."}

        index = json.loads(index_path.read_text(encoding="utf-8"))
        updated: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        for page in index.get("pages", []):
            url = page.get("canonical_url") or page.get("original_url")
            if not url:
                continue
            try:
                updated.append(self.save_url(url, commit=False))
                time.sleep(0.25)
            except WikiSaverError as exc:
                errors.append({"url": url, "error": str(exc)})

        commit_hash = None
        if self.has_staged_or_unstaged_changes():
            commit_hash = self.commit("Weekly Wikipedia page refresh")

        return {
            "ok": not errors,
            "count": len(updated),
            "updated": updated,
            "errors": errors,
            "commit": commit_hash,
        }

    def ensure_repo(self) -> None:
        self.repo_path.mkdir(parents=True, exist_ok=True)
        if not (self.repo_path / ".git").exists():
            self._git("init")
        self._ensure_git_identity()
        readme = self.repo_path / "README.md"
        if not readme.exists():
            self._write_text(
                readme,
                "# Local Wikipedia Archive\n\n"
                "Saved Wikipedia pages live under `pages/` and are versioned with git.\n"
                "Run `git log --stat` here to inspect changes over time.\n",
            )
        index_path = self.repo_path / "index.json"
        if not index_path.exists():
            self._write_json(index_path, {"pages": []})

    def has_staged_or_unstaged_changes(self) -> bool:
        status = self._git("status", "--porcelain", capture=True)
        return bool(status.strip())

    def commit(self, message: str) -> str | None:
        self._git("add", "-A")
        staged = self._git("diff", "--cached", "--name-only", capture=True)
        if not staged.strip():
            return None
        self._git("commit", "-m", message)
        return self._git("rev-parse", "--short", "HEAD", capture=True).strip()

    def _update_index(self, site: str, slug: str, metadata: dict[str, Any]) -> None:
        index_path = self.repo_path / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"pages": []}
        pages = index.setdefault("pages", [])
        key = f"{site}/{slug}"
        record = {
            "key": key,
            "title": metadata["title"],
            "site": site,
            "slug": slug,
            "pageid": metadata["pageid"],
            "canonical_url": metadata["canonical_url"],
            "original_url": metadata["original_url"],
            "latest_revision_id": metadata["revision_id"],
            "latest_revision_timestamp": metadata["revision_timestamp"],
            "last_saved_at": metadata["saved_at"],
            "path": f"pages/{site}/{slug}",
        }

        for idx, page in enumerate(pages):
            if page.get("key") == key:
                pages[idx] = record
                break
        else:
            pages.append(record)

        pages.sort(key=lambda page: (page.get("site", ""), page.get("title", "").lower()))
        self._write_json(index_path, index)

    def _ensure_git_identity(self) -> None:
        if not self._git_config_exists("user.name"):
            self._git("config", "user.name", "Wikipedia Saver")
        if not self._git_config_exists("user.email"):
            self._git("config", "user.email", "wikipedia-saver@localhost")

    def _git_config_exists(self, key: str) -> bool:
        try:
            return bool(self._git("config", "--get", key, capture=True).strip())
        except WikiSaverError:
            return False

    def _git(self, *args: str, capture: bool = False) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_path,
                check=True,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            raise WikiSaverError("git is required but was not found on PATH.") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise WikiSaverError(f"git {' '.join(args)} failed: {detail}") from exc
        return result.stdout if capture else ""

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
