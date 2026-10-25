#!/usr/bin/env python3
"""Append one task outcome to a run directory and regenerate report.md.

Typical usage after each handled task:

    python3 log_task.py --run-dir <run_dir> \
        --module 芭芭农场 --name "浏览某某会场 15 秒" \
        --verdict BROWSE --result 完成 --seconds 18 --note "出现「已获得」提示"

Skipped / failed rows work identically, e.g.:

    python3 log_task.py --run-dir <run_dir> --module 淘金币 \
        --name "去蚂蚁庄园喂鸡" --verdict THIRD_PARTY --result 跳过 --note "需跳转第三方 App"

The report table and the summary counters at <run_dir>/report.md are rewritten
from scratch on every call based on tasks.jsonl.
"""

import argparse
import json
import os
import sys
from datetime import datetime

VERDICTS = ["BROWSE", "GAME", "THIRD_PARTY", "OTHER", "DONE", "UNKNOWN"]
# "失败-未入账" is a distinct sub-kind of failure: the browse timer ran long
# enough but the reward/progress never moved. It counts into 失败 in the report
# (the counters below match on prefix) but stays visible in the detail table.
RESULTS = ["完成", "跳过", "失败", "失败-未入账"]
# Progress is tracked per logged round, e.g. "3/5"; the same task name may
# appear many times, once per round, until it reaches N/N.


