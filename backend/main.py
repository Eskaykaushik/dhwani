import asyncio
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from ai_assistant import parse_audio_request
from audio_engine import (
    apply_operation,
    ensure_dirs,
    generate_waveform,
    get_audio_info,
    get_current_file,
    get_specific_file,
    load_versions,
)
from models import (
    ApplyRequest,
    ApplyResponse,
    ChatRequest,
    ChatResponse,
    UploadResponse,
    VersionInfo,
)

logger = logging.getLogger("dhwani")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
FRONTEND_DIR = BASE_DIR / "frontend"
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024)))  # default 50 MB
FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{8}$")

chat_histories = {}


def get_allowed_origins():
    raw = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,https://eskaykaushik.github.io",
    )
    if raw.strip() == "*":
        return ["*"]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        return [o.strip() for o in raw.split(",") if o.strip()]
    except json.JSONDecodeError:
        return [o.strip() for o in raw.split(",") if o.strip()]


def validate_file_id(file_id: str):
    if not FILE_ID_PATTERN.match(file_id):
        raise HTTPException(status_code=400, detail="Invalid file_id")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    logger.info("Dhwani API started")
    yield
    logger.info("Dhwani API shutting down")


app = FastAPI(title="Dhwani - AI Music Editor", lifespan=lifespan)

origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials="*" not in origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload_audio(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in [".mp3", ".wav", ".ogg", ".flac", ".m4a"]:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    file_id = str(uuid.uuid4())[:8]
    filepath = UPLOAD_DIR / f"{file_id}{ext}"

    try:
        with open(filepath, "wb") as f:
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
                    )
                f.write(chunk)
    except Exception:
        filepath.unlink(missing_ok=True)
        raise

    info = await asyncio.to_thread(get_audio_info, str(filepath))
    logger.info("Uploaded %s -> %s (%.1fs, %dHz, %dch)", file.filename, file_id, info["duration"], info["sample_rate"], info["channels"])

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        duration=info["duration"],
        sample_rate=info["sample_rate"],
        channels=info["channels"],
        bpm=info["bpm"],
    )


@app.get("/audio/{file_id}")
async def get_audio(file_id: str, version: int | None = None):
    validate_file_id(file_id)
    current = get_specific_file(file_id, version)
    if not current:
        raise HTTPException(status_code=404, detail="Audio not found")
    ext = Path(current).suffix.lower()
    media_type = "audio/mpeg" if ext == ".mp3" else "audio/wav"
    return FileResponse(current, media_type=media_type)


@app.get("/waveform/{file_id}")
async def get_waveform(file_id: str):
    validate_file_id(file_id)
    current = get_current_file(file_id)
    if not current:
        raise HTTPException(status_code=404, detail="Audio not found")
    waveform = await asyncio.to_thread(generate_waveform, current)
    return {"waveform": waveform}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    validate_file_id(request.file_id)
    current = get_current_file(request.file_id)
    if not current:
        raise HTTPException(status_code=404, detail="Audio not found")

    info = await asyncio.to_thread(get_audio_info, current)

    history = chat_histories.get(request.file_id, [])
    history.append({"role": "user", "content": request.message})

    result = await asyncio.to_thread(parse_audio_request, request.message, info, history)
    op = result.get("operation") if isinstance(result, dict) else None
    logger.info("Chat %s: %r -> operation=%s", request.file_id, request.message, (op or {}).get("operation") if isinstance(op, dict) else None)

    history.append({"role": "assistant", "content": result.get("reply", "")})
    chat_histories[request.file_id] = history[-20:]

    try:
        return ChatResponse(
            file_id=request.file_id,
            reply=result.get("reply", "Done!"),
            operation=result.get("operation"),
        )
    except Exception:
        logger.exception("Failed to build chat response for %s", request.file_id)
        return ChatResponse(
            file_id=request.file_id,
            reply=result.get("reply", "Done!"),
            operation=None,
        )


@app.post("/apply", response_model=ApplyResponse)
async def apply_edit(request: ApplyRequest):
    try:
        validate_file_id(request.file_id)
        version, filepath = await asyncio.to_thread(
            apply_operation, request.file_id, request.operation.model_dump()
        )
        logger.info("Applied %s v%d (op=%s)", request.file_id, version, request.operation.operation)
        return ApplyResponse(
            version=version,
            filename=Path(filepath).name,
            status="success",
        )
    except ValueError as e:
        logger.warning("Apply failed for %s: %s", request.file_id, e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Apply error for %s", request.file_id)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/versions/{file_id}")
async def get_versions(file_id: str):
    validate_file_id(file_id)
    versions = load_versions(file_id)
    result = [
        VersionInfo(
            version=v["version"],
            filename=Path(v["path"]).name,
            operation=v["operation"],
        )
        for v in sorted(versions.values(), key=lambda x: x["version"])
    ]
    return {"versions": result}


@app.get("/")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/{path:path}")
async def serve_static(path: str):
    if path.startswith(("api/",)):
        raise HTTPException(status_code=404, detail="Not found")
    file_path = (FRONTEND_DIR / path).resolve()
    if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path, headers={"Cache-Control": "no-store"})
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-store"})

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
