# Fin Mind: Enterprise Financial Intelligence Platform

Fin Mind is a highly secure, zero-trust, multi-agent financial platform designed to analyze SEC 10-K filings, compute deterministic financial ratios via SQL, and evaluate compliance against internal banking policies.

## 🏛️ Architecture Whitepaper

The system uses a **Multi-Agent LangGraph Orchestration** architecture with a Supervisor agent routing requests to specialized sub-nodes.

### Key Architectural Pillars
1. **Zero Raw Arithmetic & Zero Dynamic SQL**: LLMs are restricted from generating dynamic SQL or executing mathematical computations. All financial metrics (Revenue, Leverage Ratios) are processed via strictly typed, pre-compiled SQLAlchemy templates via the `sql_agent`.
2. **Pre-Filtered Vector Search**: We employ Role-Based Access Control (RBAC) at the vector database query level (ChromaDB) to prevent filter starvation and unauthorized data exfiltration. Viewers cannot retrieve internal documents.
3. **Enterprise UI & Telemetry**: The UI is a custom React/Vite application that heavily implements a "Perplexity-style" Citation Engine. It maps sources and RAG reasoning steps into a distinct visual block. Backed by a SQLite telemetry logger tracking `latency_ms` and RAG Faithfulness/Relevancy scores.
4. **Cryptographic Secret Management**: API keys and secrets are never stored in plaintext within the application memory. They are managed by an abstract `SecretManager` that supports Zero-Downtime `.env` hot-reloading for enterprise-grade secret rotation.

---

## 🔐 Role-Based Access Control & Capabilities

The system enforces strict RBAC. Each user account is assigned one of the following clearance levels:

### 1. 👁️ VIEWER
**Capabilities:** Can only read public SEC data (Level 1). Cannot query SQL financial tables or confidential documents.
* **Example Question 1:** "What are Apple's main risk factors according to their SEC 10-K?"
* **Example Question 2:** "What are Microsoft's business segments?"
* **Example Question 3:** "Who are the primary competitors of Tesla?"
* **Example Question 4:** "What does Apple say about macroeconomic conditions in their filings?"
* **Example Question 5:** "What are Google's main R&D expenses used for?"
* **Expected Answer:** The RAG Agent will search the `sec-filings` collection, display the "Scanned SEC filings" reasoning step, render the `[1]` inline citations, and list the source document (e.g., `AAPL_10K_2023.pdf`) in the Sources block.

### 2. 📊 ANALYST
**Capabilities:** Inherits Viewer rights. Can *also* query quantitative structured data via the `sql_agent`.
* **Example Question 1:** "What is the total revenue for Apple in 2023?"
* **Example Question 2:** "What is Microsoft's net income for the latest fiscal year?"
* **Example Question 3:** "Calculate Tesla's debt-to-equity ratio."
* **Example Question 4:** "Show me Google's total operating expenses."
* **Example Question 5:** "What was Apple's gross margin last year?"
* **Expected Answer:** The Supervisor will route this to the Quantitative Engine. The UI will show "Executed AST query" and render a structured data table containing the exact financial figure retrieved securely from the SQLite database.

### 3. 🛡️ ADMIN
**Capabilities:** Inherits Analyst rights. Can *also* query confidential Level 3 documents.
* **Example Question 1:** "Summarize the confidential merger policy."
* **Example Question 2:** "What are the internal guidelines for approving high-risk credit loans?"
* **Example Question 3:** "Show me the board meeting minutes regarding the upcoming acquisition."
* **Example Question 4:** "What is the compliance checklist for tier-3 transactions?"
* **Example Question 5:** "Detail the internal employee stock option plan."
* **Expected Answer:** The RAG Agent will retrieve documents tagged with `clearance_level=3`. A Viewer asking this exact same question would receive an "Access Denied / Information not found" error because the vector search pre-filters the chunks based on their role.

### 4. ⚙️ SUPER ADMIN
**Capabilities:** Inherits all rights. Full control over the platform's control plane, including hot-reloading secrets without restarting the server.
* **Example Question 1:** "Hot-reload API keys."
* **Example Question 2:** "Change the active LLM provider to Anthropic."
* **Example Question 3:** "Show me the last 10 cryptographic audit logs."
* **Example Question 4:** "Update the default system prompt for the SQL agent."
* **Example Question 5:** "Purge the vector database cache."
* **Expected Answer:** The Supervisor routes to the `admin_agent`. For the hot-reload command, the agent will trigger the `EnvSecretManager.reload_secrets()` function, returning a success message indicating secrets have been flushed and reloaded into memory.

---

## 💾 Account Management & Storage

* **Where are passwords stored?**
Usernames and Passwords are stored locally in the backend SQLite database inside the `users` table (`app.models.rbac.User`). Passwords are mathematically hashed using `passlib` (bcrypt) before being stored; they are never saved as plaintext.
* **Can Super Admins add/delete accounts?**
While the Super Admin control plane allows for editing configurations and viewing audit logs, the system provides a seeding script (`scripts/seed_rbac.py`) to initialize default role accounts. A full user-management CRUD API (Add/Delete/Modify users) is available for Super Admins.

---

## 🚀 Quickstart

### 1. Setup & Start Backend

```bash
cd backend
python -m venv venv

# Windows:
.\venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
copy .env.example .env      # Windows
# cp .env.example .env      # macOS / Linux

# Open .env and insert your Gemini API Key:
# GEMINI_API_KEY="your-actual-api-key"

# Initialize the database and provision default roles
python scripts/seed_rbac.py

# Start the FastAPI server (runs on http://localhost:8000)
uvicorn app.main:app --reload
```

### 2. Setup & Start Frontend

```bash
cd frontend
npm install
npm run dev
```

Navigate to `http://localhost:5173` to access the Enterprise UI.

---

