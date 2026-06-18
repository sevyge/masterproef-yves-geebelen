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
import threading
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))

# Google Drive setup
SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "service_account.json")


def get_results_dir() -> str:
    """Return the absolute path to the unified results directory."""
    # Inside Docker, the volume is mounted at /app/results
    if os.path.exists("/app/results"):
        return "/app/results"
    
    # Outside Docker (on host), resolve to the root results folder
    root_results = os.path.abspath(os.path.join(BASE_DIR, "..", "results"))
    os.makedirs(root_results, exist_ok=True)
    return root_results


# Thread-local storage for the Drive service to prevent concurrent access issues
_thread_local = threading.local()


def get_drive_service():
    """Create a new instance of the Drive API service."""
    # Check if this thread already has an active client
    if hasattr(_thread_local, "drive_service"):
        return _thread_local.drive_service

    # Try loading credentials from environment variable (for hosting)
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        try:
            import json
            info = json.loads(service_account_json)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES
            )
            logging.info("Service account credentials from .env loaded successfully.")
            _thread_local.drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
            return _thread_local.drive_service
        except Exception as e:
            logging.error(f"Failed to load credentials from GOOGLE_SERVICE_ACCOUNT_JSON: {e}")

    # Fallback to local file (for local development)
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        try:
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            logging.info("Service account credentials from local file loaded successfully.")
            _thread_local.drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
            return _thread_local.drive_service
        except Exception as e:
            logging.error(f"Failed to load credentials from local file: {e}")
    return None


def get_or_create_participant_folder(participant_id: str) -> str:
    """Return the Drive folder ID for a participant, creating it if needed."""
    if os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true":
        return participant_id

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


def get_or_create_subfolder(parent_id: str, folder_name: str) -> str:
    """Return the Drive folder ID for a subfolder, creating it if needed."""
    if os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true":
        return f"{parent_id}/{folder_name}"

    service = get_drive_service()
    if service is None:
        raise FileNotFoundError("Service account file not found.")

    query = (
        f"name = '{folder_name}' and '{parent_id}' in parents "
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
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }

    folder = (
        service.files()
        .create(body=folder_metadata, fields="id", supportsAllDrives=True)
        .execute()
    )
    logging.info(f"Created Drive subfolder '{folder_name}' with ID: {folder['id']}")
    return folder["id"]


