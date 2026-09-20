# 抖音网页版自动私信（GitHub Actions + Playwright）

> ⚠️ **风险提示**：本项目仅供个人账号低频自动化学习使用。抖音网页版存在风控机制，高频或异常操作可能导致账号被限流、封禁或私信功能受限。使用本项目产生的一切后果由使用者自行承担。请务必遵守抖音服务条款，合理控制频率，模拟真人操作。

## 一、项目用途

每天通过 GitHub Actions 定时（北京时间 07:00）启动 Playwright Chromium，加载预先生成的登录态，自动打开抖音网页版，给指定好友发送文字消息（可选附带短视频/视频链接），并支持失败截图、日志归档和 Webhook 通知。

**核心能力：**
- ✅ 本地扫码登录 → 生成 `storage_state.json` → base64 存入 GitHub Secret
- ✅ GitHub Actions 无头浏览器复用登录态，无需再次扫码
- ✅ 文字消息逐字输入，模拟真人；随机等待 2-8 秒
- ✅ 支持本地视频上传；无上传入口时降级为「视频链接 + 文案」
- ✅ `dry_run` 模式：只定位好友和输入框，不点击发送
- ✅ 失败自动截图、上传日志与截图 artifact
- ✅ 可选 Webhook 通知（飞书 / 钉钉 / 企业微信 / 通用）

---

## 二、本地安装依赖

```bash
# 1. 创建虚拟环境（推荐）
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright Chromium 浏览器
playwright install chromium --with-deps
```

> 要求 Python 3.11+。

---

## 三、获取登录态（本地运行 login.py）

GitHub Actions 环境无法扫码，必须在本地先生成登录态文件。

```bash
python scripts/login.py
```

1. 脚本会弹出有头 Chromium 浏览器，自动打开抖音网页版。
2. 在浏览器中扫码登录。
3. 登录成功后，回到终端按**回车**。
4. 脚本会在项目根目录生成 `storage_state.json`。

> `storage_state.json` 包含你的登录态，**绝不能提交到仓库**（已在 `.gitignore` 中排除）。

---

## 四、Base64 编码并配置 GitHub Secret

将 `storage_state.json` 编码为 base64 字符串：

**Windows PowerShell：**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("storage_state.json"))
```

**Linux / macOS：**
```bash
base64 -w0 storage_state.json
```

复制输出的字符串，在 GitHub 仓库中：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

---

## 五、需要配置的 GitHub Secrets

| Secret 名称 | 必填 | 说明 |
|---|---|---|
| `DOUYIN_STORAGE_STATE_B64` | ✅ | `storage_state.json` 的 base64 编码 |
| `DOUYIN_FRIEND_NAME` | ✅ | 好友昵称（用于搜索） |
| `DOUYIN_MESSAGE` | ✅ | 要发送的文字消息 |
| `DOUYIN_VIDEO_URL` | ⬜ | 短视频直链（无上传入口时作为链接发送） |
| `NOTIFY_WEBHOOK` | ⬜ | 通知 Webhook（飞书/钉钉/企微/通用均可） |

**可选环境变量：**
- `DRY_RUN`：`true`（默认，不发送）/ `false`（真实发送）
- `HEADLESS`：`true`（默认）/ `false`

> 多个好友可通过 `config/friends.json` 配置（复制 `config/friends.example.json` 修改），但主好友仍以环境变量为准。

---

## 六、手动触发 workflow_dispatch

1. 打开仓库的 **Actions** 标签页。
2. 左侧选择 **douyin-daily**。
3. 点击 **Run workflow**。
4. 选择 `dry_run`：
   - `true`：调试模式，只定位不发送（推荐首次使用）
   - `false`：真实发送
5. 点击 **Run workflow** 开始执行。

---

## 七、查看 Actions 日志与 Artifact

- **实时日志**：进入某次运行 → 点击 `douyin-daily` job → 展开各步骤查看输出。
- **日志与截图**：运行结束后，在该次运行页面底部的 **Artifacts** 区域下载 `douyin-run-artifacts`，其中包含：
  - `logs/`：本次运行的完整日志
  - `screenshots/`：关键步骤截图（含失败截图）

---

## 八、定时任务延迟说明

- 工作流使用 `cron: '0 23 * * *'`，对应 **UTC 23:00 = 北京时间 07:00**。
- ⚠️ GitHub Actions 的定时任务**不保证精确触发**，通常会有 **几分钟到几十分钟** 的延迟，高负载时段可能更久。
- 如需确保在某个时间点前完成，建议适当提前 cron 时间，或结合手动触发。

---

## 九、抖音风控与账号安全提醒

1. **低频使用**：建议每天不超过 1-2 次私信，避免被判定为营销号。
2. **模拟真人**：脚本已加入随机等待（2-8 秒）和逐字输入，请勿修改为极速模式。
3. **登录态有效期**：抖音登录态可能在数天到数周后失效。失效时脚本会截图并以**非零退出码**退出，同时发送通知。请重新运行 `scripts/login.py` 生成并更新 Secret。
4. **账号安全**：不要在公共仓库配置 Secret，不要将 `storage_state.json`、Cookie、手机号、Webhook 提交到仓库。
5. **内容合规**：发送内容请遵守相关法律法规和抖音社区规则。
6. **风控应对**：如遇验证码、滑块或登录弹窗，说明登录态已失效或触发风控，请立即停止自动化并手动登录确认账号状态。

---

## 文件结构

```
.
├── .github/workflows/douyin-daily.yml   # GitHub Actions 工作流
├── src/
│   ├── __init__.py
│   ├── main.py                          # 入口
│   ├── douyin_client.py                 # Playwright 核心逻辑
│   ├── config_loader.py                 # 配置加载
│   ├── selectors.py                     # 选择器集中管理
│   └── notifier.py                      # Webhook 通知
├── scripts/
│   └── login.py                         # 本地扫码登录脚本
├── config/
│   └── friends.example.json             # 多好友配置示例
├── requirements.txt
├── .gitignore
└── README.md
```

## 本地调试运行

```bash
# Dry Run（推荐先测试）
DRY_RUN=true HEADLESS=false DOUYIN_FRIEND_NAME="好友昵称" DOUYIN_MESSAGE="测试消息" python -m src.main

# 真实发送
DRY_RUN=false HEADLESS=false DOUYIN_FRIEND_NAME="好友昵称" DOUYIN_MESSAGE="你好" python -m src.main
```

## 常见问题

**Q: 运行报「未找到搜索框/私信按钮」？**
A: 抖音网页版 DOM 经常改版。请打开 `src/selectors.py`，根据最新页面结构更新对应选择器（已提供多组 fallback）。同时查看 artifact 中的截图辅助定位。

**Q: 登录态失效怎么办？**
A: 重新运行 `python scripts/login.py` 扫码登录，重新 base64 编码并更新 `DOUYIN_STORAGE_STATE_B64` Secret。

**Q: 视频无法上传？**
A: 抖音私信面板的文件上传 input 可能隐藏或仅接受特定格式。脚本会自动降级为发送「视频链接 + 文案」。
