"""Render the full cut's title cards (T7.5), in the v0.1 cards' style: white DejaVu Sans Bold on
the terminal's grey, two lines, 6 s over the top-left of each part. Pillow only; run once and
commit the PNGs, so the cut needs no renderer on the machine that makes it.

    python3 docs/demo/video/v2/cards.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
GREY = (90, 90, 90, 255)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

CARDS = {
    "t1": (
        "Faultline - the full cut: `make demo` on the v2 world",
        "one fault, nine agents, five tools, every claim cited",
    ),
    "t2": ("the wait, compressed", "correlation, a 90 s settle, the investigation"),
    "t3": ("the incident screen", "the report, its evidence, a trace citation opened in Tempo"),
    "t4": (
        "the same fault again, and a person approves the fix",
        "the action plane spends one token; the world recovers",
    ),
    "t5": ("the eval dashboard", "every version of the pipeline, every rate with its n"),
}


def render(name: str, lines: tuple[str, str]) -> None:
    font = ImageFont.truetype(FONT, 40)
    pad, gap = 18, 8
    widths = [font.getlength(line) for line in lines]
    height = sum(font.getbbox(line)[3] for line in lines) + gap + 2 * pad
    image = Image.new("RGBA", (int(max(widths)) + 2 * pad, int(height)), GREY)
    draw = ImageDraw.Draw(image)
    y = pad
    for line in lines:
        draw.text((pad, y), line, font=font, fill=(255, 255, 255, 255))
        y += font.getbbox(line)[3] + gap
    image.save(HERE / f"{name}.png")


if __name__ == "__main__":
    for name, lines in CARDS.items():
        render(name, lines)
