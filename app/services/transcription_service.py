import logging
import uuid
from pathlib import Path

from faster_whisper import WhisperModel

from app.core.config import Settings
from app.schemas.transcription import TranscriptionResponse, TranscriptionSegment

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when transcription fails."""

    def __init__(self, message: str = "Transcription failed"):
        super().__init__(message)
        self.message = message


class TranscriptionService:
    """Loads the Whisper model once and reuses it across requests."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._model: WhisperModel | None = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            logger.info(
                "Loading Whisper model '%s' (device=%s, compute_type=%s)",
                self._settings.model_name,
                self._settings.device,
                self._settings.compute_type,
            )
            self._model = WhisperModel(
                self._settings.model_name,
                device=self._settings.device,
                compute_type=self._settings.compute_type,
            )
        return self._model

    def transcribe(self, audio_path: Path, duration: float | None = None) -> TranscriptionResponse:
        """
        Transcribe an audio file and return timestamped segments.

        Uses VAD to skip silence, which improves quality and speed on long recordings.
        """
        try:
            model = self._get_model()
            segments_iter, info = model.transcribe(
                str(audio_path),
                vad_filter=True,
            )

            segments = [
                TranscriptionSegment(
                    start=round(segment.start, 3),
                    end=round(segment.end, 3),
                    text=segment.text.strip(),
                )
                for segment in segments_iter
            ]

            full_text = " ".join(seg.text for seg in segments if seg.text)

            if duration is None:
                duration = getattr(info, "duration", None)

            return TranscriptionResponse(
                id=str(uuid.uuid4()),
                language=getattr(info, "language", None),
                duration=duration,
                text=full_text,
                segments=segments,
            )

        except Exception as exc:
            logger.exception("Transcription failed for %s", audio_path)
            raise TranscriptionError(f"Transcription failed: {exc}") from exc
