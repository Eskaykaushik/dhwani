# Dhwani — Improvement Plan

> **Status legend**: ✅ DONE · 🔲 TODO · ⚠️ BLOCKED/CONFLICT
> Last updated: chat reliability hardened (max_tokens under free-tier limit, output coercion, no-500-on-bad-shapes), mobile auto-apply shipped (`b773d60`).

## 1. Project Overview

**Dhwani** is an AI-powered conversational audio editor (tagline: "AI Music Editor"). The core concept: a user uploads an audio file, describes edits in natural language, and the AI converts that request into a structured audio operation that gets applied by a Python audio engine.

### Data Flow
```
User Upload → Audio Analysis → AI Chat (Groq LLM) → Structured Edit JSON → Python Audio Engine → Processed Audio → Version History → Audio Player
```

### Tech Stack
- **Frontend**: Static HTML/CSS/JS (Wavesurfer.js v7)
- **Backend**: Python FastAPI
- **AI**: Groq (`qwen/qwen3.6-27b`)
- **Audio**: librosa, numpy, soundfile, pedalboard

---

## 2. Backend Architecture

### Entry Point: `backend/main.py` (FastAPI)
- `POST /upload` — accepts audio, saves to `uploads/`, returns file_id + metadata
- `GET /audio/{file_id}?version=N` — serves audio file
- `GET /waveform/{file_id}` — returns waveform data
- `POST /chat` — LLM chat, returns structured operation
- `POST /apply` — applies operation, creates new version
- `GET /versions/{file_id}` — lists all versions

### Audio Engine: `backend/audio_engine.py`
- `apply_operation(file_id, operation)` — core DSP function
- Thread-safe versioning via `threading.Lock`
- Atomic writes to `versions.json`
- Output: always WAV to `output/`

### AI Assistant: `backend/ai_assistant.py`
- Uses Groq API with JSON mode (falls back to plain text + regex extraction)
- System prompt defines all available operations
- Returns `{reply, operation, operations}`

---

## 3. Current Audio Tools

| Operation | Status | Notes |
|-----------|--------|-------|
| `trim` | ✅ Implemented | NumPy slice on audio array |
| `volume` | ✅ Implemented | Linear gain multiplication |
| `fade_in` / `fade_out` | ✅ Implemented | Linear ramp |
| `normalize` | ✅ Implemented | Peak scaling to 0.95 |
| `eq` | ⚠️ Weak | Uses Highpass + Lowpass + Gain (band-pass, not true parametric EQ) |
| `compress` | ✅ Implemented | Pedalboard Compressor |
| `reverb` | ⚠️ Limited | Fixed room_size=0.5, damping=0.5; no user control |
| `delay` | ✅ Implemented | Pedalboard Delay |
| `pitch` | ✅ Implemented | Pedalboard PitchShift |
| `tempo` | ⚠️ Broken | Uses `librosa.resample` which changes pitch (varispeed) |
| `layer` | ❌ Not implemented | Listed in AI prompt but raises ValueError |

### Unimplemented but Advertised
- **`layer`**: The AI prompt tells the LLM it can layer audio, but the backend raises `ValueError` for unknown operations.
- **Recommendation**: either implement layer mixing (`load layer file → gain → mix`), or remove `layer` from `KNOWN_OPS` + the system prompt so the AI never suggests a failing operation.

---

## 4. Critical Backend Issues

### 4.1 Layer Operation Missing
- **File**: `backend/ai_assistant.py:17` includes `"layer"` in `KNOWN_OPS`
- **File**: `backend/audio_engine.py:123-226` raises `ValueError` for unknown ops
- **Impact**: AI suggests layering, but it fails at runtime
- **Fix**: Either implement `layer` or remove it from `KNOWN_OPS` and the system prompt
- **Recommendation**: simplest safe fix is removing `layer` from `KNOWN_OPS` + prompt until a real mixing implementation exists; implementing requires a second `file_id` (a previously uploaded/layered file) + gain + mono/stereo alignment.
- **Status**: 🔲 TODO

### 4.2 Tempo Changes Alter Pitch
- **File**: `backend/audio_engine.py:220-223`
- **Current**: `librosa.resample` changes sample rate, which alters pitch (varispeed effect)
- **Impact**: Speeding up makes audio chipmunk; slowing down makes it deep
- **Fix**: Use `librosa.effects.time_stretch` for pitch-preserving tempo changes

