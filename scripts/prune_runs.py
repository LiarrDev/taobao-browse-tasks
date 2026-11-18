#!/usr/bin/env python3
"""按保留期清理运行目录，避免 .taobao-task-runs 里的截图与日志无限堆积。

只处理 root 的**直接子目录**，且目录名要像一次运行（含 `YYYYMMDD` 日期，兼容
`20261117-103145` / `20261113-1532` / `signin-20261102` 几种写法），并且里面得有
运行产物（`report.md` / `meta.json` / `tasks.jsonl` / `rounds_status.jsonl` / `shots/`）。
符号链接、普通文件、名字不合规或没有产物的目录一律跳过——也就是说，即使 --dir
传错成别的地方，也不会去动用户的其它文件。

用法：
    python3 scripts/prune_runs.py                     # 只报告，不删（默认干跑）
    python3 scripts/prune_runs.py --apply             # 真删
    python3 scripts/prune_runs.py --keep-days 7       # 改保留期（默认 3 天）
    python3 scripts/prune_runs.py --dir /abs/path --apply

输出一个 JSON：{"root", "keep_days", "applied", "removed": [...], "kept",
"skipped": [...], "freed_bytes", "errors": [...]}

init_run.py 每次建新运行目录前会自动调用 `prune(..., apply=True)`，
所以正常跑任务不需要手工执行本脚本。
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta

DEFAULT_ROOT = ".taobao-task-runs"  # relative to the current working directory
DEFAULT_KEEP_DAYS = 3

# 允许 init_run.py 的标准命名 20261117-103145，以及手工建过的变体：
# 20261113-1532（时:分）/ 20261113-1621-signin / signin-20261102
RUN_NAME_RE = re.compile(
    r"^(?:[a-z]{2,12}-)?(?P<date>\d{8})(?:-(?P<time>\d{4}|\d{6}))?(?:-[a-z]{2,12})?$"
)
# 内容指纹：至少命中一个才认为是本 skill 产出的运行目录
RUN_MARKERS = ("report.md", "meta.json", "tasks.jsonl", "rounds_status.jsonl", "shots")


def _run_started_at(name):
    """按目录名解析运行开始时间；名字不合规返回 None。

    兼容 `signin-20261102` 这种缺时分秒的写法（补 00:00:00）。
    """
    m = RUN_NAME_RE.match(name)
    if not m:
        return None
    timestr = m.group("time") or ""
    if len(timestr) == 4:  # HHMM
        timestr += "00"
    try:
        return datetime.strptime(m.group("date") + (timestr or "000000"), "%Y%m%d%H%M%S")
    except ValueError:  # 形如 20261399-256099 的合法位数但非法日期
        return None


def _looks_like_run(path):
    """目录里得有运行产物之一，才认定是运行目录（防止误伤同名空目录）。"""
    return any(os.path.exists(os.path.join(path, m)) for m in RUN_MARKERS)


def _check_root(root):
    """拦住「root 是根目录 / home 或 home 的上级 / 符号链接」这几种误删。"""
    real = os.path.realpath(root)
    home = os.path.realpath(os.path.expanduser("~"))
    if real == os.path.abspath(os.sep) or real == home or home.startswith(real + os.sep):
        raise SystemExit(f"拒绝在 {real} 上执行清理：它是根目录，或用户 home 的上级目录")
    if os.path.islink(root):
        raise SystemExit(f"拒绝在符号链接 {root} 上执行清理")
    if not os.path.isdir(real):
        raise SystemExit(f"目录不存在：{root}")
    return real


def _dir_size(path):
    total = 0
    for base, _dirs, files in os.walk(path, followlinks=False):
        for fn in files:
            try:
                total += os.lstat(os.path.join(base, fn)).st_size
            except OSError:
                pass
    return total


def prune(root=DEFAULT_ROOT, keep_days=DEFAULT_KEEP_DAYS, apply=False, now=None):
    """删除 root 下开始时间早于 keep_days 天、且近期没被动过的运行目录。

    apply=False 时只统计不删。返回报告 dict（结构即命令行输出的 JSON）。
    """
    root = os.path.abspath(os.path.expanduser(root))
    real = _check_root(root)
    now = now or datetime.now()
    cutoff = now - timedelta(days=keep_days)
    cutoff_ts = cutoff.timestamp()

    report = {
        "root": real,
        "keep_days": keep_days,
        "cutoff": cutoff.isoformat(timespec="seconds"),
        "applied": bool(apply),
        "removed": [],
        "kept": 0,
        "skipped": [],
        "freed_bytes": 0,
        "errors": [],
    }

    for entry in sorted(os.scandir(real), key=lambda e: e.name):
        if not entry.is_dir(follow_symlinks=False):
            continue  # 文件 / 符号链接
        started = _run_started_at(entry.name)
        if started is None:
            report["skipped"].append(entry.name)  # 名字不像运行目录，不碰
            continue
        if not _looks_like_run(entry.path):
            report["skipped"].append(entry.name)  # 里面没有运行产物，不碰
            continue
        if started >= cutoff:
            report["kept"] += 1
            continue
        try:
            # 还在写入（目录 mtime 晚于截止点）就先留着，交给下一轮运行再清
            if entry.stat(follow_symlinks=False).st_mtime >= cutoff_ts:
                report["kept"] += 1
                continue
        except OSError as exc:
            report["errors"].append(f"{entry.name}: {exc}")
            continue

        size = _dir_size(entry.path)
        if apply:
            try:
                shutil.rmtree(entry.path)
            except OSError as exc:
                report["errors"].append(f"{entry.name}: {exc}")
                continue
        report["removed"].append(
            {"dir": entry.name, "started_at": started.isoformat(timespec="seconds"), "bytes": size}
        )
        report["freed_bytes"] += size

    return report


def main():
    parser = argparse.ArgumentParser(description="清理超过保留期的淘宝任务运行目录。")
    parser.add_argument(
        "--dir",
        default=DEFAULT_ROOT,
        help=f"运行目录的根，相对 CWD 或绝对路径 (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--keep-days",
        type=int,
        default=DEFAULT_KEEP_DAYS,
        help=f"保留最近多少天 (default: {DEFAULT_KEEP_DAYS})",
    )
    parser.add_argument("--apply", action="store_true", help="真正删除；默认只报告不删")
    args = parser.parse_args()

    report = prune(args.dir, args.keep_days, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
