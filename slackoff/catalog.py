"""内置网站清单、搜索引擎，以及用户自己添加的网站。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SiteSpec:
    id: str
    name: str
    url: str
    color: str
    note: str = ""

    @property
    def initial(self) -> str:
        return self.name[:1]


SITES: tuple[SiteSpec, ...] = (
    SiteSpec("iqiyi", "爱奇艺", "https://www.iqiyi.com/", "#00C25F", "电视剧 / 综艺 / 电影"),
    SiteSpec("tencent", "腾讯视频", "https://v.qq.com/", "#00A4FF", "热播剧集与动漫"),
    SiteSpec("youku", "优酷", "https://www.youku.com/", "#1E90FF", "港剧 / 纪录片"),
    SiteSpec("mgtv", "芒果TV", "https://www.mgtv.com/", "#FF6A00", "综艺主场"),
    SiteSpec("bilibili", "哔哩哔哩", "https://www.bilibili.com/", "#FB7299", "弹幕与 UP 主"),
    SiteSpec("douyin", "抖音网页版", "https://www.douyin.com/", "#FE2C55", "刷两条就下班"),
    SiteSpec("sohu", "搜狐视频", "https://tv.sohu.com/", "#F04142", "美剧专区"),
    SiteSpec("xigua", "西瓜视频", "https://www.ixigua.com/", "#FF5C33", "中长视频"),
    SiteSpec("douyu", "斗鱼直播", "https://www.douyu.com/", "#FF7F00", "游戏直播"),
    SiteSpec("huya", "虎牙直播", "https://www.huya.com/", "#FFA200", "赛事直播"),
    SiteSpec("youtube", "YouTube", "https://www.youtube.com/", "#FF0000", "需要网络环境"),
    SiteSpec("yangshipin", "央视频", "https://www.yangshipin.cn/", "#C8102E", "央视节目回看"),
)

SEARCH_ENGINES: dict[str, tuple[str, str]] = {
    "baidu": ("百度", "https://www.baidu.com/s?wd={}"),
    "bing": ("必应", "https://www.bing.com/search?q={}"),
    "google": ("Google", "https://www.google.com/search?q={}"),
    "sogou": ("搜狗", "https://www.sogou.com/web?query={}"),
}


def find_site(site_id: str) -> SiteSpec | None:
    return next((s for s in SITES if s.id == site_id), None)


def custom_sites(settings) -> list[SiteSpec]:
    """把 config 里的自定义网站转成 SiteSpec。"""
    sites: list[SiteSpec] = []
    for entry in settings.custom_sites:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not url or not name:
            continue
        digest = hashlib.md5(url.lower().encode("utf-8")).hexdigest()[:8]
        sites.append(
            SiteSpec(
                id=str(entry.get("id") or f"site-{digest}"),
                name=name,
                url=url,
                color=str(entry.get("color") or "#7C9CFF"),
                note="自定义",
            )
        )
    return sites
