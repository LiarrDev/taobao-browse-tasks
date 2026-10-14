# taobao-browse-tasks

一个 [WorkBuddy](https://www.workbuddy.cn) / Claude-style Agent Skill：通过 [mobile-mcp](https://github.com/mobile-next/mobile-mcp) 驱动一台已连接的 Android 真机，在淘宝 App 内自动完成「芭芭农场」和「淘金币」的**浏览类任务**（浏览 / 逛店 15~20 秒领奖励）。

说一句「刷淘宝任务」「做芭芭农场」「赚更多金币」即可触发。

> **兼容性**：本 skill 在 [WorkBuddy](https://www.workbuddy.cn) 中创建并验证，但它只是一份标准的 `SKILL.md` + 参考文档 + 脚本，**任何支持 Agent Skill / 能用 MCP 工具的 AI Agent 理论上都可以加载使用**。

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

## 工作原理与耗时

每一轮操作都是一条完整的「感知 → 决策 → 执行」链路：

1. mobile-mcp 截图并列出当前屏幕的可访问性元素（文案 / ref / 坐标）
2. 交给大模型读屏、判断当前页面类型、决定下一步点哪里
3. 再调用 mobile-mcp（或其他工具）执行点击 / 滑动 / 返回，然后重新识屏验证

> ⚠️ **因为每一步都要走一遍「识屏 + 大模型推理 + 调用工具」，整体耗时比你自己在手机上手动做任务要长很多。** 单个浏览任务实测约 28~30 秒（含落地、18 秒停留保活、返回），其中真正有效的浏览时长只占一半左右，其余都花在识屏与推理上。追求效率的话，手刷更快；这个 skill 的价值在于**你不用盯着屏幕**。

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

### 设备支持

| 平台 | 状态 |
|---|---|
| Android 真机 | ✅ 已实测验证（华为 Mate 30 Pro 5G / Android 12） |
| iOS 真机 | 🟡 **未在 iOS 上验证过**；但 [mobile-mcp](https://github.com/mobile-next/mobile-mcp) 本身支持 iOS 驱动，**理论上 iOS 设备也能使用本 skill** |

iOS 上的差异主要在这几处，遇到时可据此调整：设备发现与连接走 mobile-mcp 的 iOS 通道（而非 adb）、返回手势不是 `BACK` 按钮而是边缘滑动、App 启动用的是 bundle id 而非 package name。`SKILL.md` 里的判定规则与流程本身与平台无关。

### 手机端前置

- Android：开发者选项 → **USB 调试**已开，并已授权本机
- iOS：按 mobile-mcp 文档的 iOS 通道完成配对与信任
- **建议开启屏幕常亮**（开发者选项里的「充电时不锁定屏幕」，或把自动锁屏调到最长时间）。跑满 60 分钟的任务期间屏幕一旦熄灭，滑动与识屏都会失效，skill 会误判为卡死。

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
- 跑任务前**建议开启屏幕常亮**并插上电源：中途熄屏会让滑动与识屏全部失效。
