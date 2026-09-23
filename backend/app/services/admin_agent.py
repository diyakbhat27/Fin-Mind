import json
import logging
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from sqlalchemy.orm import Session
from app.services.secret_manager import get_secret
from app.models.rbac import User
from app.models.audit import AuditLog

from typing import Optional
from app.auth.security import get_password_hash
import uuid

logger = logging.getLogger("finmind.admin_agent")

class AdminIntent(BaseModel):
    action: str = Field(description="Must be one of: 'count_users', 'hot_reload', 'list_audit_logs', 'add_user', 'delete_user', 'unknown'")
    target_username: Optional[str] = Field(None, description="Username to add or delete, if applicable.")
    target_role: Optional[str] = Field(None, description="Role to assign to the new user, if applicable. Must be one of: VIEWER, ANALYST, ADMIN, SUPER_ADMIN")
    target_password: Optional[str] = Field(None, description="Password to assign to the new user, if applicable.")

class AdminAgent:
    def __init__(self, db: Session = None):
        self.db = db
        api_key = get_secret("GEMINI_API_KEY") or "mock_api_key_for_local_eval"
        self.llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0.0, max_retries=3, api_key=api_key)
        self.parser = PydanticOutputParser(pydantic_object=AdminIntent)

    def execute(self, query: str, user_role: str) -> dict:
        if user_role not in ["ADMIN", "SUPER_ADMIN"]:
            return {"error": "Forbidden: Admin Agent requires ADMIN or SUPER_ADMIN role."}

        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content="You are the Admin Agent. Map the user query to an admin action."),
            HumanMessage(content=f"Query: {query}\n\n{self.parser.get_format_instructions()}")
        ]

        try:
            response = self.llm.invoke(messages)
            content_str = response.content
            if isinstance(content_str, list):
                texts = [block.get("text", "") for block in content_str if isinstance(block, dict)]
                content_str = " ".join(texts)
                
            intent = self.parser.invoke(content_str)
        except Exception as e:
            logger.error("Admin query parse failed: %s", e, exc_info=True)
            return {"error": "Failed to parse admin instruction."}

        if intent.action == "count_users":
            if not self.db: return {"error": "Database session missing."}
            count = self.db.query(User).count()
            return {"answer": f"There are currently {count} users registered in the system.", "citations": []}
            
        elif intent.action == "hot_reload":
            if user_role != "SUPER_ADMIN": return {"error": "Forbidden: Hot-reload requires SUPER_ADMIN role."}
            from dotenv import load_dotenv
            import os
            env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
            if os.path.exists(env_path):
                load_dotenv(dotenv_path=env_path, override=True)
                return {"answer": "Secrets successfully hot-reloaded from .env into memory.", "citations": []}
            return {"error": ".env file not found."}
                
        elif intent.action == "list_audit_logs":
            if not self.db: return {"error": "Database session missing."}
            logs = self.db.query(AuditLog).order_by(AuditLog.id.desc()).limit(10).all()
            if not logs:
                return {"answer": "No audit logs found.", "citations": []}
            log_str = "\n".join([f"- {log.timestamp}: {log.event_type} by {log.user_id}" for log in logs])
            return {"answer": f"Here are the recent audit logs:\n{log_str}", "citations": []}
            
        elif intent.action == "add_user":
            if not self.db: return {"error": "Database session missing."}
            if not intent.target_username or not intent.target_password or not intent.target_role:
                return {"answer": "Please provide a username, password, and role (VIEWER, ANALYST, ADMIN, SUPER_ADMIN) to add a user.", "citations": []}
            
            is_privileged = intent.target_role in ["ADMIN", "SUPER_ADMIN"]
            if is_privileged and user_role != "SUPER_ADMIN":
                return {"error": "Forbidden: Only SUPER_ADMIN can create ADMIN or SUPER_ADMIN users."}
                
            existing = self.db.query(User).filter(User.username == intent.target_username).first()
            if existing:
                return {"answer": f"User '{intent.target_username}' already exists.", "citations": []}
                
            new_user = User(
                id=str(uuid.uuid4()),
                username=intent.target_username,
                email=f"{intent.target_username}@finmind.local",
                hashed_password=get_password_hash(intent.target_password),
                role=intent.target_role
            )
            self.db.add(new_user)
            self.db.commit()
            return {"answer": f"Successfully created user '{intent.target_username}' with role '{intent.target_role}'.", "citations": []}

        elif intent.action == "delete_user":
            if not self.db: return {"error": "Database session missing."}
            if not intent.target_username:
                return {"answer": "Please specify the username to delete.", "citations": []}
                
            target_user = self.db.query(User).filter(User.username == intent.target_username).first()
            if not target_user:
                return {"answer": f"User '{intent.target_username}' not found.", "citations": []}
                
            if target_user.role in ["ADMIN", "SUPER_ADMIN"] and user_role != "SUPER_ADMIN":
                return {"error": "Forbidden: Only SUPER_ADMIN can delete privileged users."}
                
            self.db.delete(target_user)
            self.db.commit()
            return {"answer": f"Successfully deleted user '{intent.target_username}'.", "citations": []}
            
        return {"answer": "Admin command not recognized or supported by this agent.", "citations": []}
