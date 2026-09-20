# -*- coding: utf-8 -*-
"""抖音网页版私信核心客户端（Playwright sync API，支持多标签页）。

流程：首页检查登录 → 消息页 → 搜索好友 → 点击（可能开新标签页）
→ 资料页点「私信」（也可能开新标签页）→ 会话页输入框 → 发送。
所有页面操作都使用目标页面对象，处理完关闭多余标签页。
"""

from __future__ import annotations

import logging
import random
import re
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.config_loader import FriendConfig
from src import selectors as SEL

logger = logging.getLogger("douyin.client")


class DouyinClient:
    def __init__(
        self,
        storage_state: str = "storage_state.json",
        headless: bool = True,
        screenshot_dir: str = "screenshots",
    ) -> None:
        self.storage_state = storage_state
        self.headless = headless
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._main_page: Optional[Page] = None

    # ---------- 生命周期 ----------
    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if Path(self.storage_state).exists():
            ctx_kwargs["storage_state"] = self.storage_state
            logger.info("加载登录态: %s", self.storage_state)
        else:
            logger.warning("未找到 storage_state.json，将以未登录状态启动")

        self._context = self._browser.new_context(**ctx_kwargs)
        self._main_page = self._context.new_page()

    def close(self) -> None:
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception as e:  # noqa: BLE001
            logger.warning("关闭浏览器资源时出错: %s", e)

    def __enter__(self) -> "DouyinClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ---------- 工具 ----------
    def _screenshot(self, name: str, page: Optional[Page] = None) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r'[\\/:*?"<>|]', "_", name)
        path = self.screenshot_dir / f"{ts}_{safe}.png"
        target = page or self._main_page
        try:
            if target:
                target.screenshot(path=str(path), full_page=True)
                logger.info("截图已保存: %s", path)
        except Exception as e:  # noqa: BLE001
            logger.warning("截图失败: %s", e)
        return path

    def _close_extra_pages(self) -> None:
        """关闭除主页面外的所有标签页，避免影响下一个好友。"""
        if not self._context:
            return
        for p in list(self._context.pages):
            if p != self._main_page:
                try:
                    p.close()
                    logger.info("已关闭多余标签页: %s", p.url[:60])
                except Exception:  # noqa: BLE001
                    pass

    def _human_sleep(self, lo: float = 2.0, hi: float = 8.0) -> None:
        time.sleep(random.uniform(lo, hi))

    def _find_visible(
        self,
        page: Page,
        selectors: list[str],
        timeout_ms: int = 15000,
        label: str = "元素",
    ) -> Optional[Locator]:
        """依次尝试选择器，用 wait_for_selector 等待，找到「可见」的才用。"""
        deadline = time.time() + timeout_ms / 1000
        per = max(1500, int(timeout_ms / max(len(selectors), 1)))

        for sel in selectors:
            remaining = int((deadline - time.time()) * 1000)
            wait_t = min(per, max(300, remaining))
            if wait_t <= 0:
                break
            try:
                el = page.wait_for_selector(sel, timeout=wait_t, state="visible")
                if el:
                    logger.info("命中选择器[%s]: %s", label, sel)
                    return page.locator(sel).first
            except Exception:  # noqa: BLE001
                continue

        # 兜底：即时可见性检查
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    logger.info("兜底命中选择器[%s]: %s", label, sel)
                    return loc
            except Exception:  # noqa: BLE001
                continue

        logger.warning("所有选择器均未命中[%s]: %s", label, selectors)
        return None

    def _any_visible(self, page: Page, selectors: list[str]) -> bool:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def _find_dm_button(self, page: Page, timeout_ms: int = 15000) -> Optional[Locator]:
        """按 SEL.DM_BUTTON_STRATEGIES 顺序定位「私信」按钮。

        每个策略等待一段时间，必须 is_visible() 才算命中。
        """
        deadline = time.time() + timeout_ms / 1000
        strategies = SEL.DM_BUTTON_STRATEGIES
        per = max(1500, int(timeout_ms / max(len(strategies), 1)))

        for kind, arg, arg2 in strategies:
            remaining = int((deadline - time.time()) * 1000)
            wait_t = min(per, max(300, remaining))
            if wait_t <= 0:
                break
            desc = f"{kind}:{arg}" + (f"/{arg2}" if arg2 else "")
            try:
                if kind == "role":
                    loc = page.get_by_role(arg, name=arg2).first
                elif kind == "text_exact":
                    loc = page.get_by_text(arg, exact=True).first
                elif kind == "text_visible":
                    try:
                        loc = page.locator(arg).filter(visible=True).first
                    except TypeError:
                        loc = page.locator(arg).first
                else:
                    loc = page.locator(arg).first

                try:
                    loc.wait_for(timeout=wait_t, state="visible")
                except Exception:  # noqa: BLE001
                    logger.info("策略未命中[私信按钮]: %s", desc)
                    continue
                if loc.is_visible():
                    logger.info("命中选择器[私信按钮]: %s", desc)
                    return loc
            except Exception as e:  # noqa: BLE001
                logger.info("策略异常[私信按钮] %s: %s", desc, e)
                continue

        logger.warning("所有策略均未命中[私信按钮]")
        return None

    # ---------- 登录态检查（主页面） ----------
    def is_logged_in(self) -> bool:
        assert self._main_page is not None
        self._main_page.goto(SEL.HOME_URL, wait_until="domcontentloaded")
        self._human_sleep(2, 4)
        for attempt in range(2):
            result = self._check_login_state(self._main_page)
            if result is not None:
                return result
            logger.info("登录态未明确，等待后重试 (%d/2)", attempt + 1)
            self._human_sleep(2, 3)
        logger.warning("多次检查仍无法确认登录态，保守判定为未登录")
        return False

    def _check_login_state(self, page: Page) -> bool | None:
        """返回 True=已登录, False=未登录, None=无法确认。"""
        # 1) URL 被重定向到登录/验证页 → 未登录
        try:
            url = page.url
            if "login" in url.lower() or "verify" in url.lower() or "captcha" in url.lower():
                logger.warning("页面被重定向到: %s，判定为未登录", url)
                return False
        except Exception:  # noqa: BLE001
            pass

        # 2) 检查未登录标志（"登录"按钮 / 登录弹窗）
        for sel in SEL.LOGGED_OUT_INDICATORS:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    logger.warning("检测到未登录标志: %s", sel)
                    return False
            except Exception:  # noqa: BLE001
                continue

        # 3) 检查已登录标志（用户头像 / 用户信息）
        for sel in SEL.LOGGED_IN_INDICATORS:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    logger.info("检测到已登录标志: %s", sel)
                    return True
            except Exception:  # noqa: BLE001
                continue

        # 4) 兜底：导航栏已加载且无"登录"按钮 → 已登录
        try:
            nav = page.locator('[data-e2e="douyin-navigation"]').first
            if nav.count() > 0:
                login_btn = page.locator('button:has-text("登录")').first
                if login_btn.count() == 0:
                    logger.info("导航栏已加载且无登录按钮，判定为已登录")
                    return True
        except Exception:  # noqa: BLE001
            pass

        return None

    # ---------- 步骤3：打开消息页（主页面） ----------
    def open_message_page(self, page: Page) -> bool:
        """直达消息页：优先 URL，失败回退首页导航「消息」入口。"""
        for url in SEL.MESSAGE_PAGE_URLS:
            try:
                logger.info("尝试直达消息页: %s", url)
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_load_state("domcontentloaded")
                ready = self._find_visible(
                    page, SEL.MESSAGE_PAGE_READY, timeout_ms=10000, label="消息页加载标志"
                )
                if ready:
                    logger.info("消息页打开成功: %s", url)
                    return True
                logger.warning("URL %s 已打开但未出现消息页标志", url)
            except Exception as e:  # noqa: BLE001
                logger.warning("打开 %s 失败: %s", url, e)

        # 回退：首页点导航「消息」
        logger.info("URL 直达失败，回退到首页导航「消息」入口")
        try:
            page.goto(SEL.HOME_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:  # noqa: BLE001
            logger.warning("回首页失败: %s", e)

        entry = self._find_visible(page, SEL.MESSAGE_NAV_ENTRY, timeout_ms=10000, label="消息导航入口")
        if not entry:
            logger.error("未找到消息入口（导航页也无「消息」）")
            self._screenshot("message_entry_not_found", page)
            return False
        try:
            entry.click()
        except Exception as e:  # noqa: BLE001
            logger.error("点击消息入口失败: %s", e)
            self._screenshot("message_entry_click_failed", page)
            return False

        ready = self._find_visible(page, SEL.MESSAGE_PAGE_READY, timeout_ms=10000, label="消息页加载标志")
        if not ready:
            logger.error("点击消息入口后未出现消息页标志")
            self._screenshot("message_page_not_ready", page)
            return False
        logger.info("通过导航入口进入消息页成功")
        return True

    # ---------- 步骤4：消息页搜索好友 ----------
    def _search_friend_in_message_page(self, page: Page, friend_name: str) -> bool:
        box = self._find_visible(page, SEL.MESSAGE_SEARCH_BOX, timeout_ms=15000, label="消息页搜索框")
        if not box:
            logger.error("未找到消息页搜索框")
            self._screenshot("message_search_box_not_found", page)
            return False

        box.click()
        try:
            box.fill("")
        except Exception:  # noqa: BLE001
            pass
        self._human_sleep(0.3, 0.8)

        for ch in friend_name:
            box.type(ch, delay=random.randint(80, 200))
        self._human_sleep(0.5, 1.2)
        box.press("Enter")
        logger.info("已在消息页搜索: %s", friend_name)

        try:
            page.wait_for_load_state("domcontentloaded")
        except Exception:  # noqa: BLE001
            pass
        self._human_sleep(1, 2)
        return True

    # ---------- 步骤5：定位好友结果项 ----------
    def _locate_friend_result(self, page: Page, friend_name: str) -> Optional[Locator]:
        """优先昵称精确匹配，多结果取第一个完全一致的。"""
        exact_selectors = [f'text="{friend_name}"']
        exact_selectors += [f'{base}:has-text("{friend_name}")' for base in SEL.FRIEND_RESULT_ITEM]
        found = self._find_visible(page, exact_selectors, timeout_ms=12000, label="好友结果(昵称匹配)")
        if found:
            return found

        logger.warning("未找到昵称精确匹配，尝试取第一个结果项")
        return self._find_visible(page, SEL.FRIEND_RESULT_ITEM, timeout_ms=8000, label="好友结果(第一项)")

    # ---------- 步骤6+7：点击好友进入会话（处理新标签页） ----------
    def open_chat_with(self, page: Page, friend_name: str) -> Optional[tuple[Page, Locator]]:
        """搜索好友并进入会话。成功返回 (目标页面, 输入框Locator)，失败返回 None。"""
        # 步骤3
        if not self.open_message_page(page):
            return None

        # 步骤4
        if not self._search_friend_in_message_page(page, friend_name):
            return None

        # 步骤5
        item = self._locate_friend_result(page, friend_name)
        if not item:
            logger.error("搜索结果中未找到好友: %s", friend_name)
            self._screenshot(f"friend_not_found_{friend_name}", page)
            return None

        # 步骤6：点击好友，监听是否打开新标签页
        try:
            with self._context.expect_page(timeout=10000) as new_page_info:  # type: ignore[union-attr]
                item.click()
            target_page = new_page_info.value
            target_page.wait_for_load_state("domcontentloaded")
            logger.info("好友资料页在新标签页打开: %s", target_page.url[:60])
        except PlaywrightTimeoutError:
            target_page = page
            logger.info("好友「%s」在当前标签页打开", friend_name)
        except Exception as e:  # noqa: BLE001
            logger.error("点击好友结果失败: %s", e)
            self._screenshot(f"friend_click_failed_{friend_name}", page)
            return None

        target_page.wait_for_timeout(2000)
        logger.info("当前操作页面: %s", target_page.url[:60])

        # 先找输入框（会话页直接打开的情况）
        chat_input = self._find_visible(
            target_page, SEL.CHAT_INPUT, timeout_ms=5000, label="聊天输入框(会话页判断)"
        )
        if chat_input:
            logger.info("已直接进入会话页")
            return target_page, chat_input

        # 找不到输入框 → 资料页，点「私信」按钮
        logger.info("判定为用户资料页，查找「私信」按钮")
        dm_btn = self._find_dm_button(target_page, timeout_ms=15000)
        if not dm_btn:
            logger.error("资料页上未找到「私信」按钮")
            self._screenshot("dm_button_not_found_profile", target_page)
            return None

        # 点「私信」，监听会话是否在新标签页打开
        try:
            with self._context.expect_page(timeout=8000) as chat_page_info:  # type: ignore[union-attr]
                dm_btn.click()
            chat_page = chat_page_info.value
            chat_page.wait_for_load_state("domcontentloaded")
            logger.info("会话页在新标签页打开: %s", chat_page.url[:60])
        except PlaywrightTimeoutError:
            chat_page = target_page
            logger.info("会话页在当前标签页打开")
        except Exception as e:  # noqa: BLE001
            logger.warning("点击「私信」常规失败，尝试强制点击: %s", e)
            try:
                dm_btn.click(force=True)
                chat_page = target_page
                logger.info("已强制点击「私信」按钮")
            except Exception as e2:  # noqa: BLE001
                logger.error("点击「私信」按钮失败: %s", e2)
                self._screenshot("dm_button_click_failed", target_page)
                return None

        # 步骤7：在会话页定位输入框
        chat_page.wait_for_timeout(2000)
        logger.info("会话操作页面: %s", chat_page.url[:60])
        chat_input = self._find_visible(chat_page, SEL.CHAT_INPUT, timeout_ms=15000, label="聊天输入框")
        if not chat_input:
            logger.error("进入会话后未找到输入框")
            self._screenshot("chat_input_not_found", chat_page)
            return None

        try:
            chat_input.click()
            logger.info("已定位并聚焦会话输入框")
        except Exception as e:  # noqa: BLE001
            logger.warning("点击输入框失败（可能已被聚焦）: %s", e)

        return chat_page, chat_input

    # ---------- 发送逻辑 ----------
    def send_to_friend(self, friend: FriendConfig, dry_run: bool = True) -> bool:
        """给单个好友发送消息。返回是否成功。"""
        logger.info("开始处理好友: %s (dry_run=%s)", friend.name, dry_run)
        try:
            # 步骤1-7：进会话、定位并聚焦输入框
            result = self.open_chat_with(self._main_page, friend.name)
            if not result:
                return False
            page, _chat_input = result

            # 步骤13：DRY_RUN 只定位，不输入不发送
            if dry_run:
                logger.info("[DRY_RUN] 已定位好友和输入框，不输入不发送")
                self._screenshot("dry_run_input_located", page)
                return True

            has_local_video = bool(friend.video_path and Path(friend.video_path).exists())
            has_video_url = bool(friend.video_url)
            text = (friend.message or "").strip()

            # 步骤8：视频上传（本地文件优先）
            if has_local_video:
                if self._try_upload_video(page, friend.video_path):
                    logger.info("视频上传成功")
                    if text:
                        return self._send_text(page, text)
                    return self._click_send(page)
                logger.info("视频上传不支持，已降级为发送链接")
                name = Path(friend.video_path).name
                text = (f"给你分享一个视频（{name}）：\n{friend.video_url}\n{text}").strip()
                return self._send_text(page, text) if text else False

            if has_video_url:
                logger.info("仅提供视频 URL，私信无法直接上传远程视频，降级为发送链接")
                text = (f"给你分享一个视频：{friend.video_url}\n{text}").strip()
                return self._send_text(page, text) if text else False

            # 步骤9-11：仅文字
            if text:
                return self._send_text(page, text)

            logger.warning("好友 %s 没有可发送的内容", friend.name)
            return False
        finally:
            # 无论成功失败，关闭多余标签页，只保留主页面
            self._close_extra_pages()

    def _try_upload_video(self, page: Page, video_path: str) -> bool:
        """尝试在会话面板上传本地视频，最多等 60 秒。失败返回 False（降级）。"""
        file_input = self._find_visible(page, SEL.FILE_INPUT, timeout_ms=8000, label="文件上传入口")
        if not file_input:
            logger.info("视频上传不支持（未找到 input[type=file]），已降级为发送链接")
            self._screenshot("file_input_not_found", page)
            return False

        try:
            file_input.set_input_files(video_path)
            logger.info("已选择本地视频文件: %s，等待上传完成（最多60秒）", video_path)
        except Exception as e:  # noqa: BLE001
            logger.warning("设置上传文件失败: %s", e)
            return False

        return self._wait_upload_done(page, timeout=60)

    def _wait_upload_done(self, page: Page, timeout: int = 60) -> bool:
        """轮询判断上传是否完成：预览出现=成功；超时=失败降级。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._any_visible(page, SEL.UPLOAD_PREVIEW):
                logger.info("检测到上传预览，视频上传完成")
                return True
            if not self._any_visible(page, SEL.UPLOAD_PROGRESS):
                time.sleep(3)
                if self._any_visible(page, SEL.UPLOAD_PREVIEW):
                    return True
                logger.info("未检测到上传进度/预览，视为已进入可发送状态")
                return True
            time.sleep(2)
        logger.warning("视频上传等待超时（%d秒），降级处理", timeout)
        self._screenshot("upload_timeout", page)
        return False

    def _click_send(self, page: Page) -> bool:
        """视频上传后无文案时直接点发送。"""
        send_btn = self._find_visible(page, SEL.SEND_BUTTON, timeout_ms=5000, label="发送按钮")
        if send_btn:
            send_btn.click()
            logger.info("点击发送按钮发送视频")
        else:
            logger.warning("未找到发送按钮，尝试 Ctrl+Enter 发送视频")
            page.keyboard.press("Control+Enter")
        time.sleep(3)
        self._screenshot("after_send_video", page)
        return True

    def _send_text(self, page: Page, text: str) -> bool:
        """输入文字并发送（步骤9-12）。"""
        chat_input = self._find_visible(page, SEL.CHAT_INPUT, timeout_ms=10000, label="聊天输入框")
        if not chat_input:
            logger.error("未找到私信输入框，无法发送文字")
            self._screenshot("chat_input_not_found", page)
            return False

        try:
            chat_input.click()
            chat_input.fill("")
        except Exception:  # noqa: BLE001
            pass

        logger.info("逐字输入文字消息 (长度=%d, 每字 80-200ms)", len(text))
        for ch in text:
            chat_input.type(ch, delay=random.randint(80, 200))

        # 步骤10：发送前随机等待 2-8 秒
        self._human_sleep(2, 8)

        # 步骤11：点击发送按钮，或按 Enter
        send_btn = self._find_visible(page, SEL.SEND_BUTTON, timeout_ms=5000, label="发送按钮")
        if send_btn:
            try:
                send_btn.click()
                logger.info("已点击发送按钮")
            except Exception as e:  # noqa: BLE001
                logger.warning("点击发送按钮失败，改用 Enter: %s", e)
                chat_input.press("Enter")
        else:
            logger.info("未找到发送按钮，使用 Enter 发送")
            chat_input.press("Enter")

        # 步骤12：发送后等待 3 秒并截图
        try:
            page.wait_for_load_state("domcontentloaded")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3)
        self._screenshot("after_send", page)
        logger.info("文字消息已发送")
        return True
