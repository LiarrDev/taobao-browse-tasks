# mobile-mcp 操作手册

## 工具可用性

mobile-mcp 的工具属于延迟加载工具：若当前工具列表中没有 `mobile_*`，先用 ToolSearch 按精确名字加载，再用 DeferExecuteTool 调用。

需要加载的核心工具（全部以 `mcp__mobile-mcp__` 开头）：

| 工具 | 用途 |
|------|------|
| `mobile_list_available_devices` | 发现本机已连接的设备（无参数） |
| `mobile_list_remote_devices` | 查看远程云真机队列 |
| `mobile_allocate_remote_device` | 申请远程真机（**计费，必须先征得用户同意**） |
| `mobile_release_remote_device` | 任务全部结束后释放远程设备 |
| `mobile_get_screen_size` | 拿 W×H，用于换算滑动距离 |
| `mobile_get_foreground_app` | 校验当前是否还在目标 App |
| `mobile_list_apps` | 确认包名（淘宝主包：`com.taobao.taobao`） |
| `mobile_launch_app` | 冷启动 / 重新拉起 App |
| `mobile_list_elements_on_screen` | 取 ref / 坐标 / 文案，必传 `device` |
| `mobile_click_on_screen_at_coordinates` | 点击，`ref` 优先于 `x,y` |
| `mobile_swipe_on_screen` | 滑动保活 |
| `mobile_press_button` | HOME / BACK / ENTER 等 |
| `mobile_take_screenshot` | 看画面（不缓存） |
| `mobile_save_screenshot` | 截图落盘到运行目录 |
| `mobile_type_keys` | 输入搜索关键词 |

## device 参数

所有交互类工具都要传 `device`，取 `mobile_list_available_devices` 返回的 `id` 字段（例如 `2KE0219B16002658`），不是 name/model。

## ref 的生命周期

`mobile_list_elements_on_screen` 返回的 ref（形如 `@e5`）**只在当前屏幕布局不变时有效**。下述情况必须重新 list：

- 任何点击导致页面跳转 / 弹层出现或消失
- 列表刷新、新增或重排条目
- 按下 BACK 之后
- 勾选 / 展开 / 收起等局部布局变化

**反例（禁止）**：拿到列表 ref 后，先去别的页面转一圈，回来直接用旧 ref 点第二个任务。

## 点击优先级

1. 元素出现在 list 结果里 → 用 `ref`
2. 只在截图上看得到、list 里没有（例如图片型按钮、Webview 内部控件）→ `mobile_take_screenshot` 观察后换算坐标点 `x,y`
3. 点击失败（无响应）→ 重新 list 拿新 ref，不要用同一坐标反复戳

## 坐标换算

`mobile_take_screenshot` 会把画面缩到 `maxSize`（默认 1024）以内，返回信息里会说明「截图坐标 → 屏幕坐标」的换算方式。**按该说明换算后再传 `x,y`**，直接把截图里的像素值当屏幕坐标是错的。

参考示例：屏幕 1176×2400 的设备，截图宽被缩到 1024 时，换算系数约 1176/1024 ≈ 1.148。

## 滑动

```json
{ "device": "<id>", "direction": "up", "x": 588, "y": 1700, "distance": 360 }
```

- `direction`：`up` / `down` / `left` / `right`
- `distance`：Android 不传时默认为屏幕某维度的 30%（对 2400 高的屏约 720px，通常过长，容易滑过头），浏览保活建议显式给 `H × 0.15`（约 340~380px）
- `x, y`：起点，不传则默认屏幕中心；保活滑动建议起点放在偏下部，避免误触顶部悬浮控件
- **方向语义以实际效果为准**：第一次滑动后用 list 或截图核对内容是否朝预期方向移动，反了就改成相反方向

## 等待

工具集里没有 sleep 工具，需要等待时用 Bash：

```bash
sleep 3
```

常用等待时长：App 冷启动 4s，H5 页面加载 3s，弹窗动画 1s，滑动保活间隔 3s。

## 前台校验

滑动循环里穿插 `mobile_get_foreground_app`，判断是否被跳转到第三方 App：

- 返回 `com.taobao.taobao` → 正常
- 返回其他包名 → 立即 `mobile_press_button` BACK，回到淘宝；回不到任务列表就 HOME 后重新 `mobile_launch_app`

## 截图留痕

每完成一个任务至少存一张关键截图：

```json
{ "device": "<id>", "saveTo": "<run_dir>/shots/<n>_<slug>.png", "maxSize": 720 }
```

文件名用「序号_任务短名」避免覆盖，不要用 `mobile_take_screenshot` 的结果代替落盘——它不缓存、不可回溯。
