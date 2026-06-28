import os
import logging
from services.storage_service import get_participant_transcript

# Forceer lokale modus voor testen
os.environ["LOCAL_STORAGE_MODE"] = "true"

def main():
    logging.info("--- Running evaluate_annotations.py ---")
    participant_id = "4"
    logging.info(f"Loading data for participant: {participant_id}")
    
    try:
        data = get_participant_transcript(participant_id)
    except Exception as e:
        logging.error(f"Failed to load participant data: {e}")
        return
        
    logging.info(f"Successfully loaded {len(data)} segments.\n")
    for row in data:
        print(f"Segment ID: {row['segment_id']}")
        print(f"Transcript: {row['transcript']}")
        print(f"LLM Annotations: {row['llm_annotaties']}")
        print(f"Human Annotations: {row['human_annotaties']}")
        print("-" * 50)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    main()

