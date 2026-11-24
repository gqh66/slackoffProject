"""摸鱼神器启动入口。

    python main.py            # 正常启动
    python main.py --hidden   # 直接躲在托盘里
    python main.py --debug    # 控制台输出调试日志
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

log = logging.getLogger("slackoff")


def setup_logging(debug: bool = False) -> None:
    from slackoff import paths

    paths.data_dir()
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    try:
        file_handler = RotatingFileHandler(
            paths.log_path(), maxBytes=1_500_000, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        pass

    if debug and sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)


def _configure_qt() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    from slackoff import winapi

    if sys.platform == "win32":
        winapi.set_app_user_model_id("SlackOff.Moyu.Desktop.1")


def main(argv: list[str] | None = None) -> int:
    from slackoff import __app_name__, __version__

    parser = argparse.ArgumentParser(description=f"{__app_name__} v{__version__}")
    parser.add_argument("--hidden", action="store_true", help="启动后直接隐藏（老板键唤回）")
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    parser.add_argument("--no-web", action="store_true", help="禁用内嵌浏览器（用系统浏览器打开）")
    parser.add_argument("--headless", action="store_true", help="无托盘 / 无热键，用于自动化测试")
    parser.add_argument("--quit-after", type=float, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    # 这两个开关必须在导入浏览器模块之前生效
    if args.no_web:
        os.environ["SLACKOFF_NO_WEB"] = "1"
    if args.headless:
        os.environ["SLACKOFF_HEADLESS"] = "1"

    setup_logging(args.debug)
    log.info("启动 %s v%s（Python %s）", __app_name__, __version__, sys.version.split()[0])

    _configure_qt()

    from slackoff import paths, winapi
    from slackoff.config import Settings
    from slackoff.single_instance import SingleInstance
    from slackoff.ui import theme

    app = QApplication(sys.argv[:1])
    app.setApplicationName("SlackOff")
    app.setOrganizationName("SlackOff")
    app.setQuitOnLastWindowClosed(False)
    theme.apply_theme(app)

    guard = SingleInstance(paths.project_root(), app)
    if not guard.acquire():
        log.info("已有实例在运行，已发送唤回请求")
        return 0

    from slackoff.ui.main_window import MainWindow

    settings = Settings.load()
    # 任务栏分组身份也跟着伪装走（运行中切换时，下次启动完全生效）
    try:
        winapi.set_app_user_model_id(f"SlackOff.Disguise.{settings.disguise.preset}.1")
    except Exception:
        pass
    window = MainWindow(settings, headless=args.headless, start_hidden=args.hidden)
    guard.activated.connect(window.activate_from_external)
    app.aboutToQuit.connect(guard.close)
    app.aboutToQuit.connect(window.shutdown)

    if not args.hidden:
        if settings.window.start_maximized:
            window.showMaximized()
        else:
            window.show()
        window.ensure_on_screen()
        window.raise_()
        window.activateWindow()

    start_url = settings.browser.start_url.strip()
    if start_url:
        QTimer.singleShot(800, lambda: window.open_site(start_url))

    if args.quit_after and args.quit_after > 0:
        QTimer.singleShot(int(args.quit_after * 1000), window.quit_app)

    try:
        return app.exec()
    except Exception:
        log.exception("运行期异常")
        QMessageBox.critical(None, __app_name__, f"程序出错了，详情见日志：\n{paths.log_path()}")
        return 1
    finally:
        log.info("主循环结束")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        try:
            app = QApplication.instance()
            if app is not None:
                QMessageBox.critical(None, "摸鱼神器", traceback.format_exc())
        except Exception:
            pass
        sys.exit(1)
