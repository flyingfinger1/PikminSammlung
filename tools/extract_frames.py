"""Extract one still frame per Pikmin from a Pikmin Bloom screen recording.

The recording flips through the Pikmin detail view. The 3D model and the map
animate constantly, so change detection only looks at the text card
(name, hearts, steps, location, date), which is static while a Pikmin is shown.

Usage: py tools/extract_frames.py <video.mp4> [out_dir]
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

FFMPEG = "ffmpeg"
SAMPLE_FPS = 10
SMALL_W = 216  # analysis width (1080 / 5)
CARD_TOP, CARD_BOTTOM = 0.42, 0.90  # text card as fraction of frame height
STABLE_DIFF = 2.0  # mean abs diff below which two samples count as "same"
MIN_STABLE = 3  # samples (0.3 s) a view must hold to count
SAME_PIKMIN_DIFF = 8.0  # max row diff below which neighbouring segments merge
DIALOG_DIM = 40  # a view this much darker than usual is covered by a dialog


def probe_size(video):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video)],
        text=True)
    w, h = map(int, out.strip().split(",")[:2])
    return w, h


def read_samples(video, w, h):
    small_h = round(h * SMALL_W / w)
    cmd = [FFMPEG, "-v", "error", "-i", str(video),
           "-vf", f"fps={SAMPLE_FPS},scale={SMALL_W}:{small_h},format=gray",
           "-f", "rawvideo", "-"]
    raw = subprocess.check_output(cmd)
    frames = np.frombuffer(raw, np.uint8).reshape(-1, small_h, SMALL_W)
    top, bottom = int(small_h * CARD_TOP), int(small_h * CARD_BOTTOM)
    return frames[:, top:bottom].astype(np.int16)


def stable_segments(cards):
    diffs = np.abs(np.diff(cards, axis=0)).mean(axis=(1, 2))
    segments, start = [], 0
    for i, d in enumerate(diffs, start=1):
        if d > STABLE_DIFF:
            if i - start >= MIN_STABLE:
                segments.append((start, i - 1))
            start = i
    if len(cards) - start >= MIN_STABLE:
        segments.append((start, len(cards) - 1))
    return segments


def drop_dialogs(cards, segments):
    """Remove views dimmed by an overlay (e.g. an accidental "Namen ändern")."""
    brightness = [cards[(a + b) // 2].mean() for a, b in segments]
    normal = np.median(brightness)
    return [s for s, v in zip(segments, brightness) if v > normal - DIALOG_DIM]


def merge_same(cards, segments):
    merged = []
    for seg in segments:
        mid = (seg[0] + seg[1]) // 2
        if merged:
            prev = merged[-1]
            prev_mid = (prev[0] + prev[1]) // 2
            # worst text row: similar cards differ only in a few lines, which
            # a whole-card mean would dilute (same Pikmin ~2, different >=25)
            row_diff = np.abs(cards[mid] - cards[prev_mid]).mean(axis=1).max()
            if row_diff < SAME_PIKMIN_DIFF:
                merged[-1] = (prev[0], seg[1])
                continue
        merged.append(seg)
    return merged


def main():
    video = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("frames")
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = probe_size(video)
    cards = read_samples(video, w, h)
    # dropping a dialog leaves the same Pikmin twice in a row -> merge after
    segments = merge_same(cards, drop_dialogs(cards, stable_segments(cards)))
    print(f"{len(cards)} samples -> {len(segments)} Pikmin")
    for n, (a, b) in enumerate(segments, start=1):
        # take the sharpest-looking sample: the middle of the stable run
        t = ((a + b) / 2) / SAMPLE_FPS
        target = out_dir / f"pikmin_{n:03d}.png"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}",
                        "-i", str(video), "-frames:v", "1", str(target)],
                       check=True)
        print(f"{target.name}  t={t:6.1f}s  ({(b - a + 1) / SAMPLE_FPS:.1f}s)")


if __name__ == "__main__":
    main()
