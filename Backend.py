from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from typing import Any
from openai import AzureOpenAI
from datetime import datetime
import threading
import tempfile
import time
import os
import logging
from dotenv import load_dotenv
from schemas.chat import ChatClassification
from utils.signature_utils import (
    decode_signature_data,
    stamp_signature_on_page_two,
)
from services.google_drive_service import (
    get_or_create_participant_folder,
    get_next_participant_id,
    upload_to_google_drive,
    upload_transcript_files,
)
from prompts.system_prompt import SYSTEM_PROMPT

load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
TRANSCRIBE_DEPLOYMENT = os.getenv(
    "TRANSCRIBE_DEPLOYMENT", os.getenv("WHISPER_DEPLOYMENT", "gpt-4o-transcribe")
)
CHAT_DEPLOYMENT = os.getenv("CHAT_DEPLOYMENT", "")
TTS_DEPLOYMENT = os.getenv("TTS_DEPLOYMENT", "")

ALLOWED_ORIGINS = [
    os.getenv("ALLOWED_ORIGINS_LOCAL", ""),
    os.getenv("ALLOWED_ORIGINS_HOSTED", ""),
]

app = FastAPI(
    description="Masterproef Yves Geebelen - Backend API",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
)

# In-memory transcript log per participant
transcript_log: dict[str, list[dict[str, Any]]] = {}
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
SILENCE_GAP_THRESHOLD_SECONDS = float("5.00")

# Per-participant lock to avoid concurrent transcript file uploads.
participant_upload_locks: dict[str, Any] = {}
participant_upload_locks_guard = threading.Lock()


def get_participant_upload_lock(participant_id: str):
    with participant_upload_locks_guard:
        if participant_id not in participant_upload_locks:
            participant_upload_locks[participant_id] = threading.Lock()
        return participant_upload_locks[participant_id]


def add_silence_segment_if_needed(
    participant_entries: list[dict[str, Any]],
    start_dt: datetime,
    transcript_text: str | None = None,
):
    if not participant_entries:
        return

    previous_end_time = participant_entries[-1].get("end_time")
    if not previous_end_time:
        return

    try:
        previous_end_dt = datetime.strptime(previous_end_time, TIMESTAMP_FORMAT)
    except ValueError:
        return

    gap_seconds = (start_dt - previous_end_dt).total_seconds()
    if gap_seconds < SILENCE_GAP_THRESHOLD_SECONDS:
        return

    participant_entries.append(
        {
            "entry_number": len(participant_entries) + 1,
            "transcript": transcript_text or f"**{gap_seconds:.2f}s stilte**",
            "labels": "NONE",
            "confidence_score": 1.0,
            "start_time": previous_end_dt.strftime(TIMESTAMP_FORMAT),
            "end_time": start_dt.strftime(TIMESTAMP_FORMAT),
        }
    )


def upload_transcript_files_with_lock(participant_id: str, participant_log: list):
    lock = get_participant_upload_lock(participant_id)
    with lock:
        upload_transcript_files(participant_id, participant_log)


@app.get("/")
async def root():
    return {"message": "Success"}


# Informed consent endpoint
@app.post("/consent")
def consent(
    participant_id: str = Form(None),
    signature_data: str = Form(None),
):
    if not participant_id:
        participant_id = get_next_participant_id()
        logging.info(f"Generated new participant ID: {participant_id}")
    else:
        logging.info(f"Received consent from participant: {participant_id}")

    if not signature_data:
        raise HTTPException(
            status_code=400,
            detail="Missing required field: signature_data is required.",
        )

    signed_at_iso = time.strftime("%Y-%m-%d %H:%M:%S")

    try:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        signed_filename = f"Consent_signed_{participant_id}_{timestamp}.pdf"

        participant_folder = get_or_create_participant_folder(participant_id)

        template_path = "toestemmingsformulier.pdf"
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Consent template not found at {template_path}")
        signature_png = decode_signature_data(signature_data)
        signed_pdf_content = stamp_signature_on_page_two(
            template_path=template_path,
            signature_png=signature_png,
            signed_at_iso=signed_at_iso,
            participant_id=participant_id,
        )

        signed_file = upload_to_google_drive(
            file_stream=signed_pdf_content,
            filename=signed_filename,
            mimetype="application/pdf",
            folder_id=participant_folder,
        )

        logging.info(
            "Uploaded signed consent PDF (%s) for participant %s",
            signed_file.get("file_id"),
            participant_id,
        )

    except Exception as e:
        logging.error(f"Error uploading consent PDF to Google Drive: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to generate or upload signed consent form."
        )

    return {
        "message": f"Consent received for participant {participant_id}",
        "participant_id": participant_id,
    }


