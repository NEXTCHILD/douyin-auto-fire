# -*- coding: utf-8 -*-
"""抖音网页版自动私信 - 主入口。"""

from __future__ import annotations

import logging
import random
import sys
import time
from pathlib import Path

# Windows 控制台默认 GBK，统一 UTF-8 避免中文日志乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from src.config_loader import load_config
from src.douyin_client import DouyinClient
from src.notifier import notify_result

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> logging.Logger:
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"run_{ts}.log"
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)
    return logging.getLogger("douyin")


def main() -> int:
    logger = setup_logging()
    config = load_config()
    friends = config.friends
    logger.info("=" * 60)
    logger.info("配置: dry_run=%s headless=%s storage=%s", config.dry_run, config.headless, config.storage_state)
    logger.info("好友数: %d", len(friends))
    for f in friends:
        tag = "（含视频链接）" if f.video_url else ""
        logger.info("  - %s%s", f.name, tag)

    if not friends:
        logger.error("未配置任何好友（DOUYIN_FRIENDS_CONFIG / DOUYIN_FRIEND_NAME / config/friends.json），退出")
        notify_result(config.notify_webhook, False, "缺少好友配置")
        return 2

    client = DouyinClient(
        storage_state=config.storage_state,
        headless=config.headless,
    )
    success_count = 0
    fail_count = 0
    error_detail = ""

    try:
        client.start()

        # 登录态检查
        if not client.is_logged_in():
            logger.error("登录态失效，请重新生成 storage_state.json")
            client._screenshot("login_failed")  # noqa: SLF001
            error_detail = "登录态失效 (storage_state 过期或无效)"
            notify_result(
                config.notify_webhook,
                False,
                "抖音登录态失效，自动私信未执行",
                error_detail,
            )
            return 3

        total_friends = len(friends)
        processed = 0  # 实际已处理（非空昵称）的好友序号
        for idx, friend in enumerate(friends):
            if not friend.name:
                continue
            processed += 1
            logger.info("=" * 40)
            logger.info("第 %d/%d 个好友: %s", processed, total_friends, friend.name)
            # 好友之间随机等待 10-20 秒，避免同时发送触发风控
            if processed > 1:
                wait = random.uniform(10, 20)
                logger.info("好友间隔随机等待 %.1f 秒...", wait)
                time.sleep(wait)
            try:
                ok = client.send_to_friend(friend, dry_run=config.dry_run)
                if ok:
                    success_count += 1
                    logger.info("第 %d/%d 个好友「%s」发送成功", processed, total_friends, friend.name)
                else:
                    fail_count += 1
                    logger.error("第 %d/%d 个好友「%s」发送失败", processed, total_friends, friend.name)
            except Exception as e:  # noqa: BLE001
                fail_count += 1
                err = f"{type(e).__name__}: {e}"
                error_detail += f"\n- {friend.name}: {err}"
                logger.exception("第 %d/%d 个好友 %s 处理时发生异常", processed, total_friends, friend.name)
                client._screenshot(f"error_{friend.name}")  # noqa: SLF001
    except Exception as e:  # noqa: BLE001
        logger.exception("运行过程中发生未捕获异常")
        error_detail = f"{type(e).__name__}: {e}"
        fail_count += 1
    finally:
        client.close()

    total = success_count + fail_count
    overall_ok = fail_count == 0 and success_count > 0
    summary = (
        f"运行完成: 成功 {success_count}/{total}, 失败 {fail_count} "
        f"(dry_run={config.dry_run})"
    )
    logger.info(summary)

    if config.notify_webhook:
        notify_result(config.notify_webhook, overall_ok, summary, error_detail)

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
