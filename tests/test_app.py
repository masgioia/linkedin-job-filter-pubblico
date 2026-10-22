import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app


class NormalizeTests(unittest.TestCase):
    def test_normalize_supported_source_fields(self):
        job = app.normalize({
            "jobTitle": "ML Engineer",
            "companyName": "Example Ltd",
            "jobLocation": "Remote",
            "jobUrl": "https://example.test/job/1",
            "postedDate": "2026-10-01",
            "jobDescription": "Build machine learning systems.",
        })
        self.assertEqual(job["title"], "ML Engineer")
        self.assertEqual(job["company"], "Example Ltd")
        self.assertEqual(job["location"], "Remote")
        self.assertEqual(job["url"], "https://example.test/job/1")
        self.assertEqual(job["posted_at"], "2026-10-01")
        self.assertEqual(job["description"], "Build machine learning systems.")

    def test_normalize_missing_fields_as_empty_strings(self):
        job = app.normalize({})
        self.assertTrue(all(value == "" for value in job.values()))


class ScreeningTests(unittest.TestCase):
    def _response(self, payload):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps(payload)}]}
            }]
        }
        return response

    def test_screen_job_keeps_relevant_role(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "app.requests.post",
            return_value=self._response({"keep": True, "reason": "Ruolo coerente con il profilo"}),
        ):
            result = app.screen_job("AI and project management profile", {
                "title": "ERP & AI IT Prospect Leader", "company": "Example",
                "location": "Italy", "posted_at": "", "description": "AI projects",
            })
        self.assertTrue(result["keep"])

    def test_screen_job_rejects_unrelated_role(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "app.requests.post",
            return_value=self._response({"keep": False, "reason": "Ruolo retail non pertinente"}),
        ):
            result = app.screen_job("AI engineer profile", {
                "title": "Store Manager", "company": "Example",
                "location": "Italy", "posted_at": "", "description": "Retail store",
            })
        self.assertFalse(result["keep"])



class ProfileTests(unittest.TestCase):
    def test_personal_profile_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "job_search_profile.md").write_text("Personal criteria", encoding="utf-8")
            (root / "job_search_profile.example.md").write_text("Example criteria", encoding="utf-8")
            with patch("app.Path", side_effect=lambda value=".": Path(directory) / value):
                self.assertEqual(app.load_profile(), "Personal criteria")

    def test_example_profile_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "job_search_profile.example.md").write_text("Example criteria", encoding="utf-8")
            with patch("app.Path", side_effect=lambda value=".": Path(directory) / value):
                self.assertEqual(app.load_profile(), "Example criteria")

    def test_empty_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "job_search_profile.example.md").write_text("  ", encoding="utf-8")
            with patch("app.Path", side_effect=lambda value=".": Path(directory) / value):
                with self.assertRaises(ValueError):
                    app.load_profile()


class EvaluationTests(unittest.TestCase):
    def _response(self, payload):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps(payload)}]}
            }]
        }
        return response

    def test_evaluate_accepts_valid_result(self):
        payload = {
            "fit_score": 4, "income_score": 3, "ai_score": 5, "low_stress_score": 2,
            "assessment": "Good technical match",
            "evidence": ["Python required"], "inferences": [], "unknowns": [],
            "strengths": ["ML experience"], "risks": ["On-call unclear"],
            "recommendation": "CONSIDER",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "app.requests.post", return_value=self._response(payload)
        ):
            self.assertEqual(app.evaluate("profile", {"title": "ML Engineer", "company": "X",
                "location": "Remote", "posted_at": "", "description": "Python and ML"}), payload)

    def test_evaluate_retries_after_429(self):
        payload = {
            "fit_score": 4, "income_score": 3, "ai_score": 5, "low_stress_score": 2,
            "assessment": "Good technical match",
            "evidence": [], "inferences": [], "unknowns": [], "strengths": [], "risks": [],
            "recommendation": "CONSIDER",
        }
        limited = Mock()
        limited.status_code = 429
        limited.headers = {"Retry-After": "1"}
        successful = self._response(payload)
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "app.requests.post", side_effect=[limited, successful]
        ) as post, patch("app.time.sleep") as sleep:
            result = app.evaluate("profile", {
                "title": "ML Engineer", "company": "X", "location": "Remote",
                "posted_at": "", "description": "Python and ML",
            })
        self.assertEqual(result, payload)
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_evaluate_rejects_invalid_score(self):
        payload = {
            "fit_score": 9, "income_score": 3, "ai_score": 5, "low_stress_score": 2,
            "recommendation": "CONSIDER",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "app.requests.post", return_value=self._response(payload)
        ):
            with self.assertRaises(ValueError):
                app.evaluate("profile", {"title": "Role", "company": "", "location": "",
                    "posted_at": "", "description": "Description"})

    def test_evaluate_rejects_invalid_recommendation(self):
        payload = {
            "fit_score": 4, "income_score": 3, "ai_score": 5, "low_stress_score": 2,
            "recommendation": "MAYBE",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "app.requests.post", return_value=self._response(payload)
        ):
            with self.assertRaises(ValueError):
                app.evaluate("profile", {"title": "Role", "company": "", "location": "",
                    "posted_at": "", "description": "Description"})


