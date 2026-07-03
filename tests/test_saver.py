import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from wiki_saver.saver import GitBackedWikiArchive, WikiSaverError, page_slug, parse_wikipedia_url


class SaverTests(unittest.TestCase):
    def test_parse_wikipedia_article_url(self):
        ref = parse_wikipedia_url("https://en.wikipedia.org/wiki/Wikipedia:About#History")
        self.assertEqual(ref.host, "en.wikipedia.org")
        self.assertEqual(ref.title, "Wikipedia:About")

    def test_rejects_non_wikipedia_url(self):
        with self.assertRaises(WikiSaverError):
            parse_wikipedia_url("https://example.com/wiki/Wikipedia")

    def test_slug_escapes_filesystem_sensitive_characters(self):
        self.assertEqual(page_slug("C++/CLI"), "C%2B%2B%2FCLI")

    def test_saved_status_requires_article_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            (repo / "index.json").write_text(
                json.dumps(
                    {
                        "pages": [
                            {
                                "key": "en.wikipedia.org/Wikipedia",
                                "title": "Wikipedia",
                                "site": "en.wikipedia.org",
                                "slug": "Wikipedia",
                                "path": "pages/Wikipedia",
                                "canonical_url": "https://en.wikipedia.org/wiki/Wikipedia",
                                "original_url": "https://en.wikipedia.org/wiki/Wikipedia#History",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            archive = GitBackedWikiArchive(repo)
            self.assertFalse(archive.saved_status("https://en.wikipedia.org/wiki/Wikipedia")["saved"])

            page_dir = repo / "pages" / "Wikipedia"
            page_dir.mkdir(parents=True)
            (page_dir / "article.wikitext").write_text("text\n", encoding="utf-8")
            (page_dir / "article.html").write_text("<p>text</p>\n", encoding="utf-8")
            (page_dir / "metadata.json").write_text("{}\n", encoding="utf-8")

            self.assertTrue(archive.saved_status("https://en.wikipedia.org/wiki/Wikipedia")["saved"])
            self.assertFalse(archive.saved_status("https://en.wikipedia.org/wiki/Git")["saved"])

    def test_english_pages_store_directly_under_pages(self):
        archive = GitBackedWikiArchive("/tmp/example")
        self.assertEqual(
            archive._page_relative_path("en.wikipedia.org", "Wikipedia"),
            Path("pages") / "Wikipedia",
        )

    def test_non_english_pages_store_under_site_folder(self):
        archive = GitBackedWikiArchive("/tmp/example")
        self.assertEqual(
            archive._page_relative_path("fr.wikipedia.org", "Paris"),
            Path("pages") / "fr.wikipedia.org" / "Paris",
        )

    def test_saved_at_alone_does_not_count_as_page_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            page_dir = Path(tmpdir)
            (page_dir / "article.wikitext").write_text("same\n", encoding="utf-8")
            (page_dir / "article.html").write_text("<p>same</p>\n", encoding="utf-8")
            (page_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "title": "Same",
                        "revision_id": 1,
                        "saved_at": "old",
                        "original_url": "https://en.wikipedia.org/wiki/Same#old",
                    }
                ),
                encoding="utf-8",
            )

            archive = GitBackedWikiArchive("/tmp/example")
            self.assertFalse(
                archive._page_changed(
                    page_dir,
                    "same",
                    "<p>same</p>",
                    {
                        "title": "Same",
                        "revision_id": 1,
                        "saved_at": "new",
                        "original_url": "https://en.wikipedia.org/wiki/Same#new",
                    },
                )
            )

    def test_index_repair_does_not_count_as_page_refresh(self):
        class FakeWikipediaClient:
            def __init__(self, host):
                self.host = host

            def fetch_page(self, title):
                return {
                    "title": "Wikipedia",
                    "pageid": 1,
                    "canonical_url": "https://en.wikipedia.org/wiki/Wikipedia",
                    "revision": {
                        "revid": 1,
                        "parentid": 0,
                        "timestamp": "2026-01-01T00:00:00Z",
                        "user": "Example",
                        "comment": "No change",
                    },
                    "wikitext": "same",
                    "html": "<p>same</p>",
                }

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            page_dir = repo / "pages" / "Wikipedia"
            page_dir.mkdir(parents=True)
            (page_dir / "article.wikitext").write_text("same\n", encoding="utf-8")
            (page_dir / "article.html").write_text("<p>same</p>\n", encoding="utf-8")
            (page_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "title": "Wikipedia",
                        "site": "en.wikipedia.org",
                        "pageid": 1,
                        "canonical_url": "https://en.wikipedia.org/wiki/Wikipedia",
                        "original_url": "https://en.wikipedia.org/wiki/Wikipedia",
                        "revision_id": 1,
                        "parent_id": 0,
                        "revision_timestamp": "2026-01-01T00:00:00Z",
                        "revision_user": "Example",
                        "revision_comment": "No change",
                        "saved_at": "old",
                    }
                ),
                encoding="utf-8",
            )
            (repo / "index.json").write_text(
                json.dumps(
                    {
                        "pages": [
                            {
                                "key": "en.wikipedia.org/Wikipedia",
                                "title": "Wikipedia",
                                "site": "en.wikipedia.org",
                                "slug": "Wikipedia",
                                "path": "pages/en.wikipedia.org/Wikipedia",
                                "canonical_url": "https://en.wikipedia.org/wiki/Wikipedia",
                                "original_url": "https://en.wikipedia.org/wiki/Wikipedia",
                                "latest_revision_id": 1,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            archive = GitBackedWikiArchive(repo)
            with patch("wiki_saver.saver.WikipediaClient", FakeWikipediaClient):
                result = archive.save_url("https://en.wikipedia.org/wiki/Wikipedia", commit=False)

            self.assertFalse(result["changed"])
            self.assertTrue(result["archive_changed"])
            self.assertEqual(
                json.loads((repo / "index.json").read_text(encoding="utf-8"))["pages"][0]["path"],
                "pages/Wikipedia",
            )
            self.assertEqual(
                json.loads((page_dir / "metadata.json").read_text(encoding="utf-8"))["saved_at"],
                "old",
            )

    def test_settings_round_trip_refresh_interval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = GitBackedWikiArchive(tmpdir)
            result = archive.update_settings({"refresh_interval_days": 14})

            self.assertEqual(result["settings"]["refresh_interval_days"], 14)
            self.assertEqual(archive.get_settings()["settings"]["refresh_interval_days"], 14)
            self.assertTrue((Path(tmpdir) / ".gitignore").read_text(encoding="utf-8").count(".wiki-saver-settings.json"))

    def test_update_all_skips_when_refresh_not_due(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = GitBackedWikiArchive(tmpdir)
            archive.ensure_repo()
            archive._write_settings(
                {
                    "refresh_interval_days": 7,
                    "last_refresh_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                }
            )

            result = archive.update_all()

            self.assertTrue(result["skipped"])
            self.assertEqual(result["reason"], "not_due")


if __name__ == "__main__":
    unittest.main()
