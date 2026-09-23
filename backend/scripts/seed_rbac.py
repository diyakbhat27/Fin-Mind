import sys
import os
import uuid

# Add backend dir to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database.session import SessionLocal, engine
from app.models.rbac import Base, User, Role, Permission
from app.auth.security import get_password_hash

def seed_db():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # 1. Check if seeded
    if db.query(Role).first():
        print("Database already contains roles. Clearing for fresh seed...")
        # Since it's a simple SQLite MVP, we can drop all and recreate to ensure clean state
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    print("Seeding permissions...")
    permissions_data = {
        "read:public": "Read public financial documents",
        "read:confidential": "Read confidential/internal policy docs",
        "query:financial": "Financial analysis / SQL agent (query)",
        "run:compliance": "Compliance scenario check (run)",
        "manage:users_basic": "User management (non-privileged users only)",
        "manage:users_all": "User management (all users)",
        "view:prompts": "Prompt templates (view only)",
        "edit:prompts": "Prompt templates (full edit+version)",
        "change:llm": "LLM/model config (change)",
        "view:secrets": "Secret references (view ref names only)",
        "manage:secrets": "Secret references (manage refs)",
        "view:audit_ops": "Audit logs (operational subset)",
        "view:audit_full": "Audit logs (full)"
    }
    
    perm_objects = {}
    for code, desc in permissions_data.items():
        p = Permission(id=str(uuid.uuid4()), code=code, description=desc)
        db.add(p)
        perm_objects[code] = p
        
    db.commit()
    
    print("Seeding roles...")
    roles_data = {
        "VIEWER": ["read:public"],
        "ANALYST": ["read:public", "query:financial", "run:compliance"],
        "ADMIN": [
            "read:public", "read:confidential", "query:financial", "run:compliance",
            "manage:users_basic", "view:prompts", "view:secrets", "view:audit_ops"
        ],
        "SUPER_ADMIN": [
            "read:public", "read:confidential", "query:financial", "run:compliance",
            "manage:users_basic", "manage:users_all", "view:prompts", "edit:prompts",
            "change:llm", "view:secrets", "manage:secrets", "view:audit_ops", "view:audit_full"
        ]
    }
    
    role_objects = {}
    for r_name, p_codes in roles_data.items():
        r = Role(id=str(uuid.uuid4()), name=r_name, description=f"{r_name} role")
        for code in p_codes:
            r.permissions.append(perm_objects[code])
        db.add(r)
        role_objects[r_name] = r
        
    db.commit()
    
    print("Seeding users...")
    users_data = [
        {"username": "viewer", "password": os.getenv("SEED_VIEWER_PASSWORD", "viewer123"), "role": "VIEWER"},
        {"username": "analyst", "password": os.getenv("SEED_ANALYST_PASSWORD", "analyst123"), "role": "ANALYST"},
        {"username": "admin", "password": os.getenv("SEED_ADMIN_PASSWORD", "admin123"), "role": "ADMIN"},
        {"username": "superadmin", "password": os.getenv("SEED_SUPERADMIN_PASSWORD", "superadmin123"), "role": "SUPER_ADMIN"}
    ]
    
    for u_data in users_data:
        u = User(
            id=str(uuid.uuid4()),
            username=u_data["username"],
            email=f"{u_data['username']}@finmind.local",
            hashed_password=get_password_hash(u_data["password"]),
            is_active=True
        )
        u.roles.append(role_objects[u_data["role"]])
        db.add(u)
        
    db.commit()
    print("Database seeding completed successfully.")

if __name__ == "__main__":
    seed_db()