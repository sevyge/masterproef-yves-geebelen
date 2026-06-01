import os
import logging
from dotenv import load_dotenv
from services.storage_service import get_drive_service, upload_to_google_drive, get_results_dir
from openai import AzureOpenAI
from prompts.system_prompt import SYSTEM_PROMPT
from schemas.chat import ChatClassification
import io
import csv

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def get_participant_folders(service, parent_id):
    """Retrieve all participant folders inside the root project folder."""
    query = (
        f"'{parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    return results.get("files", [])


def main():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    load_dotenv(os.path.join(BASE_DIR, "..", ".env"))
    logging.info(".env file loaded successfully.")
    logging.info("Starting post-hoc classification process...")

    LOCAL_STORAGE_MODE = os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true"

    service = None
    if not LOCAL_STORAGE_MODE:
        # Connect to Google Drive
        service = get_drive_service()
        if not service:
            logging.error("Failed to connect to Google Drive.")
            return
        logging.info("Successfully connected to Google Drive!")
    else:
        logging.info("Running in LOCAL STORAGE MODE.")

    # Initialize Azure OpenAI Client
    AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
    CHAT_DEPLOYMENT = os.getenv("CHAT_DEPLOYMENT", "")

    client = None
    if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT:
        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
        )

    if not client:
        logging.error("Failed to initialize AzureOpenAI client. Cannot perform classification.")
        return

    # Find Participant Folder
    parent_id = None
    if not LOCAL_STORAGE_MODE:
        parent_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not parent_id:
            logging.error("GOOGLE_DRIVE_FOLDER_ID environment variable is not set.")
            return

    participant_id = input("Enter Participant ID or Folder Name: ").strip()
    if not participant_id:
        logging.error("No participant ID entered.")
        return

    folder = None
    if not LOCAL_STORAGE_MODE:
        # Find the specific participant folder in Google Drive
        participant_folders = get_participant_folders(service, parent_id)
        logging.info(f"Found {len(participant_folders)} participant folders.")
        
        for f in participant_folders:
            if f['name'] == participant_id:
                folder = f
                break

        if not folder:
            logging.error(f"Participant folder '{participant_id}' not found in Google Drive.")
            return

        logging.info(f"Processing Folder: {folder['name']} (ID: {folder['id']})")
    else:
        # Check local folder existence
        local_folder_path = os.path.join(get_results_dir(), participant_id)
        if not os.path.isdir(local_folder_path):
            logging.error(f"Participant folder '{participant_id}' not found locally at: {os.path.abspath(local_folder_path)}")
            return
            
        logging.info(f"Processing Local Folder: {local_folder_path}")
        # Mimic folder dict structure
        folder = {"name": participant_id, "id": participant_id}

    file_name = f"transcript_met_kennisstructuur_{participant_id}.csv"

    if not LOCAL_STORAGE_MODE:
        # 1. Search for transcript_met_kennisstructuur_{id}.csv in this folder
        query = f"'{folder['id']}' in parents and mimeType = 'text/csv' and name contains 'transcript_met_kennisstructuur' and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = results.get("files", [])
        
        if not files:
            logging.info(f"No transcript CSV found in {folder['name']}.")
            return
            
        file_id = files[0]['id']
        file_name = files[0]['name']
        logging.info(f"Found transcript: {file_name}")
        
        # 2. Download the CSV
        request = service.files().get_media(fileId=file_id)
        file_content = request.execute()
        csv_text = file_content.decode('utf-8-sig')
    else:
        csv_path = os.path.join(get_results_dir(), participant_id, file_name)
        if not os.path.exists(csv_path):
            logging.error(f"No transcript CSV found at {csv_path}.")
            return
        logging.info(f"Found local transcript: {csv_path}")
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            csv_text = f.read()

    reader = csv.DictReader(io.StringIO(csv_text), delimiter=';')
    
    rows = list(reader)
    updated = False
    
    # 3. Iterate through rows and classify all entries
    for row in rows:
        transcript_text = (row.get("transcript") or "").strip()
        
        # Skip empty transcripts
        if not transcript_text:
            logging.info(f"Entry {row.get('entry_number')} has an empty transcript. Skipping.")
            continue
            
        # Skip if already classified
        labels = (row.get("labels") or "").strip()
        if labels and labels not in ["Fout met Azure API credentials"]:
            logging.info(f"Entry {row.get('entry_number')} is already classified ({labels}). Skipping.")
            continue

        logging.info(f"Classifying entry {row.get('entry_number')}...")
        user_content = [{"type": "input_text", "text": transcript_text}]
        
        try:
            response = client.responses.parse(
                model=CHAT_DEPLOYMENT,
                instructions=SYSTEM_PROMPT,
                input=[{"role": "user", "content": user_content}], # type: ignore
                text_format=ChatClassification,
            )
            
            parsed = response.output_parsed
            if parsed:
                row["labels"] = ", ".join(parsed.labels) if parsed.labels else "None"
                row["confidence_score"] = parsed.confidence_score
                updated = True
                logging.info(f"Result: {row['labels']} (Conf: {row['confidence_score']})")
            else:
                logging.error("Model returned no parsed output.")
                
        except Exception as e:
            logging.error(f"Error calling LLM: {e}")
                
    # 4. If updated, upload the new CSV back to Google Drive
    if updated:
        logging.info(f"Uploading updated {file_name} back to Google Drive...")
        
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["entry_number", "start_time", "end_time", "transcript", "screenshot_filename", "labels", "confidence_score"],
            delimiter=";",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(rows)
        
        upload_to_google_drive(
            file_stream=output.getvalue().encode("utf-8-sig"),
            filename=file_name,
            mimetype="text/csv",
            folder_id=folder['id'],
            overwrite=True,
        )
        logging.info(f"Update complete for {folder['name']}.")
    else:
        logging.info(f"No pending classifications found for {folder['name']}.")


if __name__ == "__main__":
    main()