def load_tasks(tasks_log: str) -> list:
    tasks = []
    if os.path.exists(tasks_log):
        with open(tasks_log, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        tasks.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return tasks


def write_report(report_path: str, meta: dict, tasks: list, finished_at: str = None) -> dict:
    done = [t for t in tasks if str(t.get("result", "")).startswith("完成")]
    skipped = [t for t in tasks if str(t.get("result", "")).startswith("跳过")]
    failed = [t for t in tasks if str(t.get("result", "")).startswith("失败")]
    total_seconds = sum(int(t.get("seconds") or 0) for t in done)

    lines = []
    lines.append("# 淘宝浏览任务运行记录\n")
    lines.append(f"- 开始时间：{meta.get('started_at', '-')}")
    lines.append(f"- 结束时间：{finished_at or '（进行中）'}")
    lines.append(f"- 设备：{meta.get('device') or '（未指定）'}")
    lines.append(f"- 模块：{'、'.join(meta.get('modules', []))}")
    lines.append(f"- 安全上限：最多 {meta.get('max_tasks')} 轮 / {meta.get('max_minutes')} 分钟\n")
    lines.append("## 汇总\n")
    lines.append(f"- 完成：{len(done)} 轮（累计浏览 {total_seconds} 秒）")
    unrecorded = [t for t in failed if str(t.get("result", "")).startswith("失败-")]
    lines.append(f"- 跳过：{len(skipped)} 个")
    for v in ["GAME", "THIRD_PARTY", "OTHER", "DONE"]:
        lines.append(f"  - {v}：{len([t for t in skipped if t.get('verdict') == v])} 个")
    lines.append(f"- 失败：{len(failed)} 个")
    if unrecorded:
        lines.append(f"  - 其中「未入账」（停留够但进度/余额没动）：{len(unrecorded)} 个")
    lines.append("")

    # Per-slot progress: a slot is one (module, task name) pair that may be
    # executed several rounds until its (n/N) counter is maxed out.
    # NOTE: --progress holds the counter read at the START of a round, so the
    # last round of a filled slot always shows (N-1)/N. We therefore also treat
    # an explicit "做满" in the note as proof the slot actually reached N/N.
    slots = {}
    slot_full = {}
    slot_truncated = {}
    for t in tasks:
        if not t.get("progress"):
            continue
        key = (t.get("module", ""), t.get("name", ""))
        try:
            n, total = (int(x) for x in str(t["progress"]).split("/", 1))
        except ValueError:
            continue
        cur = slots.get(key)
        if cur is None or (n, total) >= (cur[0], cur[1]):
            slots[key] = (n, total)
        note = t.get("note") or ""
        if "做满" in note:
            slot_full[key] = True
        elif "截断" in note:
            slot_truncated[key] = note
    if slots:
        full = 0
        lines.append("## 多轮槽位进度\n")
        for (module, name), (n, total) in slots.items():
            key = (module, name)
            if slot_full.get(key):
                full += 1
                flag, shown = "做满 ✅", f"{total}/{total}"
            elif slot_truncated.get(key):
                flag, shown = "被截断 ⚠️", f"{n}/{total}"
            else:
                flag, shown = "未满 ⏳", f"{n}/{total}"
            extra = f"（{slot_truncated[key]}）" if flag == "被截断 ⚠️" and slot_truncated[key] != "截断" else ""
            lines.append(f"- {module} · {name}：{shown} {flag}{extra}")
        lines.append(f"\n共 {len(slots)} 个多轮槽位，其中做满 {full} 个\n")

    lines.append("## 任务明细\n")
    lines.append("| # | 模块 | 任务 | 进度 | 判定 | 结果 | 停留 | 备注 |")
    lines.append("|---|------|------|------|------|------|------|------|")
    for i, t in enumerate(tasks, 1):
        secs = t.get("seconds")
        stay = f"{secs}s" if secs else "-"
        lines.append(
            f"| {i} | {t.get('module', '')} | {t.get('name', '')} | {t.get('progress') or '-'} "
            f"| {t.get('verdict', '')} | {t.get('result', '')} | {stay} | {t.get('note', '')} |"
        )
    if not tasks:
        lines.append("| - | - | 暂无记录 | - | - | - | - |")

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return {"done": len(done), "skipped": len(skipped), "failed": len(failed), "seconds": total_seconds}


def main() -> int:
    parser = argparse.ArgumentParser(description="Log one Taobao task outcome and refresh report.md.")
    parser.add_argument("--run-dir", required=True, help="Run directory created by init_run.py")
    # TEMP(双十一临时活动): 去掉 help 里的「直播体力」即可。
    # TEMP(双十一赛车临时活动): 去掉 help 里的「赛车活动」即可。
    # TEMP(小黑盒临时活动): 去掉 help 里的「小黑盒」即可。
    parser.add_argument("--module", default="", help="芭芭农场 / 淘金币 / 直播体力(临时活动) / 赛车活动(临时活动) / 小黑盒(临时活动)")
    parser.add_argument("--name", default="", help="Task title as shown on screen")
    parser.add_argument("--verdict", default="UNKNOWN", choices=VERDICTS)
    parser.add_argument("--result", default="跳过", choices=RESULTS)
    parser.add_argument("--seconds", type=int, default=0,
                        help="Wall-clock seconds actually stayed on the landing page "
                             "(the measured now - t0, not the page's nominal target)")
    parser.add_argument(
        "--progress",
        default="",
        help="Multi-round progress read from the task row, e.g. 3/5. Log one row per round.",
    )
    parser.add_argument("--note", default="", help="Reason or evidence")
    parser.add_argument("--finish", action="store_true", help="Mark the run as finished")
    args = parser.parse_args()

    run_dir = os.path.expanduser(args.run_dir)
    tasks_log = os.path.join(run_dir, "tasks.jsonl")
    report_path = os.path.join(run_dir, "report.md")
    if not os.path.isdir(run_dir):
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        return 1

    meta = {}
    meta_path = os.path.join(run_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)

    tasks = load_tasks(tasks_log)
    if args.name:
        tasks.append(
            {
                "at": datetime.now().isoformat(timespec="seconds"),
                "module": args.module,
                "name": args.name,
                "verdict": args.verdict,
                "result": args.result,
                "seconds": args.seconds,
                "progress": args.progress,
                "note": args.note,
            }
        )
        with open(tasks_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(tasks[-1], ensure_ascii=False) + "\n")

    finished_at = None
    if args.finish:
        finished_at = datetime.now().isoformat(timespec="seconds")

    counts = write_report(report_path, meta, tasks, finished_at)
    counts["tasks_total"] = len(tasks)
    counts["report_path"] = report_path
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
