import os
import uuid
import json
import numpy as np
import librosa
import soundfile as sf
from pathlib import Path
from pedalboard import (
    Pedalboard,
    Reverb,
    Compressor,
    Gain,
    HighpassFilter,
    LowpassFilter,
)
from pedalboard import Delay, PitchShift

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
VERSIONS_FILE = BASE_DIR / "versions.json"


def ensure_dirs():
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def get_audio_info(filepath: str) -> dict:
    y, sr = librosa.load(filepath, sr=None, mono=False)
    duration = librosa.get_duration(y=y, sr=sr)

    if y.ndim == 1:
        channels = 1
    else:
        channels = y.shape[0]

    tempo, _ = librosa.beat.beat_track(y=y if y.ndim == 1 else y[0], sr=sr)

    return {
        "duration": float(duration),
        "sample_rate": int(sr),
        "channels": channels,
        "bpm": float(tempo) if tempo else None
    }


def generate_waveform(filepath: str, points: int = 500) -> list:
    y, sr = librosa.load(filepath, sr=None, mono=True)
    hop_length = len(y) // points
    waveform = []
    for i in range(0, len(y), hop_length):
        chunk = y[i:i + hop_length]
        if len(chunk) > 0:
            waveform.append(float(np.max(np.abs(chunk))))
    return waveform


def get_current_file(file_id: str) -> str:
    versions = load_versions(file_id)
    if versions:
        latest = max(versions.keys(), key=lambda x: versions[x]["version"])
        return versions[latest]["path"]
    return get_original_file(file_id)


def get_specific_file(file_id: str, version: int = None) -> str:
    if version is None:
        return get_current_file(file_id)
    versions = load_versions(file_id)
    if str(version) in versions:
        return versions[str(version)]["path"]
    return get_original_file(file_id)


def get_original_file(file_id: str) -> str:
    import glob
    matches = glob.glob(str(UPLOAD_DIR / f"{file_id}.*"))
    return matches[0] if matches else None


def load_versions(file_id: str) -> dict:
    if VERSIONS_FILE.exists():
        all_versions = json.loads(VERSIONS_FILE.read_text())
        return all_versions.get(file_id, {})
    return {}


def save_version(file_id: str, version: int, filepath: str, operation: str):
    if VERSIONS_FILE.exists():
        all_versions = json.loads(VERSIONS_FILE.read_text())
    else:
        all_versions = {}

    if file_id not in all_versions:
        all_versions[file_id] = {}

    all_versions[file_id][str(version)] = {
        "version": version,
        "path": filepath,
        "operation": operation
    }

    VERSIONS_FILE.write_text(json.dumps(all_versions, indent=2))


def apply_operation(file_id: str, operation: dict) -> tuple:
    current = get_current_file(file_id)
    if not current:
        raise ValueError("File not found")

    versions = load_versions(file_id)
    current_version = max([v["version"] for v in versions.values()], default=0)
    new_version = current_version + 1

    y, sr = librosa.load(current, sr=None, mono=False)

    if y.ndim == 1:
        y = y.reshape(1, -1)

    op_type = operation.get("operation")

    if op_type == "trim":
        start = operation.get("start", 0)
        end = operation.get("end", len(y[0]) / sr)
        start_sample = int(start * sr)
        end_sample = int(end * sr)
        y = y[:, start_sample:end_sample]

    elif op_type == "volume":
        gain_db = operation.get("gain", 0)
        gain_linear = 10 ** (gain_db / 20)
        y = y * gain_linear

    elif op_type == "fade_in":
        duration = operation.get("duration", 1.0)
        fade_samples = int(duration * sr)
        fade = np.linspace(0, 1, fade_samples)
        y[:, :fade_samples] *= fade

    elif op_type == "fade_out":
        duration = operation.get("duration", 1.0)
        fade_samples = int(duration * sr)
        fade = np.linspace(1, 0, fade_samples)
        y[:, -fade_samples:] *= fade

    elif op_type == "normalize":
        max_val = np.max(np.abs(y))
        if max_val > 0:
            y = y / max_val * 0.95

    elif op_type == "eq":
        freq = operation.get("frequency", 1000)
        gain_db = operation.get("gain", 0)
        q_factor = operation.get("q_factor", 1.0)

        board = Pedalboard([
            HighpassFilter(cutoff_frequency_hz=max(20, freq - (freq / q_factor) / 2)),
            LowpassFilter(cutoff_frequency_hz=min(sr // 2 - 1, freq + (freq / q_factor) / 2)),
            Gain(gain_db=gain_db)
        ])

        for ch in range(y.shape[0]):
            y[ch] = board(y[ch].astype(np.float32), sr)

    elif op_type == "compress":
        threshold = operation.get("threshold", -20)
        ratio = operation.get("ratio", 4.0)

        board = Pedalboard([
            Compressor(threshold_db=threshold, ratio=ratio, attack_ms=10, release_ms=100)
        ])

        for ch in range(y.shape[0]):
            y[ch] = board(y[ch].astype(np.float32), sr)

    elif op_type == "reverb":
        wet = operation.get("wet", 0.5)

        board = Pedalboard([
            Reverb(room_size=0.5, damping=0.5, wet_level=wet, dry_level=1.0 - wet)
        ])

        for ch in range(y.shape[0]):
            y[ch] = board(y[ch].astype(np.float32), sr)

    elif op_type == "delay":
        delay_time = operation.get("delay_time", 0.5)
        feedback = operation.get("feedback", 0.3)

        board = Pedalboard([
            Delay(delay_seconds=delay_time, feedback=feedback, mix=0.4)
        ])

        for ch in range(y.shape[0]):
            y[ch] = board(y[ch].astype(np.float32), sr)

    elif op_type == "pitch":
        semitones = operation.get("semitones", 0)

        board = Pedalboard([
            PitchShift(semitones=semitones)
        ])

        for ch in range(y.shape[0]):
            y[ch] = board(y[ch].astype(np.float32), sr)

    elif op_type == "tempo":
        factor = operation.get("factor", 1.0)
        y = librosa.resample(y, orig_sr=sr, target_sr=int(sr * factor))
        sr = int(sr * factor)

    else:
        raise ValueError(f"Unknown operation: {op_type}")

    output_path = OUTPUT_DIR / f"{file_id}_v{new_version}.wav"
    sf.write(str(output_path), y.T if y.shape[0] > 1 else y.flatten(), sr)

    op_name = op_type
    if op_type == "eq":
        op_name = f"eq ({operation.get('frequency', 1000)}Hz, {operation.get('gain', 0)}dB)"
    elif op_type == "volume":
        op_name = f"volume ({operation.get('gain', 0)}dB)"
    elif op_type == "trim":
        op_name = f"trim ({operation.get('start', 0)}s - {operation.get('end', 0)}s)"
    elif op_type == "compress":
        op_name = f"compress (threshold: {operation.get('threshold', -20)}dB, ratio: {operation.get('ratio', 4)})"
    elif op_type == "reverb":
        op_name = f"reverb (wet: {operation.get('wet', 0.5)})"
    elif op_type == "pitch":
        op_name = f"pitch ({operation.get('semitones', 0)} semitones)"

    save_version(file_id, new_version, str(output_path), op_name)

    return new_version, str(output_path)
