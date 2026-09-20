# -*- coding: utf-8 -*-
"""
抖音网页版选择器集中管理（消息页直达流程）。

⚠️ 抖音网页版 DOM 经常改版，每个元素都提供多组 fallback 选择器。
   使用方式：依次尝试，找到「可见」的才用（见 douyin_client._find_visible）。
   全部失败时记录日志并截图。
"""

# ===================== 首页 / 登录态 =====================
HOME_URL = "https://www.douyin.com/"

# 已登录的标志：用户头像 / 用户信息区域（登录后出现）
LOGGED_IN_INDICATORS = [
    'div[data-e2e="user-info"]',
    'div[data-e2e="guide-icon"]',
    'img[data-e2e="user-avatar"]',
    'div[data-e2e="something-button"]:has-text("投稿")',
]

# 未登录标志：登录按钮 / 登录弹窗（出现任一即视为未登录）
LOGGED_OUT_INDICATORS = [
    'button:has-text("登录")',
    'div[data-e2e="login-modal"]',
    'div.login-modal',
    'button[data-e2e="login-button"]',
    'div[data-e2e="login-guide"]',
]

# ===================== 消息页入口 =====================
# 消息页 URL（依次尝试直达）
MESSAGE_PAGE_URLS = [
    "https://www.douyin.com/follow?tab=message",
    "https://www.douyin.com/message",
]

# 首页顶部导航「消息」入口（URL 直达失败时的回退）
MESSAGE_NAV_ENTRY = [
    '[data-e2e="message"]',
    'a[href*="message"]',
    '[data-e2e="douyin-navigation"] :text("消息")',
    ':text("消息")',
]

# 消息页加载成功的标志（搜索框或会话列表出现任一即可）
MESSAGE_PAGE_READY = [
    'input[placeholder*="搜索"]',
    'input[type="search"]',
    '[data-e2e="conversation-list"]',
    '[data-e2e="chat-list"]',
]

# ===================== 消息页搜索 =====================
# 消息页搜索框
MESSAGE_SEARCH_BOX = [
    'input[placeholder*="搜索"]',
    'input[type="search"]',
    '[data-e2e="search-input"]',
    'input[data-e2e="searchbar-input"]',
    'input[placeholder*="查找"]',
]

# ===================== 好友结果项 =====================
# 搜索结果 / 会话列表中的可点击项（代码里会先用昵称精确文本匹配）
FRIEND_RESULT_ITEM = [
    '[data-e2e="friend-item"]',
    '[data-e2e="search-result-item"]',
    '[data-e2e="conversation-item"]',
    '[data-e2e="chat-item"]',
    'div[class*="conversation"] div[class*="item"]',
]

# 「私信」按钮定位策略（按顺序依次尝试，找到可见的第一个就用）。
# kind 说明：
#   role        -> page.get_by_role(kind_arg, name=arg2)
#   text_exact  -> page.get_by_text(arg, exact=True)
#   text_visible-> page.locator(arg).filter(visible=True)
#   css         -> page.locator(arg)
DM_BUTTON_STRATEGIES = [
    ("role", "button", "私信"),
    ("text_exact", "私信", None),
    ("text_visible", "text=私信", None),
    ("css", "button:has-text('私信')", None),
    ("css", "div:has-text('私信')", None),
    ("css", "a:has-text('私信')", None),
    ("css", "[data-e2e*='message']", None),
]

# ===================== 私信会话窗口 =====================
# 聊天输入框（优先 contenteditable div，备选 textarea）
CHAT_INPUT = [
    'div[contenteditable="true"]',
    'textarea',
    '[data-e2e="message-input"]',
    'textarea[placeholder*="输入"]',
    'div[data-e2e="chat-input"] textarea',
]

# 发送按钮
SEND_BUTTON = [
    '[data-e2e="send-button"]',
    'button:has-text("发送")',
    'div[data-e2e="chat-send"] button',
]

# ===================== 视频上传 =====================
# 私信面板中的文件上传 input（通常隐藏）
FILE_INPUT = [
    'input[type="file"][accept*="video"]',
    'div[data-e2e="chat-input"] input[type="file"]',
    'input[type="file"]',
]

# 上传中的进度标志（出现表示还在传）
UPLOAD_PROGRESS = [
    'text=上传中',
    '[class*="progress"]',
]

# 上传完成的预览标志（出现表示上传成功）
UPLOAD_PREVIEW = [
    'video',
    '[class*="upload-success"]',
    'img[class*="preview"]',
]

# ===================== 通用 =====================
# 弹窗关闭按钮
CLOSE_BUTTON = [
    'button[aria-label="关闭"]',
    'div.modal-close',
    'svg.close-icon',
]