# Upload video endpoint
@app.post("/upload-video")
def upload_video(video: UploadFile = File(...), participant_id: str = Form(...)):
    # input validation
    if video.content_type not in ["video/webm", "video/mp4"]:
        return {"error": "Invalid file type. Only .webm and .mp4 are allowed."}

    # Log upload
    logging.info(f"Received video upload from participant: {participant_id}")

    try:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"{participant_id}-recording-{timestamp}.webm"

        participant_folder = get_or_create_participant_folder(participant_id)

        result = upload_to_google_drive(
            file_stream=video.file,
            filename=filename,
            mimetype="video/webm",
            folder_id=participant_folder,
        )

        return {"message": "Video uploaded to Google Drive successfully", **result}
    except FileNotFoundError as e:
        return {"error": str(e)}
    except Exception as e:
        logging.error(f"Error uploading video: {e}")
        return {"error": str(e)}


@app.post("/transcribe")
def transcribe(audio: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
        temp_file.write(audio.file.read())
        temp_file_path = temp_file.name

    try:
        logging.info(
            f"Speech to text processing started at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        with open(temp_file_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model=TRANSCRIBE_DEPLOYMENT, file=f, language="nl"
            )
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        logging.info(f"Transcription finished at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return {"transcription": result.text}
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        logging.error(f"Error during transcription: {e}")
        raise e


@app.post("/chat")
def chat(
    background_tasks: BackgroundTasks,
    transcript: str = Form(...),
    screenshot: str = Form(None),
    previous_response_id: str = Form(None),
    participant_id: str = Form(...),
    start_time: str = Form(None),
    end_time: str = Form(None),
    skip_silence_entry: bool = Form(False),
):
    logging.info(f"Received chat prompt: {transcript}")

    user_content: list[dict[str, str]] = [{"type": "input_text", "text": transcript}]
    # if screenshot:
    #    user_content.append({"type": "input_image", "image_url": screenshot})

    system_prompt = SYSTEM_PROMPT

    response = client.responses.parse(
        model=CHAT_DEPLOYMENT,
        instructions=system_prompt,
        # tools=[
        #     {"type": "file_search", "vector_store_ids": ["vs_Nby42pG9UlWm64WxQmIPBHtW"]}
        # ],
        input=[
            {
                "role": "user",
                "content": user_content,
            }  # type: ignore
        ],
        text_format=ChatClassification,
        previous_response_id=previous_response_id,
    )

    parsed = response.output_parsed

    if parsed is None:
        logging.error("Model returned no parsed output (possible refusal).")
        return {"error": "No structured output returned by the model."}

    labels = parsed.labels
    confidence_score = parsed.confidence_score

    if not start_time or not end_time:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: start_time and end_time are required.",
        )

    start_time_dt = datetime.fromisoformat(
        start_time.strip().replace("Z", "+00:00")
    ).replace(tzinfo=None)

    end_time_dt = datetime.fromisoformat(
        end_time.strip().replace("Z", "+00:00")
    ).replace(tzinfo=None)

    start_time_value = start_time_dt.strftime(TIMESTAMP_FORMAT)
    end_time_value = end_time_dt.strftime(TIMESTAMP_FORMAT)

    logging.info(f"Chat response: {labels} (confidence: {confidence_score})")

    # Create an empty log for this participant if it doesn't exist yet
    if participant_id not in transcript_log:
        transcript_log[participant_id] = []

    if skip_silence_entry:
        add_silence_segment_if_needed(
            transcript_log[participant_id], start_time_dt, "**Opname hervat na pauze**"
        )
    else:
        add_silence_segment_if_needed(transcript_log[participant_id], start_time_dt)

    entry_number = len(transcript_log[participant_id]) + 1
    labels_str = ", ".join(labels) if labels else "None"

    # Add the transcript with the knowledge structure classification to the log
    transcript_log[participant_id].append(
        {
            "entry_number": entry_number,
            "transcript": transcript,
            "labels": labels_str,
            "confidence_score": confidence_score,
            "start_time": start_time_value,
            "end_time": end_time_value,
        }
    )

    background_tasks.add_task(
        upload_transcript_files_with_lock,
        participant_id,
        list(transcript_log[participant_id]),
    )

    return {"response": labels_str, "response_id": response.id}


@app.post("/tts-stream")
def tts_stream(text: str = Form(...)):
    try:
        logging.info(f"TTS streaming started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        response = client.audio.speech.create(
            model=TTS_DEPLOYMENT, voice="nova", input=text, response_format="wav"
        )
        logging.info(f"TTS streaming finished at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return StreamingResponse(
            response.iter_bytes(),
            media_type="audio/wav",
            headers={
                "Accept-Ranges": "bytes",
            },
        )
    except Exception as e:
        logging.error(f"TTS streaming error: {e}")
        return Response(content="", status_code=500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
