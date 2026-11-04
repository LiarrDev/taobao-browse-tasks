#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝浏览任务保活滑动（拟人化轨迹版）

一次「滑动」= 一条连续手指轨迹，而不是一条固定直线的 input swipe：
1. 贝塞尔弧线：三次贝塞尔取点，控制点沿法向随机偏离（幅度为行程的 6%~15%），
   约 1/4 的滑动走 S 形；手指不会给出完美直线。
2. 起终点抖动：起点、终点各自再叠随机偏移，落点不会每轮撞在同一像素。
3. 多段变速：位置按 ease-in-out 采样（首尾慢、中间快），每段时长再叠 ±13% 抖动，
   偶发一次中途停顿；另按小概率切换「短促快滑 / 长距慢拖」，速度分布也不是单一峰。
4. 连贯手势：DOWN → 若干 MOVE → UP 放在同一次 adb shell 里执行，是一条手势。
   `input swipe` 只能走直线匀速，所以默认不用它（设备不支持 motionevent 时才降级）。
5. 验证拦截：周期性检测滑块/人脸验证弹窗，命中立即硬停（退出码 42）。

退出码：0 = 正常完成；42 = 检测到验证需人工处理；1 = adb/设备错误。
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time

# 淘宝常见验证弹窗关键词（避免单独用「验证」以免误判普通文本）
CAPTCHA_KEYWORDS = [
    "安全验证", "滑块", "拖动滑块", "拼图验证", "滑动验证",
    "人机验证", "请完成以下验证", "向右滑动填充", "请按住滑块",
    "拖动完成拼图", "刷脸验证", "人脸识别", "face verification",
    "请拖动", "验证一下", "安全校验",
]

DEFAULT_OVERHEAD_S = 0.040  # 设备端单次 `input` 调用开销的兜底估值


def resolve_adb():
    for cand in ["adb", os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")]:
        try:
            subprocess.run([cand, "version"], capture_output=True, text=True, timeout=10)
            return cand
        except Exception:
            continue
    return "adb"


ADB = resolve_adb()


def adb_run(device, args, timeout=30):
    cmd = [ADB, "-s", device] + args
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def device_sh(device, script, timeout=30):
    """整段脚本作为单个带引号的参数下发，否则 adb 会把分号拆成多条命令。"""
    return adb_run(device, ["shell", "sh -c '%s'" % script], timeout=timeout)


def screen_size(device):
    p = adb_run(device, ["shell", "wm", "size"], timeout=10)
    for line in (p.stdout or "").splitlines() if p else []:
        if ":" in line and "x" in line.split(":")[-1]:
            try:
                w, h = line.split(":")[-1].strip().lower().split("x")
                return int(w), int(h)
            except ValueError:
                continue
    return 1176, 2400


def supports_motionevent(device):
    p = adb_run(device, ["shell", "input"], timeout=10)
    text = (p.stdout or "") + (p.stderr or "") if p else ""
    return "motionevent" in text


def estimate_overhead(device, w, h):
    """实测一次 `input motionevent` 的进程开销，用于把变速卡在设备能分辨的粒度上。"""
    x, y = w // 2, h // 2
    one = "input motionevent MOVE %d %d" % (x, y)
    many = "; ".join(["input motionevent MOVE %d %d" % (x, y + i) for i in range(5)])

    t0 = time.perf_counter()
    p = device_sh(device, one, timeout=20)
    t1 = time.perf_counter()
    if not p or p.returncode != 0:
        return DEFAULT_OVERHEAD_S
    t2 = time.perf_counter()
    q = device_sh(device, many, timeout=20)
    t3 = time.perf_counter()
    if not q or q.returncode != 0:
        return DEFAULT_OVERHEAD_S
    per_call = (t3 - t2 - (t1 - t0)) / 4.0
    return per_call if 0.005 < per_call < 0.25 else DEFAULT_OVERHEAD_S


def bezier(p0, c1, c2, p3, t):
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0],
            a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1])


