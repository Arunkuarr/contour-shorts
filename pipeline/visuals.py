"""Scene images: Pexels stock for modern/nature scenes, free AI images for historic ones.
Falls back to a branded title card so a run never fails because an image API is down."""
import os, re, time, urllib.parse
import requests

# ---- No-people guard -------------------------------------------------------
# AI image models love to add random people. We (1) strip people from prompts,
# (2) ask for empty scenes, and (3) reject any image where a face/person detector
# finds someone, then retry or reuse a neighbouring people-free picture.
PEOPLE = re.compile(r"\b(man|men|woman|women|people|person|persons|villagers?|children|child|kids?|boys?|girls?|"
    r"teachers?|lawyers?|judges?|jurors?|jury|diplomats?|crowds?|workers?|clerks?|customers?|scientists?|engineers?|"
    r"governors?|soldiers?|knights?|sailors?|farmers?|kings?|queens?|emperors?|monks?|priests?|officials?|students?|"
    r"family|families|crew|guards?|merchants?|explorers?|doctors?|nurses?|actors?|audience|spectators?|shoppers?|"
    r"passengers?|tourists?|historians?|inventors?|wife|husband|couple|portrait|codebreakers?|scholars?|"
    r"astronomers?|researchers?|miners?|fishermen|townspeople|citizens?|residents?|locals?|riders?|pilots?|captain|"
    r"players?|operators?|keepers?|brothers?|sisters?|mother|father|baby|babies|wives|husbands|lawman|sheriff|"
    r"pharaoh|ruler|rulers|nobles?|peasants?|servants?|slaves?|warriors?|vikings?|samurai|gladiators?|senators?|"
    r"president|mayor|officers?|police|detectives?|thief|thieves|prisoners?|someone|everyone|human|humans|hands?)\b", re.I)
EMPTY = "completely empty scene, no people, no humans, no faces, no figures, uninhabited"


_P = PEOPLE.pattern[2:-2]
_CLOTH = (r"(?:dress|dresses|gowns?|robes?|coats?|suits?|uniforms?|armou?r|caps?|hats?|helmets?|cardigans?|sweaters?|"
          r"wigs?|clothes|clothing|attire|shawls?|turbans?|battledress|tunics?|togas?|cloaks?|aprons?|overalls|jackets?|"
          r"crowns?|furs?|hides?|rags|frock coats?|waistcoats?|bonnets?|veils?|scarves|boots|kimonos?|saris?|shirts?)\b")


def _clean_clause(c):
    c = re.sub(r"\b(?:with|beside|alongside|and|as|while|among|surrounded by)\s+(?:[\w'-]+\s+){0,3}?" + _P
               + r"\b(?:\s+(?:in|wearing)\s+[^,]*)?", "", c, flags=re.I)                 # "...with soldiers in helmets"
    m = re.match(r"^\s*(?:[\w'-]+\s+){0,4}?" + _P + r"(?:'s)?\b(?:\s+of\s+(?:[\w'-]+\s+){0,3}?" + _P + r"\b)?",
                 c, flags=re.I)                                                             # leading "Two medieval kings"
    if m:
        c = c[m.end():]
        c = re.sub(r"^\s*(?:in|wearing)\s+(?:[\w'-]+\s+){0,5}?" + _CLOTH + r"(?:\s+and\s+(?:[\w'-]+\s+){0,3}?"
                   + _CLOTH + r")?", "", c, flags=re.I)                                      # "in crowns and robes"
        c = re.sub(r"^\s*(?:\w+ly\s+)?(?:\w+ing|gathered|seated)\b\s*", "", c, flags=re.I)  # "signing"
    c = re.sub(r"\b" + _P + r"(?:'s)?\b", "", c, flags=re.I)                              # any leftovers
    c = re.sub(r"^\s*(?:to|at|on|in|by|beside|near|around|behind|under|inside|across|over|up|down|into|through|from)\s+", "", c, flags=re.I)
    c = re.sub(r"\s+", " ", c).strip(" ,.-;:")
    if re.match(r"(?:his|her|their|its)\b", c, flags=re.I):
        return ""
    return c if len(re.sub(r"\b(\w+ly|a|an|the|and|of)\b", "", c).strip()) > 3 else ""


