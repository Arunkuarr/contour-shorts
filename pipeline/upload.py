"""Upload to YouTube as PRIVATE using a stored OAuth refresh token.
Secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (see README / get_token.py)."""
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def upload(mp4, short, cfg):
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        token_uri="https://oauth2.googleapis.com/token",
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": short["title"][:95] + " #shorts",
            "description": short["description"] + "\n\n#facts #history #didyouknow #shorts",
            "tags": [t.strip() for t in short.get("tags", "").split(",") if t.strip()] + ["facts", "history", "shorts"],
            "categoryId": cfg["upload"]["category_id"],
            "defaultLanguage": "en", "defaultAudioLanguage": "en",
        },
        "status": {"privacyStatus": cfg["upload"]["privacy"], "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(mp4, chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    print("  uploaded:", "https://youtu.be/" + resp["id"])
    return resp["id"]
