---
name: taobao-browse-tasks
description: 通过 mobile-mcp 控制已连接的 Android 设备，在淘宝 App 内自动完成「芭芭农场」和「淘金币」的浏览类任务（浏览/逛店 15~20 秒领奖励），自动跳过游戏类、第三方 App 跳转类（蚂蚁庄园、头条、百度、淘宝特价版等）以及下单/加购/关注/邀请等其他类型任务，循环执行到列表无可做任务为止。当用户提到「刷淘宝任务」「做淘宝任务」「芭芭农场」「淘金币」「集肥料」「赚更多金币」「浏览任务」「淘宝薅金币」等诉求时使用本技能。
agent_created: true
---

# 淘宝浏览任务自动完成

## 目的

用 mobile-mcp 驱动一台已连接的 Android 设备，进入淘宝内的指定模块，打开任务列表，**只挑浏览类任务做完，其余一律跳过**，循环直到该模块没有可执行的浏览任务为止。

## 参数解析

- 用户未指定模块 → 默认两个都跑：先「芭芭农场」，再「淘金币」
- 用户指定其中一个 → 只跑该模块
- 安全上限默认 `max_tasks=30`、`max_minutes=20`，用户口头要求可覆盖

## 铁律（每次执行都必须遵守）

1. **只做浏览类任务**。判定规则见 `references/task-classification.md`；拿不准的一律跳过，宁可漏做，不可乱点。
2. **绝对不触发第三方 App 跳转**。一旦出现「是否打开 XX 应用」系统弹窗 → 立即 BACK 或点「取消」。真的离开了淘宝且回不到任务列表时，把该任务加入本次运行黑名单，后续不再点。
3. **不产生任何交易或承诺**：不下单、不付款、不结算加购、不签约、不开会员/免密、不授权通讯录/相册/定位、不安装 App、不输入账号密码。
4. **不碰游戏**：「去玩」「挑战」「抽奖」「合成」等一律跳过（用户明确要求）。
5. 每个任务最多重试 2 次；同一模块连续失败 3 次 → 判定该模块不可用，停止并汇报。
6. 触达 `max_tasks` 或 `max_minutes` 立即收尾汇报，不再继续。

## 执行流程

### 阶段 -1：确认 mobile-mcp 已安装（缺失则先装上）

本 skill 完全依赖 mobile-mcp。**先探测，不要假设它存在**。

1. **探测**：用 ToolSearch 按名字加载 `mcp__mobile-mcp__mobile_list_available_devices`。
   - 能加载且调用成功 → 已安装，跳到阶段 0
   - 工具不存在 / 加载不到任何 `mobile_*` → 未安装，走下面第 2 步
2. **安装**：合并进 MCP 配置文件 `~/.workbuddy/mcp.json`（**注意是 `mcp.json`，不是 `.mcp.json`**），加到 `mcpServers` 里，**不要覆盖已有的其他 server**。
3. **启用**：改完配置不会自动生效，需要用户在自定义连接器入口点「信任」新 server（或重启会话）；告知用户并等待其确认后再继续。
4. **验证**：重新 ToolSearch + `mobile_list_available_devices`，返回设备列表即成功。

#### 安装配置（Android 真机，macOS 已验证）

