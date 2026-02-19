import unittest
from fastapi.testclient import TestClient

from backend.main import app


class AgentApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_agent_reel_endpoint(self):
        payload = {
            "source_video": "sample.mp4",
            "platform": "reels",
            "template": "viral-hook-v1",
            "objective": "maximize watch-time",
        }
        response = self.client.post("/api/agent/reel", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("plan", data)
        self.assertIn("score", data)
        self.assertIn("execution", data)
        self.assertIn("candidates", data)
        self.assertGreaterEqual(len(data["candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
