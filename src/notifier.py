# -*- coding: utf-8 -*-
"""Webhook 通知模块，支持飞书/钉钉/企业微信/通用 JSON。"""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger("douyin.notifier")


def send_webhook(webhook_url: str, title: str, content: str) -> bool:
    """
    发送 Webhook 通知。
    自动识别常见平台格式；无法识别时发送通用 JSON。
    返回是否成功。
    """
    if not webhook_url:
        logger.info("未配置 NOTIFY_WEBHOOK，跳过通知")
        return False

    payload = _build_payload(webhook_url, title, content)
    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code < 400:
            logger.info("Webhook 通知发送成功: %s", resp.status_code)
            return True
        logger.warning("Webhook 返回非 2xx: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:  # noqa: BLE001
        logger.exception("Webhook 通知发送失败: %s", e)
    return False


def _build_payload(webhook_url: str, title: str, content: str) -> dict:
    url = webhook_url.lower()
    # 钉钉
    if "oapi.dingtalk.com" in url:
        return {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": f"### {title}\n\n{content}"},
        }
    # 飞书
    if "open.feishu.cn" in url or "open.larkoffice.com" in url:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": content}],
            },
        }
    # 企业微信
    if "qyapi.weixin.qq.com" in url:
        return {
            "msgtype": "markdown",
            "markdown": {"content": f"## {title}\n{content}"},
        }
    # 通用
    return {"title": title, "content": content}


def notify_result(
    webhook_url: str,
    success: bool,
    summary: str,
    detail: Optional[str] = None,
) -> bool:
    """发送运行结果通知。"""
    title = "✅ 抖音私信成功" if success else "❌ 抖音私信失败"
    content = summary
    if detail:
        content += f"\n\n**详情:**\n{detail}"
    return send_webhook(webhook_url, title, content)
