#!/usr/bin/env python3
"""Compare two screenshots and decide whether the screen actually changed.

Main use: deciding when the Taobao task-list poplayer has scrolled to the
bottom. Inside that poplayer the uiautomator dump goes stale after a swipe
(the overlay subtree comes back byte-identical while the background page in
the same dump does refresh), so "the element list is unchanged" is NOT proof
of "no more content" — only the pixels are. Feed this script two consecutive
shots and it tells you whether they are the same screen.

    python3 diff_shots.py <run_dir>/shots/list_a.png <run_dir>/shots/list_b.png

Exit code 0 always (except errors); the answer is in the JSON on stdout:

    {"same_screen": true, "score": 99.4, "threshold": 98.0, "changed": 612,
     "total": 259200, "a": "...", "b": "..."}

`score` is the mean per-pixel similarity across all channels (0-100).
`same_screen` is `score >= threshold`; when it is true, stop scrolling — the
list is at the bottom.

Runs on plain Pillow; no ImageMagick needed.
"""

import argparse
import json
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    print(json.dumps({"error": "Pillow is required: python3 -m pip install pillow"}))
    sys.exit(2)

# Downscale target: tall-enough to catch a scrolled list, small enough to be
# instant. A Taobao poplayer row is ~210px on a 2400px screen, still ~63px here.
WORK_W = 300


def load(path: str):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if w > WORK_W:
        im = im.resize((WORK_W, max(1, round(h * WORK_W / w))))
    return im


def compare(a_path: str, b_path: str, threshold: float) -> dict:
    a, b = load(a_path), load(b_path)
    if a.size != b.size:
        # Different crops/rotations: normalise b onto a's grid.
        b = b.resize(a.size)

    aw, ah = a.size
    total = aw * ah
    pa, pb = a.load(), b.load()

    # Per-pixel mean absolute difference over the 3 channels; a pixel counts as
    # changed when it moves more than 12/255 on any channel (kills JPEG noise).
    NOISE = 12
    diff_sum = 0
    changed = 0
    for y in range(ah):
        for x in range(aw):
            r1, g1, b1 = pa[x, y]
            r2, g2, b2 = pb[x, y]
            d = abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
            diff_sum += d
            if max(abs(r1 - r2), abs(g1 - g2), abs(b1 - b2)) > NOISE:
                changed += 1

    mean_per_channel = diff_sum / (total * 3)
    score = 100.0 * (1.0 - mean_per_channel / 255.0)
    return {
        "same_screen": score >= threshold,
        "score": round(score, 2),
        "threshold": threshold,
        "changed": changed,
        "total": total,
        "a": a_path,
        "b": b_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Pixel-diff two screenshots.")
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument(
        "--threshold",
        type=float,
        default=98.0,
        help="score at or above this = same screen (default 98)",
    )
    args = parser.parse_args()

    try:
        print(json.dumps(compare(args.a, args.b, args.threshold), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
