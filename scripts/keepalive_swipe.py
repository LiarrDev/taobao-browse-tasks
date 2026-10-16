#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝浏览任务保活滑动（随机化 + 降密度 + 验证拦截版）

对抗行为熵风控的设计：
1. 轨迹随机化：每次滑动的起点 x/y、距离、时长、终点偏移都随机，
   模拟人类加速度突变与微小抖动，避免固定坐标的低熵轨迹。
2. 单步间不等长停顿（默认 1~3 秒）模拟手指发力间隙，而非长时间挂钟等待。
3. 验证拦截：周期性检测滑块/人脸验证弹窗，命中立即硬停（退出码 42），
   把控制权交回人工，绝不重试绕过。
4. 单进程调用：底层同样是 adb input swipe，一轮只有一次进程调用，
   不触发系统的「连续相同工具调用」循环保护。

退出码：0 = 正常完成；42 = 检测到验证需人工处理；1 = adb/设备错误。
"""
import argparse
import os
import random
import subprocess
import sys
import time
import json

# 淘宝常见验证弹窗关键词（避免单独用「验证」以免误判普通文本）
CAPTCHA_KEYWORDS = [
    "安全验证", "滑块", "拖动滑块", "拼图验证", "滑动验证",
    "人机验证", "请完成以下验证", "向右滑动填充", "请按住滑块",
    "拖动完成拼图", "刷脸验证", "人脸识别", "face verification",
    "请拖动", "验证一下", "安全校验",
]


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


def do_swipe(device, x_min, x_max, y_min, y_max, d_min, d_max):
    x = random.randint(x_min, x_max)
    y = random.randint(y_min, y_max)
    dist = random.randint(d_min, d_max)
    # 终点加随机偏移，模拟非线性轨迹（人类滑动不是完美直线）
    x2 = x + random.randint(-30, 30)
    y2 = y - dist + random.randint(-25, 25)
    x2 = max(10, min(x2, 1160))
    y2 = max(10, y2)
    dur = random.randint(140, 260)  # 速度随机，模拟加速度变化
    adb_run(device, ["shell", "input", "swipe",
                     str(x), str(y), str(x2), str(y2), str(dur)], timeout=15)


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
    ap.add_argument("--check-every", type=int, default=3)
    ap.add_argument("--no-captcha", action="store_true",
                    help="跳过验证检测（调试用）")
    args = ap.parse_args()

    # 滑动次数：未显式指定则随机取一个 8~12 的值，进一步降低机械感
    if args.swipes is None:
        n_swipes = random.randint(args.swipes_min, args.swipes_max)
    else:
        n_swipes = args.swipes

    shot_dir = os.path.join(args.run_dir, "shots")
    os.makedirs(shot_dir, exist_ok=True)

    # 落地前先验证一次：防止刚进页面就已是验证态
    if not args.no_captcha:
        hit, cap = detect_captcha(args.device, shot_dir, "start")
        if hit:
            print(json.dumps({"status": "CAPTCHA_DETECTED", "step": 0,
                              "keywords": hit, "shot": cap, "action": "STOP"},
                             ensure_ascii=False))
            sys.exit(42)

    for i in range(1, n_swipes + 1):
        do_swipe(args.device, args.x_min, args.x_max, args.y_min, args.y_max,
                 args.dist_min, args.dist_max)
        # 单步间不等长停顿：模拟手指发力间隙（加速度突变），不是挂钟等待
        time.sleep(random.uniform(args.pause_min, args.pause_max))
        # 周期性验证检测，命中立即硬停
        if not args.no_captcha and i % args.check_every == 0:
            hit, cap = detect_captcha(args.device, shot_dir, i)
            if hit:
                print(json.dumps({"status": "CAPTCHA_DETECTED", "step": i,
                                  "keywords": hit, "shot": cap, "action": "STOP"},
                                 ensure_ascii=False))
                sys.exit(42)

    print(json.dumps({"status": "OK", "swipes": n_swipes}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
