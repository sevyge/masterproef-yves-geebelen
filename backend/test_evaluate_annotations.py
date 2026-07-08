import unittest
from evaluate_annotations import calculate_jaccard, clean_quote_words

class TestOverlapAndJaccard(unittest.TestCase):
    
    def test_clean_quote_words(self):
        """Controleer of quotes correct worden schoongemaakt en gesplitst in woorden."""
        self.assertEqual(clean_quote_words(""), set())
        self.assertEqual(clean_quote_words("de bottleneck."), {"de", "bottleneck"})
        self.assertEqual(clean_quote_words("Een Histogram!"), {"een", "histogram"})

    def test_calculate_jaccard(self):
        """Controleer de Jaccard-berekening bij verschillende overlaps en edge cases."""
        # 1. Geen fysieke overlap
        fragment_human = {"start": 12, "end": 17, "quote": "model"}
        fragment_llm = {"start": 42, "end": 47, "quote": "model"}
        self.assertEqual(calculate_jaccard(fragment_human, fragment_llm), 0.0)
        
        # 2. Gedeeltelijke overlap (50%)
        fragment_human = {"start": 10, "end": 19, "quote": "histogram"}
        fragment_llm = {"start": 6, "end": 19, "quote": "een histogram"}
        self.assertAlmostEqual(calculate_jaccard(fragment_human, fragment_llm), 0.50)
        
        # 3. Exacte match (100%)
        fragment_human = {"start": 100, "end": 165, "quote": "Ik open het model."}
        fragment_llm = {"start": 101, "end": 166, "quote": "Ik open het model."}
        self.assertEqual(calculate_jaccard(fragment_human, fragment_llm), 1.0)

    def test_find_candidate_matches(self):
        """Controleer dat alleen kandidaat-matches boven de drempelwaarde worden verzameld."""
        from evaluate_annotations import find_candidate_matches
        
        human_anns = [
            {"start": 101, "end": 166, "quote": "Ik ga de Road Traffic Fine Management Process Dataset analyseren.", "label": "DOM"}
        ]
        llm_anns = [
            {"start": 100, "end": 165, "quote": "Ik ga de Road Traffic Fine Management Process Dataset analyseren.", "label": "DOM"},
            {"start": 832, "end": 903, "quote": "Ik zie hier meteen al dat de verschillende activiteiten zichtbaar zijn.", "label": "DK"} 
        ]
        
        candidates = find_candidate_matches(human_anns, llm_anns, threshold=0.5)
        
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["score"], 1.0)
        self.assertEqual(candidates[0]["human_fragment_index"], 0)
        self.assertEqual(candidates[0]["llm_fragment_index"], 0)

    def test_match_segment_annotations(self):
        """Controleer of bij gelijke Jaccard-overlap het overeenstemmende label prioriteit krijgt."""
        from evaluate_annotations import match_segment_annotations
        
        # 1 fragment (label: PK)
        human_anns = [
            {"start": 100, "end": 200, "quote": "ik open de Directly Follows graph", "label": "PK"}
        ]
        
        # 2 verschillende overlappende fragmenten met dezelfde Jaccard score
        llm_anns = [
            {"start": 103, "end": 200, "quote": "open de Directly Follows graph", "label": "DOM"},
            {"start": 100, "end": 195, "quote": "ik open de Directly Follows", "label": "PK"}
        ]
        
        result = match_segment_annotations(human_anns, llm_anns, threshold=0.5)
        
        self.assertEqual(len(result["matched_pairs"]), 1)
        self.assertEqual(result["matched_pairs"][0]["human_fragment_index"], 0)
        self.assertEqual(result["matched_pairs"][0]["llm_fragment_index"], 1)
        self.assertEqual(result["unmatched_llm_annotations"], [0])

if __name__ == "__main__":
    unittest.main()
