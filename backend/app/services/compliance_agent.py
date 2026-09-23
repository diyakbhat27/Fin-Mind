import json
import logging
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from sqlalchemy.orm import Session
from app.core.prompts import get_config, COMPLIANCE_SYSTEM_PROMPT_DEFAULT
from app.services.secret_manager import get_secret

logger = logging.getLogger("finmind.compliance_agent")

class ComplianceDecision(BaseModel):
    status: str = Field(description="Must be either 'APPROVED' or 'REJECTED'")
    reasoning: str = Field(description="Detailed explanation citing the policy rule that was triggered.")

class ComplianceAgent:
    """
    Evaluates scenarios against hardcoded compliance rules.
    """
    def __init__(self, db: Session = None):
        self.db = db
        # Read model config from DB or fallback
        llm_model = get_config(self.db, "compliance_llm_model", "gemini-3.8-flash")
        
        api_key = get_secret("GEMINI_API_KEY") or "mock_api_key_for_local_eval"
        
        # Primary Model (Complex Reasoning)
        primary_llm = ChatGoogleGenerativeAI(model=llm_model, temperature=0.0, max_retries=3, api_key=api_key)
        
        # Fallback Model (Crash prevention)
        fallback_llm = ChatGoogleGenerativeAI(model="gemini-3.7-flash", temperature=0.0, max_retries=3, api_key=api_key)
        
        self.llm = primary_llm.with_fallbacks([fallback_llm])
        self.parser = PydanticOutputParser(pydantic_object=ComplianceDecision)
        
        self.system_prompt = get_config(self.db, "compliance_system_prompt", COMPLIANCE_SYSTEM_PROMPT_DEFAULT)

    def evaluate(self, scenario: str) -> dict:
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Scenario to evaluate: {scenario}\n\n{self.parser.get_format_instructions()}")
        ]
        
        try:
            response = self.llm.invoke(messages)
            
            content_str = response.content
            if isinstance(content_str, list):
                texts = [block.get("text", "") for block in content_str if isinstance(block, dict)]
                content_str = " ".join(texts)
                
            decision = self.parser.invoke(content_str)
            return {
                "answer": f"**COMPLIANCE {decision.status}**\n\nReasoning: {decision.reasoning}",
                "citations": []
            }
        except Exception as e:
            logger.error("Compliance evaluation failed: %s", e, exc_info=True)
            return {"error": "Compliance evaluation failed due to an internal processing error."}