### 4.3 No BPM Detection
- **File**: `backend/audio_engine.py:34-41` — `get_audio_info` always returns `bpm: None`
- **Impact**: AI has no tempo context to make smart suggestions (e.g., "match BPM to 128")
- **⚠️ Performance Conflict**: commit `c9cb32e` deliberately removed `librosa.load` from `get_audio_info()` because it made upload take ~110s (now ~2.9s via `soundfile.info`). BPM detection would reintroduce that regression into the request path.
- **Recommendation (APPROVED — do NOT block the request path)**: option (a) compute BPM lazily in a background thread after upload and cache it per `file_id`; option (b) compute BPM during `/apply` instead of `/upload`/`/chat`; or (c) skip BPM entirely and prompt the LLM without tempo. If added, cap cost (e.g., mono downmix + `librosa.beat.beat_track` on a decimated signal, run via `asyncio.to_thread`).

### 4.4 EQ is Musically Limited
- **File**: `backend/audio_engine.py:164-176`
- **Current**: Highpass + Lowpass + Gain centered on frequency = band-pass filter
- **Impact**: Can't do proper bell curves, shelves, or narrow Q boosts/cuts
- **Fix**: Use `pedalboard.PeakFilter` or `EQBand` for proper parametric EQ

### 4.5 Fixed Reverb Parameters
- **File**: `backend/audio_engine.py:189-197`
- **Current**: `room_size=0.5`, `damping=0.5` are hardcoded
- **Impact**: Users can't control reverb character
- **Fix**: Expose `room_size` and `damping` as operation parameters

### 4.6 Missing Common Operations
- No `reverse` (reverse audio) → **trivial**: `y[:, ::-1]` (numpy flip)
- No `silence_remove` (trim silence) → medium effort (`librosa.effects.split`)
- No `noise_reduce` (noise reduction) → high effort (needs a noise profile / `noisereduce`-style)
- **Status**: all still TODO (not implemented)

### 4.7 WAV-Only Output
- **File**: `backend/audio_engine.py:245` — always writes WAV via `sf.write`
- **Impact**: Large file sizes, no MP3/FLAC export option
- **Fix**: Allow format selection or at least FLAC for smaller files
- **Note**: `.wav` extension is hardcoded in `add_version()` (output path `{file_id}_v{n}.wav`) and `ApplyResponse.filename`; changing format touches `audio_engine.py`, `main.py`, `models.py`, and frontend URL building.

---

## 5. Mobile UI Issues

### 5.1 Chat Blocks Audio View
- **File**: `frontend/style.css:619-629`
- **Current**: Chat panel is a fixed bottom sheet covering up to 60vh
- **Impact**: After applying an operation, user must manually close chat to see waveform
- ~~**Desired**: Chat auto-closes after apply so user can immediately play the result~~
- **Status: ✅ DONE** (commit `b773d60`) — on ≤800px screens, chat auto-closes after a successful auto-apply.

### 5.2 Manual Apply Required
- **File**: `frontend/app.js:288-306` — operation cards have explicit "Apply" button
- **Impact**: Extra tap required after every AI suggestion
- ~~**Desired**: Auto-apply on mobile for faster workflow~~
- **Status: ✅ DONE** (commit `b773d60`) — `sendMessage` auto-applies `data.operation` after ~1s on ≤800px screens; desktop still shows the Apply button card.

### 5.3 FAB innerHTML Replacement Bug
- **File**: `frontend/app.js:432-434` — `toggleChat()` replaces `innerHTML`, destroying/recreating DOM
- **Impact**: Potential duplicate IDs, lost state, janky toggle
- ~~**Fix**: Toggle CSS classes instead of replacing HTML~~
- **Status: ✅ DONE** (commit `b773d60`) — icons are now CSS-swapped (`.fab-icon-chat` / `.fab-icon-close` + rotate); `toggleChat()` only toggles classes.

---

## 6. Recommended Fixes

### Priority: High

| # | Issue | Files to Change | Status |
|---|-------|-----------------|--------|
| 1 | Layer operation broken | `backend/ai_assistant.py`, `backend/audio_engine.py` | 🔲 TODO — implement or remove from prompt |
| 2 | Tempo changes pitch | `backend/audio_engine.py:220-223` | 🔲 TODO — use `librosa.effects.time_stretch` |
| 3 | No BPM detection | `backend/audio_engine.py:34-41` | ⚠️ Blocked by perf regression — see §4.3 recommendation |
| 4 | Mobile auto-apply + auto-close | `frontend/app.js`, `frontend/index.html`, `frontend/style.css` | ✅ DONE (`b773d60`) |
| 5 | FAB innerHTML bug | `frontend/app.js:429-435` | ✅ DONE (`b773d60`) |

