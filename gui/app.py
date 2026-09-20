# -*- coding: utf-8 -*-
"""
抖音自动发送 - 配置面板（Tkinter GUI）

功能：
- 多好友管理（列表 + 编辑，保存到 config/friends.json）
- 调用 scripts/login.py 扫码登录
- 生成 storage_state.json 的 base64 并复制到剪贴板
- 定时时间设置（保存到 config/schedule.json + 修改 workflow cron）
- Dry Run 测试 / 真实发送，实时显示日志
"""

from __future__ import annotations

import base64
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

# 项目根目录 = gui/app.py 的上一级
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config_loader import (  # noqa: E402
    FriendConfig,
    ScheduleConfig,
    load_friends_from_file,
    load_schedule,
    save_friends_to_file,
    save_schedule,
)

CONFIG_PATH = ROOT / "config" / "friends.json"
SCHEDULE_PATH = ROOT / "config" / "schedule.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "douyin-daily.yml"
STORAGE_STATE_PATH = ROOT / "storage_state.json"
LOGIN_SCRIPT = ROOT / "scripts" / "login.py"
LOGS_DIR = ROOT / "logs"

PYTHON = sys.executable


class DouyinGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("抖音自动发送 - 配置面板")
        self.root.geometry("820x720")
        self.root.minsize(700, 600)

        # 内存中的好友列表
        self._friends: list[FriendConfig] = []
        self._selected_index: int = -1

        # 子进程相关
        self._proc: subprocess.Popen | None = None
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._reader_thread: threading.Thread | None = None

        self._build_ui()
        self._load_existing_config()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_log_queue()

    # ===================== UI 构建 =====================
    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # 1. 多好友配置区
        friend_frame = ttk.LabelFrame(main, text=" 好友配置（多好友） ", padding=8)
        friend_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # 左侧列表
        left = ttk.Frame(friend_frame)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        ttk.Label(left, text="好友列表").pack(anchor=tk.W)
        self.friend_listbox = tk.Listbox(left, width=28, height=12, exportselection=False)
        self.friend_listbox.pack(fill=tk.Y, expand=True, pady=(2, 4))
        self.friend_listbox.bind("<<ListboxSelect>>", self._on_select_friend)

        list_btns = ttk.Frame(left)
        list_btns.pack(fill=tk.X)
        ttk.Button(list_btns, text="新增", width=6, command=self._add_friend).pack(side=tk.LEFT, padx=1)
        ttk.Button(list_btns, text="删除", width=6, command=self._delete_friend).pack(side=tk.LEFT, padx=1)
        ttk.Button(list_btns, text="上移", width=6, command=lambda: self._move_friend(-1)).pack(side=tk.LEFT, padx=1)
        ttk.Button(list_btns, text="下移", width=6, command=lambda: self._move_friend(1)).pack(side=tk.LEFT, padx=1)

        # 右侧编辑区
        right = ttk.Frame(friend_frame)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(right, text="好友昵称：").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.name_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.name_var).grid(row=0, column=1, sticky=tk.EW, pady=3, padx=(4, 0))

        ttk.Label(right, text="消息文案：").grid(row=1, column=0, sticky=tk.NW, pady=3)
        self.message_text = scrolledtext.ScrolledText(right, height=4, wrap=tk.WORD)
        self.message_text.grid(row=1, column=1, sticky=tk.EW, pady=3, padx=(4, 0))

        ttk.Label(right, text="视频链接：").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.video_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.video_var).grid(row=2, column=1, sticky=tk.EW, pady=3, padx=(4, 0))

        ttk.Button(right, text="保存修改到当前好友", command=self._save_current_friend).grid(
            row=3, column=1, sticky=tk.W, pady=(6, 0)
        )

        right.columnconfigure(1, weight=1)

        # 底部：保存全部
        bottom = ttk.Frame(friend_frame)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        ttk.Button(bottom, text="保存全部到 config/friends.json", command=self._save_all_friends).pack(side=tk.LEFT)

        # 2. 登录态区
        login_frame = ttk.LabelFrame(main, text=" 登录态 ", padding=8)
        login_frame.pack(fill=tk.X, pady=(0, 8))

        btn_row2 = ttk.Frame(login_frame)
        btn_row2.pack(fill=tk.X)
        self.btn_login = ttk.Button(btn_row2, text="打开扫码登录", command=self._start_login)
        self.btn_login.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_login_done = ttk.Button(
            btn_row2, text="我已扫码登录", command=self._confirm_login, state=tk.DISABLED
        )
        self.btn_login_done.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_b64 = ttk.Button(btn_row2, text="生成 base64", command=self._gen_base64)
        self.btn_b64.pack(side=tk.LEFT)

        ttk.Label(
            login_frame,
            text="把生成的 base64 粘贴到 GitHub Secret：DOUYIN_STORAGE_STATE_B64",
            foreground="#666",
        ).pack(anchor=tk.W, pady=(6, 0))

        # 3. 定时设置区
        sched_frame = ttk.LabelFrame(main, text=" 定时设置（北京时间） ", padding=8)
        sched_frame.pack(fill=tk.X, pady=(0, 8))

        sched_row = ttk.Frame(sched_frame)
        sched_row.pack(fill=tk.X)
        ttk.Label(sched_row, text="时间：").pack(side=tk.LEFT)
        self.hour_var = tk.StringVar(value="7")
        self.minute_var = tk.StringVar(value="0")
        ttk.Spinbox(
            sched_row, from_=0, to=23, width=4, textvariable=self.hour_var, format="%02.0f",
            command=self._update_cron_preview,
        ).pack(side=tk.LEFT)
        ttk.Label(sched_row, text=" : ").pack(side=tk.LEFT)
        ttk.Spinbox(
            sched_row, from_=0, to=59, width=4, textvariable=self.minute_var, format="%02.0f",
            command=self._update_cron_preview,
        ).pack(side=tk.LEFT)
        ttk.Label(sched_row, text="  (Asia/Shanghai)  →  cron: ").pack(side=tk.LEFT)
        self.cron_preview = ttk.Label(sched_row, text="0 23 * * *", foreground="#0a7")
        self.cron_preview.pack(side=tk.LEFT)

        ttk.Button(sched_frame, text="保存时间设置", command=self._save_schedule).pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(
            sched_frame,
            text="注意：修改时间后，需要把 .github/workflows/douyin-daily.yml\n"
                 "提交并 push 到 GitHub，定时任务才会按新时间运行。\n"
                 "本地界面只是配置工具，不负责定时执行。",
            foreground="#c60",
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # 4. 测试区
        test_frame = ttk.LabelFrame(main, text=" 测试运行 ", padding=8)
        test_frame.pack(fill=tk.X, pady=(0, 8))

        btn_row3 = ttk.Frame(test_frame)
        btn_row3.pack(fill=tk.X)
        self.btn_dry = ttk.Button(btn_row3, text="Dry Run 测试（不发送）", command=lambda: self._run_main(dry_run=True))
        self.btn_dry.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_send = ttk.Button(btn_row3, text="真实发送一次", command=lambda: self._run_main(dry_run=False))
        self.btn_send.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_logs = ttk.Button(btn_row3, text="查看最近日志", command=self._open_logs)
        self.btn_logs.pack(side=tk.LEFT)

        # 5. 日志区
        log_frame = ttk.LabelFrame(main, text=" 运行日志 ", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("error", foreground="red")
        self.log_text.tag_configure("success", foreground="green")

    # ===================== 好友管理 =====================
    def _load_existing_config(self) -> None:
        """启动时加载已有好友列表和定时设置。"""
        self._friends = load_friends_from_file(CONFIG_PATH)
        self._refresh_listbox()
        sched = load_schedule(SCHEDULE_PATH)
        self.hour_var.set(str(sched.hour))
        self.minute_var.set(str(sched.minute))
        self._update_cron_preview()

    def _refresh_listbox(self) -> None:
        self.friend_listbox.delete(0, tk.END)
        for f in self._friends:
            msg = f.message.replace("\n", " ")
            if len(msg) > 12:
                msg = msg[:12] + "…"
            self.friend_listbox.insert(tk.END, f"{f.name}  |  {msg}")
        if self._friends and self._selected_index >= 0:
            idx = min(self._selected_index, len(self._friends) - 1)
            self.friend_listbox.selection_set(idx)

    def _on_select_friend(self, _event=None) -> None:
        sel = self.friend_listbox.curselection()
        if not sel:
            return
        self._selected_index = sel[0]
        f = self._friends[self._selected_index]
        self.name_var.set(f.name)
        self.message_text.delete("1.0", tk.END)
        self.message_text.insert("1.0", f.message)
        self.video_var.set(f.video_url)

    def _add_friend(self) -> None:
        self._friends.append(FriendConfig(name="新好友", message=""))
        self._selected_index = len(self._friends) - 1
        self._refresh_listbox()
        self._on_select_friend()

    def _save_current_friend(self) -> None:
        if self._selected_index < 0 or self._selected_index >= len(self._friends):
            messagebox.showwarning("提示", "请先在左侧选择一个好友")
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "好友昵称不能为空")
            return
        # 重复校验（排除自己）
        for i, f in enumerate(self._friends):
            if i != self._selected_index and f.name == name:
                messagebox.showwarning("提示", f"好友昵称重复：{name}")
                return
        f = self._friends[self._selected_index]
        f.name = name
        f.message = self.message_text.get("1.0", tk.END).strip()
        f.video_url = self.video_var.get().strip()
        self._refresh_listbox()
        self._log(f"已更新好友：{name}\n", success=True)

    def _delete_friend(self) -> None:
        if self._selected_index < 0 or self._selected_index >= len(self._friends):
            return
        name = self._friends[self._selected_index].name
        if not messagebox.askyesno("确认", f"确定删除好友「{name}」？"):
            return
        del self._friends[self._selected_index]
        self._selected_index = min(self._selected_index, len(self._friends) - 1)
        self._refresh_listbox()
        if self._friends:
            self._on_select_friend()
        else:
            self.name_var.set("")
            self.message_text.delete("1.0", tk.END)
            self.video_var.set("")

    def _move_friend(self, delta: int) -> None:
        if self._selected_index < 0:
            return
        new_idx = self._selected_index + delta
        if new_idx < 0 or new_idx >= len(self._friends):
            return
        self._friends[self._selected_index], self._friends[new_idx] = (
            self._friends[new_idx],
            self._friends[self._selected_index],
        )
        self._selected_index = new_idx
        self._refresh_listbox()

    def _save_all_friends(self) -> None:
        # 校验：不能为空、不能重复
        names = [f.name.strip() for f in self._friends]
        if not all(names):
            messagebox.showwarning("提示", "存在昵称不能为空的好友")
            return
        if len(names) != len(set(names)):
            messagebox.showwarning("提示", "好友昵称不能重复")
            return
        save_friends_to_file(CONFIG_PATH, self._friends)
        self._log(f"已保存 {len(self._friends)} 个好友到 {CONFIG_PATH}\n", success=True)
        messagebox.showinfo("成功", f"已保存 {len(self._friends)} 个好友")

    # ===================== 定时设置 =====================
    def _update_cron_preview(self) -> None:
        try:
            h = int(self.hour_var.get() or 0)
            m = int(self.minute_var.get() or 0)
            sched = ScheduleConfig(hour=max(0, min(23, h)), minute=max(0, min(59, m)))
            self.cron_preview.config(text=sched.to_cron())
        except ValueError:
            self.cron_preview.config(text="无效")

    def _save_schedule(self) -> None:
        try:
            h = int(self.hour_var.get() or 0)
            m = int(self.minute_var.get() or 0)
        except ValueError:
            messagebox.showerror("错误", "时间格式不正确")
            return
        h = max(0, min(23, h))
        m = max(0, min(59, m))
        sched = ScheduleConfig(hour=h, minute=m)

        # 1. 保存 schedule.json
        save_schedule(SCHEDULE_PATH, sched)

        # 2. 修改 workflow 的 cron 行
        cron = sched.to_cron()
        if WORKFLOW_PATH.exists():
            try:
                backup_path = WORKFLOW_PATH.with_suffix(".yml.bak")
                shutil.copy2(WORKFLOW_PATH, backup_path)
                text = WORKFLOW_PATH.read_text(encoding="utf-8")
                new_text, n = re.subn(
                    r"(-\s+cron:\s*)['\"][^'\"]*['\"]",
                    rf"\1'{cron}'",
                    text,
                    count=1,
                )
                if n == 0:
                    messagebox.showwarning("提示", f"已保存 schedule.json，但未在 workflow 中找到 cron 行。\n{cron}")
                    return
                WORKFLOW_PATH.write_text(new_text, encoding="utf-8")
                messagebox.showinfo(
                    "成功",
                    f"已更新为北京时间 {h:02d}:{m:02d}\n"
                    f"对应 cron: {cron}\n\n"
                    f"需要将 .github/workflows/douyin-daily.yml 提交并 push 到 GitHub 才生效。",
                )
                self._log(f"定时设置已保存：北京时间 {h:02d}:{m:02d} → cron: {cron}\n", success=True)
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("错误", f"修改 workflow 失败: {e}")
        else:
            messagebox.showinfo("提示", f"已保存 schedule.json，但未找到 workflow 文件。\ncron: {cron}")

    # ===================== 登录态 =====================
    def _start_login(self) -> None:
        if self._proc and self._proc.poll() is None:
            messagebox.showinfo("提示", "已有登录进程在运行")
            return
        self._log("启动扫码登录，请在弹出的浏览器中扫码...\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        self._proc = subprocess.Popen(
            [PYTHON, str(LOGIN_SCRIPT)],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            bufsize=1,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
        )
        self.btn_login.config(state=tk.DISABLED)
        self.btn_login_done.config(state=tk.NORMAL)
        self._start_reader()

    def _confirm_login(self) -> None:
        if not self._proc or self._proc.poll() is not None:
            return
        try:
            self._proc.stdin.write("\n")  # type: ignore[union-attr]
            self._proc.stdin.flush()  # type: ignore[union-attr]
            self._log("已确认登录，正在保存登录态...\n")
        except Exception as e:  # noqa: BLE001
            self._log(f"确认登录失败: {e}\n", error=True)

    def _gen_base64(self) -> None:
        if not STORAGE_STATE_PATH.exists():
            messagebox.showerror("错误", f"未找到 {STORAGE_STATE_PATH}\n请先完成扫码登录。")
            return
        raw = STORAGE_STATE_PATH.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        self.root.clipboard_clear()
        self.root.clipboard_append(b64)
        self.root.update()
        self._log(f"base64 已生成并复制到剪贴板（长度 {len(b64)}）\n", success=True)
        messagebox.showinfo("成功", "base64 已复制到剪贴板\n请粘贴到 GitHub Secret: DOUYIN_STORAGE_STATE_B64")

    # ===================== 测试运行 =====================
    def _run_main(self, dry_run: bool) -> None:
        if self._proc and self._proc.poll() is None:
            messagebox.showinfo("提示", "已有进程在运行，请等待结束")
            return
        # 保存当前好友列表到文件
        if self._friends:
            save_friends_to_file(CONFIG_PATH, self._friends)

        mode = "Dry Run 测试" if dry_run else "真实发送"
        self._log(f"===== 开始 {mode}（共 {len(self._friends)} 个好友）=====\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["DRY_RUN"] = "true" if dry_run else "false"
        env["HEADLESS"] = "false"
        # 不设 DOUYIN_FRIEND_NAME，让 main.py 从 friends.json 读取全部好友
        env.pop("DOUYIN_FRIEND_NAME", None)
        env.pop("DOUYIN_MESSAGE", None)
        env.pop("DOUYIN_VIDEO_URL", None)

        self._proc = subprocess.Popen(
            [PYTHON, "-m", "src.main"],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            bufsize=1,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
        )
        self._set_buttons_running(True)
        self._start_reader()

    def _open_logs(self) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(LOGS_DIR))  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            messagebox.showinfo("日志目录", str(LOGS_DIR))

    # ===================== 子进程输出 =====================
    def _start_reader(self) -> None:
        def reader():
            assert self._proc is not None and self._proc.stdout is not None
            for line in self._proc.stdout:
                self._log_queue.put(line)
            self._log_queue.put("__PROCESS_DONE__")

        self._reader_thread = threading.Thread(target=reader, daemon=True)
        self._reader_thread.start()

    def _poll_log_queue(self) -> None:
        try:
            while True:
                line = self._log_queue.get_nowait()
                if line == "__PROCESS_DONE__":
                    self._on_process_done()
                else:
                    self._log(line)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def _on_process_done(self) -> None:
        if self._proc:
            code = self._proc.wait()
            if code != 0:
                self._log(f"进程退出，返回码: {code}（失败）\n", error=True)
            else:
                self._log(f"进程退出，返回码: {code}（成功）\n", success=True)
            self._proc = None
        self._set_buttons_running(False)
        self.btn_login.config(state=tk.NORMAL)
        self.btn_login_done.config(state=tk.DISABLED)

    # ===================== 日志 & 按钮 =====================
    def _log(self, text: str, error: bool = False, success: bool = False) -> None:
        self.log_text.config(state=tk.NORMAL)
        tag = "error" if error else ("success" if success else "")
        if tag:
            self.log_text.insert(tk.END, text, tag)
        else:
            self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _set_buttons_running(self, running: bool) -> None:
        state = tk.DISABLED if running else tk.NORMAL
        self.btn_dry.config(state=state)
        self.btn_send.config(state=state)
        if not running:
            self.btn_login.config(state=tk.NORMAL)

    # ===================== 关闭 =====================
    def _on_close(self) -> None:
        if self._proc and self._proc.poll() is None:
            if not messagebox.askyesno("确认", "有进程正在运行，确定要关闭吗？"):
                return
            try:
                self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    DouyinGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
