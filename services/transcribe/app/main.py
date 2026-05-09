import os
import uuid
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from faster_whisper import WhisperModel

app = FastAPI(
    title="Transcription Service",
    description="Audio/video transcription API powered by faster-whisper",
    version="0.1.0",
)

# Configuration
MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "medium.en")
MODEL_DIR = os.getenv("WHISPER_MODEL_DIR", "/models")
TRANSCRIPTS_DIR = Path(os.getenv("TRANSCRIPTS_DIR", "/data/transcripts"))
WORKERS = int(os.getenv("WORKERS", "4"))

# Ensure output dir exists
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Load model at startup
model = None


@app.on_event("startup")
def load_model():
    global model
    model = WhisperModel(
        MODEL_SIZE,
        device="cuda",
        compute_type="int8",
        cpu_threads=WORKERS,
        download_root=MODEL_DIR,
    )


# --- Request/Response models ---

class URLRequest(BaseModel):
    url: str
    title: str | None = None
    tags: list[str] | None = None


class TranscriptMeta(BaseModel):
    id: str
    status: str
    title: str | None = None
    tags: list[str] | None = None
    source: str | None = None
    duration_seconds: float | None = None
    created_at: str
    file: str | None = None


# --- Helpers ---

def extract_audio(input_path: str, output_path: str) -> None:
    """Extract audio from any media file to 16kHz mono WAV."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")


def download_media(url: str, output_dir: str) -> str:
    """Download media from URL using yt-dlp. Returns path to downloaded file."""
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp", "--no-playlist",
        "-o", output_template,
        "--print", "after_move:filepath",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[-500:]}")
    filepath = result.stdout.strip().split("\n")[-1]
    return filepath


def transcribe_audio(wav_path: str) -> dict:
    """Transcribe a WAV file and return segments + metadata."""
    segments, info = model.transcribe(wav_path, beam_size=5, language="en")

    result_segments = []
    full_text_parts = []
    for seg in segments:
        result_segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        })
        full_text_parts.append(seg.text.strip())

    return {
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 2),
        "segments": result_segments,
        "text": " ".join(full_text_parts),
    }


def save_transcript(transcript_id: str, meta: dict, result: dict) -> Path:
    """Save transcript JSON to the transcripts directory."""
    output = {**meta, "result": result}
    out_path = TRANSCRIPTS_DIR / f"{transcript_id}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    return out_path


def process_transcription(
    transcript_id: str,
    media_path: str,
    source: str,
    title: str | None = None,
    tags: list[str] | None = None,
):
    """Background task: extract audio, transcribe, save."""
    meta_path = TRANSCRIPTS_DIR / f"{transcript_id}.json"
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        extract_audio(media_path, wav_path)
        result = transcribe_audio(wav_path)

        meta = {
            "id": transcript_id,
            "status": "completed",
            "title": title,
            "tags": tags or [],
            "source": source,
            "duration_seconds": result["duration"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file": str(meta_path),
        }
        save_transcript(transcript_id, meta, result)

    except Exception as e:
        error_meta = {
            "id": transcript_id,
            "status": "failed",
            "error": str(e),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(meta_path, "w") as f:
            json.dump(error_meta, f, indent=2)
    finally:
        # Clean up temp files
        if "wav_path" in locals():
            Path(wav_path).unlink(missing_ok=True)
        # Clean up downloaded media for URL jobs
        if source.startswith("http") and Path(media_path).exists():
            Path(media_path).unlink(missing_ok=True)


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_SIZE}


@app.post("/transcribe/file", response_model=TranscriptMeta)
async def transcribe_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = None,
    tags: str | None = None,
):
    """Upload a media file for transcription. Returns immediately with a job ID."""
    transcript_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]

    # Save uploaded file to temp location
    suffix = Path(file.filename).suffix if file.filename else ".bin"
    tmp_path = f"/tmp/{transcript_id}{suffix}"
    with open(tmp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    meta = TranscriptMeta(
        id=transcript_id,
        status="processing",
        title=title or file.filename,
        tags=tag_list,
        source=f"upload:{file.filename}",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # Write initial status
    with open(TRANSCRIPTS_DIR / f"{transcript_id}.json", "w") as f:
        json.dump(meta.model_dump(), f, indent=2)

    background_tasks.add_task(
        process_transcription,
        transcript_id,
        tmp_path,
        f"upload:{file.filename}",
        title or file.filename,
        tag_list,
    )

    return meta


@app.post("/transcribe/url", response_model=TranscriptMeta)
async def transcribe_url(
    background_tasks: BackgroundTasks,
    request: URLRequest,
):
    """Submit a URL for transcription. Supports YouTube and most video sites via yt-dlp."""
    transcript_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]

    meta = TranscriptMeta(
        id=transcript_id,
        status="downloading",
        title=request.title,
        tags=request.tags or [],
        source=request.url,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    with open(TRANSCRIPTS_DIR / f"{transcript_id}.json", "w") as f:
        json.dump(meta.model_dump(), f, indent=2)

    async def download_and_transcribe():
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                media_path = download_media(request.url, tmpdir)
                process_transcription(
                    transcript_id,
                    media_path,
                    request.url,
                    request.title,
                    request.tags,
                )
        except Exception as e:
            error_meta = {
                "id": transcript_id,
                "status": "failed",
                "error": str(e),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(TRANSCRIPTS_DIR / f"{transcript_id}.json", "w") as f:
                json.dump(error_meta, f, indent=2)

    background_tasks.add_task(download_and_transcribe)

    return meta


@app.get("/transcripts/{transcript_id}")
def get_transcript(transcript_id: str):
    """Retrieve a transcript by ID."""
    path = TRANSCRIPTS_DIR / f"{transcript_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    with open(path) as f:
        return json.load(f)


@app.get("/transcripts")
def list_transcripts(limit: int = 20, status: str | None = None):
    """List recent transcripts."""
    files = sorted(TRANSCRIPTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for f in files[:limit * 2]:  # over-fetch in case we filter
        with open(f) as fh:
            data = json.load(fh)
        if status and data.get("status") != status:
            continue
        # Return metadata only, not full transcript
        results.append({
            k: data.get(k) for k in
            ["id", "status", "title", "tags", "source", "duration_seconds", "created_at"]
        })
        if len(results) >= limit:
            break
    return results


@app.get("/transcripts/{transcript_id}/text")
def get_transcript_text(transcript_id: str):
    """Retrieve just the plain text of a transcript."""
    path = TRANSCRIPTS_DIR / f"{transcript_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    with open(path) as f:
        data = json.load(f)
    if data.get("status") != "completed":
        return {"status": data.get("status"), "text": None}
    return {"status": "completed", "text": data.get("result", {}).get("text", "")}
