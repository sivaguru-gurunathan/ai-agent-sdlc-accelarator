import unittest
from src.models.schemas import validate_request, AnalyzeRequest
from src.utils.github_utils import validate_github_url, extract_repo_name


class TestSchemas(unittest.TestCase):
    def test_validate_request_success(self):
        payload = {
            "github_url": "https://github.com/username/repo",
            "agent_type": "planning",
            "options": {"include_features": True},
        }
        request_data = validate_request(payload)
        self.assertIsInstance(request_data, AnalyzeRequest)
        self.assertEqual(request_data.github_url, payload["github_url"])
        self.assertEqual(request_data.agent_type, payload["agent_type"])

    def test_validate_request_missing_url(self):
        with self.assertRaises(ValueError):
            validate_request({"agent_type": "planning"})


class TestGithubUtils(unittest.TestCase):
    def test_validate_github_url_valid(self):
        self.assertTrue(validate_github_url("https://github.com/user/repo"))
        self.assertTrue(validate_github_url("https://github.com/user/repo.git"))

    def test_validate_github_url_invalid(self):
        self.assertFalse(validate_github_url("http://github.com/user/repo"))
        self.assertFalse(validate_github_url("https://gitlab.com/user/repo"))

    def test_extract_repo_name(self):
        self.assertEqual(extract_repo_name("https://github.com/user/repo"), "user/repo")
        self.assertEqual(extract_repo_name("https://github.com/user/repo.git"), "user/repo")


if __name__ == "__main__":
    unittest.main()
