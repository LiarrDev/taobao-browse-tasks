# taobao-browse-tasks

一个 [WorkBuddy](https://www.workbuddy.cn) / Claude-style Agent Skill：通过 [mobile-mcp](https://github.com/mobile-next/mobile-mcp) 驱动一台已连接的 Android 真机，在淘宝 App 内自动完成「芭芭农场」和「淘金币」的**浏览类任务**（浏览 / 逛店 15~20 秒领奖励）。

说一句「刷淘宝任务」「做芭芭农场」「赚更多金币」即可触发。

## 做什么 / 不做什么

只做浏览类任务，其余一律跳过：

| 类型 | 处理 |
|---|---|
| `BROWSE` 浏览 / 逛店 / 看会场 | ✅ 执行，停留 15~22 秒 |
| `GAME` 去玩 / 挑战 / 抽奖 / 合成 | ⏭ 跳过 |
| `THIRD_PARTY` 蚂蚁庄园 / 头条 / 百度 / 淘宝特价版 | ⏭ 跳过 |
| `OTHER` 下单 / 加购 / 关注 / 邀请 | ⏭ 跳过 |

多轮任务（`搜一搜你心仪的宝贝(0/5)` 这类带 `n/N` 的）**要做满 N 轮**才换下一个，不是做一次就走。

安全上限：默认 `max_tasks=150` 轮、`max_minutes=60` 分钟，以时间为准。

硬约束：**不下单不付款、不授权任何权限、不跳转第三方 App、不手动输入账号密码、不污染搜索历史**。

## 安装

放到你的 skill 目录即可：

```bash
# 用户级（所有项目可用）
git clone https://github.com/LiarrDev/taobao-browse-tasks.git ~/.workbuddy/skills/taobao-browse-tasks

# 或项目级
git clone https://github.com/LiarrDev/taobao-browse-tasks.git .workbuddy/skills/taobao-browse-tasks
```

### 依赖：mobile-mcp

本 skill 完全依赖 mobile-mcp。首次使用若未安装，skill 会引导你写入 `~/.workbuddy/mcp.json`，但也可以自己先装好：

```json
{
  "mcpServers": {
    "mobile-mcp": {
      "command": "<npx-绝对路径>",
      "args": ["-y", "@mobilenext/mobile-mcp@latest"],
      "env": {
        "PATH": "<node-bin-dir>:<android-sdk>/platform-tools:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "ANDROID_HOME": "<android-sdk>",
        "ANDROID_SDK_ROOT": "<android-sdk>",
        "MOBILEMCP_DISABLE_TELEMETRY": "1"
      }
    }
  }
}
```

`command` 务必写 npx 的**绝对路径**，且 `env.PATH` 必须包含 `platform-tools`，否则 adb 找不到、设备列表恒为空。

手机端前置：开发者选项 → USB 调试已开并已授权本机。

## 文件结构

```
SKILL.md                          主流程（阶段 -1 ~ 阶段 4）
references/task-classification.md 任务白/黑名单判定规则
references/module-entry.md        两个模块的入口路径与 UI 锚点
references/mobile-mcp-playbook.md mobile-mcp 工具清单与坐标换算
scripts/init_run.py               创建本次运行目录与日志骨架
scripts/log_task.py               记录单条任务结果，--finish 生成报告
```

每次运行会在工作区 `.taobao-task-runs/<时间戳>/` 下产出截图与 `report.md`。

## 注意

- 仅供个人学习研究，请遵守淘宝的用户协议与当地法律法规。
- 淘宝 UI 随时可能改版，锚点文案失效时以 `references/module-entry.md` 的兜底路径为准。
