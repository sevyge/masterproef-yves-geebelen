from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from typing import Any, Literal
from openai import AzureOpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO
from pydantic import BaseModel
import tempfile
import time
import os
import logging
import csv
import io
from dotenv import load_dotenv

load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
WHISPER_DEPLOYMENT = os.getenv("WHISPER_DEPLOYMENT", "")
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
    allow_methods=["*"],
    allow_headers=["*"],
)

client = AzureOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
)

# In-memory transcript log per participant
transcript_log: dict[str, list[dict[str, Any]]] = {}

# Google Drive setup
SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = "service_account.json"

def get_drive_service():
    """Create a new instance of the Drive API service."""
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    return None

def get_or_create_participant_folder(participant_id: str) -> str:
    """Return the Drive folder ID for a participant, creating it if needed."""
    service = get_drive_service()
    if service is None:
        raise FileNotFoundError("Service account file not found.")

    parent_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not parent_id:
        raise ValueError("GOOGLE_DRIVE_FOLDER_ID environment variable is not set.")

    # Search for an existing folder with this name inside the parent
    query = (
        f"name = '{participant_id}' and '{parent_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )

    results = (
        service.files()
        .list(
            q=query,
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    # Create the folder
    folder_metadata = {
        "name": participant_id,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }

    folder = (
        service.files()
        .create(body=folder_metadata, fields="id", supportsAllDrives=True)
        .execute()
    )
    logging.info(f"Created Drive folder '{participant_id}' with ID: {folder['id']}")
    return folder["id"]


def get_next_participant_id() -> str:
    """Determine the next participant ID by counting existing folders."""
    service = get_drive_service()
    if service is None:
        return "1"  # Fallback if no Drive access

    parent_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not parent_id:
        return "1"

    query = (
        f"'{parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )

    # Fetch list of folders and use count + 1 as the next participant ID
    results = (
        service.files()
        .list(
            q=query,
            pageSize=1000,
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )

    folders = results.get("files", [])
    return str(len(folders) + 1)


def upload_to_google_drive(
    file_stream,
    filename: str,
    mimetype: str,
    folder_id: str | None = None,
    overwrite: bool = False,
) -> dict[str, str]:
    """Upload a file to Google Drive and return its id.

    Args:
        file_stream: A file-like (readable) object or raw bytes.
        filename:    The name the file will have on Drive.
        mimetype:    MIME type of the file (e.g. "video/webm", "text/markdown").
        folder_id:   Optional Drive folder ID. Falls back to GOOGLE_DRIVE_FOLDER_ID env var.
        overwrite:   If True, search for an existing file with the same name in the folder and overwrite it.

    Returns:
        dict with key "file_id".

    Raises:
        FileNotFoundError: If the service-account JSON is missing.
        Exception:         Any Google API error.
    """
    service = get_drive_service()
    if service is None:
        raise FileNotFoundError("Service account file not found.")

    # Accept raw bytes as well as file-like objects
    if isinstance(file_stream, (bytes, bytearray)):
        file_stream = BytesIO(file_stream)

    folder = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    file_metadata: dict[str, Any] = {"name": filename}
    if folder:
        file_metadata["parents"] = [folder]

    # Set chunk size to 5MB for resilient chunked uploads
    media = MediaIoBaseUpload(file_stream, mimetype=mimetype, resumable=True, chunksize=5 * 1024 * 1024)

    existing_file_id = None
    if overwrite and folder:
        query = f"name = '{filename}' and '{folder}' in parents and trashed = false"
        results = (
            service.files()
            .list(
                q=query,
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = results.get("files", [])
        if files:
            existing_file_id = files[0]["id"]

    if existing_file_id:
        request = (
            service.files()
            .update(
                fileId=existing_file_id,
                media_body=media,
                supportsAllDrives=True,
            )
        )
    else:
        request = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
        )

    # Execute resumable upload in chunks
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logging.info(f"Uploaded {int(status.progress() * 100)}% of {filename}")

    return {"file_id": response.get("id")}


@app.get("/")
async def root():
    return {"message": "Success"}

# Informed consent endpoint
@app.post("/consent")
def consent(participant_id: str = Form(None)):
    if not participant_id:
        participant_id = get_next_participant_id()
        logging.info(f"Generated new participant ID: {participant_id}")
    else:
        logging.info(f"Received consent from participant: {participant_id}")

    try:
        filename = f"Consent_{participant_id}_{time.strftime('%Y%m%d-%H%M%S')}.pdf"

        participant_folder = get_or_create_participant_folder(participant_id)

        if os.path.exists("toestemmingsformulier.pdf"):
            with open("toestemmingsformulier.pdf", "rb") as pdf_file:
                file_id = upload_to_google_drive(
                    file_stream=pdf_file,
                    filename=filename,
                    mimetype="application/pdf",
                    folder_id=participant_folder,
                )
                logging.info(
                    f"Uploaded consent PDF to Google Drive with file ID: {file_id['file_id']}"
                )
        else:
            logging.error("Consent PDF not found.")

    except Exception as e:
        logging.error(f"Error uploading consent PDF to Google Drive: {str(e)}")

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
                model=WHISPER_DEPLOYMENT, file=f, language="nl"
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


class ChatClassification(BaseModel):
    labels: list[Literal["DK", "PK", "CK", "DOM", "NONE"]]
    confidence_score: float


def upload_transcript_files_background(participant_id: str, participant_log: list):
    try:
        # Generate CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["entry_number", "timestamp", "transcript", "labels", "confidence_score"],
            delimiter=";"
        )
        writer.writeheader()
        writer.writerows(participant_log)
        csv_content = output.getvalue()

        participant_folder = get_or_create_participant_folder(participant_id)
        upload_to_google_drive(
            file_stream=csv_content.encode("utf-8-sig"),
            filename=f"transcript_met_kennisstructuur_{participant_id}.csv",
            mimetype="text/csv",
            folder_id=participant_folder,
            overwrite=True,
        )
        logging.info(
            f"Transcript CSV updated for participant {participant_id}"
        )

        # Create full transcript
        full_transcript_text = "\n".join([f"[{entry['timestamp']}] {entry['transcript']}" for entry in participant_log])
        upload_to_google_drive(
            file_stream=full_transcript_text.encode("utf-8"),
            filename=f"full_transcript_{participant_id}.txt",
            mimetype="text/plain",
            folder_id=participant_folder,
            overwrite=True,
        )
        logging.info(
            f"Full transcript TXT updated for participant {participant_id}"
        )
    except Exception as e:
        logging.error(f"Error uploading transcript files: {e}")


@app.post("/chat")
def chat(
    background_tasks: BackgroundTasks,
    transcript: str = Form(...),
    screenshot: str = Form(None),
    previous_response_id: str = Form(None),
    participant_id: str = Form(...),
):
    logging.info(f"Received chat prompt: {transcript}")

    user_content: list[dict[str, str]] = [{"type": "input_text", "text": transcript}]
    if screenshot:
        user_content.append({"type": "input_image", "image_url": screenshot})

    system_prompt = """You are an expert cognitive scientist and qualitative researcher specializing in analyzing 'think-aloud' protocols within process mining. As an objective academic coder for an observational study, your task is to classify short transcript segments (combined with an optional screenshot) into one or more of the following labels: ['DK', 'PK', 'CK', 'DOM', 'NONE'].

    Evaluation Hierarchy & Definitions:
    Evaluate the transcript step-by-step to assign your labels. Multiple labels are allowed ONLY if distinct cognitive structures are present.
    1. Check for Domain Knowledge ('DOM'): Does the analyst use specific terminology, theories, or concepts distinct to the process mining domain? -> Add 'DOM'.
    2. Check for Conditional Knowledge ('CK'): Is the analyst formulating a hypothesis, strategy, or explaining the defining *reason/if-then* correlation behind an action? -> Add 'CK'.
    3. Check for Procedural Knowledge ('PK'): Is the analyst strictly describing *how* they are interacting with the software (e.g., clicking, basic UI navigation) WITHOUT stating a hypothesis? -> Add 'PK'.
    4. Check for Declarative Knowledge ('DK'): Is the analyst merely stating general facts, static observations ("what"), or reading data off the screen? -> Add 'DK'.
    5. Check for Non-Substantive ('NONE'): Is the utterance purely filler ("Uhm", "Let me see", "Oops") or lacks any recognizable cognitive process mining structure? -> Assign 'NONE'.

    Context Usage Instructions:
    - The input transcript is in Dutch.
    - Use the screenshot solely to resolve ambiguous verbal references (e.g., understanding *where* the analyst clicked). The final classification must be anchored to the verbal utterance.
    - IMPORTANT: The 'labels' list cannot be empty. If steps 1-4 yield no labels, or if the transcript is purely filler, you MUST return exactly ['NONE'].
    - Do not hallucinate meaning. If you are highly uncertain, prioritize ['NONE'] and output a low confidence score.
    - Provide a 'confidence_score' between 0.0 and 1.0."""

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

    logging.info(f"Chat response: {labels} (confidence: {confidence_score})")

    # Create an empty log for this participant if it doesn't exist yet
    if participant_id not in transcript_log:
        transcript_log[participant_id] = []

    entry_number = len(transcript_log[participant_id]) + 1
    labels_str = ", ".join(labels) if labels else "None"

    # Add the transcript with the knowledge structure classification to the log
    transcript_log[participant_id].append(
        {
            "entry_number": entry_number,
            "transcript": transcript,
            "labels": labels_str,
            "confidence_score": confidence_score,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }
    )

    background_tasks.add_task(
        upload_transcript_files_background,
        participant_id,
        list(transcript_log[participant_id])
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
