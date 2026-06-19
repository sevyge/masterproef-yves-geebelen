from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Any
from openai import AzureOpenAI
from groq import Groq
from datetime import datetime
import tempfile
import time
import os
import logging
import json
from dotenv import load_dotenv
from schemas.chat import ChatClassification
from utils.signature_utils import (
    decode_signature_data,
    stamp_signature_on_page_two,
)
import base64
from services.storage_service import (
    get_or_create_participant_folder,
    get_next_participant_id,
    upload_to_google_drive,
    upload_vragenlijst_csv,
    upload_screenshot,
    get_or_create_subfolder,
    get_participants_list,
    get_participant_transcript,
    get_participant_screenshot,
    upload_transcript_files,
    create_original_transcript_backup,
)
from services.transcript_service import (
    add_silence_segment_if_needed,
    upload_transcript_files_with_lock,
    TIMESTAMP_FORMAT,
)
from prompts.system_prompt import SYSTEM_PROMPT
from post_hoc_classification import classify_participant

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
TRANSCRIBE_DEPLOYMENT = os.getenv("TRANSCRIBE_DEPLOYMENT", "whisper-1")
CHAT_DEPLOYMENT = os.getenv("CHAT_DEPLOYMENT", "")
REALTIME_CLASSIFICATION = os.getenv("REALTIME_CLASSIFICATION", "false").lower() == "true"

raw_origins = [
    os.getenv("ALLOWED_ORIGIN_LOCAL"),
    os.getenv("ALLOWED_ORIGIN_DOCKER"),
    os.getenv("ALLOWED_ORIGIN_DOCKER_2"),
    os.getenv("ALLOWED_ORIGIN_HOSTED"),
]

ALLOWED_ORIGINS = []
for origin in raw_origins:
    if origin:
        cleaned = origin.strip().strip("'\"").rstrip("/")
        if cleaned:
            ALLOWED_ORIGINS.append(cleaned)

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

azure_client = None
if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT:
    try:
        azure_client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )
        logging.info("AzureOpenAI client initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize AzureOpenAI client: {e}")

groq_client = None
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        logging.info("Groq client initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize Groq client: {e}")

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
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        signed_filename = f"toestemmingsformulier_ondertekend_{participant_id}_{timestamp}.pdf"

        participant_folder = get_or_create_participant_folder(participant_id)
        get_or_create_subfolder(participant_folder, "Screenshots")

        template_path = os.path.join(BASE_DIR, "Document 5 - toestemmingsformulier voor de deelnemer.pdf")
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