### Priority: Medium

| # | Issue | Files to Change | Status |
|---|-------|-----------------|--------|
| 6 | EQ is band-pass not parametric | `backend/audio_engine.py:164-176` | 🔲 TODO — use `pedalboard.PeakFilter` |
| 7 | Fixed reverb params | `backend/audio_engine.py`, `ai_assistant.py`, `models.py` | 🔲 TODO — expose room_size/damping |
| 8 | Missing reverse/silence/noise | `backend/audio_engine.py`, `ai_assistant.py`, `models.py` | 🔲 TODO — reverse trivial; silence/noise larger |
| 9 | WAV-only output | `backend/audio_engine.py`, `models.py` | 🔲 TODO |

### Priority: Low

| # | Issue | Files to Change | Status |
|---|-------|-----------------|--------|
| 10 | Waveform loads full audio | `backend/audio_engine.py:44-52` | 🔲 TODO — chunked downsampling |

---

## 7. Mobile Auto-Apply Implementation Details

**Status: ✅ DONE** (commit `b773d60`) — implemented as above. Flow in `sendMessage`:
1. Upload file → editor appears
2. Tap FAB → chat slides up as bottom sheet
3. Type "add reverb" → send
4. AI shows operation card
5. **Auto-applies** after ~1s delay and shows toast "Version N applied"
6. **Chat auto-closes** → waveform updates
7. User immediately sees new waveform and can press play

### Code Changes (landed in `b773d60`)
- `applyOp` works without a button ref (returns `true`/`false` for auto-apply).
- `sendMessage` detects mobile (`window.innerWidth <= 800`) and auto-applies + closes chat.
- `toggleChat` toggles CSS classes only; FAB icon swap via `.fab-icon-*` spans (no innerHTML rebuild).

---

## 8. Backend Operation Implementation Details

### 8.1 Implement Layer Operation
```python
elif op_type == "layer":
    layer_file_id = operation.get("file_id")
    layer_gain_db = operation.get("gain", 0)
    # Load layer file, apply gain, mix with current audio
    # Handle mono/stereo alignment
```

### 8.2 Fix Tempo (Time Stretch)
```python
elif op_type == "tempo":
    factor = operation.get("factor", 1.0)
    y = librosa.effects.time_stretch(y, rate=factor)
    # sr stays the same, only duration changes
```

### 8.3 Add BPM Detection
```python
# NOTE: profile/cap this — librosa.load on the request path regressed upload to ~110s.
# Prefer background-thread compute or run during /apply, never in /upload.
def get_audio_info(filepath):
    info = sf.info(filepath)
    y, sr = librosa.load(filepath, sr=None, mono=True)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    return {
        "duration": float(info.duration),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "bpm": float(tempo),
    }
```

### 8.4 Fix EQ with PeakFilter
```python
elif op_type == "eq":
    freq = operation.get("frequency", 1000)
    gain_db = operation.get("gain", 0)
    q_factor = operation.get("q_factor", 1.0)
    
    board = Pedalboard([
        PeakFilter(cutoff_frequency_hz=freq, gain_db=gain_db, q=q_factor)
    ])
    
    for ch in range(y.shape[0]):
        y[ch] = board(y[ch].astype(np.float32), sr)
```

### 8.5 Expose Reverb Parameters
```python
elif op_type == "reverb":
    wet = operation.get("wet", 0.5)
    room_size = operation.get("room_size", 0.5)
    damping = operation.get("damping", 0.5)
    
    board = Pedalboard([
        Reverb(room_size=room_size, damping=damping, wet_level=wet, dry_level=1.0 - wet)
    ])
```

---

## 9. Testing Considerations

- Update `backend/test_main.py` to cover new operations
- Add mobile-specific frontend tests (auto-apply, auto-close)
- Test concurrent applies with layer operation
- Test BPM detection with various genres/tempos

---

## 10. Deployment Notes

- Backend runs on Render (ephemeral, disk wipes on restart)
- Frontend on GitHub Pages
- All new audio operations must be idempotent and thread-safe
- Versioning must remain atomic (temp file + os.replace)
- Chat history is in-memory and lost on restart (acceptable for ephemeral design)
