import os
import httpx


async def transcribe_voice(file_path: str) -> str:
    """Transcribe a voice message file using OpenAI Whisper API."""
    api_key = os.environ.get("OPENAI_API_KEY", "")

    with open(file_path, "rb") as f:
        audio_data = f.read()

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("voice.ogg", audio_data, "audio/ogg")},
            data={"model": "whisper-1", "language": "uk"}
        )
        response.raise_for_status()
        result = response.json()

    return result["text"]
