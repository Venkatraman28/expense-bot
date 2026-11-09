import io
import logging
from openai import OpenAI
from expense_bot.config import settings

logger = logging.getLogger(__name__)


class AudioClient:
    def __init__(self):
        if settings.ACTIVE_LLM_PROVIDER == "groq":
            logger.info(f"Initializing GROQ Audio model: {settings.GROQ_AUDIO_MODEL}")
            self.client = OpenAI(
                base_url=settings.GROQ_BASE_URL,
                api_key=settings.GROQ_API_KEY
            )
            self.model = settings.GROQ_AUDIO_MODEL
        else:
            logger.info(f"Initializing NVIDIA Audio model: {settings.NVIDIA_AUDIO_MODEL}")
            self.client = OpenAI(
                base_url=settings.NVIDIA_BASE_URL,
                api_key=settings.NVIDIA_API_KEY
            )
            self.model = settings.NVIDIA_AUDIO_MODEL


    def transcribe(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        """Transcribes in memory OGG/MP3/M4A audio bytes to text."""
        audio_buffer = io.BytesIO(audio_bytes)
        audio_buffer.name = filename

        transcription = self.client.audio.transcriptions.create(
            model=self.model,
            file=audio_buffer,
            response_format="text",
            language="en"
        )

        return transcription.strip()