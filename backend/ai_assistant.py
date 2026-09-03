import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")

AUDIO_OPERATIONS_PROMPT = """You are an AI audio editing assistant for a music editor called Dhwani.

You convert natural language requests into structured audio operations. You do NOT write code.

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
- "layer": Add another audio as layer. Params: file_id (of the layer), gain (dB)

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

Current audio context:
- Duration: __DURATION__ seconds
- Sample rate: __SAMPLE_RATE__ Hz
- Channels: __CHANNELS__
- BPM: __BPM__
"""


def parse_audio_request(user_message: str, audio_context: dict, history: list = None) -> dict:
    duration = audio_context.get("duration", 0)
    sample_rate = audio_context.get("sample_rate", 44100)
    channels = audio_context.get("channels", 2)
    bpm = audio_context.get("bpm", 0)

    system_prompt = (
        AUDIO_OPERATIONS_PROMPT
        .replace("__DURATION__", f"{duration:.1f}")
        .replace("__SAMPLE_RATE__", str(sample_rate))
        .replace("__CHANNELS__", str(channels))
        .replace("__BPM__", str(bpm))
    )

    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for msg in history[-10:]:
            messages.append(msg)

    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1200,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        if isinstance(result.get("operation"), dict) and "operation" in result["operation"]:
            pass
        return result
    except Exception as e:
        return {
            "reply": f"Sorry, I encountered an error: {str(e)}",
            "operation": None,
            "operations": None
        }
