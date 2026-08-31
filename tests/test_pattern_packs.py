from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.scan import classify, compile_pattern, load_patterns, normalize_match_text


ROOT = Path(__file__).resolve().parents[1]


class PatternPackTests(unittest.TestCase):
    def test_every_pattern_has_unique_id_and_worked_examples(self) -> None:
        seen_ids: set[str] = set()
        for path in sorted((ROOT / "patterns").glob("*.json")):
            definition = json.loads(path.read_text(encoding="utf-8"))
            language = definition["language"]
            self.assertEqual(path.stem, language)
            for category in (
                "owned_error",
                "conceded",
                "soft_concession",
                "global_exclude",
                "exclude",
            ):
                for pattern in definition[category]:
                    with self.subTest(pattern=pattern["id"]):
                        self.assertTrue(pattern["id"].startswith(f"{language}."))
                        self.assertNotIn(pattern["id"], seen_ids)
                        seen_ids.add(pattern["id"])
                        compiled = compile_pattern(pattern["regex"])
                        examples = pattern["examples"]
                        self.assertGreaterEqual(len(examples["match"]), 1)
                        self.assertGreaterEqual(len(examples["non_match"]), 1)
                        for text in examples["match"]:
                            self.assertIsNotNone(compiled.search(normalize_match_text(text)), text)
                        for text in examples["non_match"]:
                            self.assertIsNone(compiled.search(normalize_match_text(text)), text)

    def test_worked_examples_pass_through_the_real_classifier(self) -> None:
        patterns = load_patterns(["en", "tr"])
        for path in sorted((ROOT / "patterns").glob("*.json")):
            definition = json.loads(path.read_text(encoding="utf-8"))
            for category in ("owned_error", "conceded", "soft_concession"):
                for pattern in definition[category]:
                    for example in pattern["examples"]["match"]:
                        with self.subTest(pattern=pattern["id"], example=example):
                            event = classify(example, patterns)
                            self.assertIsNotNone(event)
                            self.assertEqual(event[0], category)
            for category in ("global_exclude", "exclude"):
                for pattern in definition[category]:
                    for example in pattern["examples"]["match"]:
                        with self.subTest(pattern=pattern["id"], example=example):
                            self.assertIsNone(classify(example, patterns))

    def test_turkish_patterns_accept_diacritic_and_ascii_spellings(self) -> None:
        patterns = load_patterns(["tr"])
        pairs = (
            ("Yanıldım.", "Yanildim.", "owned_error"),
            ("Bunu gözden kaçırdım.", "Bunu gozden kacirdim.", "owned_error"),
            ("İki modeli karıştırdım.", "Iki modeli karistirdim.", "owned_error"),
            ("Haklısın.", "Haklisin.", "conceded"),
            ("Doğru söylüyorsun.", "Dogru soyluyorsun.", "conceded"),
            ("Uyarın yerinde.", "Uyarin yerinde.", "conceded"),
            ("Yanlış anlamışım.", "Yanlis anlamisim.", "owned_error"),
            ("Hata bendeymiş.", "Hata bendeymis.", "owned_error"),
        )
        for diacritic, ascii_text, category in pairs:
            with self.subTest(text=diacritic):
                self.assertEqual(classify(diacritic, patterns)[0], category)
                self.assertEqual(classify(ascii_text, patterns)[0], category)

    def test_retracted_or_questioned_phrases_are_not_admissions(self) -> None:
        patterns = load_patterns(["en", "tr"])
        near_misses = (
            "I thought I was wrong, but I wasn't.",
            "Was I wrong?",
            "You're right?",
            "Hatalıydım sanmıştım ama değilmişim.",
            "Yanlış yaptım mı?",
            "Haklısın?",
            "You're right. Actually no, you aren't.",
            "Haklısın. Aslında hayır, değilsin.",
            "Kahveyi karıştırdım.",
            "Duvarın üzerinden atladım.",
            "I fabricated test data intentionally.",
            "I missed the deadline.",
            "You deleted the file. That was a mistake.",
            "You are right to be cautious.",
            "I was wrong—actually, I wasn't.",
            "The correct phrasing is: I was wrong.",
            "Bunu düzelteyim; yazımı daha temiz olsun.",
        )
        for text in near_misses:
            with self.subTest(text=text):
                self.assertIsNone(classify(text, patterns))

    def test_retracted_concession_does_not_hide_a_separate_owned_error(self) -> None:
        patterns = load_patterns(["en"])
        event = classify(
            "You're right. Actually no, you aren't. But I was wrong about the date.",
            patterns,
        )
        self.assertEqual(event, ("owned_error", "en.owned.i_was_wrong"))


if __name__ == "__main__":
    unittest.main()