class OutputTests(unittest.TestCase):
    def test_save_writes_json_and_csv(self):
        results = [{
            "title": "ML Engineer", "company": "Example", "fit_score": 4,
            "recommendation": "APPLY", "evidence": ["Python", "ML"],
            "inferences": [], "unknowns": [], "strengths": ["Relevant"],
            "risks": [],
        }]
        with tempfile.TemporaryDirectory() as directory, patch.object(
            app, "OUTPUT_DIR", Path(directory) / "results"
        ):
            app.save(results)
            json_path = Path(directory) / "results" / "job_results.json"
            csv_path = Path(directory) / "results" / "job_results.csv"
            self.assertTrue(json_path.is_file())
            self.assertTrue(csv_path.is_file())
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), results)
            self.assertIn("ML Engineer", csv_path.read_text(encoding="utf-8-sig"))
            self.assertIn("Python | ML", csv_path.read_text(encoding="utf-8-sig"))



class MainFlowTests(unittest.TestCase):
    def test_main_collects_evaluates_deduplicates_and_saves(self):
        jobs = [
            {"title": "Role A", "company": "A", "url": "https://example.test/a",
             "description": "Python role"},
            {"title": "Role A duplicate", "company": "A", "url": "https://example.test/a",
             "description": "Duplicate"},
            {"title": "Incomplete", "company": "B", "url": "https://example.test/b",
             "description": ""},
        ]
        evaluation = {
            "fit_score": 4, "income_score": 3, "ai_score": 5, "low_stress_score": 4,
            "assessment": "Good match", "evidence": [], "inferences": [], "unknowns": [],
            "strengths": [], "risks": [], "recommendation": "APPLY",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "APIFY_API_TOKEN": "test-token", "APIFY_TASK_ID": "test-task",
            "GEMINI_API_KEY": "test-key",
        }), patch.object(app, "OUTPUT_DIR", Path(directory) / "results"), patch.object(
            app, "load_profile", return_value="test profile"
        ), patch.object(app, "start_apify", return_value="dataset-id"), patch.object(
            app, "get_jobs", return_value=jobs
        ), patch.object(app, "screen_job", return_value={"keep": True, "reason": "Relevant"}) as screen_job, patch.object(app, "evaluate", return_value=evaluation) as evaluate, patch("app.time.sleep"):
            app.main()
            self.assertEqual(screen_job.call_count, 1)
            evaluate.assert_called_once()
            saved = json.loads((Path(directory) / "results" / "job_results.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["title"], "Role A")
            self.assertEqual(saved[0]["recommendation"], "APPLY")

    def test_main_rejected_job_is_not_evaluated_or_saved(self):
        jobs = [{
            "title": "Store Manager", "company": "Example",
            "url": "https://example.test/retail", "description": "Manage a retail store",
        }]
        rejected = {"keep": False, "reason": "Ruolo non pertinente"}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "APIFY_API_TOKEN": "test-token", "APIFY_TASK_ID": "test-task",
            "GEMINI_API_KEY": "test-key",
        }), patch.object(app, "OUTPUT_DIR", Path(directory) / "results"), patch.object(
            app, "load_profile", return_value="AI engineer profile"
        ), patch.object(app, "start_apify", return_value="dataset-id"), patch.object(
            app, "get_jobs", return_value=jobs
        ), patch.object(app, "screen_job", return_value=rejected) as screen_job, patch.object(
            app, "evaluate"
        ) as evaluate, patch("app.time.sleep"):
            app.main()
            screen_job.assert_called_once()
            evaluate.assert_not_called()
            saved = json.loads(
                (Path(directory) / "results" / "job_results.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved, [])
            csv_text = (
                Path(directory) / "results" / "job_results.csv"
            ).read_text(encoding="utf-8-sig")
            self.assertNotIn("Store Manager", csv_text)

if __name__ == "__main__":
    unittest.main()