def ease_in_out(t):
    """首尾慢、中间快：等价于手指从静止加速再减速到静止。"""
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def plan_swipe(args, w, h, overhead_s):
    x0 = random.randint(args.x_min, args.x_max) + random.randint(-8, 8)
    y0 = random.randint(args.y_min, args.y_max) + random.randint(-8, 8)
    dist = random.randint(args.dist_min, args.dist_max) + random.randint(-12, 12)
    dur = random.uniform(args.duration_min, args.duration_max)

    style = random.random()
    if style < 0.12:      # 短促快滑
        dist = int(dist * random.uniform(0.60, 0.78))
        dur *= random.uniform(0.50, 0.70)
    elif style < 0.24:    # 长距慢拖
        dist = int(dist * random.uniform(1.12, 1.30))
        dur *= random.uniform(1.20, 1.50)

    x3 = x0 + random.randint(-26, 26)
    y3 = y0 - dist + random.randint(-16, 16)
    x0 = max(6, min(x0, w - 6))
    y0 = max(6, min(y0, h - 6))
    x3 = max(6, min(x3, w - 6))
    y3 = max(6, min(y3, h - 6))
    if y0 - y3 < 80:      # 落点别贴太近，否则等于没滑
        y3 = max(6, y0 - 80)

    # 弧线：控制点在行进方向的法向上随机偏离，弯曲幅度随行程缩放
    dy = y3 - y0
    side = random.choice((-1, 1))
    bend = max(8.0, abs(dy) * random.uniform(0.06, 0.15)) * side
    if random.random() < 0.25:   # S 形：两个控制点向相反方向偏
        c1 = (x0 + bend * random.uniform(0.60, 1.00), y0 + dy * random.uniform(0.18, 0.32))
        c2 = (x3 - bend * random.uniform(0.40, 0.80), y0 + dy * random.uniform(0.68, 0.86))
    else:                        # 单弧
        c1 = (x0 + bend * random.uniform(0.60, 1.00), y0 + dy * random.uniform(0.18, 0.34))
        c2 = (x0 + bend * random.uniform(0.70, 1.15), y0 + dy * random.uniform(0.66, 0.84))
    c1 = (c1[0] + random.uniform(-4, 4), c1[1] + random.uniform(-4, 4))
    c2 = (c2[0] + random.uniform(-4, 4), c2[1] + random.uniform(-4, 4))

    n = random.randint(args.segments_min, args.segments_max)
    # 每段都要够一次设备端调用开销，否则变速会被进程启动时间抹平
    dur = max(dur, overhead_s * 1000.0 * n * 1.15)

    pts = []
    for k in range(1, n + 1):
        px, py = bezier((x0, y0), c1, c2, (x3, y3), ease_in_out(k / float(n)))
        px += random.uniform(-1.6, 1.6)
        py += random.uniform(-1.6, 1.6)
        pts.append((int(round(max(4, min(px, w - 4)))), int(round(max(4, min(py, h - 4))))))

    weights = [random.uniform(0.88, 1.12) for _ in range(n)]
    total_w = sum(weights)
    dts = [dur * wi / total_w for wi in weights]

    hesitation = None
    if n > 5 and random.random() < 0.15:   # 中途手指顿一下
        hesitation = (random.randint(1, n - 2), random.uniform(0.04, 0.09))

    return {
        "start": (x0, y0),
        "end": (x3, y3),
        "pts": pts,
        "dts": dts,
        "lead_s": random.uniform(0.02, 0.06),
        "lift_s": random.uniform(0.02, 0.07) if random.random() < 0.7 else random.uniform(0.09, 0.16),
        "hesitation": hesitation,
        "dist": y0 - y3,
        "duration_ms": int(dur),
    }


def build_script(g, overhead_s):
    parts = ["input motionevent DOWN %d %d" % g["start"]]
    parts.append("sleep %.3f" % g["lead_s"])
    for k, (px, py) in enumerate(g["pts"]):
        if k > 0:
            gap = g["dts"][k - 1] / 1000.0 - overhead_s
            if gap > 0.004:
                parts.append("sleep %.3f" % gap)
        if g["hesitation"] and g["hesitation"][0] == k:
            parts.append("sleep %.3f" % g["hesitation"][1])
        parts.append("input motionevent MOVE %d %d" % (px, py))
    parts.append("sleep %.3f" % g["lift_s"])
    parts.append("input motionevent UP %d %d" % g["pts"][-1])
    return "; ".join(parts)


def do_swipe(device, args, w, h, overhead_s, method):
    g = plan_swipe(args, w, h, overhead_s)
    if method == "motionevent":
        p = device_sh(device, build_script(g, overhead_s), timeout=20)
        ok = bool(p and p.returncode == 0)
        if p is None:             # 超时可能停在 DOWN 之后，补一次抬手免得手指卡住
            device_sh(device, "input motionevent UP %d %d" % g["pts"][-1], timeout=10)
        elif not ok or "Usage: input" in (p.stdout or "") + (p.stderr or ""):
            method = "swipe"      # 该设备不认 motionevent，降级为直线 swipe
    if method == "swipe":
        p = adb_run(device, ["shell", "input", "swipe",
                             str(g["start"][0]), str(g["start"][1]),
                             str(g["end"][0]), str(g["end"][1]),
                             str(g["duration_ms"])], timeout=20)
        ok = bool(p and p.returncode == 0)
    return ok, method, g


def dump_text(device):
    p = adb_run(device, ["exec-out", "uiautomator", "dump", "/dev/tty"], timeout=20)
    if p and p.returncode == 0 and p.stdout:
        return p.stdout
    return ""


def save_screenshot(device, path):
    p = adb_run(device, ["exec-out", "screencap", "-p"], timeout=20)
    if p and p.returncode == 0 and p.stdout:
        try:
            with open(path, "wb") as f:
                f.write(p.stdout)
            return True
        except Exception:
            return False
    return False


