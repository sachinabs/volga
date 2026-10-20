from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    start: float = Field(..., ge=0.0, description="Segment start time in seconds")
    end: float = Field(..., ge=0.0, description="Segment end time in seconds")
    text: str = Field(..., description="Transcribed text for this segment")


class TranscriptionResponse(BaseModel):
    id: str = Field(..., description="Unique transcription identifier")
    language: str | None = Field(None, description="Detected language code")
    duration: float | None = Field(None, description="Audio duration in seconds")
    text: str = Field(..., description="Complete transcription text")
    segments: list[TranscriptionSegment] = Field(..., description="Timestamped segments")


class HealthResponse(BaseModel):
    status: str = "ok"
    message: str = "Audio transcription service is running"
