# Mini PRD Builder

A tiny PRD drafting tool with a chat-style UI. Describe a product, answer a few follow-up questions, and the app incrementally fills a PRD (Problem, Users, Goals, Metrics, Requirements, Open Questions). The UI also shows the raw PRD JSON for quick debugging.

## Repo Structure

- `server/` - FastAPI backend (Python)
- `client/` - React + TypeScript frontend (Vite)

## Prerequisites

- Python 3.10+ (recommended)
- Node.js 18+ (recommended)
- Ollama (recommended for local LLM)

## Recommended: Local LLM via Ollama

This project works best with a local model served by Ollama.

### Verify Ollama is running

```bash
ollama list
```

### Pull the model used in this repo

```bash
ollama pull llama3.2:3b
```

### Quick sanity check

```bash
ollama run llama3.2:3b "say hi"
```

## Server: Setup and Run

From repo root:

### Create and activate a virtual environment

```bash
cd server
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### Install Python dependencies

```bash
pip install -r requirements.txt
```

### Export environment variables (recommended Ollama config)

```bash
export STUB_MODE=false
export LLM_BASE_URL="http://localhost:11434"
export LLM_MODEL="llama3.2:3b"
export LLM_API_KEY="ollama"
```

Notes:
- `export` only applies to the current terminal session. If you open a new terminal tab/window, you need to export again.
- If you want to run without an LLM (deterministic stub mode):

```bash
export STUB_MODE=true
```

### Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

Backend URL:
- `http://localhost:8000`

## Client: Setup and Run

Open a new terminal:

### Install Node dependencies

```bash
cd client
npm install
```

### Start the frontend

```bash
npm run dev
```

Vite will print a local URL (typically):
- `http://localhost:5173`

## Quick End-to-End Test

Open the UI (usually `http://localhost:5173`) and paste the following.

### Test prompt (initial product description)

```text
I want a PRD for a note-taking app for university students.
```

Then answer the follow-up questions using structured text like below.

### Example answer: goals

```text
Goals: faster review before exams; keep notes organized by course; quickly capture ideas during lectures
```

### Example answer: requirements

```text
Requirements: create/edit notes; organize by course + tags; full-text search
```

### Example answer: metrics

```text
Metrics: weekly active users (WAU); 4-week retention; median time to find a note
```

You should see the PRD fields fill in on the right, along with the raw PRD JSON.

## Known Limitations

This repo defaults to a small local model (`llama3.2:3b`) to keep setup simple and lightweight. As a result:

- The assistant may occasionally ask the same question more than once.
- If user answers are unstructured or mix multiple unrelated ideas, the system may fail to extract clean PRD items.
- Some PRD fields may remain incomplete unless the user provides clear, structured answers.

These issues are largely due to the limitations of the lightweight LLM. Using a stronger model generally improves extraction quality and reduces repeated questions.
