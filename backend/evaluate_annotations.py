import os
import logging
import string
from services.storage_service import get_participant_transcript, get_participants_list

# Forceer lokale modus voor testen
os.environ["LOCAL_STORAGE_MODE"] = "true"

class CategoryMetrics:
    """Houdt de evaluatieresultaten (TP, FP, FN) bij voor een categorie."""
    def __init__(self):
        self.true_positives = 0
        self.false_positives = 0
        self.false_negatives = 0

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

def filter_annotations_by_label(annotations, label):
    """Filtert een lijst met annotaties op een specifiek label."""
    filtered = []
    for ann in annotations:
        if ann.get("label") == label:
            filtered.append(ann)
    return filtered

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
    Retourneert een dict met matched_pairs, unmatched_human_annotations en unmatched_llm_annotations.
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
            
    unmatched_human_annotations = []
    for i in range(len(human_anns)):
        if i not in matched_human_indices:
            unmatched_human_annotations.append(i)
            
    unmatched_llm_annotations = []
    for i in range(len(llm_anns)):
        if i not in matched_llm_indices:
            unmatched_llm_annotations.append(i)
    
    return {
        "matched_pairs": matched_pairs,
        "unmatched_human_annotations": unmatched_human_annotations,
        "unmatched_llm_annotations": unmatched_llm_annotations
    }

def evaluate_participant_fragments(data, threshold=0.5):
    """Evalueert de fragment-matching per categorie en berekent de totalen."""
    # 1. Accumuleer counts intern met CategoryMetrics
    metrics = {
        "DOM": CategoryMetrics(),
        "DK": CategoryMetrics(),
        "PK": CategoryMetrics(),
        "CK": CategoryMetrics(),
        "TOTAAL": CategoryMetrics()
    }
    
    categories = ["DOM", "DK", "PK", "CK"]
    
    for row in data:
        for category in categories:
            human_anns = filter_annotations_by_label(row.get("human_annotaties", []), category)
            llm_anns = filter_annotations_by_label(row.get("llm_annotaties", []), category)
            
            match_res = match_segment_annotations(human_anns, llm_anns, threshold)
            
            true_positives_count = len(match_res["matched_pairs"])
            false_positives_count = len(match_res["unmatched_llm_annotations"])
            false_negatives_count = len(match_res["unmatched_human_annotations"])
            
            metrics[category].true_positives += true_positives_count
            metrics[category].false_positives += false_positives_count
            metrics[category].false_negatives += false_negatives_count
            
            metrics["TOTAAL"].true_positives += true_positives_count
            metrics["TOTAAL"].false_positives += false_positives_count
            metrics["TOTAAL"].false_negatives += false_negatives_count
            
    # 2. Bereken statistieken en formatteer naar JSON
    results = {}
    for category, m in metrics.items():
        true_positives = m.true_positives
        false_positives = m.false_positives
        false_negatives = m.false_negatives
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0.0 else 0.0
        
        results[category] = {
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score
        }
        
    return results

def print_aggregated_summary(data):
    """Bereken en print geaggregeerde statistieken op fragmentniveau."""
    print("=== SAMENVATTING OP FRAGMENTNIVEAU ===")
    results = evaluate_participant_fragments(data, threshold=0.5)
    for category, res in results.items():
        true_positives = res["true_positives"]
        false_positives = res["false_positives"]
        false_negatives = res["false_negatives"]
        precision = res["precision"]
        recall = res["recall"]
        f1_score = res["f1_score"]
        
        print(f"{category} -> Menselijke annotaties: {true_positives + false_negatives}, LLM annotaties: {true_positives + false_positives}, Overeenkomsten (Matches): {true_positives} | Precision: {precision:.1%}, Recall: {recall:.1%}, F1-score: {f1_score:.1%}")
    print()

def main():
    logging.info("--- Running evaluate_annotations.py ---")
    participant_id = input("Enter Participant ID or Folder Name (or type 'all' to evaluate everyone): ").strip()
    if not participant_id:
        logging.error("No participant ID entered.")
        return
    
    if participant_id.lower() == "all":
        try:
            participants = get_participants_list()
        except Exception as e:
            logging.error(f"Failed to load participants list: {e}")
            return
            
        logging.info(f"Found participants: {participants}")
        
        all_data = []
        incomplete_participants = []
        
        for p_id in participants:
            try:
                p_data = get_participant_transcript(p_id)
                has_human = any(row.get("human_annotaties") for row in p_data)
                has_llm = any(row.get("llm_annotaties") for row in p_data)
                
                if has_human and has_llm:
                    all_data.extend(p_data)
                else:
                    incomplete_participants.append(p_id)
            except Exception as e:
                logging.warning(f"Failed to load data for participant {p_id}: {e}")
                
        if not all_data:
            logging.error("No data found for any participant.")
            return
            
        logging.info(f"Successfully loaded a total of {len(all_data)} segments from all participants.\n")
        print_aggregated_summary(all_data)
        
        if incomplete_participants:
            list_str = ", ".join(sorted(incomplete_participants))
            print(f"[Opmerking] Deelnemer(s) {list_str} zijn onvolledig (missen menselijke of LLM annotaties) en zijn niet meegenomen in de resultaten.")
            print()
    else:
        try:
            data = get_participant_transcript(participant_id)
        except Exception as e:
            logging.error(f"Failed to load participant data: {e}")
            return
            
        logging.info(f"Successfully loaded {len(data)} segments.\n")
        print_aggregated_summary(data)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    main()


