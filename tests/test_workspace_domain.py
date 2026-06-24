from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from data_platform.chat_backend.domains.workspace import chart_render
from data_platform.chat_backend.domains.workspace import service as workspace_service

class ChartRenderTests(unittest.TestCase):
    def test_trend_sparkline_renders_svg(self) -> None:
        svg = chart_render.render_trend_sparkline([1, 2, 3, 2, 5], label="销量")
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("</svg>", svg)
        self.assertIn("path", svg)

    def test_trend_sparkline_insufficient_points_placeholder(self) -> None:
        svg = chart_render.render_trend_sparkline([1])
        self.assertIn("趋势数据不足", svg)

    def test_price_band_with_current_marker(self) -> None:
        svg = chart_render.render_price_band(10, 30, 22, label="价格带")
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("circle", svg)

    def test_competition_gauge_clamps_and_renders(self) -> None:
        svg = chart_render.render_competition_gauge(1.7)
        self.assertIn("100%", svg)

    def test_forecast_band_renders(self) -> None:
        svg = chart_render.render_forecast_band([1, 2, 3], [3, 4, 5], [2, 3, 4])
        self.assertTrue(svg.startswith("<svg"))

    def test_risk_lights_renders(self) -> None:
        svg = chart_render.render_risk_lights(
            [{"name": "退货率", "level": "warn"}, {"name": "侵权", "level": "bad"}]
        )
        self.assertIn("退货率", svg)

    def test_any_bad_input_falls_back_to_placeholder_not_raises(self) -> None:
        # 证据图渲染必须永不抛错
        self.assertTrue(chart_render.render_trend_sparkline("not-a-list").startswith("<svg"))
        self.assertTrue(chart_render.render_price_band("x", "y").startswith("<svg"))
        self.assertTrue(chart_render.render_competition_gauge(None).startswith("<svg"))

    def test_text_is_escaped(self) -> None:
        svg = chart_render.render_risk_lights([{"name": "<script>", "level": "bad"}])
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)


