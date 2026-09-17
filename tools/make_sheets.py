"""Tile the text cards of extracted frames into review sheets (for reading).

Usage: py tools/make_sheets.py <frames_dir> <sheets_dir> [per_row] [rows]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

CARD_TOP, CARD_BOTTOM = 0.40, 0.945  # 3-line names push the date down
TILE_W = 540


def main():
    frames = sorted(Path(sys.argv[1]).glob("pikmin_*.png"))
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    per_row = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    rows = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    per_sheet = per_row * rows
    for s in range(0, len(frames), per_sheet):
        batch = frames[s:s + per_sheet]
        tiles = []
        for f in batch:
            im = Image.open(f)
            w, h = im.size
            im = im.crop((0, int(h * CARD_TOP), w, int(h * CARD_BOTTOM)))
            im = im.resize((TILE_W, round(im.height * TILE_W / w)))
            ImageDraw.Draw(im).text((8, 4), f.stem.split("_")[1], fill=(255, 0, 0))
            tiles.append(im)
        th = tiles[0].height
        sheet = Image.new("RGB", (TILE_W * per_row, th * rows), "white")
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % per_row) * TILE_W, (i // per_row) * th))
        sheet.save(out / f"sheet_{s // per_sheet + 1:02d}.png")
    print(f"{len(frames)} frames -> {-(-len(frames) // per_sheet)} sheets")


if __name__ == "__main__":
    main()
