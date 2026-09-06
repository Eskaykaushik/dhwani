import json
import logging
import os
import re

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logger = logging.getLogger("dhwani")

MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")

KNOWN_OPS = {
    "trim", "volume", "fade_in", "fade_out", "normalize",
    "eq", "compress", "reverb", "delay", "pitch", "tempo", "beat", "denoise", "enhance",
}

_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client

AUDIO_OPERATIONS_PROMPT = """You are an AI audio editing assistant for a music editor called Dhwani.

You convert natural language requests into structured audio operations. You do NOT write code.
Answer directly with a JSON object only. Do not ever show chain-of-thought or thinking text.

Available operations:
- "trim": Cut audio to a time range. Params: start, end (seconds)
- "volume": Change volume. Params: gain (dB, positive= louder, negative= quieter)
- "fade_in": Add fade in. Params: duration (seconds)
- "fade_out": Add fade out. Params: duration (seconds)
- "normalize": Normalize audio. No params.
- "eq": Equalizer. Params: frequency (Hz), gain (dB), q_factor (default 1.0)
- "compress": Dynamic range compression. Params: threshold (dB), ratio (default 4.0)
- "reverb": Add reverb. Params: wet (0.0 to 1.0, default 0.5)
- "delay": Add delay/echo. Params: delay_time (seconds), feedback (0.0 to 1.0)
- "pitch": Change pitch. Params: semitones (positive = up, negative = down)
- "tempo": Change tempo. Params: factor (1.0 = same, 1.5 = 50% faster, 0.5 = half speed)
- "beat": Overlay a synthesized beat/drum layer (kick, snare, hi-hats) on the track. Params: intensity (0.0 to 1.0, higher = stronger/more prominent, default 0.45); use a higher intensity for requests like "strong beat"
- "denoise": Remove stationary background noise / hiss / hum from the track. Params: strength (0.0 to 1.0, default 0.6); use higher values like 0.85 for "remove a lot of noise"
- "enhance": One-click overall enhancement: removes noise/hiss, rolls off low rumble, tightens levels, and normalizes loudness for a polished result. Params: strength (0.0 to 1.0, denoise amount, default 0.55). Use for "enhance this track", "make it sound polished/professional/better overall"

Respond with a JSON object containing:
1. "reply": A friendly message explaining what you'll do
2. "operation": The structured operation (or null if just responding to a question)
3. "operations": List of multiple operations if needed (optional, for complex edits)

Example response 1:
{"reply": "I'll add a deeper bass layer starting at 30 seconds.", "operation": {"operation": "eq", "frequency": 80, "gain": 6}}

Example response 2 (multi-operation):
{"reply": "I'll make the drums punchier by compressing and boosting the low-mids.", "operations": [{"operation": "compress", "threshold": -18, "ratio": 4}, {"operation": "eq", "frequency": 200, "gain": 3, "q_factor": 1.2}]}

Be helpful and conversational. If the request is unclear, ask for clarification.
If the user just wants to chat, respond normally with operation as null; do not include the literal text "operation": null if there is an actual edit to make.

Important: Only the currently loaded track exists. Do NOT emit a "layer" operation — there is no second audio file to mix in. If the user asks to add a beat, drums, or rhythm, use the "beat" operation. If they ask to mix in another file, kindly explain this single-track editor can't layer external files, and offer what's possible (beat layer, reverb, EQ, tempo, compression).

Current audio context:
- Duration: __DURATION__ seconds
- Sample rate: __SAMPLE_RATE__ Hz
- Channels: __CHANNELS__
- BPM: __BPM__
"""


