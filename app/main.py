from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.services.transcription_service import TranscriptionService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.transcription_service = TranscriptionService(settings)
    app.state.transcription_store = {}
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Audio Transcription Pipeline",
        description="Accepts audio files and returns speech-to-text transcriptions with timestamps.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
