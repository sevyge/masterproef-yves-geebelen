from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from typing import Any
from openai import AzureOpenAI
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO
import tempfile
import time
import json
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Logging
logging.basicConfig(
    filename='app_activity.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
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

# Google Drive setup
SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = "service_account.json"

if os.path.exists(SERVICE_ACCOUNT_FILE):
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("drive", "v3", credentials=creds)
else:
    service = None


def upload_to_google_drive(
    file_stream,
    filename: str,
    mimetype: str,
    folder_id: str | None = None,
) -> dict[str, str]:
    """Upload a file to Google Drive and return its id.

    Args:
        file_stream: A file-like (readable) object or raw bytes.
        filename:    The name the file will have on Drive.
        mimetype:    MIME type of the file (e.g. "video/webm", "text/markdown").
        folder_id:   Optional Drive folder ID. Falls back to GOOGLE_DRIVE_FOLDER_ID env var.

    Returns:
        dict with key "file_id".

    Raises:
        FileNotFoundError: If the service-account JSON is missing.
        Exception:         Any Google API error.
    """
    if service is None:
        raise FileNotFoundError(
            "Service account file not found."
        )

    # Accept raw bytes as well as file-like objects
    if isinstance(file_stream, (bytes, bytearray)):
        file_stream = BytesIO(file_stream)

    folder = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    file_metadata: dict[str, Any] = {"name": filename}
    if folder:
        file_metadata["parents"] = [folder]

    media = MediaIoBaseUpload(file_stream, mimetype=mimetype, resumable=True)

    file = (
        service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )

    return {"file_id": file.get("id")}


@app.get("/")
async def root():
    return {"message": "Success"}

# Informed consent endpoint
@app.post("/consent")
async def consent(participant_id: str = Form(...)):
    logging.info(f"Received consent from participant: {participant_id}")
    return {"message": f"Consent received for participant {participant_id}"}

# Upload video endpoint
@app.post("/upload-video")
async def upload_video(video: UploadFile = File(...),
                       participant_id: str = Form(None)):
    # input validation
    if video.content_type not in ["video/webm", "video/mp4"]:
        return {"error": "Invalid file type. Only .webm and .mp4 are allowed."}

    # Log upload
    if participant_id:
        logging.info(f"Received video upload from participant: {participant_id}")
    else:
        logging.info("Received video upload from unknown participant")

    try:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        prefix = f"{participant_id}-" if participant_id else ""
        filename = f"{prefix}recording-{timestamp}.webm"

        result = upload_to_google_drive(
            file_stream=video.file,
            filename=filename,
            mimetype="video/webm",
        )

        return {"message": "Video uploaded to Google Drive successfully", **result}
    except FileNotFoundError as e:
        return {"error": str(e)}
    except Exception as e:
        logging.error(f"Error uploading video: {e}")
        return {"error": str(e)}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
        temp_file.write(await audio.read())
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


@app.post("/chat")
async def chat(
    prompt: str = Form(...),
    screenshot: str = Form(None),
    previous_response_id: str = Form(None),
):
    logging.info(f"Received chat prompt: {prompt}")
    response = client.responses.create(
        model=CHAT_DEPLOYMENT,
        instructions="Geef altijd een kort antwoord in het Nederlands van maximaal 2 zinnen.",
        tools=[
            {"type": "file_search", "vector_store_ids": ["vs_Nby42pG9UlWm64WxQmIPBHtW"]}
        ],
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": screenshot,
                    },
                ],
            }  # type: ignore
        ],
        previous_response_id=previous_response_id,
    )

    response_json = json.loads(response.model_dump_json())
    try:
        text_content = response_json["output"][1]["content"][0]["text"]
    except (KeyError, IndexError):
        text_content = response_json["output"][0]["content"][0]["text"]

    return {"response": text_content, "response_id": response_json["id"]}


@app.post("/tts-stream")
async def tts_stream(text: str = Form(...)):
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
