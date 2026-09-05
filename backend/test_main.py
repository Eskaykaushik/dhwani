import asyncio
import io
import struct
import wave

import pytest
from fastapi.testclient import TestClient

import ai_assistant
import audio_engine
import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(audio_engine, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(audio_engine, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(audio_engine, "VERSIONS_FILE", tmp_path / "versions.json")
    main.UPLOAD_DIR.mkdir(exist_ok=True)
    main.OUTPUT_DIR.mkdir(exist_ok=True)
    audio_engine.UPLOAD_DIR.mkdir(exist_ok=True)
    audio_engine.OUTPUT_DIR.mkdir(exist_ok=True)
    with TestClient(main.app) as c:
        yield c


def make_wav(duration=0.1, sample_rate=4000, channels=1) -> bytes:
    buf = io.BytesIO()
    n_frames = int(sample_rate * duration)
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        frames = struct.pack(f"<{n_frames}h", *([0] * n_frames))
        w.writeframes(frames)
    return buf.getvalue()


SKIP_AUDIO_DURATION = 1.0


def test_chat_route_never_500s_on_bad_operation_shape(client, monkeypatch):
    up = client.post("/upload", files={"file": ("t.wav", make_wav(SKIP_AUDIO_DURATION), "audio/wav")})
    file_id = up.json()["file_id"]

    def fake_parse(message, ctx, history):
        return {"reply": "doin it", "operation": "volume", "operations": None}

    monkeypatch.setattr(main, "parse_audio_request", fake_parse)
    resp = client.post("/chat", json={"file_id": file_id, "message": "make it louder"})
    assert resp.status_code == 200
    assert resp.json()["operation"] is None


def test_coerce_operation_normalizes_shapes():
    assert ai_assistant.coerce_operation("volume") == {"operation": "volume"}
    assert ai_assistant.coerce_operation({"operation": "volume", "gain": 6}) == {"operation": "volume", "gain": 6}
    assert ai_assistant.coerce_operation({"volume": {"gain": 6}}) == {"operation": "volume", "gain": 6}
    assert ai_assistant.coerce_operation("bogus") is None
    assert ai_assistant.coerce_operation({"operation": "bogus"}) is None
    assert ai_assistant.coerce_operation(123) is None


def test_normalize_result_picks_operations_first():
    result = ai_assistant.normalize_result(
        {"reply": "ok", "operation": "bogus", "operations": [{"operation": "trim", "start": 0, "end": 10}]}
    )
    assert result["operation"] == {"operation": "trim", "start": 0, "end": 10}
    assert result["operations"] is None


def test_normalize_result_defaults_reply():
    result = ai_assistant.normalize_result({"operation": "volume"})
    assert result["reply"] == "Done!"
    assert result["operation"] == {"operation": "volume"}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_path_traversal_blocked(client):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.serve_static("../../etc/passwd"))
    assert exc.value.status_code == 403


def test_static_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_invalid_file_id_rejected(client):
    for bad in ["zzzzzzzz", "abcdefg", "ABCDEFGH", "abcdef012", "abc"]:
        assert client.get(f"/audio/{bad}").status_code == 400
        assert client.get(f"/waveform/{bad}").status_code == 400
        assert client.get(f"/versions/{bad}").status_code == 400


def test_upload_and_audio_roundtrip(client):
    resp = client.post(
        "/upload",
        files={"file": ("test.wav", make_wav(SKIP_AUDIO_DURATION), "audio/wav")},
    )
    assert resp.status_code == 200
    data = resp.json()
    file_id = data["file_id"]
    assert len(file_id) == 8
    assert data["duration"] > 0

    audio = client.get(f"/audio/{file_id}")
    assert audio.status_code == 200

    wave_resp = client.get(f"/waveform/{file_id}")
    assert wave_resp.status_code == 200
    assert wave_resp.json()["waveform"]


def test_upload_unsupported_format(client):
    resp = client.post(
        "/upload",
        files={"file": ("bad.txt", b"not audio", "text/plain")},
    )
    assert resp.status_code == 400


def test_apply_malformed_operation_422(client):
    resp = client.post(
        "/apply",
        json={"file_id": "abcdef01", "operation": "not-a-dict"},
    )
    assert resp.status_code == 422


def test_apply_unknown_operation_422(client):
    resp = client.post(
        "/apply",
        json={"file_id": "abcdef01", "operation": {"operation": 123}},
    )
    assert resp.status_code == 422


def test_apply_unknown_file(client):
    resp = client.post(
        "/apply",
        json={"file_id": "abcdef01", "operation": {"operation": "volume", "gain": 3}},
    )
    assert resp.status_code == 404 or resp.status_code == 400


def test_apply_valid_operation_creates_version(client):
    up = client.post("/upload", files={"file": ("t.wav", make_wav(SKIP_AUDIO_DURATION), "audio/wav")})
    file_id = up.json()["file_id"]
    resp = client.post(
        "/apply",
        json={"file_id": file_id, "operation": {"operation": "volume", "gain": 3}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["version"] == 1

    versions = client.get(f"/versions/{file_id}")
    assert versions.status_code == 200
    assert len(versions.json()["versions"]) == 1


def test_concurrent_applies_get_unique_versions(tmp_path, monkeypatch):
    import concurrent.futures

    monkeypatch.setattr(audio_engine, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(audio_engine, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(audio_engine, "VERSIONS_FILE", tmp_path / "versions.json")
    audio_engine.UPLOAD_DIR.mkdir(exist_ok=True)
    audio_engine.OUTPUT_DIR.mkdir(exist_ok=True)

    file_id = "deadbeef"
    upload_path = audio_engine.UPLOAD_DIR / f"{file_id}.wav"
    upload_path.write_bytes(make_wav(SKIP_AUDIO_DURATION))

    def do_apply(i):
        return audio_engine.apply_operation(file_id, {"operation": "volume", "gain": float(i)})

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(do_apply, range(1, 6)))

    versions = [v for v, _ in results]
    assert sorted(versions) == [1, 2, 3, 4, 5]
    assert len(set(versions)) == 5
    assert len(audio_engine.load_versions(file_id)) == 5
