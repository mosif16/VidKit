import json
import unittest
from pathlib import Path

from backend.agent.models import AgentReelRequest
from backend.agent.planner import create_reel_plan, create_candidate_plans
from backend.agent.scorer import build_edit_suggestions, build_score_report, score_reel_plan
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

    def test_candidate_generation(self):
        req = AgentReelRequest(source_video="sample.mp4", platform="shorts", candidates=3)
        plans = create_candidate_plans(req)
        self.assertEqual(len(plans), 3)
        self.assertTrue(all(p.id for p in plans))

    def test_orchestrator_response_shape(self):
        req = AgentReelRequest(source_video="sample.mp4", platform="shorts", candidates=3)
        resp = run_agent_reel_dry_run(req)
        self.assertEqual(resp.status, "ok")
        self.assertTrue(resp.execution.dry_run)
        self.assertGreaterEqual(len(resp.execution.stages), 3)
        self.assertGreaterEqual(len(resp.candidates), 1)
        self.assertIsNotNone(resp.score_report)
        self.assertIsNotNone(resp.edit_suggestions)

    def test_score_report_matches_contract_shape(self):
        req = AgentReelRequest(source_video="sample.mp4", platform="reels")
        plan = create_reel_plan(req)
        score = score_reel_plan(plan)
        report = build_score_report(plan, score).model_dump()

        required = {"pqs", "eps", "vps", "feature_contributions", "failed_gates", "recommendations"}
        self.assertTrue(required.issubset(set(report.keys())))

    def test_edit_suggestions_matches_contract_shape(self):
        req = AgentReelRequest(source_video="sample.mp4", platform="reels")
        plan = create_reel_plan(req)
        suggestions = build_edit_suggestions(plan).model_dump()

        self.assertIn("suggestions", suggestions)
        self.assertGreaterEqual(len(suggestions["suggestions"]), 1)

    def test_weights_config_exists_and_loadable(self):
        cfg = Path("backend/config/viral_scoring_weights.json")
        self.assertTrue(cfg.exists())
        data = json.loads(cfg.read_text())
        self.assertIn("pqs", data)
        self.assertIn("eps", data)


if __name__ == "__main__":
    unittest.main()
