from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .llm import call_llm
from .schemas import ChatRequest, ChatResponse


def _get_port() -> int:
    raw = os.getenv("PORT", "3001").strip()
    try:
        return int(raw)
    except ValueError:
        return 3001


def create_app() -> FastAPI:
    app = FastAPI(title="PRD Builder API", version="0.1.0")

    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        return await call_llm(req.messages, req.prd)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    port = _get_port()
    uvicorn.run("server.app.main:app", host="0.0.0.0", port=port, reload=True)
