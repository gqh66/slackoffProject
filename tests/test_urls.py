import tempfile
import unittest
from pathlib import Path

from slackoff.urls import display_url, looks_like_url, normalize_input, search_url


class LooksLikeUrlTest(unittest.TestCase):
    def test_urls(self):
        for text in (
            "https://www.iqiyi.com/",
            "http://localhost:8000",
            "www.bilibili.com",
            "v.qq.com",
            "192.168.1.1:8080",
        ):
            with self.subTest(text=text):
                self.assertTrue(looks_like_url(text))

    def test_not_urls(self):
        for text in ("爱奇艺 电视剧", "hello world", "摸鱼", ""):
            with self.subTest(text=text):
                self.assertFalse(looks_like_url(text))


class NormalizeInputTest(unittest.TestCase):
    def test_keeps_scheme(self):
        self.assertEqual(normalize_input("https://example.com/a?b=1"), "https://example.com/a?b=1")
        self.assertEqual(normalize_input("file:///C:/a.html"), "file:///C:/a.html")

    def test_adds_scheme(self):
        self.assertEqual(normalize_input("www.iqiyi.com"), "https://www.iqiyi.com")
        self.assertEqual(normalize_input("v.qq.com"), "https://v.qq.com")
        self.assertEqual(normalize_input("localhost:8000"), "http://localhost:8000")
        self.assertEqual(normalize_input("10.0.0.2"), "http://10.0.0.2")

    def test_search_fallback(self):
        self.assertEqual(normalize_input("", "baidu"), None)
        self.assertEqual(
            normalize_input("摸鱼 综艺", "baidu"),
            "https://www.baidu.com/s?wd=%E6%91%B8%E9%B1%BC+%E7%BB%BC%E8%89%BA",
        )
        self.assertIn("bing.com/search?q=", normalize_input("python asyncio", "bing"))

    def test_local_html_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.html"
            path.write_text("<html></html>", encoding="utf-8")
            result = normalize_input(str(path))
            self.assertIsNotNone(result)
            self.assertTrue(result.startswith("file:///"))

    def test_display_url(self):
        self.assertEqual(display_url("https://www.iqiyi.com/"), "www.iqiyi.com/")
        self.assertEqual(display_url("http://a.b"), "a.b")

    def test_search_url_encodes(self):
        self.assertIn("%E6%91%B8%E9%B1%BC", search_url("摸鱼"))
        self.assertIn("+", search_url("a b"))


if __name__ == "__main__":
    unittest.main()
