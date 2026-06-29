import unittest
from evaluate_annotations import calculate_jaccard, clean_quote_words

class TestOverlapAndJaccard(unittest.TestCase):
    
    def test_clean_quote_words(self):
        """Controleer of quotes correct worden schoongemaakt en gesplitst in woorden."""
        self.assertEqual(clean_quote_words(""), set())
        self.assertEqual(clean_quote_words("de bottleneck."), {"de", "bottleneck"})
        self.assertEqual(clean_quote_words("Een Histogram!"), {"een", "histogram"})

    def test_no_physical_overlap(self):
        """Controleer dat fragmenten op verschillende posities niet met elkaar matchen."""
        fragment_human = {"start": 12, "end": 17, "quote": "model"}
        fragment_llm = {"start": 42, "end": 47, "quote": "model"}
        
        score = calculate_jaccard(fragment_human, fragment_llm)
        self.assertEqual(score, 0.0)

    def test_partial_jaccard_overlap(self):
        """Controleer de Jaccard berekening bij gedeeltelijke overlap."""
        fragment_human = {"start": 10, "end": 19, "quote": "histogram"}
        fragment_llm = {"start": 6, "end": 19, "quote": "een histogram"}
        
        score = calculate_jaccard(fragment_human, fragment_llm)
        self.assertAlmostEqual(score, 0.50)

    def test_exact_match(self):
        """Controleer dat exact gelijke quotes een score van 100% krijgen."""
        fragment_human = {"start": 100, "end": 165, "quote": "Ik open het model."}
        fragment_llm = {"start": 101, "end": 166, "quote": "Ik open het model."}
        
        score = calculate_jaccard(fragment_human, fragment_llm)
        self.assertEqual(score, 1.0)

if __name__ == "__main__":
    unittest.main()
