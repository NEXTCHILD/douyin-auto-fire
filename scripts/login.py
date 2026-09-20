# -*- coding: utf-8 -*-
"""
本地登录脚本：打开有头浏览器，手动扫码登录抖音，保存 storage_state.json。

用法:
    python scripts/login.py

登录成功后按提示输入回车，脚本会在项目根目录生成 storage_state.json。
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows 控制台默认 GBK，统一 UTF-8 避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# 让脚本能以 `python scripts/login.py` 方式运行时导入 src
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from src import selectors as SEL  # noqa: E402

STORAGE_STATE_PATH = ROOT / "storage_state.json"


def main() -> int:
    print("启动抖音网页版登录...")
    print("请在弹出的浏览器中扫码登录。登录成功后回到此窗口按回车。")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(SEL.HOME_URL, wait_until="domcontentloaded")

        input("\n登录完成后，请按回车继续...")

        # 保存登录态
        context.storage_state(path=str(STORAGE_STATE_PATH))
        print(f"\n登录态已保存到: {STORAGE_STATE_PATH}")
        print(f"文件大小: {STORAGE_STATE_PATH.stat().st_size} bytes")
        print(
            "\n下一步: 将该文件 base64 编码后存入 GitHub Secret: DOUYIN_STORAGE_STATE_B64\n"
            "  Windows PowerShell:\n"
            f"    [Convert]::ToBase64String([IO.File]::ReadAllBytes('{STORAGE_STATE_PATH}'))\n"
            "  Linux/macOS:\n"
            f"    base64 -w0 {STORAGE_STATE_PATH}\n"
        )
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
