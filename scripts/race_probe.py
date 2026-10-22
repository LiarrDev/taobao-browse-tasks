#!/usr/bin/env python3
"""抓取赛车活动任务弹层截图，输出：
1) 红色「去完成」按钮中心 y 坐标列表（按行序）
2) 一张小拼图（当前进度 + 全部任务行标题），供模型读数字锚点
用法: python3 race_probe.py <out_png> [--serial 2KE0219B16002658]
"""
import subprocess, sys
from PIL import Image

serial = "2KE0219B16002658"
out = sys.argv[1]
if "--serial" in sys.argv:
    serial = sys.argv[sys.argv.index("--serial") + 1]

raw = out.replace(".png", "_full.png")
data = subprocess.run(["adb", "-s", serial, "exec-out", "screencap", "-p"],
                      capture_output=True).stdout
open(raw, "wb").write(data)

im = Image.open(raw).convert("RGB")
W, H = im.size
px = im.load()

groups, cur = [], None
for y in range(400, H):
    c = 0
    for x in range(940, 1110, 4):
        r, g, b = px[x, y]
        if r > 170 and g < 120 and b < 120 and r - g > 70:
            c += 1
    if c >= 10:
        cur = [y, y] if cur is None else [cur[0], y]
    else:
        if cur:
            groups.append(tuple(cur))
        cur = None
if cur:
    groups.append(tuple(cur))
btns = [(a + b) // 2 for a, b in groups if b - a > 30]

# 小拼图：进度条 + 任务列表（左侧文字列，去掉按钮列以省像素）
head = im.crop((0, 640, 640, 860))
rows = im.crop((0, 850, 900, min(H, 2320)))
scale = 0.72
head = head.resize((int(head.width * scale), int(head.height * scale)))
rows = rows.resize((int(rows.width * scale), int(rows.height * scale)))
canvas = Image.new("RGB", (max(head.width, rows.width), head.height + rows.height + 12), "white")
canvas.paste(head, (0, 0))
canvas.paste(rows, (0, head.height + 12))
canvas.save(out)
print(f'{{"buttons_y": {btns}, "probe": "{out}", "size": {canvas.size}}}')
