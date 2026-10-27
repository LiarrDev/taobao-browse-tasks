# taobao-browse-tasks

一个 Agent Skill：通过 [mobile-mcp](https://github.com/mobile-next/mobile-mcp) 驱动一台已连接的手机，在淘宝 App 内自动完成「芭芭农场」「淘金币」和「淘宝签到（红包签到·赚元宝）」的**浏览类任务**（浏览 / 逛店 15~30 秒领奖励）。

说一句「刷淘宝任务」「做芭芭农场」「赚更多金币」即可触发；签到模块说「做签到任务」「红包签到」「赚元宝」触发、小黑盒模块说「做小黑盒任务」「集钥匙」触发（默认运行都不包含它们）。

> ⏳ **临时活动模块**：另有「双十一直播体力」「双十一赛车活动」两个临时活动模块，**都只在你明确点名时才跑**，不会自动触发，活动结束后按各自参考文档顶部的「移除清单」整份删除。
>
> - 「双十一直播体力」（deeplink 进活动页 →「赚步数」→ 只做逛直播间任务，进直播间等 7 秒返回）：说「做直播任务」才跑，见 `references/temp-double11-live.md`
> - 「双十一赛车活动」（首页 → 领淘金币 →「赚能量」→ 只做浏览类任务，判定沿用主规则）：说「做赛车活动」才跑，见 `references/temp-double11-race.md`（已实测）
>
> 「小黑盒集钥匙」（deeplink 进活动页 →「做任务集钥匙」→ 只做浏览类任务，落地静置 15 秒返回不滑动，判定沿用主规则）是常驻的手动模块，说「做小黑盒任务」「集钥匙」才跑，见 `references/blackbox-keys.md`（2026-10-25 已实测跑通）

> **兼容性**：本 skill 只是一份标准的 `SKILL.md` + 参考文档 + 脚本，**任何支持 Agent Skill / 能用 MCP 工具的 AI Agent 理论上都可以加载使用**。

## 做什么 / 不做什么

只做浏览类任务，其余一律跳过：

| 类型 | 处理 |
|---|---|
| `BROWSE` 浏览 / 逛店 / 看会场 | ✅ 执行，停留「页面提示秒数 + 3」，不设上限 |
| `GAME` 去玩 / 挑战 / 抽奖 / 合成 | ⏭ 跳过 |
| `THIRD_PARTY` 蚂蚁庄园 / 支付宝 / 头条 / 百度 / 淘宝特价版 | ⏭ 跳过 |
| 阅读 / 听书（浏览看书赚钱 / 有声小说） | ⏭ 跳过（用户明确要求） |
| `OTHER` 下单 / 加购 / 关注 / 邀请 / 看直播 | ⏭ 跳过 |

多轮任务（`搜一搜你心仪的宝贝(0/5)` 这类带 `n/N` 的）**要做满 N 轮**才换下一个，不是做一次就走。

安全上限：默认 `max_tasks=150` 轮、`max_minutes=60` 分钟，以时间为准。

硬约束：**不下单不付款、不授权任何权限、不跳转第三方 App、不手动输入账号密码、不污染搜索历史**。

## 工作原理与耗时

每一轮操作都是一条完整的「感知 → 决策 → 执行」链路：

1. mobile-mcp 读取当前屏幕的可访问性元素（`uiautomator dump`，给出文案 / ref / 坐标），**这一步不截图**
2. 交给大模型读屏、判断当前页面类型、决定下一步点哪里
3. 再调用 mobile-mcp（或其他工具）执行点击 / 滑动 / 返回，然后重新识屏验证

> ⚠️ **因为每一步都要走一遍「识屏 + 大模型推理 + 调用工具」，整体耗时比你自己在手机上手动做任务要长很多。** 单个浏览任务实测约 32~35 秒（落地确认 4s + 挂钟停留 18~23s + 返回与到达校验 8s），其中真正有效的浏览时长只占三分之二左右，其余都花在识屏与推理上。追求效率的话，手刷更快；这个 skill 的价值在于**你不用盯着屏幕**。截图只在三种情况才拍：弹层滚动到底比对、坐标点击后验落点、失败留证。

## 安装

放到你的 skill 目录即可：

```bash
# 用户级（所有项目可用，以所用 Agent 的 skill 目录规范为准）
git clone https://github.com/LiarrDev/taobao-browse-tasks.git ~/.agents/skills/taobao-browse-tasks

# 或项目级
git clone https://github.com/LiarrDev/taobao-browse-tasks.git .agents/skills/taobao-browse-tasks
```

> 下文与各文档里的命令示例均以 `.agents/skills/taobao-browse-tasks/` 为准；装到别处时按实际目录调整。

### 依赖：mobile-mcp

本 skill 完全依赖 mobile-mcp。首次使用若未安装，skill 会引导你写进所用 Agent 的 MCP 配置文件（`mcpServers`），但也可以自己先装好：

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

### 不需要无障碍权限

**本 skill 不需要你在手机里开启「无障碍 / Accessibility」服务，只要 USB 调试即可。** 不用去找那个开关，也无需 root。

原因是 mobile-mcp 完全走 adb shell 通道（运行身份 `uid=2000(shell)`），各环节实现如下：

| 能力 | 实现 | 依赖 |
|---|---|---|
| 识屏（元素列表） | `adb exec-out uiautomator dump /dev/tty`，解析 XML 取 text / content-desc / hint / resource-id / bounds | USB 调试 |
| 截图 | `adb exec-out screencap -p` | USB 调试 |
| 点击 / 滑动 | `input tap` / `input swipe` | USB 调试 |
| 返回 / 按键 | `input keyevent` | USB 调试 |
| 启动 App | `am start` / `am force-stop` | USB 调试 |
| iOS 识屏 | WebDriverAgent（XCTest）的 `/source?format=json` | WDA + 端口转发 |

> 容易混淆的一点：`uiautomator` 底层确实是 `android.app.UiAutomation`，会与系统的 AccessibilityManagerService 交互，但那是 **instrumentation / shell 的系统级通道**，不等同于「设置 → 无障碍 → 已下载的服务」里需要用户手动逐个开启的第三方无障碍服务。
>
> 实测佐证：华为 Mate 30 Pro（Android 12）上 `settings get secure enabled_accessibility_services` 返回**空**（未启用任何无障碍服务），`mobile_list_elements_on_screen` 依然正常返回完整元素树。

**唯一的例外是中文输入**：`adb shell input text` 只支持 ASCII，输入中文需要额外安装 `com.mobilenext.devicekit`（见 [devicekit-android](https://github.com/mobile-next/devicekit-android)），否则会直接报 `Non-ASCII text is not supported`。本 skill 的搜索型任务走的是「点推荐词」路线，不依赖中文输入，因此通常无需安装；只有你想让它手输关键词时才需要。

## 文件结构

```
SKILL.md                            主流程（阶段 -1 ~ 阶段 4）
references/task-classification.md   任务白/黑名单判定规则
references/module-entry.md          三个模块的入口路径与 UI 锚点
references/mobile-mcp-playbook.md   mobile-mcp 工具清单与坐标换算
references/blackbox-keys.md         模块「小黑盒集钥匙」（手动触发，默认运行不包含）
references/temp-double11-live.md    临时活动「双十一直播体力」（手动触发，可整份删除）
references/temp-double11-race.md    临时活动「双十一赛车活动」（手动触发，可整份删除）
scripts/init_run.py                 创建本次运行目录与日志骨架
scripts/log_task.py                 记录单条任务结果，--finish 生成报告
scripts/keepalive_swipe.py          浏览保活随机化滑动 + 验证弹窗拦截（退出码 42）
scripts/diff_shots.py               比对两张截图，判定任务弹层是否已滚到底
scripts/race_probe.py               赛车弹层截图扫按钮列读数（临时活动专用，可整份删除）
```

每次运行会在工作区 `.taobao-task-runs/<时间戳>/` 下产出截图与 `report.md`。

## 注册福利（邀请链接）

如果这个 skill 对你有用，下面是几个 AI Agent 的邀请链接。未曾注册过的话，通过链接注册可获得额外积分，可以直接点击跳转：

- [WorkBuddy](https://www.workbuddy.cn/events/invite?inviteCode=i9ojz1rb2c)
- [TRAE](https://www.trae.cn/events/code-fission/NMNMXE4QWUG7?utm_source=copy_link&utm_medium=code_fission)
- [LobsterAI](https://lobsterai.youdao.com/#/index?keyfrom=invitation) 邀请码：`hWPdpa`（登录时输入邀请码可额外获得 300 积分新人礼包）

## 注意

- 仅供个人学习研究，请遵守淘宝的用户协议与当地法律法规。
- 淘宝 UI 随时可能改版，锚点文案失效时以 `references/module-entry.md` 的兜底路径为准。
- 跑任务前**建议开启屏幕常亮**并插上电源：中途熄屏会让滑动与识屏全部失效。
