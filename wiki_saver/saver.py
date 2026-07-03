from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "LocalWikipediaSaver/0.1 (local personal archive)"
DEFAULT_REFRESH_INTERVAL_DAYS = 7
MIN_REFRESH_INTERVAL_DAYS = 1
MAX_REFRESH_INTERVAL_DAYS = 365
SETTINGS_FILENAME = ".wiki-saver-settings.json"


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
    return Path.home() / "Library" / "Application Support" / "WikipediaSaver" / "local-wiki"


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


def normalized_wikipedia_url(url: str) -> str:
    page_ref = parse_wikipedia_url(url)
    return page_ref.canonical_url


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

        page_rel_path = self._page_relative_path(page_ref.host, slug)
        page_dir = self.repo_path / page_rel_path
        legacy_page_dir = self._legacy_page_dir(page_ref.host, slug)
        comparison_dir = page_dir if page_dir.exists() else legacy_page_dir or page_dir

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

        page_changed = self._page_changed(comparison_dir, fetched["wikitext"], fetched["html"], metadata)
        path_changed = comparison_dir != page_dir or bool(legacy_page_dir and legacy_page_dir.exists())
        index_changed = not self._index_has_current_page(page_ref.host, slug, metadata)
        archive_changed = page_changed or path_changed or index_changed

        if page_changed:
            page_dir.mkdir(parents=True, exist_ok=True)
            self._write_text(page_dir / "article.wikitext", fetched["wikitext"])
            self._write_text(page_dir / "article.html", fetched["html"])
            self._write_json(page_dir / "metadata.json", metadata)
        elif path_changed and legacy_page_dir and legacy_page_dir.exists() and legacy_page_dir != page_dir:
            if page_dir.exists():
                shutil.rmtree(legacy_page_dir)
            else:
                page_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(legacy_page_dir), str(page_dir))

        if path_changed or index_changed or page_changed:
            self._update_index(page_ref.host, slug, metadata)

        commit_hash = None
        if commit and archive_changed and self.has_staged_or_unstaged_changes():
            message = (
                f"Save {page_ref.host} / {title}"
                if page_changed
                else f"Update archive metadata for {page_ref.host} / {title}"
            )
            commit_hash = self.commit(message)

        return {
            "ok": True,
            "title": title,
            "site": page_ref.host,
            "revision_id": revision.get("revid"),
            "path": str(page_dir),
            "repo": str(self.repo_path),
            "changed": page_changed,
            "archive_changed": archive_changed,
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

    def get_settings(self) -> dict[str, Any]:
        self.ensure_repo()
        settings = self._read_settings()
        settings["repo"] = str(self.repo_path)
        return {"ok": True, "settings": settings}

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_repo()
        settings = self._read_settings()

        if "refresh_interval_days" in payload:
            settings["refresh_interval_days"] = self._validate_refresh_interval_days(
                payload["refresh_interval_days"]
            )

        self._write_settings(settings)
        return {"ok": True, "settings": settings}

    def saved_status(self, url: str) -> dict[str, Any]:
        page_ref = parse_wikipedia_url(url)
        index_path = self.repo_path / "index.json"
        if not index_path.exists():
            return {"ok": True, "saved": False, "repo": str(self.repo_path)}

        index = json.loads(index_path.read_text(encoding="utf-8"))
        requested_key = f"{page_ref.host}/{page_slug(page_ref.title)}"
        requested_url = page_ref.canonical_url

        for page in index.get("pages", []):
            urls = [
                page.get("canonical_url"),
                page.get("original_url"),
            ]
            normalized_urls = []
            for candidate in urls:
                if not candidate:
                    continue
                try:
                    normalized_urls.append(normalized_wikipedia_url(candidate))
                except WikiSaverError:
                    continue

            if page.get("key") == requested_key or requested_url in normalized_urls:
                if not self._saved_page_files_exist(page):
                    return {"ok": True, "saved": False, "repo": str(self.repo_path)}
                return {
                    "ok": True,
                    "saved": True,
                    "repo": str(self.repo_path),
                    "page": page,
                }

        return {"ok": True, "saved": False, "repo": str(self.repo_path)}

    def update_all(self, *, force: bool = False) -> dict[str, Any]:
        self.ensure_repo()
        settings = self._read_settings()
        if not force and not self._refresh_is_due(settings):
            return {
                "ok": True,
                "skipped": True,
                "reason": "not_due",
                "settings": settings,
                "message": f"Next refresh is not due yet. Interval is {settings['refresh_interval_days']} day(s).",
            }

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

        if not errors:
            settings["last_refresh_at"] = utc_now()
            self._write_settings(settings)

        return {
            "ok": not errors,
            "skipped": False,
            "count": len(updated),
            "updated": updated,
            "errors": errors,
            "commit": commit_hash,
            "settings": settings,
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
        gitignore_path = self.repo_path / ".gitignore"
        self._ensure_gitignore_line(gitignore_path, SETTINGS_FILENAME)

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

    def _read_settings(self) -> dict[str, Any]:
        settings_path = self.repo_path / SETTINGS_FILENAME
        settings: dict[str, Any] = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                settings = {}

        settings["refresh_interval_days"] = self._validate_refresh_interval_days(
            settings.get("refresh_interval_days", DEFAULT_REFRESH_INTERVAL_DAYS)
        )
        last_refresh_at = settings.get("last_refresh_at")
        if last_refresh_at is not None:
            settings["last_refresh_at"] = str(last_refresh_at)
        return settings

    def _write_settings(self, settings: dict[str, Any]) -> None:
        self._write_json(self.repo_path / SETTINGS_FILENAME, settings)

    @staticmethod
    def _validate_refresh_interval_days(value: Any) -> int:
        try:
            days = int(value)
        except (TypeError, ValueError) as exc:
            raise WikiSaverError("Refresh interval must be a whole number of days.") from exc
        if days < MIN_REFRESH_INTERVAL_DAYS or days > MAX_REFRESH_INTERVAL_DAYS:
            raise WikiSaverError(
                f"Refresh interval must be between {MIN_REFRESH_INTERVAL_DAYS} and {MAX_REFRESH_INTERVAL_DAYS} days."
            )
        return days

    def _refresh_is_due(self, settings: dict[str, Any]) -> bool:
        last_refresh_at = settings.get("last_refresh_at")
        if not last_refresh_at:
            return True

        try:
            last_refresh = datetime.fromisoformat(str(last_refresh_at).replace("Z", "+00:00"))
        except ValueError:
            return True

        if last_refresh.tzinfo is None:
            last_refresh = last_refresh.replace(tzinfo=timezone.utc)

        interval = timedelta(days=self._validate_refresh_interval_days(settings.get("refresh_interval_days")))
        return datetime.now(timezone.utc) - last_refresh >= interval

    @staticmethod
    def _ensure_gitignore_line(path: Path, line: str) -> None:
        existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        if line not in existing:
            existing.append(line)
            path.write_text("\n".join(existing).rstrip() + "\n", encoding="utf-8")

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
            "path": str(self._page_relative_path(site, slug)),
        }

        for idx, page in enumerate(pages):
            if page.get("key") == key:
                pages[idx] = record
                break
        else:
            pages.append(record)

        pages.sort(key=lambda page: (page.get("site", ""), page.get("title", "").lower()))
        self._write_json(index_path, index)

    def _index_has_current_page(self, site: str, slug: str, metadata: dict[str, Any]) -> bool:
        index_path = self.repo_path / "index.json"
        if not index_path.exists():
            return False

        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False

        key = f"{site}/{slug}"
        expected_path = str(self._page_relative_path(site, slug))
        for page in index.get("pages", []):
            if page.get("key") != key:
                continue
            return (
                page.get("path") == expected_path
                and page.get("latest_revision_id") == metadata["revision_id"]
                and page.get("canonical_url") == metadata["canonical_url"]
            )
        return False

    def _saved_page_files_exist(self, page: dict[str, Any]) -> bool:
        page_path = page.get("path")
        if page_path:
            page_dir = self.repo_path / page_path
            if self._required_page_files_exist(page_dir):
                return True

        site = page.get("site")
        slug = page.get("slug")
        if site and slug:
            if self._required_page_files_exist(self.repo_path / self._page_relative_path(site, slug)):
                return True
            legacy_page_dir = self._legacy_page_dir(site, slug)
            if legacy_page_dir and self._required_page_files_exist(legacy_page_dir):
                return True

        return False

    @staticmethod
    def _required_page_files_exist(page_dir: Path) -> bool:
        return (
            (page_dir / "article.wikitext").is_file()
            and (page_dir / "article.html").is_file()
            and (page_dir / "metadata.json").is_file()
        )

    @staticmethod
    def _page_relative_path(site: str, slug: str) -> Path:
        if site == "en.wikipedia.org":
            return Path("pages") / slug
        return Path("pages") / site / slug

    def _legacy_page_dir(self, site: str, slug: str) -> Path | None:
        if site != "en.wikipedia.org":
            return None
        legacy = self.repo_path / "pages" / site / slug
        return legacy if legacy.exists() else None

    def _page_changed(self, page_dir: Path, wikitext: str, html: str, metadata: dict[str, Any]) -> bool:
        wikitext_path = page_dir / "article.wikitext"
        html_path = page_dir / "article.html"
        metadata_path = page_dir / "metadata.json"
        if not wikitext_path.exists() or not html_path.exists() or not metadata_path.exists():
            return True

        if wikitext_path.read_text(encoding="utf-8").rstrip() != wikitext.rstrip():
            return True
        if html_path.read_text(encoding="utf-8").rstrip() != html.rstrip():
            return True

        try:
            existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return True

        return self._stable_metadata(existing_metadata) != self._stable_metadata(metadata)

    @staticmethod
    def _stable_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        ignored = {"saved_at", "original_url"}
        return {key: value for key, value in metadata.items() if key not in ignored}

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
