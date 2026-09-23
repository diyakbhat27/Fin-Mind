"""
Tests for Agent-Specific Edge Cases:
- SQL Agent (SQ1-SQ4)
- Compliance Agent (CP1-CP4)
- Admin Agent (AA1-AA5)
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.sql_agent import QuantitativeAgent, MetricType, QuantitativeIntent
from app.services.compliance_agent import ComplianceAgent, ComplianceDecision
from app.services.admin_agent import AdminAgent, AdminIntent
from app.services.supervisor import sql_node, AgentState
from app.db.queries import FinancialMetricsEngine
from app.models.financials import FinancialReport


# =====================================================================
# 7.1 SQL Agent Edge Cases (SQ1-SQ4)
# =====================================================================

class TestSQLAgentEdges:

    def test_sq1_no_db_session_in_supervisor(self):
        """SQ1: sql_node in supervisor returns error when db_session is missing."""
        state = {
            "query": "What is the leverage ratio for AAPL in 2023?",
            "user_role": "ANALYST",
            "db_session": None,
            "next_node": None,
            "final_response": None
        }
        res = sql_node(state)
        assert "error" in res["final_response"]
        assert "Database session missing" in res["final_response"]["error"]

    def test_sq2_division_by_zero_handling(self, db):
        """SQ2: Zero total equity returns graceful error instead of ZeroDivisionError."""
        # Create a report with zero equity
        report = FinancialReport(
            ticker="ZERO_EQ",
            fiscal_year=2023,
            total_liabilities=100000.0,
            total_equity=0.0,
            operating_income=5000.0,
            net_revenue=50000.0,
            total_current_assets=20000.0,
            total_current_liabilities=10000.0,
            net_income=3000.0
        )
        db.add(report)
        db.commit()

        engine = FinancialMetricsEngine(db)
        res = engine.get_leverage_ratio("ZERO_EQ", 2023)
        assert "error" in res
        assert "missing or zero" in res["error"]

    def test_sq3_future_year_no_data(self, db):
        """SQ3: Future year with no records returns graceful error."""
        engine = FinancialMetricsEngine(db)
        res = engine.get_leverage_ratio("AAPL", 2050)
        assert "error" in res
        assert "Report not found" in res["error"]

    def test_sq4_negative_year_no_data(self, db):
        """SQ4: Negative year returns graceful error."""
        engine = FinancialMetricsEngine(db)
        res = engine.get_operating_margin("AAPL", -1)
        assert "error" in res
        assert "Report not found" in res["error"]


# =====================================================================
# 7.2 Compliance Agent Edge Cases (CP1-CP4)
# =====================================================================

class TestComplianceAgentEdges:

    @patch("app.services.compliance_agent.ChatGoogleGenerativeAI")
    def test_cp1_clear_approval_scenario(self, mock_llm):
        """CP1: Clear approval scenario returns APPROVED with reasoning."""
        mock_runnable = mock_llm.return_value.with_fallbacks.return_value
        mock_runnable.invoke.return_value = MagicMock(
            content='{"status": "APPROVED", "reasoning": "Transaction complies with Rule 144A."}'
        )
        agent = ComplianceAgent(db=None)
        res = agent.evaluate("Can we trade 100 shares of index ETF?")
        assert "COMPLIANCE APPROVED" in res["answer"]
        assert "Rule 144A" in res["answer"]

    @patch("app.services.compliance_agent.ChatGoogleGenerativeAI")
    def test_cp2_clear_rejection_scenario(self, mock_llm):
        """CP2: Clear rejection scenario returns REJECTED with policy citation."""
        mock_runnable = mock_llm.return_value.with_fallbacks.return_value
        mock_runnable.invoke.return_value = MagicMock(
            content='{"status": "REJECTED", "reasoning": "Violates insider blackout period policy."}'
        )
        agent = ComplianceAgent(db=None)
        res = agent.evaluate("Can CEO sell shares 1 day before earnings release?")
        assert "COMPLIANCE REJECTED" in res["answer"]
        assert "blackout period" in res["answer"]

    @patch("app.services.compliance_agent.ChatGoogleGenerativeAI")
    def test_cp3_ambiguous_scenario(self, mock_llm):
        """CP3: Ambiguous scenario returns structured decision with reasoning."""
        mock_runnable = mock_llm.return_value.with_fallbacks.return_value
        mock_runnable.invoke.return_value = MagicMock(
            content='{"status": "REJECTED", "reasoning": "Insufficient collateral documentation provided."}'
        )
        agent = ComplianceAgent(db=None)
        res = agent.evaluate("Loan request for unlisted entity with partial guarantee")
        assert "answer" in res
        assert "Reasoning:" in res["answer"]

    @patch("app.services.compliance_agent.ChatGoogleGenerativeAI")
    def test_cp4_llm_malformed_json_fallback(self, mock_llm):
        """CP4: LLM returning non-JSON response returns graceful error."""
        mock_runnable = mock_llm.return_value.with_fallbacks.return_value
        mock_runnable.invoke.return_value = MagicMock(
            content="I cannot evaluate this scenario because it is unclear."
        )
        agent = ComplianceAgent(db=None)
        res = agent.evaluate("Some scenario")
        assert "error" in res
        assert "Compliance evaluation failed" in res["error"]


# =====================================================================
# 7.3 Admin Agent Edge Cases (AA1-AA5)
# =====================================================================

class TestAdminAgentEdges:

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    def test_aa1_no_db_session_count_users(self, mock_llm):
        """AA1: count_users without db session returns error."""
        mock_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "count_users"}'
        )
        agent = AdminAgent(db=None)
        res = agent.execute("How many users?", user_role="ADMIN")
        assert res == {"error": "Database session missing."}

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    def test_aa2_no_db_session_add_user(self, mock_llm):
        """AA2: add_user without db session returns error."""
        mock_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": "sam", "target_role": "VIEWER", "target_password": "P"}'
        )
        agent = AdminAgent(db=None)
        res = agent.execute("Add user sam", user_role="ADMIN")
        assert res == {"error": "Database session missing."}

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    def test_aa3_add_user_missing_fields(self, mock_llm, db):
        """AA3: add_user missing required fields prompts user for details."""
        mock_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "add_user", "target_username": null, "target_role": null, "target_password": null}'
        )
        agent = AdminAgent(db=db)
        res = agent.execute("Add user", user_role="ADMIN")
        assert "Please provide a username, password, and role" in res["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    def test_aa4_unrecognized_admin_command(self, mock_llm, db):
        """AA4: Unrecognized admin command returns guidance."""
        mock_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "unknown"}'
        )
        agent = AdminAgent(db=db)
        res = agent.execute("Launch rocket to moon", user_role="ADMIN")
        assert "not recognized or supported" in res["answer"]

    @patch("app.services.admin_agent.ChatGoogleGenerativeAI")
    def test_aa5_hot_reload_missing_env(self, mock_llm, db):
        """AA5: Hot reload returns .env file not found if file is missing."""
        mock_llm.return_value.invoke.return_value = MagicMock(
            content='{"action": "hot_reload"}'
        )
        agent = AdminAgent(db=db)
        with patch("os.path.exists", return_value=False):
            res = agent.execute("Hot reload secrets", user_role="SUPER_ADMIN")
            assert res == {"error": ".env file not found."}
