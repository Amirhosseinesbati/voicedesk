"""Live 24 kHz PCM STT/TTS adapters. Audio frames are never checkpointed or retained."""

import base64
import binascii
import json
from collections.abc import AsyncIterator
from urllib.parse import quote

from openai import AsyncOpenAI
from websockets.asyncio.client import connect

from voicedesk.config import get_settings


class AudioProviderError(RuntimeError):
    pass


class OpenAITranscriber:
    def __init__(self):
        self.settings = get_settings()
        if not self.settings.openai_api_key:
            raise AudioProviderError("OPENAI_API_KEY is missing.")
        self.connection = None

    async def __aenter__(self):
        url = f"wss://api.openai.com/v1/realtime?model={quote(self.settings.openai_stt_model)}"
        self.connection = await connect(url, additional_headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                                        open_timeout=10, max_size=2_000_000)
        await self.connection.send(json.dumps({"type": "session.update", "session": {
            "type": "transcription", "audio": {"input": {"format": {"type": "audio/pcm", "rate": 24000},
                                                  "transcription": {"model": self.settings.openai_stt_model},
                                                  "turn_detection": None}}}}))
        return self

    async def __aexit__(self, *_):
        if self.connection:
            await self.connection.close()

    async def append(self, pcm_base64: str):
        if len(pcm_base64) > 120_000:
            raise AudioProviderError("Audio chunk exceeds the 64 KiB limit.")
        try:
            raw = base64.b64decode(pcm_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise AudioProviderError("Audio chunk must be base64 PCM16.") from exc
        if not raw or len(raw) > 65_536 or len(raw) % 2:
            raise AudioProviderError("Audio chunk must be non-empty 16-bit PCM, up to 64 KiB.")
        await self.connection.send(json.dumps({"type": "input_audio_buffer.append", "audio": pcm_base64}))

    async def commit(self):
        await self.connection.send(json.dumps({"type": "input_audio_buffer.commit"}))

    async def clear(self):
        await self.connection.send(json.dumps({"type": "input_audio_buffer.clear"}))

    async def events(self) -> AsyncIterator[dict]:
        async for message in self.connection:
            yield json.loads(message)


class OpenAITTS:
    def __init__(self):
        settings = get_settings()
        if not settings.openai_api_key:
            raise AudioProviderError("OPENAI_API_KEY is missing.")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=20.0, max_retries=1)
        self.model = settings.openai_tts_model
        self.voice = settings.openai_tts_voice

    async def chunks(self, text: str) -> AsyncIterator[str]:
        async with self.client.audio.speech.with_streaming_response.create(
            model=self.model, voice=self.voice, input=text,
            instructions="Speak clearly and calmly as an AI-generated home services receptionist.",
            response_format="pcm",
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=4096):
                if chunk:
                    yield base64.b64encode(chunk).decode("ascii")
