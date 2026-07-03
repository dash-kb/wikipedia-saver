import unittest

from wiki_saver.saver import WikiSaverError, page_slug, parse_wikipedia_url


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


if __name__ == "__main__":
    unittest.main()
