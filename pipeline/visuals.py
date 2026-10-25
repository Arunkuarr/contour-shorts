"""Scene images: Pexels stock for modern/nature scenes, free AI images for historic ones.
Falls back to a branded title card so a run never fails because an image API is down."""
import os, re, time, urllib.parse
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = "assets/fonts/Poppins-Bold.ttf"
BG, AMBER, TEAL = (11, 16, 32), (245, 181, 68), (61, 214, 198)


def is_historic(scene, cfg):
    pats = cfg["visuals"]["historic_words"]
    return any(re.search(rf"\b{p}\b", scene, re.I) for p in pats)


def _save_cover(img, path, w, h):
    """Crop/resize to cover w x h (with some headroom for Ken Burns zoom)."""
    img = img.convert("RGB")
    W, H = int(w * 1.15), int(h * 1.15)
    r = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * r) + 1, int(img.height * r) + 1), Image.LANCZOS)
    l, t = (img.width - W) // 2, (img.height - H) // 2
    img.crop((l, t, l + W, t + H)).save(path, quality=92)
    return path


def pexels(scene, path, w, h):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    q = re.sub(r"[,.:]", " ", scene)[:80]
    r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key},
                     params={"query": q, "orientation": "portrait", "per_page": 5}, timeout=30)
    r.raise_for_status()
    photos = r.json().get("photos", [])
    if not photos:
        return None
    img = requests.get(photos[0]["src"]["large2x"], timeout=60)
    img.raise_for_status()
    from io import BytesIO
    return _save_cover(Image.open(BytesIO(img.content)), path, w, h)


def pollinations(scene, path, w, h, cfg, seed):
    prompt = f"{scene}, {cfg['visuals']['style_suffix']}"
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
           + f"?width=768&height=1365&nologo=true&seed={seed}&model=flux")
    headers = {}
    if os.environ.get("POLLINATIONS_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["POLLINATIONS_TOKEN"]
    global _last_ai
    for attempt in range(5):
        wait = 16 - (time.time() - _last_ai)  # free tier: ~1 image per 15 s
        if wait > 0:
            time.sleep(wait)
        _last_ai = time.time()
        try:
            r = requests.get(url, headers=headers, timeout=180)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                from io import BytesIO
                im = Image.open(BytesIO(r.content))
                im = im.crop((0, 0, im.width, int(im.height * 0.93)))  # drop the free-tier watermark strip
                return _save_cover(im, path, w, h)
        except requests.RequestException:
            pass
        time.sleep(10 * (attempt + 1))
    return None


_last_ai = 0.0


def title_card(scene, path, w, h, idx):
    """Branded fallback: contour-line background + scene text."""
    W, H = int(w * 1.15), int(h * 1.15)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    cx, cy = W * (0.3 + 0.4 * (idx % 2)), H * 0.4
    for i, r in enumerate(range(60, 1800, 55)):
        d.ellipse([cx - r * 1.3, cy - r, cx + r * 1.3, cy + r], outline=TEAL if i % 3 else AMBER, width=2)
    img = img.filter(ImageFilter.GaussianBlur(1))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 64)
    scene = scene.replace("\u2192", "\u00bb")  # Poppins has no arrow glyph
    words, lines, line = scene.split(), [], ""
    for wd in words:
        if d.textlength(line + " " + wd, font=f) > W * 0.7:
            lines.append(line); line = wd
        else:
            line = (line + " " + wd).strip()
    lines.append(line)
    y = H * 0.35
    for ln in lines[:6]:
        d.text((W / 2, y), ln, font=f, fill="white", anchor="mm"); y += 84
    img.save(path, quality=92)
    return path


def get_scene_images(short, workdir, cfg):
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    mode = cfg["visuals"]["mode"]
    paths = []
    for i, scene in enumerate(short["scenes"]):
        p = os.path.join(workdir, f"scene_{i:02d}.jpg")
        got, src = None, None
        if scene.lower().startswith(("text card", "timeline", "animated timeline")):
            got, src = title_card(scene.split(":", 1)[-1].strip(), p, w, h, i), "card"
        else:
            order = ["ai"] if mode == "ai" else ["stock"] if mode == "stock" else (
                ["ai", "stock"] if is_historic(scene, cfg) else ["stock", "ai"])
            for kind in order:
                try:
                    got = pexels(scene, p, w, h) if kind == "stock" else pollinations(scene, p, w, h, cfg, short["id"] * 100 + i)
                except Exception as e:
                    print(f"  {kind} failed for scene {i}: {e}")
                if got:
                    src = kind; break
        if not got:
            got, src = title_card(scene, p, w, h, i), "fallback"
        print(f"  scene {i}: {src}")
        paths.append(got)
    return paths
