"""系统内核网页：站点识别、显示名与新窗口接管。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from slackoff import edge_web, winapi


class VideoUrlTests(unittest.TestCase):
    def test_known_video_sites(self):
        for url in (
            "https://www.iqiyi.com/v_19rr7qhfg0.html",
            "https://m.iqiyi.com/",
            "https://v.qq.com/x/cover/mzc00200.html",
            "https://film.qq.com/",
            "https://www.youku.com/",
            "https://www.mgtv.com/",
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "https://b23.tv/abc",
            "https://www.douyin.com/",
            "https://www.ixigua.com/",
            "https://www.douyu.com/",
            "https://www.huya.com/",
            "https://tv.sohu.com/",
            "https://www.youtube.com/watch?v=abc",
            "https://youtu.be/abc",
            "https://www.yangshipin.cn/",
            "v.qq.com",
        ):
            self.assertTrue(edge_web.is_video_url(url), url)

    def test_other_sites(self):
        for url in (
            "",
            "https://www.baidu.com/s?wd=iqiyi",
            "https://www.huilvbiao.com/gold",
            "https://github.com/",
            "not a url",
        ):
            self.assertFalse(edge_web.is_video_url(url), url)

    def test_lookalike_hosts_are_not_video_sites(self):
        for url in (
            "https://evil-iqiyi.com/",
            "https://iqiyi.com.example.com/",
            "https://fakev.qq.com/",
        ):
            self.assertFalse(edge_web.is_video_url(url), url)

    def test_site_label(self):
        self.assertEqual(edge_web.site_label("https://www.iqiyi.com/"), "爱奇艺")
        self.assertEqual(edge_web.site_label("https://v.qq.com/"), "腾讯视频")
        self.assertEqual(edge_web.site_label("https://www.youku.com/"), "优酷")
        self.assertEqual(edge_web.site_label("https://v.qq.com"), "腾讯视频")
        self.assertEqual(edge_web.site_label("https://www.example.com/"), "example.com")

    def test_profile_dir_name(self):
        self.assertEqual(edge_web.profile_dir().name, "edge-profile")


def _window(hwnd=1, pid=100, title="Video", class_name="Chrome_WidgetWin_1"):
    return winapi.WindowInfo(
        hwnd=hwnd,
        pid=pid,
        title=title,
        class_name=class_name,
        visible=True,
        minimized=False,
    )


class NewWindowTrackingTests(unittest.TestCase):
    """网页 target=_blank 新开窗口时的筛选规则。"""

    def _site(self, pid=100, tracked=None):
        site = edge_web.EdgeSiteWindow.__new__(edge_web.EdgeSiteWindow)
        site._pid = pid
        site._windows = tracked or {}
        site._profile_pids = {}
        return site

    def test_picks_new_browser_windows(self):
        site = self._site()
        windows = [_window(1), _window(2), _window(3, class_name="Chrome_WidgetWin_0")]
        with mock.patch.object(edge_web.winapi, "enumerate_windows", return_value=windows), \
                mock.patch.object(edge_web.winapi, "get_parent", return_value=0), \
                mock.patch.object(edge_web.winapi, "window_rect", return_value=(0, 0, 800, 600)):
            self.assertEqual(site._find_new_windows(), [1, 2])

    def test_skips_tracked_owned_small_and_foreign_windows(self):
        site = self._site(tracked={1: 0})
        windows = [
            _window(1),
            _window(2, title=""),
            _window(3),
            _window(4),
            _window(5, pid=999),
        ]
        parents = {3: 1}
        rects = {4: (0, 0, 200, 100)}
        with mock.patch.object(edge_web.winapi, "enumerate_windows", return_value=windows), \
                mock.patch.object(
                    edge_web.winapi, "get_parent", side_effect=lambda hwnd: parents.get(hwnd, 0)
                ), \
                mock.patch.object(
                    edge_web.winapi,
                    "window_rect",
                    side_effect=lambda hwnd: rects.get(hwnd, (0, 0, 800, 600)),
                ), \
                mock.patch.object(edge_web, "_pid_uses_profile", return_value=False):
            self.assertEqual(site._find_new_windows(), [])

    def test_profile_pid_is_checked_once(self):
        site = self._site()
        with mock.patch.object(edge_web, "_pid_uses_profile", return_value=True) as check:
            self.assertTrue(site._owns_pid(555))
            self.assertTrue(site._owns_pid(555))
        check.assert_called_once()
        self.assertTrue(site._owns_pid(100))

    def test_active_window_closed_falls_back_to_other(self):
        site = self._site(tracked={1: 0, 2: 1})
        site._hwnd = 2
        site._timer = SimpleNamespace(stop=lambda: None)
        site._find_new_windows = lambda: []
        with mock.patch.object(edge_web.winapi, "is_window", side_effect=lambda hwnd: hwnd == 1):
            with mock.patch.object(site, "_activate") as activate:
                site._sync_windows()
        activate.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
