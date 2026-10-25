"""Voiceover: synthesise sentence by sentence so we know exact timings for captions."""
import asyncio, os, re, subprocess, tempfile
import numpy as np
import soundfile as sf

MODEL_DIR = os.environ.get("KOKORO_DIR", "models")
SR = 24000
GAP = 0.18  # seconds of silence between sentences


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def _word_times(sentence, start, dur):
    """Spread a sentence's duration over its words by character length."""
    words = sentence.split()
    weights = [len(re.sub(r"\W", "", w)) + 2 for w in words]
    total = sum(weights)
    t, out = start, []
    for w, wt in zip(words, weights):
        d = dur * wt / total
        out.append({"word": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def _kokoro(sentences, voice, speed):
    from kokoro_onnx import Kokoro
    k = Kokoro(f"{MODEL_DIR}/kokoro-v1.0.onnx", f"{MODEL_DIR}/voices-v1.0.bin")
    lang = "en-gb" if voice.startswith("b") else "en-us"
    clips = []
    for s in sentences:
        a, sr = k.create(s, voice=voice, speed=speed, lang=lang)
        assert sr == SR
        clips.append(np.asarray(a, dtype=np.float32))
    return clips


def _edge(sentences, voice, speed):
    import edge_tts
    rate = f"{int(round((speed - 1) * 100)):+d}%"
    clips = []
    for s in sentences:
        mp3 = tempfile.mktemp(suffix=".mp3")
        asyncio.run(edge_tts.Communicate(s, voice, rate=rate).save(mp3))
        wav = mp3[:-4] + ".wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp3, "-ar", str(SR), "-ac", "1", wav], check=True)
        a, _ = sf.read(wav, dtype="float32")
        clips.append(a)
    return clips


def _google(sentences, voice, speed):
    """Google Cloud Text-to-Speech (Chirp 3 HD = very human; 1M chars/month free)."""
    import base64, io, requests
    key = os.environ["GOOGLE_TTS_API_KEY"]
    clips = []
    for s in sentences:
        r = requests.post(f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}", timeout=60, json={
            "input": {"text": s},
            "voice": {"languageCode": "-".join(voice.split("-")[:2]), "name": voice},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SR, "speakingRate": speed},
        })
        r.raise_for_status()
        a, sr = sf.read(io.BytesIO(base64.b64decode(r.json()["audioContent"])), dtype="float32")
        assert sr == SR
        clips.append(a if a.ndim == 1 else a.mean(axis=1))
    return clips


def _gemini(text, voice, style, model):
    """Gemini TTS (free tier in Google AI Studio, very human). One request per Short."""
    import base64, requests, time
    key = os.environ["GEMINI_API_KEY"]
    body = {"contents": [{"parts": [{"text": f"{style}\n\n{text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for attempt in range(4):
        r = requests.post(url, params={"key": key}, json=body, timeout=180)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(25 * (attempt + 1)); continue
        r.raise_for_status()
        break
    r.raise_for_status()
    pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def _split_on_pauses(a, n):
    """Find the n-1 longest pauses in one narration track -> sentence boundaries (sample idx)."""
    hop = int(0.02 * SR)
    env = np.array([np.abs(a[i:i + hop]).mean() for i in range(0, len(a) - hop, hop)])
    quiet = env < max(env.max() * 0.04, 1e-4)
    runs, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None: start = i
        if not q and start is not None:
            if i - start >= 6 and start > 0: runs.append((i - start, start, i))
            start = None
    best = sorted(sorted(runs, reverse=True)[: n - 1], key=lambda r: r[1])
    cuts = [((s + e) // 2) * hop for _, s, e in best]
    edges = [0] + cuts + [len(a)]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def _gemini_synth(sentences, cfg):
    v = cfg["voice"]
    a = _trim(_gemini(" ".join(sentences), v["gemini_voice"], v["gemini_style"], v["gemini_model"]))
    target = v.get("target_seconds", 34)
    if len(a) / SR > target:  # speed up (pitch kept) so Shorts stay ~30 s
        f = min(len(a) / SR / target, 1.3)
        src, dst = tempfile.mktemp(suffix=".wav"), tempfile.mktemp(suffix=".wav")
        sf.write(src, a, SR)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-filter:a", f"atempo={f:.3f}", "-ar", str(SR), dst], check=True)
        a, _ = sf.read(dst, dtype="float32")
        print(f"  sped up narration x{f:.2f}")
    segs = _split_on_pauses(a, len(sentences))
    if len(segs) != len(sentences):  # couldn't find enough pauses: one segment per sentence by length
        L = np.cumsum([len(s) for s in sentences]) / sum(len(s) for s in sentences)
        b = [0] + [int(x * len(a)) for x in L]
        segs = [(b[i], b[i + 1]) for i in range(len(sentences))]
    return a, segs


def _trim(a, thresh=0.01):
    idx = np.where(np.abs(a) > thresh)[0]
    return a[max(idx[0] - 240, 0): idx[-1] + 480] if len(idx) else a


def synthesize(text, out_wav, cfg):
    sentences = split_sentences(text)
    v = cfg["voice"]
    engine = v["engine"]
    if engine == "gemini" and os.environ.get("GEMINI_API_KEY"):
        a, segs = _gemini_synth(sentences, cfg)
        lead = 0.15
        words = []
        for s, (i, j) in zip(sentences, segs):
            # keep only the voiced part of each segment for word timing
            seg = a[i:j]; idx = np.where(np.abs(seg) > 0.02)[0]
            si, ej = (i + idx[0], i + idx[-1]) if len(idx) else (i, j)
            words += _word_times(s, lead + si / SR, (ej - si) / SR)
        audio = np.concatenate([np.zeros(int(lead * SR), dtype=np.float32), a, np.zeros(int(0.3 * SR), dtype=np.float32)])
        audio = audio / max(np.abs(audio).max(), 1e-6) * 0.9
        sf.write(out_wav, audio, SR)
        return {"duration": len(audio) / SR, "words": words, "sentences": [{"text": s} for s in sentences]}
    if engine == "gemini":
        print("  GEMINI_API_KEY not set, falling back to edge voice")
        engine = "edge"
    if engine == "google" and not os.environ.get("GOOGLE_TTS_API_KEY"):
        print("  GOOGLE_TTS_API_KEY not set, falling back to edge voice")
        engine = "edge"
    if engine == "google":
        clips = _google(sentences, v["google_voice"], v["speed"])
    elif engine == "edge":
        clips = _edge(sentences, v["edge_voice"], v["speed"])
    else:
        clips = _kokoro(sentences, v["kokoro_voice"], v["speed"])
    gap = np.zeros(int(GAP * SR), dtype=np.float32)
    audio, words, t = [np.zeros(int(0.15 * SR), dtype=np.float32)], [], 0.15
    for s, c in zip(sentences, clips):
        c = _trim(c)
        dur = len(c) / SR
        words += _word_times(s, t, dur)
        audio += [c, gap]
        t += dur + GAP
    audio = np.concatenate(audio)
    audio = audio / max(np.abs(audio).max(), 1e-6) * 0.9
    sf.write(out_wav, audio, SR)
    return {"duration": len(audio) / SR, "words": words,
            "sentences": [{"text": s} for s in sentences]}
