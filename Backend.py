from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from openai import AzureOpenAI
import tempfile
import time
import json
import os
from dotenv import load_dotenv

load_dotenv()

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


@app.get("/")
async def root():
    return {"message": "Success"}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_file:
        temp_file.write(await audio.read())
        temp_file_path = temp_file.name

    try:
        print(
            f"Speech to text processing started at {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        with open(temp_file_path, "rb") as f:
            result = client.audio.transcriptions.create(
                model=WHISPER_DEPLOYMENT, file=f, language="nl"
            )
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        print(f"Transcription finished at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return {"transcription": result.text}
    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise e


@app.post("/chat")
async def chat(
    prompt: str = Form(...),
    screenshot: str = Form(None),
    previous_response_id: str = Form(None),
):
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


@app.get("/tts-stream/{text}")
async def tts_stream(text: str):
    try:
        print(f"TTS streaming started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        response = client.audio.speech.create(
            model=TTS_DEPLOYMENT, voice="nova", input=text, response_format="wav"
        )
        print(f"TTS streaming finished at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return StreamingResponse(
            response.iter_bytes(),
            media_type="audio/wav",
            headers={
                "Accept-Ranges": "bytes",
            },
        )
    except Exception as e:
        print(f"TTS streaming error: {e}")
        return Response(content="", status_code=500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