class SerializerTests(unittest.TestCase):
    def test_serialize_workspace_maps_json_columns(self) -> None:
        now = datetime(2026, 6, 23, 1, 2, 3, tzinfo=timezone.utc)
        row = {
            "workspace_id": "ws_1",
            "theme_key": "blender",
            "title": "便携榨汁机",
            "source_run_id": "run_1",
            "brief_json": {"product_theme": "blender"},
            "evidence_json": {"trend_series": [1, 2]},
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        out = workspace_service.serialize_workspace(row)
        self.assertEqual(out["brief"], {"product_theme": "blender"})
        self.assertEqual(out["evidence"], {"trend_series": [1, 2]})
        self.assertEqual(out["created_at"], now.isoformat())

    def test_serialize_watch_defaults_when_missing(self) -> None:
        out = workspace_service.serialize_watch(None)
        self.assertFalse(out["watch_enabled"])
        self.assertEqual(out["watch_config"], {})


class UpsertWorkspaceTests(unittest.TestCase):
    @patch("data_platform.chat_backend.domains.workspace.service.repository")
    def test_upsert_inserts_when_no_existing(self, repo: MagicMock) -> None:
        repo.find_active_workspace_by_theme.return_value = None
        repo.insert_workspace.return_value = {
            "workspace_id": "ws_new",
            "theme_key": "blender",
            "title": "便携榨汁机",
            "brief_json": {},
            "evidence_json": {},
            "status": "active",
            "created_at": None,
            "updated_at": None,
        }
        result = workspace_service.upsert_workspace_from_analysis(
            conn=object(), user_id="u1", theme_key="blender", title="便携榨汁机"
        )
        repo.lock_user_theme.assert_called_once()
        repo.insert_workspace.assert_called_once()
        repo.update_workspace_payload.assert_not_called()
        self.assertEqual(result["workspace_id"], "ws_new")

    @patch("data_platform.chat_backend.domains.workspace.service.repository")
    def test_upsert_updates_when_existing(self, repo: MagicMock) -> None:
        repo.find_active_workspace_by_theme.return_value = {"workspace_id": "ws_old"}
        repo.update_workspace_payload.return_value = {
            "workspace_id": "ws_old",
            "theme_key": "blender",
            "title": "便携榨汁机 v2",
            "brief_json": {},
            "evidence_json": {},
            "status": "active",
            "created_at": None,
            "updated_at": None,
        }
        result = workspace_service.upsert_workspace_from_analysis(
            conn=object(), user_id="u1", theme_key="blender", title="便携榨汁机 v2"
        )
        repo.update_workspace_payload.assert_called_once()
        repo.insert_workspace.assert_not_called()
        self.assertEqual(result["workspace_id"], "ws_old")


class EvidenceChartTests(unittest.TestCase):
    EVIDENCE = {
        "trend_series": [{"value": 1}, {"value": 3}, {"value": 2}],
        "price_band": {"low": 10, "high": 30, "current": 22},
        "competition_score": 0.4,
        "forecast_band": {"lower": [1, 2], "upper": [3, 4], "mid": [2, 3]},
        "risk_lights": [{"name": "退货率", "level": "warn"}],
    }

    def test_chart_has_data_detection(self) -> None:
        for kind in ("trend", "price", "competition", "forecast", "risk"):
            self.assertTrue(workspace_service.chart_has_data(self.EVIDENCE, kind), kind)
        self.assertFalse(workspace_service.chart_has_data({}, "trend"))
        self.assertFalse(workspace_service.chart_has_data({"price_band": {"low": 1}}, "price"))

    def test_render_workspace_chart_returns_svg(self) -> None:
        for kind in ("trend", "price", "competition", "forecast", "risk"):
            svg = workspace_service.render_workspace_chart(self.EVIDENCE, kind)
            self.assertTrue(svg.startswith("<svg"), kind)

    def test_extract_series_values_handles_dicts_and_scalars(self) -> None:
        self.assertEqual(
            workspace_service._extract_series_values([{"value": 1}, 2, {"y": 3}]), [1, 2, 3]
        )

    @patch.object(workspace_service, "sign_chart_token", side_effect=lambda w, k: f"tok-{k}")
    def test_build_evidence_chart_links_caps_and_prioritizes(self, _sign: MagicMock) -> None:
        links = workspace_service.build_evidence_chart_links(
            "ws_1", self.EVIDENCE, public_base_url="https://x.test/", limit=3
        )
        self.assertEqual(len(links), 3)
        # 优先级顺序：trend -> competition -> price
        self.assertEqual([item["kind"] for item in links], ["trend", "competition", "price"])
        self.assertTrue(links[0]["svg_url"].startswith("https://x.test/portal/api/evidence/chart/"))

    def test_build_evidence_chart_links_empty_when_no_data(self) -> None:
        self.assertEqual(
            workspace_service.build_evidence_chart_links("ws_1", {}, public_base_url="https://x.test"),
            [],
        )


class ChartTokenTests(unittest.TestCase):
    def test_sign_then_verify_roundtrip(self) -> None:
        with patch("data_platform.chat_backend.domains.workspace.tokens.INTERNAL_SERVICE_SECRET", "s3cr3t"):
            from data_platform.chat_backend.domains.workspace import tokens

            token = tokens.sign_chart_token("ws_1", "trend")
            claims = tokens.verify_chart_token(token)
            self.assertEqual(claims, {"workspace_id": "ws_1", "chart_kind": "trend"})

    def test_tampered_token_rejected(self) -> None:
        with patch("data_platform.chat_backend.domains.workspace.tokens.INTERNAL_SERVICE_SECRET", "s3cr3t"):
            from data_platform.chat_backend.domains.workspace import tokens

            token = tokens.sign_chart_token("ws_1", "trend")
            payload_b64, _sig = token.split(".")
            forged = f"{payload_b64}.{'A' * 10}"
            self.assertIsNone(tokens.verify_chart_token(forged))

    def test_wrong_secret_rejected(self) -> None:
        with patch("data_platform.chat_backend.domains.workspace.tokens.INTERNAL_SERVICE_SECRET", "s3cr3t"):
            from data_platform.chat_backend.domains.workspace import tokens

            token = tokens.sign_chart_token("ws_1", "trend")
        with patch("data_platform.chat_backend.domains.workspace.tokens.INTERNAL_SERVICE_SECRET", "other"):
            self.assertIsNone(tokens.verify_chart_token(token))

    def test_expired_token_rejected(self) -> None:
        with patch("data_platform.chat_backend.domains.workspace.tokens.INTERNAL_SERVICE_SECRET", "s3cr3t"):
            from data_platform.chat_backend.domains.workspace import tokens

            token = tokens.sign_chart_token("ws_1", "trend", ttl_seconds=1)
            with patch("data_platform.chat_backend.domains.workspace.tokens.time.time", return_value=9999999999):
                self.assertIsNone(tokens.verify_chart_token(token))


if __name__ == "__main__":
    unittest.main()
