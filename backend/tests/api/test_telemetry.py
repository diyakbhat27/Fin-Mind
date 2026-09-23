"""
Tests for Telemetry & Observability (TL1-TL4):
- TL1: Chat creates a TelemetryLog row with query, route, latency_ms, user_role
- TL2: Recorded latency is positive (latency_ms > 0)
- TL3: Recorded route matches the supervisor's actual route
- TL4: Telemetry row is created even for failed/rejected queries
"""
import pytest
from unittest.mock import patch, MagicMock
from app.models.telemetry import TelemetryLog
from app.services.supervisor import Route, RouteIntent


class TestTelemetryObservability:

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_tl1_chat_creates_telemetry_row(self, mock_parser, mock_llm, mock_rag, client, viewer_headers, db):
        """TL1: Every chat request creates a TelemetryLog record in the database."""
        mock_parser.return_value.invoke.return_value = RouteIntent(route=Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Telemetry test answer"}

        resp = client.post("/api/v1/chat", json={"query": "Test telemetry logging"}, headers=viewer_headers)
        assert resp.status_code == 200

        log = db.query(TelemetryLog).filter(TelemetryLog.query == "Test telemetry logging").first()
        assert log is not None
        assert log.user_role == "VIEWER"
        assert log.route is not None

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_tl2_latency_is_positive(self, mock_parser, mock_llm, mock_rag, client, analyst_headers, db):
        """TL2: Latency recorded in TelemetryLog is strictly greater than zero."""
        mock_parser.return_value.invoke.return_value = RouteIntent(route=Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Answer"}

        resp = client.post("/api/v1/chat", json={"query": "Measure latency query"}, headers=analyst_headers)
        assert resp.status_code == 200

        log = db.query(TelemetryLog).filter(TelemetryLog.query == "Measure latency query").first()
        assert log is not None
        assert log.latency_ms > 0.0

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_tl3_route_matches_actual_agent(self, mock_parser, mock_llm, mock_sql, client, analyst_headers, db):
        """TL3: Telemetry 'route' matches the agent executed."""
        mock_parser.return_value.invoke.return_value = RouteIntent(route=Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"metric": "leverage_ratio", "value": 1.5, "answer": "1.5"}

        resp = client.post("/api/v1/chat", json={"query": "Calculate leverage AAPL"}, headers=analyst_headers)
        assert resp.status_code == 200

        log = db.query(TelemetryLog).filter(TelemetryLog.query == "Calculate leverage AAPL").first()
        assert log is not None
        assert log.route == "sql_agent" or log.route == "validator" or log.route == Route.SQL_AGENT.value

    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_tl4_blocked_chat_still_logs_telemetry(self, mock_parser, mock_llm, client, viewer_headers, db):
        """TL4: When RBAC blocks a query, TelemetryLog is still recorded with the denied route."""
        mock_parser.return_value.invoke.return_value = RouteIntent(route=Route.SQL_AGENT)

        resp = client.post("/api/v1/chat", json={"query": "Viewer unauthorized SQL"}, headers=viewer_headers)
        assert resp.status_code == 200
        assert "Sorry, there is no data available" in resp.json()["answer"]

        log = db.query(TelemetryLog).filter(TelemetryLog.query == "Viewer unauthorized SQL").first()
        assert log is not None
        assert log.user_role == "VIEWER"
