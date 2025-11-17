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
    - Direct links from drive.usercontent.google.com are returned as-is.
    """
    parsed = urlparse(url)

    # drive.usercontent.google.com is already a direct download host
    if "drive.usercontent.google.com" in parsed.netloc:
        return url

    if "drive.google.com" not in parsed.netloc:
        # Not a Google Drive URL → return as-is
        return url

    file_id = None

    # Pattern: /file/d/FILE_ID/...
    if "/file/d/" in parsed.path:
        try:
            file_id = parsed.path.split("/file/d/")[1].split("/")[0]
        except IndexError:
            file_id = None

    # Pattern: ?id=FILE_ID
    if not file_id:
        qs = parse_qs(parsed.query)
        file_id = qs.get("id", [None])[0]

    if not file_id:
        # Fallback: return original URL, maybe already usable
        return url

    # Standard direct-download endpoint
    return f"https://drive.google.com/uc?export=download&id={file_id}"


@app.post("/get-duration")
async def get_audio_duration(
    file: UploadFile = File(None),
    url: str = Form(None),
):
    # Validate input
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide either 'file' or 'url'.")
    if file and url:
        raise HTTPException(status_code=400, detail="Provide only one of 'file' or 'url'.")

    try:
        if url:
            # Normalize Drive share links if needed
            url_normalized = normalize_google_drive_url(url)

            try:
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    resp = await client.get(
                        url_normalized,
                        headers={
                            # some CDNs / Google endpoints can be picky without UA
                            "User-Agent": "audio-duration-bot/1.0"
                        },
                    )
                    resp.raise_for_status()
            except httpx.HTTPError as http_err:
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to download audio from URL: {str(http_err)}",
                )

            content = resp.content
            filename = url_normalized.split("/")[-1] or "downloaded_audio"

        else:
            # File upload path
            content = await file.read()
            filename = file.filename or "uploaded_audio"

        # Let pydub / ffmpeg detect format automatically
        audio = AudioSegment.from_file(io.BytesIO(content))

        # Duration in seconds
        duration = len(audio) / 1000.0

        return {
            "filename": filename,
            "duration_seconds": duration,
        }

    except HTTPException:
        # re-raise our own HTTPExceptions
        raise
    except Exception as e:
        # Any other internal error
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
