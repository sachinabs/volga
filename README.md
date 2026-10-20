# Audio Transcription Pipeline

Small FastAPI service for turning audio into text. You POST a file, it runs it
through Faster-Whisper, and you get back the transcript plus start/end times for
each chunk of speech.

I put the quick start near the bottom since most of this file is me explaining
why things are built this way.

## Endpoints

- `POST /transcriptions` - upload an audio file. Returns language, duration,
  full text, and segments with timestamps.
- `GET /transcriptions/{id}` - get a transcription back, as long as this process
  is still running.
- `GET /health` - just tells you the server is up.

## Design decisions

### Why Faster-Whisper

I didn't want to call some cloud API, and I definitely wasn't going to train
anything. Faster-Whisper is Whisper's weights running on CTranslate2 instead of
PyTorch. Same results, a lot faster, and much lighter on RAM, so `base` actually
runs fine on my laptop.

The default is CPU (`DEVICE=cpu`, `COMPUTE_TYPE=int8`). If you have an NVIDIA
card, switch `DEVICE=cuda` and `COMPUTE_TYPE=float16` in the env file. No code
changes needed for that.

### Loading the model

Whisper weights take a few seconds to load and read from disk. So I load it once
in the FastAPI lifespan and keep it on the service instance. First request pays
the load, everything after reuses it. Loading per request would make every
upload pay that cost again, which is silly.

### Voice activity detection

I turned on `vad_filter=True`. Real recordings have a lot of dead air - pauses,
silence at the start, whatever. VAD finds and skips that before it gets decoded.
Faster, and it stops Whisper from hallucinating words over silence, which is a
real problem with quiet audio.

### Uploads go to disk, not into RAM

Files get read in 1 MB pieces and written straight to a temp file that
`tempfile.mkstemp` gives me. Nothing grows in memory, and I check the size as
bytes come in, so a huge upload gets killed partway instead of after I've
buffered the whole thing. That's the main reason long recordings don't blow up
memory.

### Validation

Extension check first, before reading any bytes. It's cheap and catches the
obvious mistakes. For "is this actually valid audio", I let the decoder decide -
if Faster-Whisper can't open it, it throws, and I turn that into a client error.
No point writing my own probe when PyAV already is one.

### Temp files always get cleaned up

`temporary_audio_file` is a context manager and the delete happens in a
`finally`. So it doesn't matter if transcription worked, failed, or a validation
error blew up inside the block - the file is gone either way. Only way I could
think of to be sure nothing gets left behind.

### Errors

The services raise their own errors: `AudioValidationError` (carries a status
code) and `TranscriptionError`. The route catches them and returns plain HTTP
messages. Nothing internal leaks out - no stack traces, no file paths. A
`TranscriptionError` just becomes a generic 422; I log the real reason but don't
send it back, so a broken file can't expose anything.

### Why it's synchronous

Transcription blocks the request. For an assessment, and for short dictation
clips, that's honestly fine and it's the simplest thing that works. Making it
async without a queue doesn't buy anything - you just move the blocking call to
a thread and still tie up a request. If it needs to scale later, see the
limitations section.

### The in-memory store

`GET /transcriptions/{id}` reads from a plain dict on `app.state`. It works and
returns real results, but only while the process is alive. I'm not pretending
it's a database because it isn't.

### PyAV, and FFmpeg being optional

Faster-Whisper decodes through PyAV, which ships FFmpeg's libraries inside it.
So WAV, MP3, M4A, FLAC, OGG etc. all work without installing FFmpeg system-wide.
I do use `ffprobe` for duration if it happens to be on PATH, because the
container usually knows the exact length and that's better than guessing. If
it's missing, I fall back to whatever Whisper reports. So FFmpeg is a
nice-to-have here, not a requirement.

### One file, one job

- `main.py` builds the app and wires up the lifespan.
- `api/routes.py` is HTTP only - entry points, status codes, error mapping.
- `core/config.py` reads the env.
- `schemas/transcription.py` is the request/response shape.
- `services/audio_service.py` handles files and validation.
- `services/transcription_service.py` owns the model and nothing else.

The important part is that everything goes through
`TranscriptionService.transcribe`. The rest of the app never touches Whisper
directly, which keeps the model quarantined in one place.

## Prerequisites

- Python 3.11+
- FFmpeg is optional (see the PyAV bit above)

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env
python run.py
```

API docs are at <http://localhost:8000/docs>.

## Config

| Variable | Default | What it does |
| --- | --- | --- |
| `MODEL_NAME` | `base` | Which Whisper model (`tiny`, `base`, `small`, `medium`, `large-v3`, ...) |
| `DEVICE` | `cpu` | `cpu` or `cuda` |
| `COMPUTE_TYPE` | `int8` | `int8` on CPU, `float16` on GPU |
| `MAX_UPLOAD_SIZE_MB` | `50` | Uploads bigger than this get rejected |
| `SUPPORTED_EXTENSIONS` | `.wav,.mp3,.m4a,.flac,.ogg` | Comma-separated list of allowed extensions |

## Uploading a file

```bash
curl -X POST http://localhost:8000/transcriptions \
  -F "file=@sample.wav"
```

You get something like:

```json
{
  "id": "8f2c1e4a-0b3d-4a5e-9f1c-2d6b7a8c9d0e",
  "language": "en",
  "duration": 5.6,
  "text": "The liver appears normal. No focal lesion is seen.",
  "segments": [
    { "start": 0.0, "end": 2.8, "text": "The liver appears normal." },
    { "start": 2.8, "end": 5.6, "text": "No focal lesion is seen." }
  ]
}
```

Times are in seconds from the start of the recording.

## Limitations

Things I knowingly left out, and how I'd handle them if this weren't an
assessment:

- **The store resets on restart.** Results live in memory. Put them in a real
  database keyed by the transcription ID if you need them to stick around.
- **Requests block until done.** Long audio means long requests. The fix is a
  queue: have `POST /transcriptions` save the file and return a job id, let a
  worker call the same `TranscriptionService.transcribe`, and have
  `GET /transcriptions/{id}` poll the result. That needs Celery/Redis or
  something similar, which is overkill here for now.
- **No manual chunking.** Whisper streams the audio and VAD skips silence, so
  long files are fine memory-wise. If you ever split files yourself, make the
  chunks overlap and add each chunk's start time to its segment timestamps, or
  you'll clip words at the seams.
- **No auth or rate limiting.** That belongs at the gateway in a real deploy.

## Downstream

This service only does transcription. If something else is going to process the
text - say, turning a doctor's dictation into a structured report - it should
take `text` and `segments` and do its own thing with them. What comes out here
is raw speech recognition, not a checked medical report, and it shouldn't be
treated like one.
