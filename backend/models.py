from pydantic import BaseModel
from typing import Optional


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    duration: float
    sample_rate: int
    channels: int
    bpm: Optional[float] = None


class ChatRequest(BaseModel):
    file_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    operation: Optional[dict] = None


class ApplyRequest(BaseModel):
    file_id: str
    operation: dict


class ApplyResponse(BaseModel):
    version: int
    filename: str
    status: str


class AudioOperation(BaseModel):
    operation: str
    start: Optional[float] = None
    end: Optional[float] = None
    value: Optional[float] = None
    frequency: Optional[float] = None
    gain: Optional[float] = None
    threshold: Optional[float] = None
    ratio: Optional[float] = None
    wet: Optional[float] = None


class VersionInfo(BaseModel):
    version: int
    filename: str
    operation: str
