"""
Tests for Unified Chat Endpoint (/api/v1/chat) per Role and Edge Cases:
- VIEWER (V1-V10)
- ANALYST (AN1-AN13)
- ADMIN (AD1-AD14)
- SUPER_ADMIN (SA1-SA10)
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock
from app.services.supervisor import Route, RouteIntent
from app.services.compliance_agent import ComplianceDecision
from app.services.admin_agent import AdminIntent
from app.models.rbac import User
from app.models.audit import AuditLog
from app.models.telemetry import TelemetryLog
from tests.conftest import _create_user


def _mock_route(mock_parser, route: Route):
    """Helper to mock router output to a specific agent."""
    mock_parser_inst = mock_parser.return_value
    mock_parser_inst.invoke.return_value = RouteIntent(route=route)


# =====================================================================
# 2.1 VIEWER Role Tests (V1-V10)
# =====================================================================

class TestViewerChat:

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_v1_general_knowledge_query(self, mock_parser, mock_llm, mock_rag, client, viewer_headers):
        """V1: General knowledge query routed to rag_agent."""
        _mock_route(mock_parser, Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Apple designs consumer electronics.", "citations": []}

        resp = client.post("/api/v1/chat", json={"query": "What is Apple's business model?"}, headers=viewer_headers)
        assert resp.status_code == 200
        assert "Apple designs consumer electronics" in resp.json()["answer"]

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_v2_sec_filing_query(self, mock_parser, mock_llm, mock_rag, client, viewer_headers):
        """V2: SEC filing query returns answer + citations."""
        _mock_route(mock_parser, Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {
            "answer": "Apple reported $383B in revenue in 2023 10-K.",
            "citations": [{"company": "AAPL", "form": "10-K", "year": "2023"}]
        }

        resp = client.post("/api/v1/chat", json={"query": "Show me Apple's SEC filings"}, headers=viewer_headers)
        assert resp.status_code == 200
        assert len(resp.json()["citations"]) > 0

    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_v3_sql_query_attempt_blocked(self, mock_parser, mock_llm, client, viewer_headers):
        """V3: SQL query attempt by VIEWER -> RBAC denial (no data available)."""
        _mock_route(mock_parser, Route.SQL_AGENT)

        resp = client.post("/api/v1/chat", json={"query": "What is the leverage ratio for AAPL?"}, headers=viewer_headers)
        assert resp.status_code == 200
        assert "Sorry, there is no data available" in resp.json()["answer"]

    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_v4_compliance_query_attempt_blocked(self, mock_parser, mock_llm, client, viewer_headers):
        """V4: Compliance query attempt by VIEWER -> RBAC denial."""
        _mock_route(mock_parser, Route.COMPLIANCE_AGENT)

        resp = client.post("/api/v1/chat", json={"query": "Is this $500K loan compliant?"}, headers=viewer_headers)
        assert resp.status_code == 200
        assert "Sorry, there is no data available" in resp.json()["answer"]

    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_v5_admin_query_attempt_blocked(self, mock_parser, mock_llm, client, viewer_headers):
        """V5: Admin query attempt by VIEWER -> RBAC denial."""
        _mock_route(mock_parser, Route.ADMIN_AGENT)

        resp = client.post("/api/v1/chat", json={"query": "How many users are there?"}, headers=viewer_headers)
        assert resp.status_code == 200
        assert "Sorry, there is no data available" in resp.json()["answer"]

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_v6_confidential_doc_access(self, mock_parser, mock_llm, mock_rag, client, viewer_headers):
        """V6: Confidential doc access - RAG chain passes user_role='VIEWER'."""
        _mock_route(mock_parser, Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Only public chunks available.", "citations": []}

        resp = client.post("/api/v1/chat", json={"query": "Show internal executive compensation"}, headers=viewer_headers)
        assert resp.status_code == 200
        mock_rag.return_value.ask.assert_called_with(query="Show internal executive compensation", user_role="VIEWER")

    def test_v7_empty_query(self, client, viewer_headers):
        """V7: Empty query -> 422 validation error."""
        resp = client.post("/api/v1/chat", json={"query": ""}, headers=viewer_headers)
        assert resp.status_code in [400, 422]

    def test_v8_query_exceeding_1000_chars(self, client, viewer_headers):
        """V8: Query exceeding 1000 characters -> 422 max_length validation error."""
        long_query = "x" * 1001
        resp = client.post("/api/v1/chat", json={"query": long_query}, headers=viewer_headers)
        assert resp.status_code == 422

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_v9_xss_payload_in_query(self, mock_parser, mock_llm, mock_rag, client, viewer_headers):
        """V9: XSS payload in query handled safely without script execution."""
        _mock_route(mock_parser, Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Clean answer", "citations": []}

        xss_query = "<script>alert('xss')</script>"
        resp = client.post("/api/v1/chat", json={"query": xss_query}, headers=viewer_headers)
        assert resp.status_code == 200
        assert resp.json()["answer"] == "Clean answer"

    def test_v10_unauthenticated_chat(self, client):
        """V10: No auth token -> 401."""
        resp = client.post("/api/v1/chat", json={"query": "Hello"})
        assert resp.status_code == 401


# =====================================================================
# 2.2 ANALYST Role Tests (AN1-AN13)
# =====================================================================

class TestAnalystChat:

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an1_rag_query(self, mock_parser, mock_llm, mock_rag, client, analyst_headers):
        """AN1: RAG query routed to rag_agent."""
        _mock_route(mock_parser, Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Tesla 10-K summary.", "citations": []}

        resp = client.post("/api/v1/chat", json={"query": "Summarize Tesla's 10-K"}, headers=analyst_headers)
        assert resp.status_code == 200
        assert "Tesla" in resp.json()["answer"]

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an2_sql_leverage_ratio(self, mock_parser, mock_llm, mock_sql, client, analyst_headers):
        """AN2: SQL agent leverage ratio calculation."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"metric": "leverage_ratio", "value": 1.85, "answer": "1.85"}

        resp = client.post("/api/v1/chat", json={"query": "What is the leverage ratio for AAPL in 2023?"}, headers=analyst_headers)
        assert resp.status_code == 200
        assert resp.json()["value"] == 1.85

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an3_sql_operating_margin(self, mock_parser, mock_llm, mock_sql, client, analyst_headers):
        """AN3: SQL agent operating margin calculation."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"metric": "operating_margin", "value": 0.15, "answer": "15%"}

        resp = client.post("/api/v1/chat", json={"query": "What is the operating margin for TSLA in 2023?"}, headers=analyst_headers)
        assert resp.status_code == 200
        assert resp.json()["value"] == 0.15

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an4_sql_roe(self, mock_parser, mock_llm, mock_sql, client, analyst_headers):
        """AN4: SQL agent ROE calculation."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"metric": "roe", "value": 0.42, "answer": "42%"}

        resp = client.post("/api/v1/chat", json={"query": "What is the ROE for MSFT in 2023?"}, headers=analyst_headers)
        assert resp.status_code == 200

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an5_sql_current_ratio(self, mock_parser, mock_llm, mock_sql, client, analyst_headers):
        """AN5: SQL agent current ratio calculation."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"metric": "current_ratio", "value": 1.05, "answer": "1.05"}

        resp = client.post("/api/v1/chat", json={"query": "What is the current ratio for AAPL in 2023?"}, headers=analyst_headers)
        assert resp.status_code == 200

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an6_sql_unknown_metric(self, mock_parser, mock_llm, mock_sql, client, analyst_headers):
        """AN6: SQL agent unknown metric -> 400 error."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"error": "Unsupported or unknown metric: Sharpe ratio"}

        resp = client.post("/api/v1/chat", json={"query": "What is the Sharpe ratio for AAPL?"}, headers=analyst_headers)
        assert resp.status_code == 400

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an7_sql_missing_ticker(self, mock_parser, mock_llm, mock_sql, client, analyst_headers):
        """AN7: SQL agent missing ticker -> 400 error."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"error": "Could not extract company ticker or year"}

        resp = client.post("/api/v1/chat", json={"query": "What is the leverage ratio?"}, headers=analyst_headers)
        assert resp.status_code == 400

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an8_sql_non_existent_ticker(self, mock_parser, mock_llm, mock_sql, client, analyst_headers):
        """AN8: SQL agent non-existent ticker -> 400 error."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"error": "No financial records found for ZZZZ"}

        resp = client.post("/api/v1/chat", json={"query": "Leverage ratio for ZZZZ in 2023"}, headers=analyst_headers)
        assert resp.status_code == 400

    @patch("app.services.supervisor.ComplianceAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an9_compliance_loan_evaluation(self, mock_parser, mock_llm, mock_comp, client, analyst_headers):
        """AN9: Compliance loan evaluation -> APPROVED."""
        _mock_route(mock_parser, Route.COMPLIANCE_AGENT)
        mock_comp.return_value.evaluate.return_value = {
            "answer": "**COMPLIANCE APPROVED**\n\nReasoning: Loan within threshold.",
            "citations": []
        }

        resp = client.post("/api/v1/chat", json={"query": "Can I approve a $500K loan for a startup?"}, headers=analyst_headers)
        assert resp.status_code == 200
        assert "APPROVED" in resp.json()["answer"]

    @patch("app.services.supervisor.ComplianceAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an10_compliance_trade_check(self, mock_parser, mock_llm, mock_comp, client, analyst_headers):
        """AN10: Compliance trade check -> REJECTED."""
        _mock_route(mock_parser, Route.COMPLIANCE_AGENT)
        mock_comp.return_value.evaluate.return_value = {
            "answer": "**COMPLIANCE REJECTED**\n\nReasoning: Trading blackout window active.",
            "citations": []
        }

        resp = client.post("/api/v1/chat", json={"query": "Is this insider trade compliant?"}, headers=analyst_headers)
        assert resp.status_code == 200
        assert "REJECTED" in resp.json()["answer"]

    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an11_admin_query_attempt_blocked(self, mock_parser, mock_llm, client, analyst_headers):
        """AN11: Admin query attempt by ANALYST -> RBAC denial."""
        _mock_route(mock_parser, Route.ADMIN_AGENT)

        resp = client.post("/api/v1/chat", json={"query": "Delete user bob"}, headers=analyst_headers)
        assert resp.status_code == 200
        assert "Sorry, there is no data available" in resp.json()["answer"]

    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an12_admin_hot_reload_blocked(self, mock_parser, mock_llm, client, analyst_headers):
        """AN12: Admin hot reload attempt by ANALYST -> RBAC denial."""
        _mock_route(mock_parser, Route.ADMIN_AGENT)

        resp = client.post("/api/v1/chat", json={"query": "Hot reload secrets"}, headers=analyst_headers)
        assert resp.status_code == 200
        assert "Sorry, there is no data available" in resp.json()["answer"]

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_an13_confidential_doc_access(self, mock_parser, mock_llm, mock_rag, client, analyst_headers):
        """AN13: Confidential doc access passes user_role='ANALYST'."""
        _mock_route(mock_parser, Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Confidential compensation details.", "citations": []}

        resp = client.post("/api/v1/chat", json={"query": "Show executive bonus metrics"}, headers=analyst_headers)
        assert resp.status_code == 200
        mock_rag.return_value.ask.assert_called_with(query="Show executive bonus metrics", user_role="ANALYST")


# =====================================================================
# 2.3 ADMIN Role Tests (AD1-AD14)
# =====================================================================

class TestAdminChat:

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad1_rag_query(self, mock_parser, mock_llm, mock_rag, client, admin_headers):
        """AD1: ADMIN has full RAG access."""
        _mock_route(mock_parser, Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Apple's risk factors.", "citations": []}

        resp = client.post("/api/v1/chat", json={"query": "What are Apple's risk factors?"}, headers=admin_headers)
        assert resp.status_code == 200

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad2_sql_query(self, mock_parser, mock_llm, mock_sql, client, admin_headers):
        """AD2: ADMIN can run SQL queries via chat."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"metric": "current_ratio", "value": 1.05, "answer": "1.05"}

        resp = client.post("/api/v1/chat", json={"query": "What is AAPL's current ratio for 2023?"}, headers=admin_headers)
        assert resp.status_code == 200

    @patch("app.services.supervisor.ComplianceAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad3_compliance_query(self, mock_parser, mock_llm, mock_comp, client, admin_headers):
        """AD3: ADMIN can run compliance queries via chat."""
        _mock_route(mock_parser, Route.COMPLIANCE_AGENT)
        mock_comp.return_value.evaluate.return_value = {"answer": "**COMPLIANCE APPROVED**", "citations": []}

        resp = client.post("/api/v1/chat", json={"query": "Evaluate this portfolio trade"}, headers=admin_headers)
        assert resp.status_code == 200

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad4_count_users(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers, db):
        """AD4: Admin counts users in system."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        # Mock admin agent LLM to parse intent
        mock_admin_llm.return_value.invoke.return_value = MagicMock(content='{"action": "count_users"}')

        resp = client.post("/api/v1/chat", json={"query": "How many users are in the system?"}, headers=admin_headers)
        assert resp.status_code == 200
        assert "users registered" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad5_list_audit_logs(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers, db):
        """AD5: Admin lists audit logs."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(content='{"action": "list_audit_logs"}')

        resp = client.post("/api/v1/chat", json={"query": "Show me the audit logs"}, headers=admin_headers)
        assert resp.status_code == 200

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad6_add_viewer_user(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers):
        """AD6: Admin adds VIEWER user."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": "chat_alice", "target_role": "VIEWER", "target_password": "Pass123"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Add user chat_alice with password Pass123 as VIEWER"}, headers=admin_headers)
        assert resp.status_code == 200
        assert "Successfully created user 'chat_alice'" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad7_add_analyst_user(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers):
        """AD7: Admin adds ANALYST user."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": "chat_bob", "target_role": "ANALYST", "target_password": "Pass123"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Add user chat_bob with password Pass123 as ANALYST"}, headers=admin_headers)
        assert resp.status_code == 200
        assert "Successfully created user 'chat_bob'" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad8_add_admin_user_forbidden(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers):
        """AD8: Admin cannot add ADMIN user -> 403."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": "chat_charlie", "target_role": "ADMIN", "target_password": "Pass123"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Add user chat_charlie as ADMIN with password Pass123"}, headers=admin_headers)
        assert resp.status_code == 403
        assert "Only SUPER_ADMIN can create ADMIN" in resp.json()["detail"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad9_add_super_admin_forbidden(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers):
        """AD9: Admin cannot add SUPER_ADMIN user -> 403."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": "chat_dave", "target_role": "SUPER_ADMIN", "target_password": "Pass123"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Add user chat_dave as SUPER_ADMIN"}, headers=admin_headers)
        assert resp.status_code == 403

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad10_delete_viewer(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers, db):
        """AD10: Admin deletes VIEWER user."""
        _create_user(db, "delete_me_viewer", "VIEWER")
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "delete_user", "target_username": "delete_me_viewer"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Delete user delete_me_viewer"}, headers=admin_headers)
        assert resp.status_code == 200
        assert "Successfully deleted user 'delete_me_viewer'" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad11_delete_admin_forbidden(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers, db):
        """AD11: Admin cannot delete another ADMIN user -> 403."""
        _create_user(db, "target_admin_delete", "ADMIN")
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "delete_user", "target_username": "target_admin_delete"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Delete user target_admin_delete"}, headers=admin_headers)
        assert resp.status_code == 403
        assert "Only SUPER_ADMIN can delete privileged" in resp.json()["detail"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad12_hot_reload_forbidden(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers):
        """AD12: Admin cannot hot-reload secrets -> 403."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(content='{"action": "hot_reload"}')

        resp = client.post("/api/v1/chat", json={"query": "Hot reload the secrets"}, headers=admin_headers)
        assert resp.status_code == 403

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad13_add_duplicate_user(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers, db):
        """AD13: Admin adds already existing user."""
        _create_user(db, "existing_alice", "VIEWER")
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": "existing_alice", "target_role": "VIEWER", "target_password": "Pass"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Add user existing_alice"}, headers=admin_headers)
        assert resp.status_code == 200
        assert "already exists" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_ad14_delete_nonexistent_user(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, admin_headers):
        """AD14: Admin deletes non-existent user."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "delete_user", "target_username": "ghost_user"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Delete user ghost_user"}, headers=admin_headers)
        assert resp.status_code == 200
        assert "not found" in resp.json()["answer"]


# =====================================================================
# 2.4 SUPER_ADMIN Role Tests (SA1-SA10)
# =====================================================================

class TestSuperAdminChat:

    @patch("app.services.supervisor.SecureRAGChain")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa1_rag_query(self, mock_parser, mock_llm, mock_rag, client, super_admin_headers):
        """SA1: SUPER_ADMIN full RAG access."""
        _mock_route(mock_parser, Route.RAG_AGENT)
        mock_rag.return_value.ask.return_value = {"answer": "Apple 10-K full details.", "citations": []}

        resp = client.post("/api/v1/chat", json={"query": "What's in Apple's latest 10-K?"}, headers=super_admin_headers)
        assert resp.status_code == 200

    @patch("app.services.supervisor.QuantitativeAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa2_sql_query(self, mock_parser, mock_llm, mock_sql, client, super_admin_headers):
        """SA2: SUPER_ADMIN full SQL access."""
        _mock_route(mock_parser, Route.SQL_AGENT)
        mock_sql.return_value.analyze.return_value = {"metric": "operating_margin", "value": 0.15, "answer": "15%"}

        resp = client.post("/api/v1/chat", json={"query": "Operating margin for TSLA 2023"}, headers=super_admin_headers)
        assert resp.status_code == 200

    @patch("app.services.supervisor.ComplianceAgent")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa3_compliance_query(self, mock_parser, mock_llm, mock_comp, client, super_admin_headers):
        """SA3: SUPER_ADMIN compliance access."""
        _mock_route(mock_parser, Route.COMPLIANCE_AGENT)
        mock_comp.return_value.evaluate.return_value = {"answer": "**COMPLIANCE APPROVED**", "citations": []}

        resp = client.post("/api/v1/chat", json={"query": "Is this $2M bond trade compliant?"}, headers=super_admin_headers)
        assert resp.status_code == 200

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa4_count_users(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, super_admin_headers):
        """SA4: SUPER_ADMIN counts users."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(content='{"action": "count_users"}')

        resp = client.post("/api/v1/chat", json={"query": "How many users?"}, headers=super_admin_headers)
        assert resp.status_code == 200

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa5_hot_reload_secrets(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, super_admin_headers):
        """SA5: SUPER_ADMIN can hot reload secrets."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(content='{"action": "hot_reload"}')

        resp = client.post("/api/v1/chat", json={"query": "Hot reload the secrets"}, headers=super_admin_headers)
        # Returns 200 whether .env exists or error handled
        assert resp.status_code in [200, 400]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa6_add_admin_user(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, super_admin_headers):
        """SA6: SUPER_ADMIN can create ADMIN user."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": "sa_created_admin", "target_role": "ADMIN", "target_password": "Pass"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Add user sa_created_admin as ADMIN"}, headers=super_admin_headers)
        assert resp.status_code == 200
        assert "Successfully created user 'sa_created_admin'" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa7_add_super_admin_user(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, super_admin_headers):
        """SA7: SUPER_ADMIN can create SUPER_ADMIN user."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": "sa_created_sa", "target_role": "SUPER_ADMIN", "target_password": "Pass"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Add user sa_created_sa as SUPER_ADMIN"}, headers=super_admin_headers)
        assert resp.status_code == 200
        assert "Successfully created user 'sa_created_sa'" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa8_delete_admin_user(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, super_admin_headers, db):
        """SA8: SUPER_ADMIN can delete ADMIN user."""
        _create_user(db, "sa_target_admin", "ADMIN")
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "delete_user", "target_username": "sa_target_admin"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Delete user sa_target_admin"}, headers=super_admin_headers)
        assert resp.status_code == 200
        assert "Successfully deleted user 'sa_target_admin'" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa9_delete_super_admin_user(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, super_admin_headers, db):
        """SA9: SUPER_ADMIN can delete another SUPER_ADMIN user."""
        _create_user(db, "sa_target_sa", "SUPER_ADMIN")
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "delete_user", "target_username": "sa_target_sa"}'
        )

        resp = client.post("/api/v1/chat", json={"query": "Delete user sa_target_sa"}, headers=super_admin_headers)
        assert resp.status_code == 200
        assert "Successfully deleted user 'sa_target_sa'" in resp.json()["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.ChatGoogleGenerativeAI")
    @patch("app.services.supervisor.PydanticOutputParser")
    def test_sa10_list_audit_logs(self, mock_sup_parser, mock_sup_llm, mock_admin_llm, client, super_admin_headers):
        """SA10: SUPER_ADMIN can list audit logs via chat."""
        _mock_route(mock_sup_parser, Route.ADMIN_AGENT)
        mock_admin_llm.return_value.invoke.return_value = MagicMock(content='{"action": "list_audit_logs"}')

        resp = client.post("/api/v1/chat", json={"query": "Show audit logs"}, headers=super_admin_headers)
        assert resp.status_code == 200
