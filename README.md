# Contour Shorts pipeline

Turns researched scripts into ready-to-post YouTube Shorts, every day, on GitHub Actions (free).

```
content/queue/*.json → voice (Gemini TTS, free) → scene images (Pexels + free AI) → 9:16 video
with Ken Burns motion, word-highlight captions and logo → download (or auto-upload as Private)
```

## One-time setup (about 20 minutes)

1. **Create a private GitHub repo** and push this folder to it.
2. **Free human-sounding voice:** Google AI Studio (https://aistudio.google.com/apikey) → *Create API key* →
   add it as repo secret `GEMINI_API_KEY`. Gemini TTS free tier = 10 voiceovers/day (we use 2). No billing needed.
   Change the narrator with `gemini_voice` in `config.yaml` (Charon, Orus, Fenrir, Kore, Aoede…).
3. **Stock photos:** free key from https://www.pexels.com/api/ → secret `PEXELS_API_KEY`.
4. **AI images** use Pollinations (free, no key). Optional free token from https://auth.pollinations.ai → secret `POLLINATIONS_TOKEN` (fewer rate limits).
5. Repo → Actions → *Make Shorts* → **Run workflow**. Download the videos from the run's *Artifacts*.

## Daily routine
- The workflow runs every morning and makes `shorts_per_run` videos (default 2).
- Download, **watch each one**, then upload/schedule in YouTube Studio (title + description are in the `.json` next to each video, sources included).
- Paste the sources as a pinned comment.
- Keep the queue full: add new script files to `content/queue/` (same format as the examples).

## Optional: auto-upload to YouTube (as Private)
Google Cloud → enable *YouTube Data API v3* → OAuth consent screen (External, add yourself as test user) →
Credentials → OAuth client ID (Desktop app) → download JSON → `python get_token.py client_secret.json` on your PC →
add `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` secrets → set `upload.youtube: true`.
Note: until your API project passes YouTube's audit, API uploads are locked to Private. Manual upload works fine meanwhile.

## Stay monetizable
YouTube's inauthentic-content rules (July 2026) demonetize mass-produced, template-identical videos. So:
original, sourced scripts; varied visuals; you review every video; max 1–2 per day; mark "Altered or synthetic content" when realistic AI scenes show real events.
