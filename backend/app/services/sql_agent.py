import enum
import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from app.db.queries import FinancialMetricsEngine
from app.services.secret_manager import get_secret
from sqlalchemy.orm import Session

logger = logging.getLogger("finmind.sql_agent")

class MetricType(str, enum.Enum):
    LEVERAGE_RATIO = "leverage_ratio"
    OPERATING_MARGIN = "operating_margin"
    ROE = "roe"
    CURRENT_RATIO = "current_ratio"
    UNKNOWN = "unknown"

class QuantitativeIntent(BaseModel):
    """Schema for the LLM to strictly output."""
    metric: MetricType = Field(description="The financial metric the user is asking to calculate.")
    ticker: str = Field(description="The stock ticker symbol (e.g., AAPL).")
    year: int = Field(description="The fiscal year requested (e.g., 2023).")

class QuantitativeAgent:
    """
    LLM acts ONLY as a semantic router.
    Calculations are strictly delegated to SQLAlchemy ASTs.
    """
    def __init__(self, db: Session):
        self.db = db
        self.math_engine = FinancialMetricsEngine(db)
        
        # We need a highly deterministic model for accurate AST mapping
        api_key = get_secret("GEMINI_API_KEY") or "mock_api_key_for_local_eval"
        
        # Primary Model: gemini-3.8-flash (Fast and intelligent)
        primary_llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0.0, max_retries=3, api_key=api_key)
        
        # Fallback Model: gemini-3.7-flash 
        fallback_llm = ChatGoogleGenerativeAI(model="gemini-3.7-flash", temperature=0.0, max_retries=3, api_key=api_key)
        
        # Apply the fallback mechanism
        self.llm = primary_llm.with_fallbacks([fallback_llm])
        self.parser = PydanticOutputParser(pydantic_object=QuantitativeIntent)

    def analyze(self, query: str) -> dict:
        """
        Routes the natural language query to the appropriate math AST.
        """
        try:
            # The LLM does NOT calculate anything. It only parses intent.
            prompt = f"Extract the financial intent from this query.\nQuery: {query}\n\n{self.parser.get_format_instructions()}"
            response = self.llm.invoke(prompt)
            
            content_str = response.content
            if isinstance(content_str, list):
                texts = [block.get("text", "") for block in content_str if isinstance(block, dict)]
                content_str = " ".join(texts)
                
            intent: QuantitativeIntent = self.parser.invoke(content_str)
        except Exception as e:
            logger.error("Quantitative intent parse failed: %s", e, exc_info=True)
            return {"error": "Failed to parse query intent. Ensure the query explicitly mentions a supported metric, ticker, and year."}

        if intent.metric == MetricType.UNKNOWN:
            return {"error": "Unsupported or unknown metric. LLM is restricted from executing dynamic SQL."}
            
        # Execute the verified, read-only AST
        if intent.metric == MetricType.LEVERAGE_RATIO:
            return self.math_engine.get_leverage_ratio(intent.ticker, intent.year)
        elif intent.metric == MetricType.OPERATING_MARGIN:
            return self.math_engine.get_operating_margin(intent.ticker, intent.year)
        elif intent.metric == MetricType.ROE:
            return self.math_engine.get_roe(intent.ticker, intent.year)
        elif intent.metric == MetricType.CURRENT_RATIO:
            return self.math_engine.get_current_ratio(intent.ticker, intent.year)
            
        return {"error": "Unhandled metric route."}
