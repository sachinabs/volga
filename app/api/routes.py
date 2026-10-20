import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.core.config import Settings, get_settings
from app.schemas.transcription import HealthResponse, TranscriptionResponse
from app.services.audio_service import (
    AudioValidationError,
    temporary_audio_file,
    validate_audio_upload,
    _get_audio_duration,
)
from app.services.transcription_service import TranscriptionError, TranscriptionService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_transcription_service(request: Request) -> TranscriptionService:
    return request.app.state.transcription_service


def get_transcription_store(request: Request) -> dict[str, TranscriptionResponse]:
    return request.app.state.transcription_store


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse()


@router.post("/transcriptions", response_model=TranscriptionResponse, status_code=201)
def create_transcription(
    file: UploadFile = File(...),
    service: TranscriptionService = Depends(get_transcription_service),
    store: dict[str, TranscriptionResponse] = Depends(get_transcription_store),
    settings: Settings = Depends(get_settings),
) -> TranscriptionResponse:
    try:
        validate_audio_upload(file, settings)
        with temporary_audio_file(file, settings) as audio_path:
            duration = _get_audio_duration(audio_path)
            result = service.transcribe(audio_path, duration=duration)
    except AudioValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except TranscriptionError as exc:
        logger.warning("Transcription failed: %s", exc.message)
        raise HTTPException(status_code=422, detail="Could not transcribe the provided audio file") from exc

    store[result.id] = result
    return result


@router.get("/transcriptions/{transcription_id}", response_model=TranscriptionResponse)
def get_transcription(
    transcription_id: str,
    store: dict[str, TranscriptionResponse] = Depends(get_transcription_store),
) -> TranscriptionResponse:
    result = store.get(transcription_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return result
