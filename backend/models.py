
from pydantic import BaseModel


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    duration: float
    sample_rate: int
    channels: int
    bpm: float | None = None


class ChatRequest(BaseModel):
    file_id: str
    message: str


class ChatResponse(BaseModel):
    file_id: str
    reply: str
    operation: dict | None = None


class AudioOperation(BaseModel):
    operation: str
    start: float | None = None
    end: float | None = None
    value: float | None = None
    frequency: float | None = None
    gain: float | None = None
    threshold: float | None = None
    ratio: float | None = None
    wet: float | None = None
    duration: float | None = None
    q_factor: float | None = None
    delay_time: float | None = None
    feedback: float | None = None
    semitones: float | None = None
    factor: float | None = None
    intensity: float | None = None
    strength: float | None = None


class ApplyRequest(BaseModel):
    file_id: str
    operation: AudioOperation


class ApplyResponse(BaseModel):
    version: int
    filename: str
    status: str


class VersionInfo(BaseModel):
    version: int
    filename: str
    operation: str