def detect_captcha(device, shot_dir, tag):
    """只做文本匹配；命中验证才截图存证，平时不落图（避免堆一堆无用图片）。"""
    txt = dump_text(device)
    hit = [k for k in CAPTCHA_KEYWORDS if k in txt]
    if hit:
        os.makedirs(shot_dir, exist_ok=True)
        cap_path = os.path.join(shot_dir, "captcha_%s.png" % tag)
        save_screenshot(device, cap_path)
        return hit, cap_path
    return None, None


def human_pause(args):
    p = random.uniform(args.pause_min, args.pause_max)
    r = random.random()
    if r < 0.10:
        p *= random.uniform(0.30, 0.50)   # 连滑两下
    elif r < 0.22:
        p *= random.uniform(1.60, 2.60)   # 停下来看两眼
    return min(p, 8.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--swipes", type=int, default=None,
                    help="固定滑动次数；不指定则随机取 --swipes-min~--swipes-max")
    ap.add_argument("--swipes-min", type=int, default=8)
    ap.add_argument("--swipes-max", type=int, default=12)
    ap.add_argument("--pause-min", type=float, default=1.0)
    ap.add_argument("--pause-max", type=float, default=3.0)
    ap.add_argument("--x-min", type=int, default=360)
    ap.add_argument("--x-max", type=int, default=440)
    ap.add_argument("--y-min", type=int, default=1670)
    ap.add_argument("--y-max", type=int, default=1750)
    ap.add_argument("--dist-min", type=int, default=260)
    ap.add_argument("--dist-max", type=int, default=330)
    ap.add_argument("--duration-min", type=int, default=520,
                    help="单次滑动目标时长（毫秒）；设备粒度不够时会被自动拉长")
    ap.add_argument("--duration-max", type=int, default=780)
    ap.add_argument("--segments-min", type=int, default=10,
                    help="贝塞尔采样段数下限（每段一次 MOVE）")
    ap.add_argument("--segments-max", type=int, default=14)
    ap.add_argument("--method", choices=["motionevent", "swipe", "auto"],
                    default="auto",
                    help="motionevent = 弧线变速连续手势；swipe = 直线降级；auto = 优先 motionevent")
    ap.add_argument("--check-every", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印计划轨迹，不注入任何事件")
    ap.add_argument("--no-captcha", action="store_true",
                    help="跳过验证检测（调试用）")
    args = ap.parse_args()

    if args.swipes is None:
        n_swipes = random.randint(args.swipes_min, args.swipes_max)
    else:
        n_swipes = args.swipes

    shot_dir = os.path.join(args.run_dir, "shots")
    os.makedirs(shot_dir, exist_ok=True)

    w, h = screen_size(args.device)
    if args.method == "auto":
        method = "motionevent" if supports_motionevent(args.device) else "swipe"
    else:
        method = args.method
    if args.dry_run:
        overhead_s = DEFAULT_OVERHEAD_S
    elif method == "motionevent":
        overhead_s = estimate_overhead(args.device, w, h)
    else:
        overhead_s = 0.0

    if args.dry_run:
        plan = plan_swipe(args, w, h, overhead_s)
        print(json.dumps({"status": "DRY_RUN", "method": method,
                          "overhead_ms": round(overhead_s * 1000),
                          "script": build_script(plan, overhead_s) if method == "motionevent"
                          else "input swipe %d %d %d %d %d" % (plan["start"] + plan["end"] + (plan["duration_ms"],))},
                         ensure_ascii=False))
        sys.exit(0)

    # 落地前先验证一次：防止刚进页面就已是验证态
    if not args.no_captcha:
        hit, cap = detect_captcha(args.device, shot_dir, "start")
        if hit:
            print(json.dumps({"status": "CAPTCHA_DETECTED", "step": 0,
                              "keywords": hit, "shot": cap, "action": "STOP"},
                             ensure_ascii=False))
            sys.exit(42)

    durations = []
    for i in range(1, n_swipes + 1):
        ok, method, g = do_swipe(args.device, args, w, h, overhead_s, method)
        if not ok:
            print(json.dumps({"status": "SWIPE_FAILED", "step": i, "action": "STOP"},
                             ensure_ascii=False))
            sys.exit(1)
        durations.append(g["duration_ms"])
        # 单步间不等长停顿：模拟手指发力间隙（加速度突变），不是挂钟等待
        time.sleep(human_pause(args))
        # 周期性验证检测，命中立即硬停
        if not args.no_captcha and i % args.check_every == 0:
            hit, cap = detect_captcha(args.device, shot_dir, i)
            if hit:
                print(json.dumps({"status": "CAPTCHA_DETECTED", "step": i,
                                  "keywords": hit, "shot": cap, "action": "STOP"},
                                 ensure_ascii=False))
                sys.exit(42)

    print(json.dumps({"status": "OK", "swipes": n_swipes, "method": method,
                      "avg_swipe_ms": int(sum(durations) / len(durations))},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