def parse_audio_request(user_message: str, audio_context: dict, history: list | None = None) -> dict:
    duration = audio_context.get("duration", 0)
    sample_rate = audio_context.get("sample_rate", 44100)
    channels = audio_context.get("channels", 2)
    bpm = audio_context.get("bpm") or 0

    system_prompt = (
        AUDIO_OPERATIONS_PROMPT
        .replace("__DURATION__", f"{duration:.1f}")
        .replace("__SAMPLE_RATE__", str(sample_rate))
        .replace("__CHANNELS__", str(channels))
        .replace("__BPM__", str(bpm))
    )

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        messages.extend(history[-10:])

    messages.append({"role": "user", "content": user_message})

    max_tokens = 700
    error: Exception | None = None

    try:
        response = get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
    except Exception as exc:
        logger.exception("Groq API call failed")
        error = exc
        content = None

    result = try_parse_json(content)
    if result is not None:
        return normalize_result(result)

    retry = retry_plain_text(messages, max_tokens)
    if retry is not None:
        return normalize_result(retry)

    if error is not None:
        return api_error_reply(error, max_tokens)

    return {
        "reply": "Sorry, I couldn't understand that. Could you rephrase your request?",
        "operation": None,
        "operations": None
    }


def api_error_reply(exc: Exception, max_tokens: int | None = None) -> dict:
    name = type(exc).__name__
    msg = getattr(exc, "message", "") or str(exc)
    if "RateLimit" in name or "429" in str(getattr(exc, "status_code", "")) or "output tokens" in msg:
        return {
            "reply": "I'm a little busy right now — I hit my processing limit. Please wait a moment and try again.",
            "operation": None,
            "operations": None,
        }
    return {
        "reply": "Sorry, I ran into a problem reaching my AI backend. Please try again in a moment.",
        "operation": None,
        "operations": None,
    }


def _refers_to_layer(value) -> bool:
    if isinstance(value, dict) and isinstance(value.get("operation"), str):
        return value["operation"].strip() == "layer"
    if isinstance(value, str):
        return value.strip() == "layer"
    if isinstance(value, list):
        return any(_refers_to_layer(item) for item in value)
    return False


def normalize_result(result: dict) -> dict:
    if not isinstance(result, dict):
        result = {}
    if not isinstance(result.get("reply"), str) or not result["reply"].strip():
        result["reply"] = "Done!"

    operations = result.get("operations")

    if _refers_to_layer(result.get("operation")) or _refers_to_layer(operations):
        result["reply"] = (
            "I can only edit the currently loaded track — layering a separate "
            "audio file isn't supported. I can drop a synthesized beat layer "
            "on it instead, e.g. \"add a strong beat\"."
        )
        result["operation"] = None
        result["operations"] = None
        return result

    coerced = coerce_operation(result.get("operation"))
    if coerced is None and isinstance(operations, list):
        for op in operations:
            coerced = coerce_operation(op)
            if coerced is not None:
                break

    result["operation"] = coerced
    result["operations"] = None
    return result


def coerce_operation(operation) -> dict | None:
    if isinstance(operation, dict):
        if isinstance(operation.get("operation"), str):
            op = dict(operation)
            op["operation"] = op["operation"].strip()
            if op["operation"] in KNOWN_OPS:
                return op
            return None
        for key in KNOWN_OPS:
            if key in operation:
                params = operation[key]
                op = dict(params) if isinstance(params, dict) else {}
                op["operation"] = key
                return op
        return None
    if isinstance(operation, str) and operation.strip() in KNOWN_OPS:
        return {"operation": operation.strip()}
    return None


def try_parse_json(content):
    if not content:
        return None
    try:
        return json.loads(content)
    except Exception:
        logger.debug("Model output was not valid JSON: %r", content or "")
    if "```json" in content:
        clean = content.split("```json")[-1].split("```")[0].strip()
        try:
            return json.loads(clean)
        except Exception:
            logger.debug("JSON fence extract did not parse")
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            logger.debug("Extracted JSON fragment did not parse")
    return None


def retry_plain_text(messages, max_tokens=None):
    try:
        response = get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=max_tokens or 700,
        )
        content = response.choices[0].message.content
    except Exception:
        logger.exception("Groq retry failed")
        return None

    result = try_parse_json(content)
    if result is not None:
        return result

    if content:
        return {
            "reply": content,
            "operation": None,
            "operations": None
        }
    return None
