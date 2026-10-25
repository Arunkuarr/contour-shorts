"""Contour Shorts pipeline: take the next scripts from content/queue and turn them into videos.

Usage:  python -m pipeline.main            # next N from config
        python -m pipeline.main --id 3     # a specific script
"""
import argparse, glob, json, os, shutil
import yaml

from pipeline import tts, visuals, render


DONE_IDS = "content/done/batch_done.txt"


def next_scripts(n, only_id=None):
    """Queue = single files in content/queue/ + arrays in content/batches/*.json (minus done ids), by id."""
    items = [(json.load(open(f))["id"], f) for f in glob.glob("content/queue/*.json")]
    done = set()
    if os.path.exists(DONE_IDS):
        done = {int(l) for l in open(DONE_IDS) if l.strip()}
    for f in sorted(glob.glob("content/batches/*.json")):
        for obj in json.load(open(f)):
            if obj["id"] not in done:
                items.append((obj["id"], obj))
    items.sort(key=lambda t: t[0])
    if only_id is not None:
        items = [t for t in items if t[0] == only_id]
    return [t[1] for t in items[:n]]


def load(entry):
    short = json.load(open(entry)) if isinstance(entry, str) else dict(entry)
    if "description" not in short:
        short["description"] = short["title"] + "\n\nSources:\n" + "\n".join(short.get("sources", []))
    return short


def mark_done(entry, short):
    if isinstance(entry, str):
        shutil.move(entry, os.path.join("content/done", os.path.basename(entry)))
    else:
        with open(DONE_IDS, "a") as fh:
            fh.write(f"{short['id']}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int)
    ap.add_argument("--count", type=lambda s: int(s) if s.strip() else None)
    ap.add_argument("--keep-queue", action="store_true", help="don't move scripts to done/")
    a = ap.parse_args()
    cfg = yaml.safe_load(open("config.yaml"))
    from pipeline import assets; assets.ensure()
    os.makedirs("output", exist_ok=True); os.makedirs("content/done", exist_ok=True)
    made = []
    for f in next_scripts(a.count or cfg["shorts_per_run"], a.id):
        short = load(f)
        slug = f"{short['id']:03d}"
        work = os.path.join("work", slug); os.makedirs(work, exist_ok=True)
        print(f"[{slug}] {short['title']}")
        print("  voice…")
        timing = tts.synthesize(short["script"], os.path.join(work, "voice.wav"), cfg)
        print(f"  {timing['duration']:.1f}s narration")
        print("  visuals…")
        imgs = visuals.get_scene_images(short, work, cfg)
        print("  render…")
        out = os.path.join("output", f"{slug}.mp4")
        render.render(short, imgs, os.path.join(work, "voice.wav"), timing, work, out, cfg)
        meta = {"file": out, "title": short["title"] + " #shorts", "description": short["description"],
                "tags": short.get("tags", ""), "duration": round(timing["duration"], 1)}
        if cfg["upload"]["youtube"]:
            from pipeline import upload
            meta["youtube_id"] = upload.upload(out, short, cfg)
        json.dump(meta, open(os.path.join("output", f"{slug}.json"), "w"), indent=2)
        if not a.keep_queue:
            mark_done(f, short)
        made.append(out)
    print("Done:", made or "queue empty, add scripts to content/queue/")


if __name__ == "__main__":
    main()
