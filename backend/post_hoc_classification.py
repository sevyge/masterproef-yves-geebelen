import logging
from services.google_drive_service import get_drive_service

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def main():
    logging.info("Starting post-hoc classification process...")

    # Connect to Google Drive
    service = get_drive_service()
    if not service:
        logging.error("Failed to connect to Google Drive.")
        return

    logging.info("Successfully connected to Google Drive!")


if __name__ == "__main__":
    main()
