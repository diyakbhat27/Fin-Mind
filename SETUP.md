# Fin Mind — Setup & Run Guide

Follow these steps **in order** to get Fin Mind running on your machine. Estimated time: ~10 minutes.

---

## Prerequisites

Make sure you have these installed before starting:

| Tool | Version | Check Command | Download |
|:---|:---|:---|:---|
| **Python** | 3.10 or higher | `python --version` | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18 or higher | `node --version` | [nodejs.org](https://nodejs.org/) |
| **npm** | 9 or higher | `npm --version` | Comes with Node.js |
| **Git** | Any | `git --version` | [git-scm.com](https://git-scm.com/) |

---

## Step 1: Get a Gemini API Key (FREE)

1. Go to **[Google AI Studio](https://aistudio.google.com/apikey)**
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy the key — you'll need it in Step 3

---

## Step 2: Backend Setup

Open a terminal and navigate to the `backend/` directory:

```bash
cd backend
```

### 2a. Create a Python virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

> You should see `(.venv)` at the beginning of your terminal prompt.

### 2b. Install Python dependencies

```bash
pip install -r requirements.txt
```

> ⏱ This will take 3-5 minutes. It downloads PyTorch, Transformers, ChromaDB, LangChain, and other ML libraries.

> ⚠️ If you get a `torch` installation error on an older machine, try:
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```

---

## Step 3: Configure Environment Variables

### 3a. Copy the example env file

**Windows:**
```cmd
copy .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

### 3b. Edit `.env` and paste your Gemini API Key

Open `backend/.env` in any text editor and replace `YOUR_GEMINI_API_KEY_HERE` with your actual key:

```env
GEMINI_API_KEY="AIzaSy..... your actual key here ....."
```

> ⚠️ **The app will NOT work without a valid Gemini API key.** All LLM routing and agent responses depend on it.

---

## Step 4: Initialize the Database & Seed Demo Users

Still inside `backend/` with the venv activated:

```bash
python scripts/seed_rbac.py
```

This initializes the SQLite database (`finmind.db`), seeds cryptographic permissions, creates standard RBAC roles, and provisions default role accounts for testing (VIEWER, ANALYST, ADMIN, SUPER_ADMIN).

---

## Step 5: Start the Backend Server

```bash
uvicorn app.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

> ✅ Test it: Open [http://localhost:8000](http://localhost:8000) in your browser. You should see:
> ```json
> {"message": "Fin Mind API Core Running", "status": "ok"}
> ```

**Keep this terminal running.** Open a new terminal for Step 6.

---

## Step 6: Frontend Setup

Open a **new terminal** and navigate to the `frontend/` directory:

```bash
cd frontend
```

### 6a. Install Node.js dependencies

```bash
npm install
```

### 6b. Start the frontend dev server

```bash
npm run dev
```

You should see:
```
  VITE v8.x.x  ready in XXX ms

  ➜  Local:   http://localhost:5173/
```

---

## Step 7: Open the App

Open **[http://localhost:5173](http://localhost:5173)** in your browser.

1. **Login** with your authorized account credentials.
2. **Ask questions** like:
   - `"What are Apple's risk factors?"` (RAG — works for all roles)
   - `"What is AAPL's leverage ratio for 2023?"` (SQL Agent — requires ANALYST+)
   - `"Can I invest 50% of my portfolio in Bitcoin?"` (Compliance — requires SUPER_ADMIN)
   - `"How many users are there?"` (Admin — requires ADMIN+)

---

## Running the Test Suite (Optional)

To run all 232 automated tests:

```bash
cd backend
python -m pytest -v
```

Expected output:
```
================ 232 passed, XXX warnings in ~100s ================
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'app'`
Make sure you are running commands from inside the `backend/` directory, not the project root.

### `ERROR: Could not find a version that satisfies the requirement torch==2.14.0`
Install the CPU-only version of PyTorch first:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

### `401 Unauthorized` when trying to chat
Your JWT token has expired (15 min default). Log out and log back in.

### `Routing failed: Invalid json output`
This means the Gemini API key is missing or invalid. Double-check `backend/.env` has a valid `GEMINI_API_KEY`.

### `429 Too Many Requests`
Rate limiting is active. Wait 1 minute before retrying (5 req/min on login, 20 req/min on chat).

### Frontend shows blank page / connection refused
Make sure the backend is running on port 8000 (`uvicorn app.main:app --reload`) in a separate terminal.

### `sqlite3.OperationalError: no such table: users`
Run the seed script first: `python scripts/seed_rbac.py`

---

## Project Structure

```
Fin Mind/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── api/endpoints/      # REST API routes (auth, chat, admin, users, rag, quant, secrets)
│   │   ├── auth/               # JWT authentication, RBAC dependencies
│   │   ├── core/               # Config, prompts, rate limiting, audit middleware
│   │   ├── database/           # SQLAlchemy session & engine
│   │   ├── db/                 # ChromaDB vector store, financial queries engine
│   │   ├── ingestion/          # SEC EDGAR client, HTML/PDF parser, XBRL parser
│   │   ├── models/             # SQLAlchemy models (User, AuditLog, FinancialReport, etc.)
│   │   ├── security/           # AES-256-GCM encryption
│   │   ├── services/           # LangGraph supervisor, RAG chain, SQL/Compliance/Admin agents
│   │   └── main.py             # FastAPI app entry point
│   ├── scripts/                # Database seeding & data ingestion scripts
│   ├── tests/                  # 246 automated pytest test cases
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment variable template
├── frontend/                   # React + Vite frontend
│   ├── src/
│   │   ├── components/         # LoginScreen, ChatInterface, MessageBubble
│   │   ├── services/           # Axios API client
│   │   └── App.jsx             # Main app with auth state & theme toggle
│   └── package.json            # Node.js dependencies
├── .env.example                # Environment variable template
├── INTERVIEW_GUIDE.md          # Detailed interview preparation document
└── SETUP.md                    # ← This file
```
