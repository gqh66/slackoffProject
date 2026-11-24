import tempfile
import unittest
from pathlib import Path

from slackoff import books
from slackoff.config import Settings


class BookStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "我的电子书.txt"
        self.path.write_text("第一章 摸鱼\n第二章 下班", encoding="utf-8")
        self.settings = Settings()

    def test_add_book(self):
        book, created = books.add_path(self.settings, self.path)
        self.assertTrue(created)
        self.assertEqual(book.name, "我的电子书")
        self.assertEqual(book.path, str(self.path.resolve()))
        self.assertTrue(book.id.startswith("book-"))
        self.assertEqual(len(self.settings.pinned_books), 1)

    def test_duplicate(self):
        first, _ = books.add_path(self.settings, self.path)
        second, created = books.add_path(self.settings, self.path)
        self.assertFalse(created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.settings.pinned_books), 1)

    def test_remove_and_find(self):
        book, _ = books.add_path(self.settings, self.path)
        self.assertIsNotNone(books.find_book(self.settings, book.id))
        self.assertTrue(books.remove(self.settings, book.id))
        self.assertIsNone(books.find_book(self.settings, book.id))
        self.assertFalse(books.remove(self.settings, book.id))

    def test_reject_non_txt(self):
        other = Path(self.tmp.name) / "book.pdf"
        other.write_bytes(b"%PDF")
        with self.assertRaises(ValueError):
            books.add_path(self.settings, other)

    def test_format_size(self):
        self.assertIn("B", books.format_size(self.path))
        missing = Path(self.tmp.name) / "none.txt"
        self.assertIn("不见了", books.format_size(missing))


class BookReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_utf8(self):
        path = self.dir / "a.txt"
        path.write_text("第一章 摸鱼", encoding="utf-8")
        content = books.read_text(path)
        self.assertEqual(content.encoding, "UTF-8")
        self.assertIn("摸鱼", content.text)
        self.assertFalse(content.truncated)

    def test_utf8_bom(self):
        path = self.dir / "b.txt"
        path.write_text("带 BOM 的书", encoding="utf-8-sig")
        content = books.read_text(path)
        self.assertIn("UTF-8", content.encoding)
        self.assertIn("带 BOM", content.text)

    def test_gbk(self):
        path = self.dir / "c.txt"
        path.write_bytes("第一章 摸鱼\n第二章 下班".encode("gbk"))
        content = books.read_text(path)
        self.assertIn("摸鱼", content.text)
        self.assertIn("GB", content.encoding)

    def test_utf16(self):
        path = self.dir / "d.txt"
        path.write_bytes("电子书内容".encode("utf-16"))
        content = books.read_text(path)
        self.assertEqual(content.encoding, "UTF-16")
        self.assertIn("电子书", content.text)

    def test_truncation(self):
        path = self.dir / "big.txt"
        path.write_text("A" * 1000, encoding="utf-8")
        content = books.read_text(path, max_bytes=100)
        self.assertTrue(content.truncated)
        self.assertEqual(len(content.text), 100)

    def test_missing_file(self):
        with self.assertRaises(ValueError):
            books.read_text(self.dir / "missing.txt")


if __name__ == "__main__":
    unittest.main()
