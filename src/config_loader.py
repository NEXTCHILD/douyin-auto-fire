# -*- coding: utf-8 -*-
"""配置加载：优先环境变量，其次 JSON 配置文件。"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("douyin.config")


@dataclass
class FriendConfig:
    name: str
    message: str = ""
    video_url: str = ""
    video_path: str = ""


@dataclass
class AppConfig:
    friend_name: str
    message: str
    video_url: str = ""
    video_path: str = ""
    dry_run: bool = True
    headless: bool = True
    storage_state: str = "storage_state.json"
    notify_webhook: str = ""
    extra_friends: list[FriendConfig] = field(default_factory=list)
    # 来自 DOUYIN_FRIENDS_CONFIG（多好友 JSON）的好友列表，优先级最高
    env_friends: list[FriendConfig] = field(default_factory=list)

    @property
    def friends(self) -> list[FriendConfig]:
        """返回所有好友列表。

        优先级：
          1) DOUYIN_FRIENDS_CONFIG（多好友 JSON 环境变量）
          2) DOUYIN_FRIEND_NAME（旧的单个好友环境变量）+ friends.json
          3) config/friends.json（本地/GUI 使用）
        """
        if self.env_friends:
            return list(self.env_friends)
        if self.friend_name:
            primary = FriendConfig(
                name=self.friend_name,
                message=self.message,
                video_url=self.video_url,
                video_path=self.video_path,
            )
            return [primary] + self.extra_friends
        return list(self.extra_friends)


@dataclass
class ScheduleConfig:
    hour: int = 7
    minute: int = 0
    timezone: str = "Asia/Shanghai"

    def to_cron(self) -> str:
        """北京时间转 UTC cron 表达式。"""
        utc_hour = (self.hour - 8 + 24) % 24
        return f"{self.minute} {utc_hour} * * *"


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def parse_friends_env(raw: str) -> list[FriendConfig]:
    """解析 DOUYIN_FRIENDS_CONFIG 环境变量（JSON 字符串）。

    支持两种形态：
      1) 数组：[{"name": "好友A", "message": "早上好", "video_url": ""}, ...]
      2) 对象：{"friends": [ ... ]}

    昵称缺失或为空的条目会被跳过。JSON 非法时抛出 json.JSONDecodeError / ValueError。
    """
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("friends", [])
    if not isinstance(data, list):
        raise ValueError("DOUYIN_FRIENDS_CONFIG 必须是好友数组，或含 friends 数组的对象")

    friends: list[FriendConfig] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        friends.append(
            FriendConfig(
                name=name,
                message=str(item.get("message", "")),
                video_url=str(item.get("video_url", "") or ""),
                video_path=str(item.get("video_path", "") or ""),
            )
        )
    return friends


def load_friends_from_file(path: str | Path) -> list[FriendConfig]:
    """从 JSON 配置文件读取好友列表。

    兼容两种格式：
      1) {"friends": [ {...}, {...} ]}
      2) {"friends": {...}}              ← 旧格式，单个对象
      3) {"name": "...", "message": ...} ← 顶层单个好友
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    raw = data.get("friends", data)
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    friends: list[FriendConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        friends.append(
            FriendConfig(
                name=item.get("name", ""),
                message=item.get("message", ""),
                video_url=item.get("video_url", ""),
                video_path=item.get("video_path", ""),
            )
        )
    return friends


def save_friends_to_file(path: str | Path, friends: list[FriendConfig]) -> None:
    """将好友列表写入 JSON 配置文件。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "friends": [
            {
                "name": f.name,
                "message": f.message,
                "video_url": f.video_url,
                "video_path": f.video_path,
            }
            for f in friends
        ]
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_schedule(path: str | Path) -> ScheduleConfig:
    """读取定时设置，默认 07:00 Asia/Shanghai。"""
    p = Path(path)
    if not p.exists():
        return ScheduleConfig()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ScheduleConfig()
    hour = int(data.get("hour", 7))
    minute = int(data.get("minute", 0))
    tz = data.get("timezone", "Asia/Shanghai")
    return ScheduleConfig(hour=max(0, min(23, hour)), minute=max(0, min(59, minute)), timezone=tz)


def save_schedule(path: str | Path, schedule: ScheduleConfig) -> None:
    """写入定时设置到 JSON。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"hour": schedule.hour, "minute": schedule.minute, "timezone": schedule.timezone}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config() -> AppConfig:
    """
    加载配置。
    好友优先级：
      1) DOUYIN_FRIENDS_CONFIG（多好友 JSON 环境变量）
      2) DOUYIN_FRIEND_NAME / DOUYIN_MESSAGE / DOUYIN_VIDEO_URL（旧的单个好友）
      3) config/friends.json（本地 GUI 保存的配置文件）
    """
    # 1) 多好友 JSON 环境变量（最高优先级）
    env_friends: list[FriendConfig] = []
    friends_raw = os.getenv("DOUYIN_FRIENDS_CONFIG", "").strip()
    if friends_raw:
        try:
            env_friends = parse_friends_env(friends_raw)
            if env_friends:
                logger.info("从 DOUYIN_FRIENDS_CONFIG 加载 %d 个好友", len(env_friends))
            else:
                logger.warning("DOUYIN_FRIENDS_CONFIG 已设置，但未解析出任何有效好友")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("解析 DOUYIN_FRIENDS_CONFIG 失败，将降级到其他配置: %s", e)

    # 3) 本地配置文件（仅在环境变量未提供多好友时作为补充/降级）
    extra = load_friends_from_file("config/friends.json")

    return AppConfig(
        friend_name=_env("DOUYIN_FRIEND_NAME"),
        message=_env("DOUYIN_MESSAGE"),
        video_url=_env("DOUYIN_VIDEO_URL"),
        video_path=_env("DOUYIN_VIDEO_PATH"),
        dry_run=_env_bool("DRY_RUN", True),
        headless=_env_bool("HEADLESS", True),
        storage_state=_env("DOUYIN_STORAGE_STATE_PATH", "storage_state.json"),
        notify_webhook=_env("NOTIFY_WEBHOOK"),
        extra_friends=extra,
        env_friends=env_friends,
    )
