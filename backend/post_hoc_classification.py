import os
import logging
from dotenv import load_dotenv
from services.google_drive_service import get_drive_service

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
    load_dotenv()
    logging.info(".env file loaded successfully.")
    logging.info("Starting post-hoc classification process...")

    # Connect to Google Drive
    service = get_drive_service()
    if not service:
        logging.error("Failed to connect to Google Drive.")
        return

    logging.info("Successfully connected to Google Drive!")

    # Find Participant Folders in Google Drive
    parent_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not parent_id:
        logging.error("GOOGLE_DRIVE_FOLDER_ID environment variable is not set.")
        return

    participant_folders = get_participant_folders(service, parent_id)
    logging.info(f"Found {len(participant_folders)} participant folders.")

    for folder in participant_folders:
        logging.info(f" -> Found Folder: {folder['name']} (ID: {folder['id']})")


if __name__ == "__main__":
    main()
