import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import UploadFile

from app.core.config import Settings


class AudioValidationError(Exception):
    """Raised when an uploaded audio file fails validation."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _check_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _get_audio_duration(audio_path: Path) -> float | None:
    """Get audio duration in seconds using ffprobe. Returns None if unavailable."""
    if not shutil.which("ffprobe"):
        return None

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        duration = data.get("format", {}).get("duration")
        return float(duration) if duration is not None else None
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError, TypeError):
        return None


@contextmanager
def temporary_audio_file(upload: UploadFile, settings: Settings) -> Iterator[Path]:
    """
    Stream an uploaded file to a temporary location on disk and yield its path.
    Cleans up the file (and any partial writes) when the context exits.
    """
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(upload.filename or "audio").suffix.lower()
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=suffix, dir=settings.temp_dir)
    tmp_path = Path(tmp_path_str)

    try:
        with open(tmp_fd, "wb") as tmp_file:
            total_bytes = 0
            while True:
                chunk = upload.file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_size_bytes:
                    raise AudioValidationError(
                        f"File exceeds maximum allowed size of {settings.max_upload_size_mb} MB",
                        status_code=413,
                    )
                tmp_file.write(chunk)

        if total_bytes == 0:
            raise AudioValidationError("Uploaded file is empty", status_code=400)

        yield tmp_path
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def validate_audio_upload(upload: UploadFile, settings: Settings) -> None:
    """Validate the uploaded file's extension before any processing."""
    if not upload.filename:
        raise AudioValidationError("No filename provided", status_code=400)

    suffix = Path(upload.filename).suffix.lower()
    if not suffix:
        raise AudioValidationError("File has no extension", status_code=400)

    if suffix not in settings.allowed_extensions:
        raise AudioValidationError(
            f"Unsupported file type '{suffix}'. Allowed types: {', '.join(sorted(settings.allowed_extensions))}",
            status_code=415,
        )
