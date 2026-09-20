# -*- coding: utf-8 -*-
"""配置加载：优先环境变量，其次 JSON 配置文件。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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

    @property
    def friends(self) -> list[FriendConfig]:
        """返回所有好友列表。

        - 若环境变量配置了主好友名称，主好友 + friends.json 中的额外好友；
        - 若环境变量未配置主好友，直接使用 friends.json 中的好友列表。
        """
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
    优先级：环境变量 > config/friends.json（若存在）> 默认值。
    """
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
    )
