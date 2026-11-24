import unittest

from slackoff import disguise


class DisguiseTest(unittest.TestCase):
    def test_default(self):
        brand = disguise.get("default")
        self.assertEqual(brand.short, "摸鱼神器")
        self.assertIn("摸鱼", brand.base_title)

    def test_excel_and_wps(self):
        excel = disguise.get("excel")
        self.assertEqual(excel.short, "Excel")
        self.assertEqual(excel.base_title, "工作簿1 - Excel")
        wps = disguise.get("wps")
        self.assertEqual(wps.short, "WPS")

    def test_unknown_falls_back(self):
        self.assertEqual(disguise.get("nope").id, "default")
        self.assertEqual(disguise.get(None).id, "default")

    def test_all_presets_are_complete(self):
        for preset_id, brand in disguise.PRESETS.items():
            self.assertEqual(brand.id, preset_id)
            self.assertTrue(brand.name)
            self.assertTrue(brand.short)
            self.assertTrue(brand.subtitle)
            self.assertTrue(brand.base_title)


if __name__ == "__main__":
    unittest.main()