def setting_only(scene):
    """Turn a scene that mentions people into a people-free version of the same place and objects."""
    if not PEOPLE.search(scene):
        return scene
    keep = [k for k in (_clean_clause(c) for c in scene.split(",")) if k]
    return ", ".join(keep) or "atmospheric empty historic interior"


_det = None


def _detectors():
    """Lazy-load the face (YuNet) and person (MobileNet-SSD) detectors; None if unavailable."""
    global _det
    if _det is None:
        try:
            import cv2
            m = "models"
            net = cv2.dnn.readNetFromCaffe(f"{m}/ssd_deploy.prototxt", f"{m}/ssd_mobilenet.caffemodel")
            fd = cv2.FaceDetectorYN.create(f"{m}/yunet.onnx", "", (320, 320), 0.7, 0.3, 50)
            _det = (cv2, net, fd)
        except Exception as e:
            print(f"  people check unavailable: {e}")
            _det = False
    return _det or None


def has_people(path):
    d = _detectors()
    if not d:
        return False
    cv2, net, fd = d
    im = cv2.imread(path)
    if im is None:
        return False
    blob = cv2.dnn.blobFromImage(cv2.resize(im, (300, 300)), 0.007843, (300, 300), 127.5)
    net.setInput(blob)
    out = net.forward()
    for i in range(out.shape[2]):
        if int(out[0, 0, i, 1]) == 15 and float(out[0, 0, i, 2]) > 0.6:  # class 15 = person
            return True
    h, w = im.shape[:2]
    s = 640 / max(h, w)
    sm = cv2.resize(im, (int(w * s), int(h * s)))
    fd.setInputSize((sm.shape[1], sm.shape[0]))
    _, faces = fd.detect(sm)
    return faces is not None and len(faces) > 0
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
    q = re.sub(r"[,.:]", " ", setting_only(scene))[:80]
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
    prompt = f"{setting_only(scene)}, {EMPTY}, {cfg['visuals']['style_suffix']}"
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
    paths, srcs = [], []
    for i, scene in enumerate(short["scenes"]):
        p = os.path.join(workdir, f"scene_{i:02d}.jpg")
        got, src = None, None
        if scene.lower().startswith(("text card", "timeline", "animated timeline")):
            got, src = title_card(scene.split(":", 1)[-1].strip(), p, w, h, i), "card"
        else:
            order = ["ai"] if mode == "ai" else ["stock"] if mode == "stock" else (
                ["ai", "stock"] if is_historic(scene, cfg) else ["stock", "ai"])
            for kind in order:
                for t in range(3 if kind == "ai" else 1):
                    try:
                        got = pexels(scene, p, w, h) if kind == "stock" else pollinations(
                            scene if t == 0 else setting_only(scene) + ", wide shot",
                            p, w, h, cfg, short["id"] * 100 + i + 17 * t)
                    except Exception as e:
                        print(f"  {kind} failed for scene {i}: {e}")
                        got = None
                    if got and has_people(got):
                        print(f"  scene {i}: {kind} image had people, rejected")
                        got = None
                        continue
                    break
                if got:
                    src = kind; break
        print(f"  scene {i}: {src or 'missing'}")
        paths.append(got)
        srcs.append(src)
    # Never show raw scene instructions on screen: retry missing images with a short prompt
    # and a new seed, then reuse a neighbouring picture, and only as a last resort use the title.
    for i, got in enumerate(paths):
        if got:
            continue
        p = os.path.join(workdir, f"scene_{i:02d}.jpg")
        short_prompt = " ".join(re.sub(r"[,:;]", " ", setting_only(short["scenes"][i])).split()[:8])
        try:
            got = pollinations(short_prompt, p, w, h, cfg, short["id"] * 100 + i + 50)
            if got and has_people(got):
                print(f"  scene {i}: retry image had people, rejected")
                got = None
        except Exception as e:
            print(f"  retry failed for scene {i}: {e}")
        if not got:
            near = [paths[j] for j in sorted(range(len(paths)), key=lambda j: abs(j - i))
                    if j != i and paths[j] and srcs[j] in ("ai", "stock", "retry")]
            if near:
                import shutil
                shutil.copy(near[0], p)
                got = p
        srcs[i] = "retry" if got else "title"
        paths[i] = got or title_card(short["title"], p, w, h, i)
        print(f"  scene {i}: {srcs[i]}")
    return paths
