import threading
import logging
from typing import Any
from datetime import datetime

from services.storage_service import upload_transcript_files

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
SILENCE_GAP_THRESHOLD_SECONDS = float("5.00")


# Per-participant lock to avoid concurrent transcript file uploads.
participant_upload_locks: dict[str, threading.Lock] = {}
participant_upload_locks_guard = threading.Lock()

# Number of segments uploaded per participant
last_uploaded_length: dict[str, int] = {}


def get_participant_upload_lock(participant_id: str):
    with participant_upload_locks_guard:
        if participant_id not in participant_upload_locks:
            participant_upload_locks[participant_id] = threading.Lock()
        return participant_upload_locks[participant_id]


def add_silence_segment_if_needed(
    participant_entries: list[dict[str, Any]],
    start_dt: datetime,
    transcript_text: str | None = None,
):
    if not participant_entries:
        return

    previous_end_time = participant_entries[-1].get("eindtijd")
    if not previous_end_time:
        return

    try:
        previous_end_dt = datetime.strptime(previous_end_time, TIMESTAMP_FORMAT)
    except ValueError:
        return

    gap_seconds = (start_dt - previous_end_dt).total_seconds()
    if gap_seconds < SILENCE_GAP_THRESHOLD_SECONDS:
        return

    participant_entries.append(
        {
            "segment_id": len(participant_entries) + 1,
            "starttijd": previous_end_dt.strftime(TIMESTAMP_FORMAT),
            "eindtijd": start_dt.strftime(TIMESTAMP_FORMAT),
            "transcript": transcript_text or f"**{gap_seconds:.2f}s stilte**",
            "screenshot_bestandsnaam": "",
            "llm_annotaties": "[]",
            "human_annotaties": "[]",
        }
    )


def upload_transcript_files_with_lock(participant_id: str, participant_log: list):
    # Check outside the lock if there are any new segments to upload
    if len(participant_log) <= last_uploaded_length.get(participant_id, 0):
        return

    lock = get_participant_upload_lock(participant_id)
    with lock:
        # Double-check to prevent redundant uploads
        current_len = len(participant_log)
        if current_len <= last_uploaded_length.get(participant_id, 0):
            return

        try:
            log_snapshot = list(participant_log)
            upload_transcript_files(participant_id, log_snapshot)
            # Update the last uploaded length on success
            last_uploaded_length[participant_id] = current_len
        except Exception as e:
            logging.error(f"Error uploading transcript files for participant {participant_id}: {e}")


