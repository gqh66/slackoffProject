import unittest
from pathlib import Path

from slackoff.single_instance import instance_name


class SingleInstanceNameTest(unittest.TestCase):
    def test_stable_for_same_path(self):
        self.assertEqual(instance_name(Path("D:/slackoffProject")), instance_name(Path("D:/slackoffProject")))

    def test_different_for_other_paths(self):
        self.assertNotEqual(instance_name(Path("D:/a")), instance_name(Path("D:/b")))

    def test_prefix(self):
        self.assertTrue(instance_name(Path("D:/slackoffProject")).startswith("SlackOff-"))


if __name__ == "__main__":
    unittest.main()
