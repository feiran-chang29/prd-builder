from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Role = Literal["user", "assistant", "system"]


class Message(BaseModel):
    role: Role
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: List[Message]
    prd: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    assistant_text: str
    questions: List[str] = Field(default_factory=list, max_length=3)
    prd: Dict[str, Any] = Field(default_factory=dict)
