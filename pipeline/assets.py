"""Create brand assets if missing (keeps the repo text-only): Poppins font + Contour logo."""
import os
import requests
from PIL import Image, ImageDraw

FONT_URL = "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf"
BG, AMBER, TEAL = (11, 16, 32), (245, 181, 68), (61, 214, 198)


def ensure():
    os.makedirs("assets/fonts", exist_ok=True)
    font = "assets/fonts/Poppins-Bold.ttf"
    if not os.path.exists(font):
        r = requests.get(FONT_URL, timeout=60); r.raise_for_status()
        open(font, "wb").write(r.content)
    logo = "assets/logo.png"
    if not os.path.exists(logo):
        im = Image.new("RGB", (800, 800), BG)
        d = ImageDraw.Draw(im)
        for i, rad in enumerate(range(250, 90, -28)):
            d.arc([400 - rad, 400 - rad, 400 + rad, 400 + rad], 45, 315,
                  fill=AMBER if i % 2 == 0 else TEAL, width=16 if i % 2 == 0 else 10)
        d.ellipse([366, 366, 434, 434], fill=AMBER)
        im.save(logo)
