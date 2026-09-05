import json
import os
import tempfile
import threading
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from pedalboard import (
    Compressor,
    Delay,
    Gain,
    HighpassFilter,
    LowpassFilter,
    Pedalboard,
    PitchShift,
    Reverb,
)

BASE_DIR = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
VERSIONS_FILE = BASE_DIR / "versions.json"

_versions_lock = threading.Lock()


def ensure_dirs():
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def get_audio_info(filepath: str) -> dict:
    info = sf.info(filepath)
    return {
        "duration": float(info.duration),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "bpm": None
    }


def generate_waveform(filepath: str, points: int = 500) -> list:
    y, _ = librosa.load(filepath, sr=None, mono=True)
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


def get_specific_file(file_id: str, version: int | None = None) -> str:
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
    with _versions_lock:
        if VERSIONS_FILE.exists():
            all_versions = json.loads(VERSIONS_FILE.read_text())
            return all_versions.get(file_id, {})
    return {}


def add_version(file_id: str, operation: str) -> tuple:
    with _versions_lock:
        if VERSIONS_FILE.exists():
            all_versions = json.loads(VERSIONS_FILE.read_text())
        else:
            all_versions = {}

        file_versions = all_versions.get(file_id, {})
        current_version = max(
            [v.get("version", 0) for v in file_versions.values()], default=0
        )
        new_version = current_version + 1
        output_path = OUTPUT_DIR / f"{file_id}_v{new_version}.wav"

        if file_id not in all_versions:
            all_versions[file_id] = {}

        all_versions[file_id][str(new_version)] = {
            "version": new_version,
            "path": str(output_path),
            "operation": operation
        }

        fd, tmp_path = tempfile.mkstemp(
            dir=str(VERSIONS_FILE.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(all_versions, f, indent=2)
            os.replace(tmp_path, VERSIONS_FILE)
        except Exception:
            os.unlink(tmp_path)
            raise

        return new_version, output_path


def apply_operation(file_id: str, operation: dict) -> tuple:
    current = get_current_file(file_id)
    if not current:
        raise ValueError("File not found")

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

    fd, tmp_path = tempfile.mkstemp(dir=str(OUTPUT_DIR), suffix=".wav")
    os.close(fd)
    try:
        sf.write(str(tmp_path), y.T if y.shape[0] > 1 else y.flatten(), sr)
    except Exception:
        os.unlink(tmp_path)
        raise

    new_version, output_path = add_version(file_id, op_name)

    try:
        os.replace(tmp_path, output_path)
        return new_version, str(output_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


MP3_SAMPLE_RATES = {8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000}


def to_mp3(filepath: str, bitrate: int = 320) -> bytes:
    import lameenc

    y, sr = sf.read(filepath, dtype="float32", always_2d=True)
    y = y.T  # (channels, samples)

    if y.shape[0] == 1:
        y = np.repeat(y, 2, axis=0)

    if sr not in MP3_SAMPLE_RATES:
        target = 48000 if sr > 48000 else 44100
        y = librosa.resample(y, orig_sr=sr, target_sr=target)
        sr = target

    pcm = np.rint(np.clip(y, -1.0, 1.0) * 32767).astype(np.int16).T
    interleaved = pcm.reshape(-1)

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_in_sample_rate(sr)
    encoder.set_channels(2)
    encoder.set_quality(2)
    data = bytearray(encoder.encode(interleaved.tobytes()))
    data += encoder.flush()
    return bytes(data)
