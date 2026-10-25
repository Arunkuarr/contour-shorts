"""Assemble a 9:16 Short: Ken Burns scenes + word-highlight captions + watermark + voice."""
import os, subprocess


def _run(cmd):
    subprocess.run(cmd, check=True)


def _ts(t):
    h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(words, path, cfg):
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    n = cfg["video"]["caption_words"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Poppins,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for c in range(0, len(words), n):
        chunk = words[c:c + n]
        for j, w in enumerate(chunk):
            start = w["start"]
            end = chunk[j + 1]["start"] if j + 1 < len(chunk) else w["end"]
            txt = " ".join(
                ("{\\c&H44B5F5&}" + x["word"].upper() + "{\\c&HFFFFFF&}") if k == j else x["word"].upper()
                for k, x in enumerate(chunk))
            pop = "{\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}" if j == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{pop}{txt}")
    with open(path, "w") as f:
        f.write(head + "\n".join(lines) + "\n")


def scene_clip(img, out, dur, i, cfg):
    W, H, fps = cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"]
    frames = int(dur * fps) + 1
    zin = i % 2 == 0
    z = "min(1+0.0012*on,1.14)" if zin else "max(1.14-0.0012*on,1)"
    # gentle drift left/right alternating
    x = "iw/2-(iw/zoom/2)" + ("+on*0.25" if i % 3 == 1 else "-on*0.25" if i % 3 == 2 else "")
    vf = (f"scale={int(W*1.15)}:{int(H*1.15)},zoompan=z='{z}':d={frames}:x='{x}':y='ih/2-(ih/zoom/2)'"
          f":s={W}x{H}:fps={fps},format=yuv420p")
    _run(["ffmpeg", "-loglevel", "error", "-y", "-loop", "1", "-i", img, "-vf", vf,
          "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out])


def render(short, images, wav, timing, workdir, out_mp4, cfg):
    dur = timing["duration"]
    per = dur / len(images)
    segs = []
    for i, img in enumerate(images):
        seg = os.path.join(workdir, f"seg_{i:02d}.mp4")
        scene_clip(img, seg, per + (0.05 if i < len(images) - 1 else 0.3), i, cfg)
        segs.append(seg)
    lst = os.path.join(workdir, "segs.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(s)}'\n" for s in segs)
    ass = os.path.join(workdir, "captions.ass")
    write_ass(timing["words"], ass, cfg)
    fonts = os.path.abspath("assets/fonts")
    vf = f"[0:v]ass={ass}:fontsdir={fonts}[v]"
    inputs = ["-f", "concat", "-safe", "0", "-i", lst, "-i", wav]
    maps = ["-map", "[v]", "-map", "1:a"]
    if cfg["video"].get("watermark") and os.path.exists("assets/logo.png"):
        inputs += ["-i", "assets/logo.png"]
        vf = (f"[0:v]ass={ass}:fontsdir={fonts}[c];[2:v]scale=110:110,format=rgba,colorchannelmixer=aa=0.75[wm];"
              f"[c][wm]overlay=W-w-50:170[v]")
    _run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", vf, *maps,
          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_mp4])
    return out_mp4