# Vragenlijst endpoint
@app.post("/vragenlijst")
def submit_vragenlijst(
    participant_id: str = Form(...),
    ervaring: str = Form(default="Niet gedefinieerd"),
    epa_project: str = Form(default="Niet gedefinieerd"),
    tools: list[str] = Form(default=[]),
    rol: str = Form(default="Niet gedefinieerd"),
):
    logging.info(f"Received vragenlijst from participant: {participant_id}")

    try:
        upload_vragenlijst_csv(participant_id, ervaring, epa_project, tools, rol)
    except Exception as e:
        logging.error(f"Error saving vragenlijst to Google Drive: {e}")
        raise HTTPException(status_code=500, detail="Failed to save questionnaire.")

    return {
        "message": f"Vragenlijst saved for participant {participant_id}",
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
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"schermopname_{participant_id}_{timestamp}.webm"

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
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
            temp_file.write(audio.file.read())
            temp_file_path = temp_file.name

        context_prompt = (
            "Dit is een think-aloud sessie van een procesdata-analyse. "
            "Termen gerelateerd aan het verkeersboeteproces en process mining zijn: "
            "Disco, ProM, Create Fine, Send Fine, Insert Fine Notification, "
            "Add Penalty, Send for Credit Collection, Payment, Appeal to Judge, Prefecture, "
            "verjaringstermijn, betaaltermijn, seponering, boeteverhoging, incassobureau."
        )

        # Groq
        if groq_client:
            try:
                logging.info(
                    f"Speech to text processing with Groq (whisper-large-v3) started at {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                with open(temp_file_path, "rb") as f:
                    result = groq_client.audio.transcriptions.create(
                        file=(os.path.basename(temp_file_path), f.read()),
                        model="whisper-large-v3",
                        language="nl",
                        temperature=0,
                        prompt=context_prompt,
                    )
                logging.info(f"Transcription finished at {time.strftime('%Y-%m-%d %H:%M:%S')}")
                return {"transcription": result.text, "provider": "Groq (v3)"}
            except Exception as e_v3:
                logging.error(f"Error during Groq whisper-large-v3 transcription: {e_v3}")
                logging.info("Attempting backup with Groq (whisper-large-v3-turbo)...")
                try:
                    with open(temp_file_path, "rb") as f:
                        result = groq_client.audio.transcriptions.create(
                            file=(os.path.basename(temp_file_path), f.read()),
                            model="whisper-large-v3-turbo",
                            language="nl",
                            temperature=0,
                            prompt=context_prompt,
                        )
                    logging.info(f"Transcription finished at {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    return {"transcription": result.text, "provider": "Groq (Turbo)"}
                except Exception as e_turbo:
                    logging.error(f"Error during Groq whisper-large-v3-turbo transcription: {e_turbo}")
                    logging.info("Attempting fallback to Azure transcription...")

        # Fallback to Azure if Groq fails
        if not azure_client:
            return {"transcription": "Fout met Azure API credentials of Groq API credentials"}

        try:
            logging.info(
                f"Speech to text processing with Azure started at {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            with open(temp_file_path, "rb") as f:
                result = azure_client.audio.transcriptions.create(
                    file=f,
                    model=TRANSCRIBE_DEPLOYMENT,
                    language="nl",
                    temperature=0,
                    prompt=context_prompt,
                )
            logging.info(f"Transcription finished at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            return {"transcription": result.text, "provider": "Azure"}
        except Exception as e:
            logging.error(f"Error during Azure transcription: {e}")
            raise e

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as e_cleanup:
                logging.error(f"Failed to delete temporary file {temp_file_path}: {e_cleanup}")


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

    llm_annotations = []
    response_id = ""

    if REALTIME_CLASSIFICATION and azure_client:
        response = azure_client.responses.parse(
            model=CHAT_DEPLOYMENT,
            instructions=system_prompt,
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

        for ann in parsed.annotations:
            quote = ann.exact_quote
            label = ann.label
            conf = ann.confidence_score
            
            start_idx = transcript.find(quote)
            if start_idx != -1:
                end_idx = start_idx + len(quote)
            else:
                start_idx = transcript.lower().find(quote.lower())
                if start_idx != -1:
                    end_idx = start_idx + len(quote)
                else:
                    start_idx = -1
                    end_idx = -1
                    
            llm_annotations.append({
                "label": label,
                "quote": quote,
                "start": start_idx,
                "end": end_idx,
                "confidence_score": conf
            })
                 
        response_id = response.id

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

    logging.info(f"Chat response: Segments: {len(llm_annotations)}")

    # Create an empty log for this participant if it doesn't exist yet
    if participant_id not in transcript_log:
        transcript_log[participant_id] = []

    if skip_silence_entry:
        add_silence_segment_if_needed(
            transcript_log[participant_id], start_time_dt, "**Opname hervat na pauze**"
        )
    else:
        add_silence_segment_if_needed(transcript_log[participant_id], start_time_dt)

    segment_id = len(transcript_log[participant_id]) + 1

    # Upload screenshot to google drive
    screenshot_filename = ""
    if screenshot:
        screenshot_filename = f"screenshot_deelnemer_{participant_id}_fragment_{segment_id}.jpg"

        if "," in screenshot:
            _, b64_data = screenshot.split(",", 1)
        else:
            b64_data = screenshot

        screenshot_bytes = base64.b64decode(b64_data)

        background_tasks.add_task(
            upload_screenshot,
            participant_id,
            screenshot_bytes,
            screenshot_filename
        )

    # Add the transcript with the knowledge structure classification to the log
    transcript_log[participant_id].append(
        {
            "segment_id": segment_id,
            "starttijd": start_time_value,
            "eindtijd": end_time_value,
            "transcript": transcript,
            "screenshot_bestandsnaam": screenshot_filename,
            "llm_annotaties": json.dumps(llm_annotations, ensure_ascii=False),
            "human_annotaties": "[]",
        }
    )

    background_tasks.add_task(
        upload_transcript_files_with_lock,
        participant_id,
        transcript_log[participant_id],
    )

    return {"response": "success", "response_id": response_id}


# Researcher tool endpoints
# Get participant folder names
@app.get("/researcher/participants")
def list_participants():
    try:
        return get_participants_list()
    except Exception as e:
        logging.error(f"Error listing participants: {e}")
        raise HTTPException(status_code=500, detail="Failed to list participants")


# Get transcript segments for a participant
@app.get("/researcher/participant/{participant_id}/transcript")
def get_transcript(participant_id: str):
    try:
        return get_participant_transcript(participant_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error loading transcript for participant {participant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load transcript")


# Get screenshot image for a participant
@app.get("/researcher/participant/{participant_id}/screenshot/{filename}")
def get_screenshot(participant_id: str, filename: str):
    try:
        img_bytes = get_participant_screenshot(participant_id, filename)
        return Response(content=img_bytes, media_type="image/jpeg")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error loading screenshot: {e}")
        raise HTTPException(status_code=500, detail="Failed to load screenshot")


# Save annotations for a participant
@app.post("/researcher/participant/{participant_id}/annotations")
def save_annotations(participant_id: str, updated_segments: list[dict[str, Any]]):
    try:
        # Create a backup of the original transcript
        create_original_transcript_backup(participant_id)
        
        participant_log = []
        for seg in updated_segments:
            llm_ann = seg.get("llm_annotaties")
            if not isinstance(llm_ann, str):
                llm_ann = json.dumps(llm_ann, ensure_ascii=False)
                
            human_ann = seg.get("human_annotaties")
            if not isinstance(human_ann, str):
                human_ann = json.dumps(human_ann, ensure_ascii=False)
                
            participant_log.append({
                "segment_id": seg.get("segment_id"),
                "starttijd": seg.get("starttijd"),
                "eindtijd": seg.get("eindtijd"),
                "transcript": seg.get("transcript"),
                "screenshot_bestandsnaam": seg.get("screenshot_bestandsnaam"),
                "llm_annotaties": llm_ann,
                "human_annotaties": human_ann,
            })
            
        upload_transcript_files(participant_id, participant_log)
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Error saving annotations for participant {participant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save annotations")


# Run post-hoc classification for a participant
@app.post("/researcher/participant/{participant_id}/classify_post_hoc")
def run_post_hoc_classification(participant_id: str):
    try:
        classify_participant(participant_id)
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Error executing post-hoc classification for participant {participant_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute post-hoc classification: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
