import os
import logging
import string
from services.storage_service import get_participant_transcript

# Forceer lokale modus voor testen
os.environ["LOCAL_STORAGE_MODE"] = "true"

def clean_quote_words(quote):
    """Zet de quote om naar een set van schone, kleine woorden zonder leestekens."""
    if not quote:
        return set()
    text = quote.lower()
    for leesteken in string.punctuation:
        text = text.replace(leesteken, "")
    words = text.split()
    return set(words)


def calculate_jaccard(fragment_a, fragment_b):
    """
    Controleert of de karakter-intervallen elkaar fysiek overlappen en berekent vervolgens de Jaccard-overlap op woordniveau van de fragmenten.
    Returns: float (Jaccard score, 0.0 indien geen overlap of lege fragmenten)
    """
    start_index_a, end_index_a = fragment_a["start"], fragment_a["end"]
    start_index_b, end_index_b = fragment_b["start"], fragment_b["end"]
    
    # Fysieke overlap van de fragmenten checken
    has_overlap = max(start_index_a, start_index_b) < min(end_index_a, end_index_b)
    
    if not has_overlap:
        return 0.0
        
    # Jaccard berekening op woorden van het fragment
    words_a = clean_quote_words(fragment_a.get("quote", ""))
    words_b = clean_quote_words(fragment_b.get("quote", ""))
    
    if not words_a or not words_b:
        return 0.0
        
    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)
    
    return len(intersection) / len(union)

def find_candidate_matches(human_anns, llm_anns, threshold=0.5):
    """
    Verzamel alle kandidaat-matches die fysiek overlappen en een Jaccard-score boven de drempelwaarde hebben.
    """
    candidates = []
    for human_fragment_index, human_ann in enumerate(human_anns):
        for llm_fragment_index, llm_ann in enumerate(llm_anns):
            score = calculate_jaccard(human_ann, llm_ann)
            if score >= threshold:
                candidates.append({
                    "human_fragment_index": human_fragment_index,
                    "llm_fragment_index": llm_fragment_index,
                    "score": score
                })
    return candidates

def match_segment_annotations(human_anns, llm_anns, threshold=0.5):
    """
    Koppelt menselijke annotaties en LLM-annotaties 1-op-1 op basis van de hoogste Jaccard-overlap.
    Bij gelijke Jaccard-overlap krijgt een koppeling met een overeenstemmend label voorrang.
    Retourneert een dict met matched_pairs, unmatched_human en unmatched_llm.
    """
    candidates = find_candidate_matches(human_anns, llm_anns, threshold)
    
    def get_sort_key(candidate):
        human_ann = human_anns[candidate["human_fragment_index"]]
        llm_ann = llm_anns[candidate["llm_fragment_index"]]
        same_label = 1 if human_ann.get("label") == llm_ann.get("label") else 0
        return (candidate["score"], same_label)
        
    candidates.sort(key=get_sort_key, reverse=True)
    
    matched_pairs = []
    matched_human_indices = set()
    matched_llm_indices = set()
    
    for candidate in candidates:
        human_fragment_index = candidate["human_fragment_index"]
        llm_fragment_index = candidate["llm_fragment_index"]
        
        if human_fragment_index not in matched_human_indices and llm_fragment_index not in matched_llm_indices:
            matched_pairs.append(candidate)
            matched_human_indices.add(human_fragment_index)
            matched_llm_indices.add(llm_fragment_index)
            
    unmatched_human = [
        i for i in range(len(human_anns)) if i not in matched_human_indices
    ]
    unmatched_llm = [
        i for i in range(len(llm_anns)) if i not in matched_llm_indices
    ]
    
    return {
        "matched_pairs": matched_pairs,
        "unmatched_human": unmatched_human,
        "unmatched_llm": unmatched_llm
    }

def main():
    logging.info("--- Running evaluate_annotations.py ---")
    participant_id = "4"
    
    try:
        data = get_participant_transcript(participant_id)
    except Exception as e:
        logging.error(f"Failed to load participant data: {e}")
        return
        
    logging.info(f"Successfully loaded {len(data)} segments.\n")
    
    for row in data:
        human_anns = row.get("human_annotaties", [])
        llm_anns = row.get("llm_annotaties", [])
        
        # Sla lege segmenten over
        if not human_anns and not llm_anns:
            continue
            
        print(f"=== Segment ID: {row['segment_id']} ===")
        print(f"Aantal mens-annotaties: {len(human_anns)}")
        print(f"Aantal LLM-annotaties:  {len(llm_anns)}")
        
        result = match_segment_annotations(human_anns, llm_anns, threshold=0.5)
        
        print(f"Koppelingen (True Positives): {len(result['matched_pairs'])}")
        for match in result["matched_pairs"]:
            human_ann = human_anns[match["human_fragment_index"]]
            llm_ann = llm_anns[match["llm_fragment_index"]]
            print(f"  [Match - Jaccard {match['score']:.2%}]")
            print(f"    MENS: '{human_ann['quote']}' [{human_ann.get('label', 'N/A')}]")
            print(f"    LLM : '{llm_ann['quote']}' [{llm_ann.get('label', 'N/A')}]")
            
        if result["unmatched_human"]:
            print(f"Gemist door LLM (False Negatives): {len(result['unmatched_human'])}")
            for idx in result["unmatched_human"]:
                ann = human_anns[idx]
                print(f"  MENS: '{ann['quote']}' [{ann.get('label', 'N/A')}]")
                
        if result["unmatched_llm"]:
            print(f"Verzonnen door LLM (False Positives): {len(result['unmatched_llm'])}")
            for idx in result["unmatched_llm"]:
                ann = llm_anns[idx]
                print(f"  LLM : '{ann['quote']}' [{ann.get('label', 'N/A')}]")
                
        print("-" * 50)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    main()


