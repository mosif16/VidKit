import unittest

from backend.agent.models import AgentReelRequest
from backend.agent.planner import create_reel_plan
from backend.agent.scorer import score_reel_plan
from backend.agent.orchestrator import run_agent_reel_dry_run


class AgentReelEngineTests(unittest.TestCase):
    def test_planner_returns_reel_plan(self):
        req = AgentReelRequest(source_video="sample.mp4", platform="reels")
        plan = create_reel_plan(req)
        self.assertEqual(plan.platform, "reels")
        self.assertTrue(plan.hook.text)
        self.assertGreaterEqual(plan.cuts.scene_count_target, 4)

    def test_scorer_returns_valid_range(self):
        req = AgentReelRequest(source_video="sample.mp4", platform="tiktok")
        plan = create_reel_plan(req)
        score = score_reel_plan(plan)
        self.assertGreaterEqual(score.total, 0)
        self.assertLessEqual(score.total, 100)

    def test_orchestrator_response_shape(self):
        req = AgentReelRequest(source_video="sample.mp4", platform="shorts")
        resp = run_agent_reel_dry_run(req)
        self.assertEqual(resp.status, "ok")
        self.assertTrue(resp.execution.dry_run)
        self.assertGreaterEqual(len(resp.execution.stages), 3)


if __name__ == "__main__":
    unittest.main()
