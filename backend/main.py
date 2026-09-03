import os
import uuid
import glob
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from models import (
    UploadResponse,
    ChatRequest,
    ChatResponse,
    ApplyRequest,
    ApplyResponse,
    VersionInfo,
)
from audio_engine import (
    ensure_dirs,
    get_audio_info,
    generate_waveform,
    get_current_file,
    get_specific_file,
    load_versions,
    apply_operation,
)
from ai_assistant import parse_audio_request

app = FastAPI(title="Dhwani - AI Music Editor")

def get_allowed_origins():
    raw = os.getenv("ALLOWED_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [o.strip() for o in raw.split(",") if o.strip()]

origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials="*" not in origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
FRONTEND_DIR = BASE_DIR / "frontend"

chat_histories = {}


@app.on_event("startup")
async def startup():
    ensure_dirs()


@app.post("/upload", response_model=UploadResponse)
async def upload_audio(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in [".mp3", ".wav", ".ogg", ".flac", ".m4a"]:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    file_id = str(uuid.uuid4())[:8]
    filepath = UPLOAD_DIR / f"{file_id}{ext}"

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    info = get_audio_info(str(filepath))

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        duration=info["duration"],
        sample_rate=info["sample_rate"],
        channels=info["channels"],
        bpm=info["bpm"],
    )


@app.get("/audio/{file_id}")
async def get_audio(file_id: str, version: int = None):
    current = get_specific_file(file_id, version)
    if not current:
        raise HTTPException(status_code=404, detail="Audio not found")
    ext = Path(current).suffix.lower()
    media_type = "audio/mpeg" if ext == ".mp3" else "audio/wav"
    return FileResponse(current, media_type=media_type)


@app.get("/waveform/{file_id}")
async def get_waveform(file_id: str):
    current = get_current_file(file_id)
    if not current:
        raise HTTPException(status_code=404, detail="Audio not found")
    waveform = generate_waveform(current)
    return {"waveform": waveform}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    current = get_current_file(request.file_id)
    if not current:
        raise HTTPException(status_code=404, detail="Audio not found")

    info = get_audio_info(current)

    history = chat_histories.get(request.file_id, [])
    history.append({"role": "user", "content": request.message})

    result = parse_audio_request(request.message, info, history)

    history.append({"role": "assistant", "content": result.get("reply", "")})
    chat_histories[request.file_id] = history[-20:]

    operation = result.get("operation")
    operations = result.get("operations")

    if operations:
        operation = operations[0]

    return ChatResponse(
        reply=result.get("reply", "Done!"),
        operation=operation,
    )


@app.post("/apply", response_model=ApplyResponse)
async def apply_edit(request: ApplyRequest):
    try:
        version, filepath = apply_operation(request.file_id, request.operation)
        return ApplyResponse(
            version=version,
            filename=Path(filepath).name,
            status="success",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/versions/{file_id}")
async def get_versions(file_id: str):
    versions = load_versions(file_id)
    result = []
    for v in sorted(versions.values(), key=lambda x: x["version"]):
        result.append(VersionInfo(
            version=v["version"],
            filename=Path(v["path"]).name,
            operation=v["operation"],
        ))
    return {"versions": result}


@app.get("/")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/{path:path}")
async def serve_static(path: str):
    if path.startswith(("api/",)):
        raise HTTPException(status_code=404, detail="Not found")
    file_path = FRONTEND_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path, headers={"Cache-Control": "no-store"})
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-store"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
