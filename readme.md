# Dhwani — AI Music Editor

A simple AI-powered audio editor that lets users modify songs using natural-language instructions.

Upload a song → chat with the AI → apply an edit → listen to the result.

## ✨ Example

```
Upload: Bam Lehri.mp3

You:
"Add a deeper bass from 30 seconds."

AI:
"I'll add a deeper bass layer starting at 00:30."

[ Apply Changes ]

⏳ Processing...

✓ Ready

▶ Play
```

## 🧠 How It Works

```
User
 │
 ▼
Upload Audio
 │
 ▼
Audio Analysis (BPM, duration, waveform, beat info)
 │
 ▼
AI Assistant (natural language)
 │
 ▼
Structured Edit
 │
 ▼
Python Audio Engine
 │
 ▼
Processed Audio
 │
 ▼
Audio Player
```

The AI does **not** generate or execute arbitrary Python code. It converts the user's request into a structured operation that the audio engine validates and executes:

```json
{
  "operation": "compress",
  "start": 30,
  "end": 90,
  "threshold": -18,
  "ratio": 4
}
```

## 🎚️ Audio Operations

- Trim / Cut
- Volume
- Fade in / out
- Normalize
- EQ
- Compression
- Limiter
- Reverb
- Delay
- Pitch
- Tempo
- Add audio/sample layer

More advanced effects can be added later.

## 🐍 Tech Stack

- **Frontend:** HTML, CSS, JavaScript (Wavesurfer.js)
- **Backend:** Python, FastAPI
- **AI:** LLM with structured/tool calling (Groq — `qwen/qwen3.6-27b`)
- **Audio:** NumPy, SciPy, librosa, soundfile, FFmpeg, Pedalboard

## 🚀 Run Locally

```bash
# 1. Create and activate a virtual env
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure the Groq API key
cp .env.example .env
# edit .env and set GROQ_API_KEY=your-key

# 4. Start the server
cd backend
python main.py
```

Then open **http://localhost:8000** in your browser.

## 🔄 Versioning

The original file is never overwritten. Each edit produces a new version you can listen to and undo:

```
Original
   │
   ├── Version 1 ── Added bass
   │
   ├── Version 2 ── Added compression
   │
   └── Version 3 ── Added reverb
```

> **Note:** The current version stores files on the local filesystem. In production (free hosting) this is an **ephemeral session** — files persist only until the service restarts or redeploys, which resets the session to a clean state.

## 🚀 Deployment

Free deployment as a **single, ephemeral session** using one repo with two folders:

```
dhwani/
├── backend/   → Render (FastAPI + audio engine)
└── frontend/  → GitHub Pages (static UI)
```

### 1. GitHub Pages (frontend)

- The frontend is static HTML/CSS/JS hosted on GitHub Pages.
- With the repo deployed to Pages, the site is served at `https://<user>.github.io/dhwani/`.
- The `API` base URL in `frontend/app.js` points at the Render backend.

### 2. Render (backend)

- The repo includes a `render.yaml` Blueprint ready for Render.
- Create a free account at <https://render.com>, then:
  1. **New → Blueprint** and connect the repository.
  2. Render reads `render.yaml` and provisions the service on the **Free** plan.
  3. Add the secret **`GROQ_API_KEY`** (and optionally `ALLOWED_ORIGINS`).
  4. Deploy. The service runs on `https://dhwani-bv20.onrender.com` (or your chosen name).

### 3. Environment variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `GROQ_API_KEY` | Key for the Groq LLM provider | Yes |
| `GROQ_MODEL` | Model name (default `qwen/qwen3.6-27b`) | No |
| `ALLOWED_ORIGINS` | CORS allowlist as JSON array or comma-separated (default localhost; never `*` in production) | No |
| `MAX_UPLOAD_SIZE` | Max upload size in bytes (default 50 MB) | No |
| `HOST` / `PORT` | Bind address / port for `python main.py` (default `127.0.0.1:8000`) | No |

### 4. Single-session behavior

Uploads and edits are stored on Render's ephemeral disk. On every restart/redeploy the disk is wiped, so the session resets cleanly — no stale data, no cleanup needed.

## 🧪 Tests & Linting

```bash
# Run the test suite (from repo root)
python -m pytest backend/test_main.py -q

# Lint
cd backend && python -m ruff check .

# Health check
curl http://localhost:8000/health   # -> {"status": "ok"}
```

CI runs both on every push/PR via `.github/workflows/ci.yml`.

## 🎯 Goal

Build a simple conversational audio editor, not a full DAW. The user shouldn't need to understand compressors, EQs, plugins, or DSP — they just say:

"Make the drums punchier."

and let the AI figure out how to achieve it.

Upload → Tell the AI what you want → Apply → Listen.