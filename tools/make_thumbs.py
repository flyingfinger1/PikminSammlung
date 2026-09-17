"""Cut a Pikmin portrait for every extracted frame into one sprite sheet.

The portrait is taken shortly after a view became stable, before an
accidental dialog could dim it (the frame from extract_frames is the middle).

Usage: py tools/make_thumbs.py <video.mp4> <out.jpg>
Prints the sprite geometry; frame numbering matches extract_frames.py.
"""
import io
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import extract_frames as ef  # noqa: E402

CROP = (0.13, 0.10, 0.87, 0.385)  # figure + decor icon, fractions of w/h
THUMB = 160
COLS = 20


def main():
    video, out = Path(sys.argv[1]), Path(sys.argv[2])
    w, h = ef.probe_size(video)
    cards = ef.read_samples(video, w, h)
    segments = ef.merge_same(cards, ef.drop_dialogs(cards, ef.stable_segments(cards)))
    box = (int(CROP[0] * w), int(CROP[1] * h), int(CROP[2] * w), int(CROP[3] * h))
    th = round(THUMB * (box[3] - box[1]) / (box[2] - box[0]))
    rows = -(-len(segments) // COLS)
    sheet = Image.new("RGB", (COLS * THUMB, rows * th), "white")
    for n, (a, _) in enumerate(segments):
        t = (a + 2) / ef.SAMPLE_FPS
        png = subprocess.check_output(
            [ef.FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
        im = Image.open(io.BytesIO(png)).convert("RGB").crop(box).resize((THUMB, th))
        sheet.paste(im, ((n % COLS) * THUMB, (n // COLS) * th))
    sheet.save(out, quality=85)
    print(f"{len(segments)} thumbs, {COLS} cols, {THUMB}x{th} -> {out}")


if __name__ == "__main__":
    main()