```json
{
  "mcpServers": {
    "mobile-mcp": {
      "command": "<managed-npx-绝对路径>",
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

关键细节（踩过的坑）：

- **`command` 用 npx 绝对路径**，不要写裸 `npx` —— 托管环境里 PATH 不一定带 node，裸命令会启动失败。可用 `<node-bin-dir>/npx` 指代（例如 `~/.workbuddy/binaries/node/versions/22.22.2-6/bin/npx`），实际路径以本机 `which npx` 为准。
- **`env.PATH` 必须显式带上 `platform-tools`**，否则 server 找不到 `adb`，设备列表恒为空且报错信息不明显。默认 Android SDK 位置 `~/Library/Android/sdk`。
- **`MOBILEMCP_DISABLE_TELEMETRY=1`** 关闭匿名遥测，建议默认带上。

#### 前置依赖

| 依赖 | 要求 | 检查命令 |
|---|---|---|
| Node.js | v20+（本机托管版 22.22.2） | `<node-path> -v` |
| adb / Android Platform Tools | 必须在 PATH 上 | `which adb`，或查 `~/Library/Android/sdk/platform-tools/adb` |
| 手机端 | 开发者选项 → **USB 调试**已开，且已授权本机 | 见下 |

若 `adb` 不存在：装 Android Studio 或单独下 platform-tools，再把路径补进 `env.PATH` 并重启 MCP server。

手机连不上时的排查顺序（实测「扫不到设备」多半是这几条）：

1. USB 线/口换一个，部分线只能充电
2. 手机端重新开关「USB 调试」，重新弹出的授权框点「允许」
3. `adb devices` 看是否列出（`unauthorized` = 未授权，`offline` = 重插）
4. **首次探测为空时，隔几秒再查一次**——实测刚插上或刚授权时第一次会返回空列表，重连一次就能读到

官方文档与更多客户端的配置方式：<https://github.com/mobile-next/mobile-mcp>

### 阶段 0：环境与前置检查

1. 加载工具：若当前工具列表中没有 mobile_* 工具，先用 ToolSearch 按名字加载所需 mobile-mcp 工具，之后统一用 DeferExecuteTool 调用（**加载不到 → 回到阶段 -1 装 mobile-mcp**）。常用清单与调用要点见 `references/mobile-mcp-playbook.md`。
2. `mobile_list_available_devices` → 挑 **platform=android 且 type=real** 的设备：
   - 仅一台 → 直接使用，并向用户报出设备名
   - 多台 → 停下来问用户选哪台
   - 没有本地设备 → **不要静默申请远程设备**（计费资源），先告知用户并询问是否调用 `mobile_allocate_remote_device`
3. `mobile_get_screen_size` → 记录 W×H，后续滑动距离按 H 的比例换算。
4. 初始化本次运行目录与日志：
   ```bash
   python3 .workbuddy/skills/taobao-browse-tasks/scripts/init_run.py --module both
   ```
   脚本返回运行目录、截图目录与日志文件路径（默认落在当前工作区的 `.taobao-task-runs/<时间戳>/`），之后所有截图与记录都写到这里。
5. `mobile_launch_app` 启动 `com.taobao.taobao`，等待约 4 秒让首屏渲染。
6. 出现开屏广告 / 摇一摇 / 红包弹层 / 升级提示 → 点「跳过」「关闭」或 X，绝不点带商品图的区域。

### 阶段 1：进入目标模块

UI 锚点、文案与兜底路径详见 `references/module-entry.md`，摘要：

- **芭芭农场**：我的淘宝 → 「芭芭农场」入口 → 进入后点「**集肥料**」→ 任务列表打开
- **淘金币**：我的淘宝 → 「淘金币」入口 → 进入后点「**赚更多金币**」→ 任务列表打开

关键约束：

- 两个模块多为 H5/小程序容器，**加载慢且会白屏**。点击后 `sleep 3` 再 `mobile_list_elements_on_screen`，未出现目标文案就再等一轮，最多三轮，仍不出现才算卡死。
- 每次导航或页面变化后都要重新 `mobile_list_elements_on_screen`：**ref 只在当前屏幕布局有效，页面一变立即失效**。
- UI 探索 3 次仍找不到入口 → 降级到淘宝搜索框输入「芭芭农场」/「淘金币」，从结果卡片进入；再失败则记录原因并进入下一个模块。

### 阶段 2：解析任务列表

1. `mobile_list_elements_on_screen`（建议 `format: json`，便于读 ref / 坐标 / 文案三元组）。
2. 识别列表结构：每行 = 标题 + 副标题（奖励文案）+ 右侧动作按钮。列表页特征锚点：「集肥料」「赚更多金币」「做任务」「今日任务」「去浏览」「领取」。
3. 逐行分类（严格按 `references/task-classification.md`）：
   - `BROWSE` → 加入可执行队列
   - `GAME` / `THIRD_PARTY` / `OTHER` / `DONE` → 记入跳过清单并注明原因
4. 列表一屏放不下 → 先处理当前屏，处理完再下滑补齐下一屏。**每处理完一个任务，列表常会重排或刷新，必须重新 list。**

### 阶段 3：执行单个浏览任务

对每个 `BROWSE` 任务：

1. **点击**：优先用该行按钮的 `ref`；ref 不可靠时改用其中心坐标。
2. **落地页分流**：点完先 list 一次，判断落在哪种页面，按类型走不同分支：
   - **搜索页** → 有 `EditText` 搜索框 + 「搜索有福利 / 搜索后浏览立得奖励 / 历史搜索 / 搜索发现」等锚点 → 走下方「搜索型浏览任务」分支
   - **会场 / 店铺 / 商品列表页** → 直接进第 4 步浏览保活
3. **拦截二次弹窗**：落地前的「新手引导」「授权弹窗」「领取浮层」一律找 X / 「关闭」/ 「取消」点掉，禁止接受任何权限授权。

#### 搜索型浏览任务（「搜一搜你喜欢的商品」「搜索 XX 得奖励」等）

这类任务点了「去完成」后会落到淘宝搜索页，**必须先进到搜索结果页才算浏览**。处理顺序：

1. **优先点推荐词**（默认做法，不要手输）：`mobile_list_elements_on_screen`，在「搜索发现」/「历史搜索」区域找推荐词卡片，直接点其中一个即可跳进结果页。
   - 典型形态：`android.view.View` 或 `Button`，label 形如「净水器 近一个月曝光超10万」「茶叶 近一个月曝光超2万」「麦片」「衣架」
   - 选词原则：挑**中性纯品类名词**（麦片、卫生纸、衣架、茶叶），避开带明显营销或诱导文案的条目
   - **禁止点搜索框手动输入**——会污染账号搜索历史与个性化推荐；也不要点右侧「搜索」按钮
2. **降级路径**：搜索页没渲染出推荐词（白屏 / 元素列表为空）→ `sleep 3` 后重新 list，最多三轮；三轮后仍无推荐词，才用 `mobile_type_keys` 输入一个中性词并 `submit: true`
3. 落到结果页后照常走第 4 步浏览保活，判定与返回不变

非搜索页直接走这里；搜索型任务点完推荐词落到结果页后，也回到这里继续：

4. **浏览保活循环**（核心）:
   - 目标时长 T：读页面提示的秒数（「浏览 15 秒」「再逛 20 秒」等），读不到则默认 18 秒；最终取 `max(15, min(T, 22))`，始终落在 15~22 秒。
   - 每约 3 秒执行一次 `mobile_swipe_on_screen`：`direction` 先用 `"up"`，起点取屏幕中下部，`distance ≈ H × 0.15`。
   - 第一次滑动后核对内容是否真的向下滚动；方向反了就改用 `"down"`，以实际滚动效果为准，不要盲信方向命名。
   - 每次滑动后 `mobile_get_foreground_app` 校验：
     - 仍是 `com.taobao.taobao` → 继续
     - 已跳到第三方 App → 立刻 BACK；回不来则 HOME 后重进模块，该任务记 `blocked` 并加入黑名单
   - 计时用 Bash `sleep`，每轮把一次截图存进运行目录。
5. **判定完成**：T 秒后再 list 一次，寻找「任务完成」「已获得」「奖励已发放」「去领取」「返回」等文案。有明确信号 → `done`；无信号但停留时长已够 → 也记 `done`，备注写明「未见显式提示」。
6. **返回列表**：连续按 BACK，每按一次 list 一次，看是否出现模块锚点文案，**最多 5 次**。仍回不去 → `mobile_launch_app` 重启淘宝并按阶段 1 重进。
7. **领取**（保守策略）：回到列表后，若该任务按钮变成「领取 / 收下 / 立即领取」且文案不含「去使用 / 去下单 / 去玩」，点一下，点完立刻 BACK 回列表；领取后的落地页不再做任何操作。按钮没变化就不管，多数奖励会自动入账。
8. 追加一行记录到本次运行日志（报告会自动重算，不需要手工维护汇总）：

   ```bash
   python3 .workbuddy/skills/taobao-browse-tasks/scripts/log_task.py \
     --run-dir <run_dir> --module 芭芭农场 --name "浏览某某会场 15 秒" \
     --verdict BROWSE --result 完成 --seconds 18 --note "出现「已获得」提示"
   ```

   跳过的同样要记，方便复盘规则是否合理：

   ```bash
   python3 .workbuddy/skills/taobao-browse-tasks/scripts/log_task.py \
     --run-dir <run_dir> --module 淘金币 --name "去蚂蚁庄园喂鸡" \
     --verdict THIRD_PARTY --result 跳过 --note "需跳转第三方 App"
   ```

### 阶段 4：终止

满足任一条件即停止该模块：

- 自上而下完整遍历列表（最多下滑 6 屏）后无任何 `BROWSE`
- 已完成任务数达到 `max_tasks`
- 已用时长达到 `max_minutes`
- 设备离线、连接失败或淘宝反复闪退

收尾：按 HOME 退出，用 `--finish` 生成最终 report.md，并把它作为交付物呈现给用户：

```bash
python3 .workbuddy/skills/taobao-browse-tasks/scripts/log_task.py --run-dir <run_dir> --finish
```

汇报时要包含：完成 / 跳过（分类别）/ 失败的数量、总浏览时长、日志与截图目录。

## 汇报格式

每个模块一张表：

| # | 任务 | 判定 | 结果 | 停留 | 备注 |
|---|------|------|------|------|------|
| 1 | 浏览某某会场 15 秒 | BROWSE | 完成 | 18s | 出现「已获得」提示 |
| 2 | 去蚂蚁庄园喂鸡 | THIRD_PARTY | 跳过 | - | 需跳转第三方 App |

再附一段小结：完成 N 个、跳过 M 个（游戏 X / 第三方 Y / 其他 Z）、失败 K 个、总耗时、截图与日志所在目录。

## 已知坑

- **ref 失效**：页面任何变化后必须重新 list，复用旧 ref 极易误点到别的位置。
- **截图坐标 ≠ 屏幕坐标**：截图默认缩到 maxSize 1024 以内，工具返回会给出换算比例；用坐标点击前务必先换算。**优先用 ref 规避这个问题**。
- **H5 白屏**：最常见的失败原因，多等一轮再 list 往往就出现了，别急着判失败。
- **屏幕熄灭 / 锁屏**：滑动无响应且 list 返回空时可能已锁屏，提醒用户解锁后继续。
- **列表重排**：完成一个任务后列表常变化，不要凭记忆中的位置点下一个。
- **搜索型任务落在搜索页**：这是最容易走错的一步。别急着在 `EditText` 里 `mobile_type_keys`——先找「搜索发现」/「历史搜索」的推荐词卡片直接点，效果一样且不留搜索痕迹。
- **`EditText` 未必能输入中文**：即便走降级路径手输，`mobile_type_keys` 在部分机型/输入法下可能输入为空，此时放弃该任务记「失败」，不要反复尝试。

## 资源

- 阶段 -1 安装 mobile-mcp 的官方安装文档：<https://github.com/mobile-next/mobile-mcp>
- `scripts/init_run.py` — 创建本次运行的目录、截图目录与日志骨架，并打印路径
- `scripts/log_task.py` — 追加一条任务结果并自动重算 report.md；`--finish` 收尾
- `references/module-entry.md` — 两个模块的入口路径、UI 锚点文案与兜底方案
- `references/task-classification.md` — 任务白/黑名单判定规则，务必先读再动手
- `references/mobile-mcp-playbook.md` — mobile-mcp 工具清单、调用要点、坐标换算与滑动要点
