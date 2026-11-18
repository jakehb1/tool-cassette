"""Render demo.png from the real output of `python demo.py`. Dev-only; needs Pillow."""
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
lines = out.rstrip("\n").split("\n")


def font(size, bold=False):
    p = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono%s.ttf" % ("-Bold" if bold else "")
    return ImageFont.truetype(p, size) if os.path.exists(p) else ImageFont.load_default()


F, FB, FT, FS = font(20), font(20, True), font(44, True), font(22)
W, PAD, LH = 1500, 56, 32
H = 190 + LH * len(lines) + 50
img = Image.new("RGB", (W, H), "#0d1117")
d = ImageDraw.Draw(img)
d.text((PAD, 44), "tool-cassette", font=FT, fill="#e6edf3")
d.text((W - PAD - 330, 56), "Applied Logic · a-l.studio", font=FS, fill="#8b949e")
d.text((PAD, 104), "Record an agent's tool calls once. Replay them offline. Catch API drift.",
       font=FS, fill="#8b949e")
y = 165
for ln in lines:
    s = ln.strip()
    if ln.startswith("$"):
        d.text((PAD, y), ln, font=FB, fill="#e6edf3")
    elif s.startswith("FAIL"):
        d.text((PAD, y), ln, font=F, fill="#f85149")
    elif s.startswith(("drifted", "1 tool call")):
        d.text((PAD, y), ln, font=F, fill="#d29922")
    elif s.startswith(("0 recorded", "no drift")) or s == "(exit code 0)":
        d.text((PAD, y), ln, font=F, fill="#3fb950")
    elif s.startswith(("CHANGED", "CassetteMiss", "REMOVED", "ADDED")) or s == "(exit code 1)":
        d.text((PAD, y), ln, font=FB, fill="#f85149")
    else:
        d.text((PAD, y), ln, font=F, fill="#c9d1d9")
    y += LH
img.save(os.path.join(ROOT, "demo.png"))
print("wrote demo.png")