def get_next_participant_id() -> str:
    """Determine the next participant ID by counting existing folders."""
    if os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true":
        local_dir = get_results_dir()
        if not os.path.exists(local_dir):
            return "1"
        folders = [f for f in os.listdir(local_dir) if os.path.isdir(os.path.join(local_dir, f)) and f.isdigit()]
        return str(len(folders) + 1)

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
    if os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true":
        local_dir = get_results_dir()
        if folder_id:
            local_dir = os.path.join(local_dir, folder_id)
        os.makedirs(local_dir, exist_ok=True)

        file_path = os.path.join(local_dir, filename)

        if isinstance(file_stream, (bytes, bytearray)):
            with open(file_path, "wb") as f:
                f.write(file_stream)
        else:
            with open(file_path, "wb") as f:
                if hasattr(file_stream, "read"):
                    f.write(file_stream.read())
                else:
                    f.write(file_stream)

        logging.info(f"[LOCAL STORAGE] Saved {filename} to {file_path}")
        return {"file_id": f"local_{filename}"}

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
                "segment_id",
                "starttijd",
                "eindtijd",
                "transcript",
                "screenshot_bestandsnaam",
                "llm_annotaties",
                "human_annotaties",
            ],
            delimiter=";",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(participant_log)
        csv_content = output.getvalue()

        participant_folder = get_or_create_participant_folder(participant_id)
        upload_to_google_drive(
            file_stream=csv_content.encode("utf-8-sig"),
            filename=f"transcript_{participant_id}.csv",
            mimetype="text/csv",
            folder_id=participant_folder,
            overwrite=True,
        )
        logging.info(f"Transcript CSV updated for participant {participant_id}")

        # Create full transcript
        full_transcript_text = "\n\n".join(
            [
                (
                    f"[{entry.get('starttijd') or ''} - "
                    f"{entry.get('eindtijd') or ''}] "
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
    participant_id: str, ervaring: str, epa_project: str, tools: list[str], rol: str
):
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["deelnemer_id", "praktijkervaring", "eerder_epa_project", "gebruikte_tools", "huidige_rol", "indiendatum"]
        )
        tools_str = ", ".join(tools) if tools else "Geen tools geselecteerd"
        writer.writerow(
            [
                participant_id,
                ervaring,
                epa_project,
                tools_str,
                rol,
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

        csv_content = output.getvalue()

        participant_folder = get_or_create_participant_folder(participant_id)
        filename = f"vragenlijst_{participant_id}.csv"

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


def upload_screenshot(participant_id: str, screenshot_bytes: bytes, filename: str):
    try:
        participant_folder = get_or_create_participant_folder(participant_id)
        screenshot_folder = get_or_create_subfolder(participant_folder, "Screenshots")
        upload_to_google_drive(
            file_stream=screenshot_bytes,
            filename=filename,
            mimetype="image/jpeg",
            folder_id=screenshot_folder,
            overwrite=True
        )
        logging.info(f"Uploaded screenshot {filename} to Google Drive.")
    except Exception as e:
        logging.error(f"Failed to upload screenshot {filename}: {e}")


def get_participants_list() -> list[str]:
    """Retrieve all folders names from local storage or Google Drive."""
    LOCAL_STORAGE_MODE = os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true"
    if LOCAL_STORAGE_MODE:
        local_dir = get_results_dir()
        if not os.path.exists(local_dir):
            return []
        folders = []
        for name in os.listdir(local_dir):
            if not name.startswith("."):
                folders.append(name)
        return folders
    else:
        service = get_drive_service()
        if service is None:
            logging.error("Failed to connect to Google Drive inside get_participants_list.")
            return []
        parent_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not parent_id:
            logging.error("GOOGLE_DRIVE_FOLDER_ID not set inside get_participants_list.")
            return []
        query = (
            f"'{parent_id}' in parents and "
            f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        )
        try:
            results = service.files().list(
                q=query,
                pageSize=1000,
                fields="files(name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            folders = results.get("files", [])
            names = []
            for f in folders:
                if f.get('name'):
                    names.append(f['name'])
            return names
        except Exception as e:
            logging.error(f"Error fetching participant folders from Google Drive: {e}")
            return []


def get_participant_transcript(participant_id: str) -> list[dict]:
    """Retrieve and parse the transcript CSV for a given participant."""
    import json
    
    LOCAL_STORAGE_MODE = os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true"
    csv_text = ""
    
    # Fetch CSV content
    if LOCAL_STORAGE_MODE:
        file_path = os.path.join(get_results_dir(), participant_id, f"transcript_{participant_id}.csv")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Transcript CSV not found for participant {participant_id}")
        with open(file_path, "r", encoding="utf-8-sig") as f:
            csv_text = f.read()
    else:
        service = get_drive_service()
        if service is None:
            raise FileNotFoundError("Google Drive service not initialized")
        folder_id = get_or_create_participant_folder(participant_id)
        file_name = f"transcript_{participant_id}.csv"
        
        query = f"'{folder_id}' in parents and mimeType = 'text/csv' and name = '{file_name}' and trashed = false"
        results = service.files().list(
            q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True
        ).execute()
        files = results.get("files", [])
        if not files:
            raise FileNotFoundError(f"Transcript CSV not found on Google Drive for participant {participant_id}")
            
        request = service.files().get_media(fileId=files[0]['id'])
        csv_text = request.execute().decode('utf-8-sig')

    # Parse CSV
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=';')
    rows = []
    for row in reader:
        try:
            row["llm_annotaties"] = json.loads(row.get("llm_annotaties") or "[]")
            row["human_annotaties"] = json.loads(row.get("human_annotaties") or "[]")
        except Exception:
            row["llm_annotaties"] = []
            row["human_annotaties"] = []
        rows.append(row)
        
    return rows


def get_participant_screenshot(participant_id: str, filename: str) -> bytes:
    """Retrieve the raw screenshot image bytes."""
    LOCAL_STORAGE_MODE = os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true"
    
    if LOCAL_STORAGE_MODE:
        file_path = os.path.join(get_results_dir(), participant_id, "Screenshots", filename)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Screenshot {filename} not found locally.")
        with open(file_path, "rb") as f:
            return f.read()
    else:
        service = get_drive_service()
        if service is None:
            raise FileNotFoundError("Google Drive service not initialized")
            
        participant_folder = get_or_create_participant_folder(participant_id)
        screenshot_folder = get_or_create_subfolder(participant_folder, "Screenshots")
        
        query = f"'{screenshot_folder}' in parents and name = '{filename}' and trashed = false"
        results = service.files().list(
            q=query, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True
        ).execute()
        
        files = results.get("files", [])
        if len(files) == 0:
            raise FileNotFoundError(f"Screenshot {filename} not found on Google Drive.")
            
        file_id = files[0]['id']
        request = service.files().get_media(fileId=file_id)
        return request.execute()


def create_original_transcript_backup(participant_id: str):
    """Create a backup of the transcript (e.g. transcript_{participant_id}_original.csv)
    before human annotations are saved, if it doesn't exist yet."""
    import shutil
    LOCAL_STORAGE_MODE = os.getenv("LOCAL_STORAGE_MODE", "").lower() == "true"
    
    filename = f"transcript_{participant_id}.csv"
    backup_filename = f"transcript_{participant_id}_original.csv"
    
    if LOCAL_STORAGE_MODE:
        local_dir = os.path.join(get_results_dir(), participant_id)
        file_path = os.path.join(local_dir, filename)
        backup_path = os.path.join(local_dir, backup_filename)
        
        if os.path.exists(file_path) and not os.path.exists(backup_path):
            try:
                shutil.copyfile(file_path, backup_path)
                logging.info(f"[BACKUP] Created original backup at {backup_path}")
            except Exception as e:
                logging.error(f"[BACKUP] Failed to create original backup: {e}")
    else:
        service = get_drive_service()
        if service is None:
            logging.error("[BACKUP] Google Drive service not initialized for backup.")
            return
            
        try:
            folder_id = get_or_create_participant_folder(participant_id)
            
            # Check if original backup already exists
            query_backup = f"'{folder_id}' in parents and name = '{backup_filename}' and trashed = false"
            results_backup = service.files().list(
                q=query_backup, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            
            if not results_backup.get("files", []):
                # Search for original file
                query_orig = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
                results_orig = service.files().list(
                    q=query_orig, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True
                ).execute()
                
                orig_files = results_orig.get("files", [])
                if orig_files:
                    orig_file_id = orig_files[0]["id"]
                    # Copy on Google Drive
                    copied_file = service.files().copy(
                        fileId=orig_file_id,
                        body={"name": backup_filename, "parents": [folder_id]},
                        supportsAllDrives=True
                    ).execute()
                    logging.info(f"[BACKUP] Created original Google Drive backup with ID: {copied_file.get('id')}")
        except Exception as e:
            logging.error(f"[BACKUP] Failed to create Google Drive backup: {e}")





