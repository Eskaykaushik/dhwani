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

    elif op_type == "beat":
        raw = operation.get("intensity")
        intensity = float(raw) if isinstance(raw, (int, float)) and raw is not None else 0.45
        intensity = max(0.0, min(1.0, intensity))

        bpm = _beat_bpm(y, sr)
        left, right = _synth_beat_drums(y.shape[1], sr, bpm)

        peak = max(1e-9, float(np.max(np.abs(left))), float(np.max(np.abs(right))))
        drums_l = left / peak * intensity
        drums_r = right / peak * intensity

        if y.shape[0] > 1:
            drums = np.stack([drums_l, drums_r])
        else:
            drums = ((drums_l + drums_r) / 2.0)[None, :]
        y = np.clip(y + drums, -0.95, 0.95)

    elif op_type == "denoise":
        import noisereduce

        raw = operation.get("strength")
        strength = float(raw) if isinstance(raw, (int, float)) and raw is not None else 0.6
        strength = max(0.0, min(1.0, strength))

        n_fft = 1024
        smooth_ms = max(64.0, 1.5 * n_fft * 1000.0 / sr)

        def _denoise_channel(ch):
            return noisereduce.reduce_noise(
                y=ch.astype(np.float32),
                sr=sr,
                prop_decrease=strength,
                stationary=True,
                n_fft=n_fft,
                time_mask_smooth_ms=smooth_ms,
                use_tqdm=False,
            )

        if y.shape[1] >= 2 * n_fft:
            if y.shape[0] > 1:
                y = np.array([_denoise_channel(ch) for ch in y])
            else:
                y = _denoise_channel(y[0])[None, :]

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
    elif op_type == "beat":
        op_name = f"beat ({intensity:.0%})"
    elif op_type == "denoise":
        op_name = f"denoise ({strength:.0%})"

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


def _beat_bpm(y: np.ndarray, sr: int) -> float:
    mono = np.mean(y, axis=0) if y.ndim > 1 else np.asarray(y)
    try:
        tempo, _ = librosa.beat.beat_track(y=mono, sr=sr)
        bpm = float(np.atleast_1d(tempo)[0])
    except Exception:
        bpm = 0.0
    if not np.isfinite(bpm) or bpm < 40 or bpm > 220:
        bpm = 120.0
    return bpm


def _add_hit(buf: np.ndarray, sig: np.ndarray, start: int):
    if start >= len(buf):
        return
    n = min(len(sig), len(buf) - start)
    if n <= 0:
        return
    buf[start:start + n] += sig[:n]


def _synth_beat_drums(total_samples: int, sr: int, bpm: float) -> tuple:
    nyq = sr / 2.0
    beat_samples = max(1, round((60.0 / bpm) * sr))
    n_beats = max(1, (total_samples + beat_samples - 1) // beat_samples)

    t_kick = np.arange(int(0.22 * sr)) / sr
    freq = 45 + 100 * np.exp(-t_kick / 0.02)
    freq = np.minimum(freq, nyq * 0.8)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    kick_env = np.exp(-t_kick / 0.16)
    sub = np.sin(2 * np.pi * min(55, nyq * 0.8) * t_kick) * np.exp(-t_kick / 0.22) * 0.5
    kick_sig = np.clip(np.sin(phase) * kick_env * 0.6 + sub, -1, 1)

    t_snare = np.arange(int(0.14 * sr)) / sr
    noise = np.random.randn(len(t_snare)) * np.exp(-t_snare / 0.10)
    tone = np.sin(2 * np.pi * min(190, nyq * 0.8) * t_snare) * np.exp(-t_snare / 0.09)
    snare_sig = np.clip(noise * 0.8 + tone * 0.25, -1, 1)

    t_hat = np.arange(int(0.05 * sr)) / sr
    hat_sig = np.clip(np.random.randn(len(t_hat)) * np.exp(-t_hat / 0.018), -1, 1) * 0.5

    left = np.zeros(total_samples)
    right = np.zeros(total_samples)
    half = max(1, beat_samples // 2)
    for i in range(n_beats):
        start = i * beat_samples
        _add_hit(left, kick_sig, start)
        _add_hit(right, kick_sig, start)
        if i % 4 in (1, 3):
            _add_hit(left, snare_sig * 0.85, start)
            _add_hit(right, snare_sig * 1.15, start)
        _add_hit(left, hat_sig * 1.15, start + half)
        _add_hit(right, hat_sig * 0.85, start + half)
    return left, right


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
