#!/usr/bin/env python3
"""
Unit tests for query_lightrag.py evaluation logic and formatting.
"""

import unittest
import os
import json
import tempfile
from query_lightrag import evaluate_response, format_prompt, save_results, load_existing_results


class TestQueryLightRAG(unittest.TestCase):

    def test_evaluate_correct_single_letter(self):
        # Exact match
        status, letter = evaluate_response("B", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, 1)
        self.assertEqual(letter, "B")

        # Lowercase should match case-insensitively
        status, letter = evaluate_response("b", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, 1)
        self.assertEqual(letter, "B")

    def test_evaluate_wrong_single_letter(self):
        # Mismatch
        status, letter = evaluate_response("A", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, 0)
        self.assertEqual(letter, "A")

        status, letter = evaluate_response("C", "D", ["A", "B", "C", "D"])
        self.assertEqual(status, 0)
        self.assertEqual(letter, "C")

    def test_evaluate_unable_or_unconfident(self):
        # Explicit -1
        status, ans = evaluate_response("-1", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, -1)

        # "sorry i cant help"
        status, ans = evaluate_response("sorry i cant help", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, -1)

        status, ans = evaluate_response("Sorry, I can't help with that.", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, -1)

        # Explanations / multi-word responses
        status, ans = evaluate_response("The answer is B because God created heaven and earth.", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, -1)

        status, ans = evaluate_response("I do not have sufficient information in the knowledge base.", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, -1)

        # Empty string or None
        status, ans = evaluate_response("", "B", ["A", "B", "C", "D"])
        self.assertEqual(status, -1)

        status, ans = evaluate_response(None, "B", ["A", "B", "C", "D"])
        self.assertEqual(status, -1)

    def test_markdown_and_punctuation_handling(self):
        # Markdown bold
        status, letter = evaluate_response("**B**", "B", ["A", "B", "C", "D"], strict=False)
        self.assertEqual(status, 1)
        self.assertEqual(letter, "B")

        # Trailing period
        status, letter = evaluate_response("B.", "B", ["A", "B", "C", "D"], strict=False)
        self.assertEqual(status, 1)
        self.assertEqual(letter, "B")

        # In strict mode, "**B**" should fail to be a single letter -> -1
        status, ans = evaluate_response("**B**", "B", ["A", "B", "C", "D"], strict=True)
        self.assertEqual(status, -1)

    def test_missing_correct_answer(self):
        # When correct_answer is None or empty
        status, ans = evaluate_response("B", None, ["A", "B", "C", "D"])
        self.assertEqual(status, -1)

    def test_format_prompt(self):
        template = "Q: {question}\nOpts:\n{options}"
        q = {
            "id": 1,
            "question": "What did God create?",
            "options": {"A": "Water", "B": "Heavens and earth"}
        }
        res = format_prompt(template, q)
        self.assertIn("What did God create?", res)
        self.assertIn("A. Water", res)
        self.assertIn("B. Heavens and earth", res)

    def test_save_and_load_results(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            results = {
                1: {"question_number": 1, "response_status": 1},
                2: {"question_number": 2, "response_status": 0},
                3: {"question_number": 3, "response_status": -1}
            }
            save_results(results, temp_path)

            loaded = load_existing_results(temp_path)
            self.assertEqual(len(loaded), 3)
            self.assertEqual(loaded[1]["response_status"], 1)
            self.assertEqual(loaded[2]["response_status"], 0)
            self.assertEqual(loaded[3]["response_status"], -1)

            # Check JSON contents directly
            with open(temp_path, "r") as f:
                data = json.load(f)
            self.assertIsInstance(data, list)
            self.assertEqual(data[0]["question_number"], 1)
            self.assertEqual(data[0]["response_status"], 1)

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
