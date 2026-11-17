#!/usr/bin/env python3
"""单轮浏览任务执行器：点任务行的按钮列 -> 判落地形态 -> 按形态浏览 -> 回任务弹层。

只做浏览类。绝不下单／加购／关注／授权／安装／离开淘宝；命中验证弹窗立即停手。

处理的落地形态（每轮重判，不沿用上一轮）：
    STATIC   详情页 / 整屏内容流       -> 静置 N 秒不滑动 -> BACK
    IRP      拍立淘双列图片结果页      -> 停留 6 秒 -> BACK
    VENUE    TMS 会场 / 商铺 / 混合流  -> keepalive_swipe 一轮拟人化连发 -> BACK
    SEARCH   TMS「搜索有福利」中间页 / 原生搜索门
             -> 点「搜索发现」中性品类词 -> 结果页滑 1 次 -> 点普通商品卡
             -> 详情静置 N 秒 -> 逐次 BACK 判落点回弹层
    UNKNOWN  未知容器 -> 停手，留证交人工

用法（先自己看 race_probe.py 的 buttons_y 或 list 结果，确认这一行是浏览类再传 y）：
    python3 scripts/browse_round.py \
      --device 2KE0219B16002658 --run-dir .taobao-task-runs/20261105-115406 \
      --y 958 --rounds 9,10 --rest 27 --static 20

注意：本脚本**不判断这一行是什么任务**——第三方/玩法行被点中会跳走。
调用方负责先确认该 y 对应的是 BROWSE 行；弹层每轮会重排，跨轮不能沿用旧 y。
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from io import BytesIO

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("需要 Pillow：python3 -m pip install pillow")

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
KEEPALIVE = os.path.join(SCRIPTS_DIR, "keepalive_swipe.py")

# 权限/验证/登录类容器：一出现就停手，交人工
BAD_CONTAINERS = (
    "Ext2ContainerActivity", "Permission", "packageinstaller",
    "GrantPermissions", "UserLoginActivity", "LoginActivity",
)


def find_adb():
    p = shutil.which("adb")
    if p:
        return p
    for cand in (
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
        "/usr/local/bin/adb", "/opt/homebrew/bin/adb",
    ):
        if os.path.exists(cand):
            return cand
    sys.exit("找不到 adb：把它放进 PATH，或设置 ANDROID_HOME")


ADB = find_adb()


class Device:
    def __init__(self, serial, run_dir, width, height):
        self.serial = serial
        self.run_dir = run_dir
        self.shots = os.path.join(run_dir, "shots")
        os.makedirs(self.shots, exist_ok=True)
        self.w = width
        self.h = height

    # ---------- 基础注入 ----------
    def adb(self, *args, binary=False):
        p = subprocess.run([ADB, "-s", self.serial, *map(str, args)], capture_output=True)
        return p.stdout if binary else p.stdout.decode("utf-8", "ignore").strip()

    def shell(self, *args):
        return self.adb("shell", *args)

    def focus(self):
        # 只用 grep -m1 取整行：grep -oE 会命中更靠前的 mFocusedApp，读数永远对不上
        out = subprocess.run(
            f"{ADB} -s {self.serial} shell dumpsys window | grep -m1 mCurrentFocus",
            shell=True, capture_output=True, text=True,
        ).stdout
        return out.strip()

    def tap(self, x, y):
        """坐标点击：框内随机偏几像素，不次次命中同一像素"""
        self.shell("input", "tap", int(x) + random.randint(-3, 3), int(y) + random.randint(-3, 3))

    def back(self):
        self.shell("input", "keyevent", 4)

    def shot(self, name):
        path = os.path.join(self.shots, name)
        with open(path, "wb") as fp:
            fp.write(self.adb("exec-out", "screencap", "-p", binary=True))
        return path

    def grab(self, name):
        data = self.adb("exec-out", "screencap", "-p", binary=True)
        path = os.path.join(self.shots, name)
        with open(path, "wb") as fp:
            fp.write(data)
        return Image.open(BytesIO(data)).convert("RGB")


# ---------- 图像判据 ----------
def button_centers(im, x_from=None):
    """按钮列色块中心 y 列表（默认扫右侧 x∈[0.80W, 0.95W]）

    淘宝各模块弹层的按钮配色不同：淘金币/赛车是红色，芭芭农场是绿色，
    所以红、绿两族都算，只看「高饱和纯色块」这层共性。
    """
    w, h = im.size
    x0 = x_from if x_from is not None else int(w * 0.80)
    x1 = int(w * 0.95)
    px = im.load()
    segs, cur = [], None
    for y in range(int(h * 0.15), h):
        cnt = 0
        for x in range(x0, x1, 4):
            r, g, b = px[x, y]
            red = r > 170 and g < 120 and b < 120 and r - g > 70
            green = g > 140 and r < 130 and b < 140 and g - r > 60
            # 淘金币弹层的「去完成/去逛逛」是橙黄渐变（g≈120~170），
            # 纯红/绿两族都漏判；补一族橙色，弹层返回判定才认得出按钮列。
            orange = r > 200 and 60 < g < 200 and b < 130 and r - g > 55 and r - b > 120
            if red or green or orange:
                cnt += 1
        if cnt >= 10:
            cur = [y, y] if cur is None else [cur[0], y]
        else:
            if cur:
                segs.append(tuple(cur))
                cur = None
    if cur:
        segs.append(tuple(cur))
    return [(a + b) // 2 for a, b in segs if b - a > 30]


def is_popup_layer(im, expect_ys=None, tol=40):
    """任务弹层判定。

    弹层特征：右侧按钮列有 ≥4 个红色色块，且相邻中心间距是同一行距的整数倍
    （「已完成」的行按钮变灰、色块消失，间距就会变成 2×/3× 行距，所以要按行距拟合）。
    会场 / feeds / 搜索结果页不会有这种等距按钮列——这比「黑进度条」更通用。
    给了 expect_ys（该模块实测行位）时，命中 ≥4 个直接判弹层（弹层滚动会有 ±30px 平移）。
    """
    ys = button_centers(im)
    if expect_ys:
        hit = sum(1 for y in ys if any(abs(y - e) < tol for e in expect_ys))
        if hit >= 4:
            return True, ys
    if len(ys) < 4:
        return False, ys
    gaps = [b - a for a, b in zip(ys, ys[1:]) if b - a >= 100]
    if len(gaps) < 3:
        return False, ys
    # 行距取「最小间距」而不是中位数：弹层里灰掉的行会让间距变成 2×/3× 行距，
    # 一半的间距是倍数时中位数会翻倍，反而全部拟合失败。
    pitch = min(gaps)
    if not (120 <= pitch <= 400):
        return False, ys
    slack = max(6.0, pitch * 0.04)
    fits = sum(1 for g in gaps if min(abs(g - k * pitch) for k in (1, 2, 3)) <= slack)
    return fits >= 3 and fits >= len(gaps) - 1, ys


def white_ratio(im):
    """顶部横幅区全白像素占比：搜索中间页 ≥0.86，会场/结果页 ≤0.36"""
    w, h = im.size
    box = (0, int(h * 0.167), w, int(h * 0.458))
    crop = im.crop(box)
    px = list(crop.getdata())
    return sum(1 for r, g, b in px if r > 235 and g > 235 and b > 235) / max(1, len(px))


def save_probe(im, dev, tag):
    """留一张对账拼图：顶部读数区 + 任务行区；能量区单独放大；每 3 轮补一张全屏缩略"""
    w, h = im.size
    head = im.crop((0, int(h * 0.267), int(w * 0.545), int(h * 0.358)))
    rows = im.crop((0, int(h * 0.354), int(w * 0.765), int(h * 0.967)))
    s = 0.72
    head = head.resize((int(head.width * s), int(head.height * s)))
    rows = rows.resize((int(rows.width * s), int(rows.height * s)))
    canvas = Image.new("RGB", (max(head.width, rows.width), head.height + rows.height + 12), "white")
    canvas.paste(head, (0, 0))
    canvas.paste(rows, (0, head.height + 12))
    canvas.save(os.path.join(dev.shots, f"{tag}_after_probe.png"))
    im.crop((0, int(h * 0.087), int(w * 0.474), int(h * 0.15))).resize((1040, 300)).save(
        os.path.join(dev.shots, f"{tag}_energy.png"))
    num = "".join(ch for ch in tag if ch.isdigit())
    if num and int(num) % 3 == 0:
        im.resize((int(w * 0.4), int(h * 0.4))).save(os.path.join(dev.shots, f"{tag}_full_small.png"))


# ---------- 动作 ----------
def swipe_batch(dev, run_dir, swipes_min=8, swipes_max=12, dist=(260, 330), dur=(520, 780)):
    cmd = [
        sys.executable, KEEPALIVE, "--device", dev.serial, "--run-dir", run_dir,
        "--swipes-min", str(swipes_min), "--swipes-max", str(swipes_max),
        "--pause-min", "1", "--pause-max", "3",
        "--x-min", str(int(dev.w * 0.31)), "--x-max", str(int(dev.w * 0.37)),
        "--y-min", str(int(dev.h * 0.70)), "--y-max", str(int(dev.h * 0.73)),
        "--dist-min", str(dist[0]), "--dist-max", str(dist[1]),
        "--duration-min", str(dur[0]), "--duration-max", str(dur[1]),
        "--check-every", "3",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    tail = (p.stdout.strip().splitlines() or [""])[-1]
    print(f"  swipe: {tail[-160:]}", flush=True)
    return p.returncode


def swipe_wake(dev, run_dir):
    """双列 feeds 唤醒：单次短行程，只为触发滚动、把新卡带进视口"""
    cmd = [
        sys.executable, KEEPALIVE, "--device", dev.serial, "--run-dir", run_dir,
        "--swipes", "1", "--pause-min", "1", "--pause-max", "2",
        "--x-min", str(int(dev.w * 0.30)), "--x-max", str(int(dev.w * 0.38)),
        "--y-min", str(int(dev.h * 0.70)), "--y-max", str(int(dev.h * 0.74)),
        "--dist-min", "200", "--dist-max", "265", "--duration-min", "460", "--duration-max", "660",
    ]
    return subprocess.run(cmd, capture_output=True, text=True).returncode


def back_until_layer(dev, tag, expect_ys=None, tries=5, settle=2.1):
    """逐次 BACK 并判落点，回弹层即停（不连按，弹层 dump 会冻结）"""
    for i in range(1, tries + 1):
        dev.back()
        time.sleep(settle + i * 0.25)
        im = dev.grab(f"{tag}_back_{i}.png")
        ok, _ = is_popup_layer(im, expect_ys)
        f = dev.focus()
        print(f"  back{i}: layer={ok} focus={f.split('/')[-1][:-1][:44]}", flush=True)
        if ok:
            return im
        if "com.taobao.taobao/" not in f:
            print(f"  back{i}: 已离开淘宝，补一次 BACK", flush=True)
            dev.back()
            time.sleep(2.4)
    return None


# ---------- 单轮 ----------
def run_round(dev, n, y, cfg, expect_ys=None):
    tag = f"r{n}"
    dev.tap(int(dev.w * 0.87), y)
    print(f"{tag} tap button@{int(dev.w * 0.87)},{y}", flush=True)
    time.sleep(cfg.settle)
    f = dev.focus()
    if "Welcome" in f:            # 窗口切换竞态：等 4~5 秒再取
        time.sleep(4.3)
        f = dev.focus()
    im = dev.grab(f"{tag}_land.png")
    if any(k in f for k in BAD_CONTAINERS):
        print(f"{tag} STOP 验证/授权/登录页：{f.split('/')[-1][:-1]}", flush=True)
        return "ALERT"
    if "com.taobao.taobao/" not in f:
        time.sleep(3.5)
        f = dev.focus()
    if "com.taobao.taobao/" not in f:
        print(f"{tag} STOP 已离开淘宝：{f.split('/')[-1][:-1]}", flush=True)
        dev.back()
        return "LEFT_APP"
    landed_popup, _ = is_popup_layer(im, expect_ys)
    if landed_popup:
        print(f"{tag} STOP 点击未跳转，仍在弹层", flush=True)
        return "NO_JUMP"

    tag_name = f.split("/")[-1][:-1] if "/" in f else f
    print(f"{tag} focus={tag_name[:52]}", flush=True)

    # --- 搜索中间页：点推荐词 -> 结果页 -> 点卡 -> 静置 ---
    if "SearchActivity" in f or ("TMSActivity" in f and white_ratio(im) >= cfg.search_wr):
        wx = random.choice(cfg.words)
        dev.tap(wx[0], wx[1])
        print(f"{tag} 搜索中间页 点推荐词 {wx}", flush=True)
        time.sleep(4.9)
        swipe_wake(dev, cfg.run_dir)
        cx = random.choice(cfg.cards)
        dev.tap(cx[0], cx[1])
        time.sleep(5.0)
        f2 = dev.focus()
        if "Welcome" in f2:
            time.sleep(3.6)
            f2 = dev.focus()
        print(f"{tag} 结果页点卡后 focus={f2.split('/')[-1][:-1][:44]}", flush=True)
        if "TTDetailActivity" in f2 or "NewDetailActivity" in f2:
            print(f"{tag} 详情静置 {cfg.static:.1f}s 未滑动", flush=True)
            time.sleep(cfg.static + random.uniform(-0.5, 1.2))
        else:
            time.sleep(3.0)      # 没进详情：按结果页浏览计，直接退
        layer = back_until_layer(dev, tag, expect_ys, tries=3)
        if layer is None:
            return "BACK_FAIL"
        save_probe(layer, dev, tag)
        return "SEARCH"

    # --- 拍立淘：双列图片结果页，停留即算 ---
    if "IrpActivity" in f:
        time.sleep(6.0)
        layer = back_until_layer(dev, tag, expect_ys, tries=2)
        if layer is None:
            return "BACK_FAIL"
        save_probe(layer, dev, tag)
        return "IRP"

    # --- 详情 / 整屏内容流：静置，不滑 ---
    if "NewDetailActivity" in f or "TTDetailActivity" in f:
        print(f"{tag} 整屏内容流静置 {cfg.static:.1f}s 未滑动", flush=True)
        time.sleep(cfg.static + random.uniform(-0.6, 1.0))
        layer = back_until_layer(dev, tag, expect_ys, tries=2)
        if layer is None:
            return "BACK_FAIL"
        save_probe(layer, dev, tag)
        return "STATIC"

    # --- 会场 / feeds / 混合模块流：连发拟人化滑动保活 ---
    if "TMSActivity" in f or "Activity" in f:
        print(f"{tag} 会场型落地（wr={white_ratio(im):.2f}），连发拟人化滑动", flush=True)
        rc = swipe_batch(dev, cfg.run_dir, cfg.swipes_min, cfg.swipes_max)
        if rc == 42:
            print(f"{tag} STOP 命中验证弹窗（退出码 42）", flush=True)
            return "CAPTCHA"
        if rc == 1:
            print(f"{tag} STOP 手势注入失败（设备掉线 / adb 超时）", flush=True)
            return "SWIPE_FAIL"
        layer = back_until_layer(dev, tag, expect_ys, tries=2)
        if layer is None:
            return "BACK_FAIL"
        save_probe(layer, dev, tag)
        return "VENUE"

    print(f"{tag} STOP 未知容器：{tag_name[:52]}", flush=True)
    return "UNKNOWN"


def main():
    ap = argparse.ArgumentParser(
        description="淘宝任务弹层单轮浏览执行器（点行 -> 判形态 -> 浏览 -> 回弹层）")
    ap.add_argument("--device", required=True, help="adb serial（mobile_list_available_devices 的 id）")
    ap.add_argument("--run-dir", required=True, help="init_run.py 生成的运行目录")
    ap.add_argument("--y", type=int, required=True,
                    help="该行按钮中心 y。必须是已确认为浏览类的行；弹层每轮重排，别沿用旧值")
    ap.add_argument("--rounds", default="1", help="逗号分隔的轮次编号，用于截图命名，如 9,10,11")
    ap.add_argument("--rest", type=float, default=26.0, help="轮间休息秒数（铁律 13 降密度）")
    ap.add_argument("--static", type=float, default=20.0, help="静置型停留秒数（15 秒档取 20）")
    ap.add_argument("--settle", type=float, default=5.2, help="点击后等落地秒数")
    ap.add_argument("--search-wr", type=float, default=0.86,
                    help="TMSActivity 白屏率阈值：≥该值判搜索中间页，实测搜索页 ≥0.86 / 会场 ≤0.36")
    ap.add_argument("--expect-ys", default="",
                    help="该模块弹层按钮行 y 列表（逗号分隔，弹层判定用）；留空则按等距按钮列自动判")
    ap.add_argument("--swipes-min", type=int, default=8)
    ap.add_argument("--swipes-max", type=int, default=12)
    ap.add_argument("--words", default="",
                    help="搜索发现词块中心坐标，分号分隔：x,y;x,y；留空按屏宽比例取 8 个默认格")
    ap.add_argument("--cards", default="", help="结果页商品卡中心坐标，同上格式")
    ap.add_argument("--keep-going", action="store_true", help="失败也继续跑后面的轮次（默认遇到异常即停）")
    cfg = ap.parse_args()

    # 屏幕尺寸（坐标全部按比例换算，换机型不用改脚本）
    sz = subprocess.run([ADB, "-s", cfg.device, "shell", "wm", "size"],
                        capture_output=True, text=True).stdout
    dims = sz.strip().splitlines()[-1].split(":")[-1].strip().split("x")
    w, h = int(dims[0]), int(dims[1])
    dev = Device(cfg.device, cfg.run_dir, w, h)

    def parse_pairs(s, default):
        if not s.strip():
            return default
        return [tuple(int(v) for v in part.replace(" ", "").split(","))
                for part in s.split(";") if part.strip()]

    word_default = [(int(w * 0.255), int(h * r)) for r in (0.533, 0.635, 0.733, 0.833)] + \
                   [(int(w * 0.734), int(h * r)) for r in (0.533, 0.635, 0.733, 0.833)]
    card_default = [(int(w * 0.255), int(h * 0.325)), (int(w * 0.734), int(h * 0.325)),
                    (int(w * 0.255), int(h * 0.65)), (int(w * 0.734), int(h * 0.65))]
    cfg.words = parse_pairs(cfg.words, word_default)
    cfg.cards = parse_pairs(cfg.cards, card_default)
    cfg.run_dir = os.path.abspath(cfg.run_dir)
    expect_ys = [int(v) for v in cfg.expect_ys.split(",") if v.strip()] or None

    print(json.dumps({"device": cfg.device, "screen": f"{w}x{h}", "run_dir": cfg.run_dir,
                      "y": cfg.y, "rounds": cfg.rounds, "static": cfg.static,
                      "words": cfg.words, "cards": cfg.cards}, ensure_ascii=False), flush=True)

    for idx, n in enumerate([int(v) for v in cfg.rounds.split(",")]):
        time.sleep(random.uniform(2, 4) if idx == 0 else max(1.0, cfg.rest + random.uniform(-3, 4)))
        status = run_round(dev, n, cfg.y, cfg, expect_ys)
        with open(os.path.join(cfg.run_dir, "rounds_status.jsonl"), "a") as fp:
            fp.write(json.dumps({"round": n, "y": cfg.y, "status": status}, ensure_ascii=False) + "\n")
        print(f"== r{n} -> {status}", flush=True)
        if status not in ("STATIC", "IRP", "VENUE", "SEARCH") and not cfg.keep_going:
            print(f"batch stop at r{n}: {status}", flush=True)
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
