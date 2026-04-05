from typing import Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO
import os
import time
import logging
import csv
import io
from dotenv import load_dotenv

load_dotenv()

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
    media = MediaIoBaseUpload(
        file_stream, mimetype=mimetype, resumable=True, chunksize=5 * 1024 * 1024
    )

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
        request = service.files().update(
            fileId=existing_file_id,
            media_body=media,
            supportsAllDrives=True,
        )
    else:
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )

    # Execute resumable upload in chunks
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logging.info(f"Uploaded {int(status.progress() * 100)}% of {filename}")

    return {"file_id": response.get("id")}


def upload_transcript_files(participant_id: str, participant_log: list):
    try:
        # Generate CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "entry_number",
                "start_time",
                "end_time",
                "transcript",
                "labels",
                "confidence_score",
            ],
            delimiter=";",
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
        logging.info(f"Transcript CSV updated for participant {participant_id}")

        # Create full transcript
        full_transcript_text = "\n\n".join(
            [
                (
                    f"[{entry.get('start_time') or ''} - "
                    f"{entry.get('end_time') or ''}] "
                    f"{entry['transcript']}"
                )
                for entry in participant_log
            ]
        )
        upload_to_google_drive(
            file_stream=full_transcript_text.encode("utf-8"),
            filename=f"full_transcript_{participant_id}.md",
            mimetype="text/markdown",
            folder_id=participant_folder,
            overwrite=True,
        )
        logging.info(f"Full transcript MD updated for participant {participant_id}")
    except Exception as e:
        logging.error(f"Error uploading transcript files: {e}")


def upload_vragenlijst_csv(
    participant_id: str, kennis: str, epa_project: str, status: str
):
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["Participant ID", "Kennisniveau EPA", "Eerder EPA Project", "Huidige Status", "Indiendatum"]
        )
        writer.writerow(
            [
                participant_id,
                kennis,
                epa_project,
                status,
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

        csv_content = output.getvalue()

        participant_folder = get_or_create_participant_folder(participant_id)
        filename = f"vragenlijst_antwoorden_{participant_id}.csv"

        upload_to_google_drive(
            file_stream=csv_content.encode("utf-8"),
            filename=filename,
            mimetype="text/csv",
            folder_id=participant_folder,
        )
        logging.info(f"Vragenlijst CSV uploaded for participant {participant_id}")
    except Exception as e:
        logging.error(f"Error uploading vragenlijst CSV: {e}")
        raise
