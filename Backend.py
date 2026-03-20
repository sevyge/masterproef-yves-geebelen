from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from typing import Any
from openai import AzureOpenAI
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
    upload_transcript_files
)

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
):
    logging.info(f"Received chat prompt: {transcript}")

    user_content: list[dict[str, str]] = [{"type": "input_text", "text": transcript}]
    # if screenshot:
    #    user_content.append({"type": "input_image", "image_url": screenshot})

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
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    background_tasks.add_task(
        upload_transcript_files,
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
