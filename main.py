from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydub import AudioSegment
from urllib.parse import urlparse, parse_qs
import httpx
import io

app = FastAPI()

def normalize_google_drive_url(url: str) -> str:
    """
    Convert common Google Drive share URLs to a direct download URL.
    Supports:
    - https://drive.google.com/file/d/FILE_ID/view?usp=...
    - https://drive.google.com/open?id=FILE_ID&...
    """
    parsed = urlparse(url)

    if "drive.google.com" not in parsed.netloc:
        return url  # not a Drive URL, return as-is

    file_id = None

    # Pattern: /file/d/FILE_ID/...
    if "/file/d/" in parsed.path:
        try:
            file_id = parsed.path.split("/file/d/")[1].split("/")[0]
        except IndexError:
            pass

    # Pattern: ?id=FILE_ID
    if not file_id:
        qs = parse_qs(parsed.query)
        file_id = qs.get("id", [None])[0]

    if not file_id:
        # Fallback: return original URL, maybe it's already direct
        return url

    return f"https://drive.google.com/uc?export=download&id={file_id}"


@app.post("/get-duration")
async def get_audio_duration(
    file: UploadFile = File(None),
    url: str = Form(None)
):
    # Validate input
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide either 'file' or 'url'.")
    if file and url:
        raise HTTPException(status_code=400, detail="Provide only one of 'file' or 'url'.")

    try:
        if url:
            # Normalize Google Drive URLs if needed
            url_normalized = normalize_google_drive_url(url)

            async with httpx.AsyncClient() as client:
                resp = await client.get(url_normalized)
                resp.raise_for_status()
                content = resp.content

            # Try to infer filename from URL
            filename = url_normalized.split("/")[-1] or "downloaded_audio"
        else:
            # File upload path
            content = await file.read()
            filename = file.filename or "uploaded_audio"

        # Read audio with pydub
        audio = AudioSegment.from_file(io.BytesIO(content))

        # Duration in seconds
        duration = len(audio) / 1000.0

        return {
            "filename": filename,
            "duration_seconds": duration
        }

    except Exception as e:
        # You might want to log e in real app
        raise HTTPException(status_code=500, detail=str(e))
