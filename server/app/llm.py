from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .schemas import ChatResponse, Message

DEBUG_LLM_RAW = os.getenv("DEBUG_LLM_RAW", "false").lower() in ("1", "true", "yes")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def _extract_json_object(text: str) -> Dict[str, Any]:
    """
    Best-effort JSON object extraction.
    Expectation: model returns ONLY JSON, but this guards against minor leakage.
    """
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        return json.loads(s)

    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return json.loads(s[start : end + 1])


def _build_system_prompt() -> str:
    return (
        "You are a PRD assistant.\n"
        "Return ONLY one JSON object and nothing else. No markdown. No code fences. No extra text.\n"
        "\n"
        "Your output MUST follow this exact JSON schema:\n"
        "{\n"
        '  \"assistant_text\": string,\n'
        '  \"questions\": string[] ,\n'
        '  \"prd\": {\n'
        '    \"problem\": string,\n'
        '    \"users\": string[],\n'
        '    \"goals\": string[],\n'
        '    \"metrics\": string[],\n'
        '    \"requirements\": string[],\n'
        '    \"open_questions\": string[]\n'
        "  }\n"
        "}\n"
        "\n"
        "Field definitions:\n"
        "- prd.problem: a short user pain/problem statement (6-12 words). Not a product description like \"an app for ...\".\n"
        "- prd.users/goals/metrics/requirements/open_questions: arrays of short strings.\n"
        "\n"
        "Conversation policy:\n"
        "- Ask at most ONE question per turn.\n"
        "- assistant_text must contain exactly that one question (no extra questions, no fluff).\n"
        "- questions[] must contain exactly the same one question (or be empty if you ask none).\n"
        "- prd.open_questions[] must be IDENTICAL to questions[] (same items, same order).\n"
        "- Do NOT ask definition/clarification questions like \"What do you mean by X?\" or \"Can you define X?\".\n"
        "- Avoid generic filler (e.g., \"This app should help users...\"). Be direct.\n"
        "\n"
        "Question priority (choose the next missing piece):\n"
        "1) goals (primary goal/outcome)\n"
        "2) metrics (1-3 ways to measure success)\n"
        "3) requirements (must-have features/constraints)\n"
        "Only ask about pain points or workflows if the above are already filled.\n"
        "\n"
        "Extraction/update rules:\n"
        "- Always keep all prd keys present in the output, even if empty.\n"
        "- prd.open_questions[] must be identical to questions[] in EVERY response.\n"
        "- If the user statement clearly implies a user group, fill prd.users immediately.\n"
        "- If you ask one question, prd.open_questions[] MUST contain that question.\n"
        "- If the user provides goals/metrics/requirements/users in their message, extract them and update the arrays.\n"
        "- Do not delete existing prd items unless the user explicitly changes them.\n"
        "- When you ask a question, do not update prd fields speculatively in the same turn (besides problem/users if obvious).\n"
        "\n"
        "Problem filling rules:\n"
        "- Always set prd.problem.\n"
        "- If the user only says they want a PRD for a product, infer a reasonable pain statement.\n"
        "- If you cannot infer, use a generic pain statement related to the product domain.\n"
        "\n"
        "Formatting rules:\n"
        "- questions[] length must be 0 or 1.\n"
        "- Keep strings short. No paragraphs.\n"
        "Question style:\n"
        "- The single question must be short and direct (max 12 words).\n"
        "- Avoid repeating the user/product phrase in the question.\n"
        "- Prefer templates like:\n"
        "  - \"What is the primary goal you want?\"\n"
        "  - \"How will you measure success (1–3 metrics)?\"\n"
        "  - \"What are the must-have features?\"\n"
    )



def _ensure_prd_shape(prd: dict) -> dict:
    if not isinstance(prd, dict):
        prd = {}
    prd.setdefault("problem", "")
    prd.setdefault("users", [])
    prd.setdefault("goals", [])
    prd.setdefault("metrics", [])
    prd.setdefault("requirements", [])
    prd.setdefault("open_questions", [])
    return prd


def _build_user_context(messages: List[Message], prd: Optional[Dict[str, Any]]) -> str:
    prd_json = json.dumps(prd or {}, ensure_ascii=False)
    convo_lines: List[str] = []
    for m in messages:
        role = m.role.strip().lower()
        convo_lines.append(f"{role}: {m.content}")
    convo = "\n".join(convo_lines)

    return (
        "Current PRD (may be empty):\n"
        f"{prd_json}\n\n"
        "Conversation so far:\n"
        f"{convo}\n"
    )


def _stub_response(messages: List[Message], prd: Optional[Dict[str, Any]]) -> ChatResponse:
    """
    Offline stub so the rest of the system can be built without a real LLM call.
    """
    last_user = ""
    for m in reversed(messages):
        if m.role.lower() == "user":
            last_user = m.content
            break

    existing = prd or {}
    # Minimal PRD shape (you can expand later)
    base_prd = {
        "problem": existing.get("problem", ""),
        "users": existing.get("users", []),
        "goals": existing.get("goals", []),
        "metrics": existing.get("metrics", []),
        "requirements": existing.get("requirements", []),
        "open_questions": existing.get("open_questions", []),
    }

    questions: List[str] = []
    if not base_prd["users"]:
        questions.append("Who is the target user for this product?")
    if not base_prd["goals"]:
        questions.append("What is the primary goal or outcome you want?")
    if not base_prd["metrics"]:
        questions.append("How will you measure success (1–3 metrics)?")

    assistant_text = (
        "Got it. I can start drafting a PRD. "
        "Answer these questions so I can refine it:\n"
        + "\n".join([f"- {q}" for q in questions])
        if questions
        else "Thanks. I updated the PRD based on your latest input."
    )

    if not base_prd["problem"] and last_user:
        base_prd["problem"] = last_user.strip()

    text = last_user.strip()

    def _grab(after: str) -> str:
        idx = text.lower().find(after.lower())
        if idx == -1:
            return ""
        start = idx + len(after)
        # stop at next label if present
        stops = []
        for label in ["goal:", "success metrics:", "metrics:", "target users:"]:
            j = text.lower().find(label, start)
            if j != -1:
                stops.append(j)
        end = min(stops) if stops else len(text)
        return text[start:end].strip(" .;\n\t")

    users_str = _grab("target users:")
    goal_str = _grab("goal:")
    metrics_str = _grab("success metrics:")
    if not metrics_str:
        metrics_str = _grab("metrics:")

    if users_str and not base_prd["users"]:
        base_prd["users"] = [users_str]

    if goal_str and not base_prd["goals"]:
        base_prd["goals"] = [goal_str]

    if metrics_str and not base_prd["metrics"]:
        # allow comma-separated
        parts = [p.strip() for p in metrics_str.split(",") if p.strip()]
        base_prd["metrics"] = parts if parts else [metrics_str]

    return ChatResponse(assistant_text=assistant_text, questions=questions[:3], prd=base_prd)


async def call_llm(messages: List[Message], prd: Optional[Dict[str, Any]]) -> ChatResponse:
    """
    Returns ChatResponse:
      - assistant_text
      - questions (0..3)
      - prd (full PRD object)

    To keep things simple:
      - If STUB_MODE=true, returns a deterministic stub response.
      - Otherwise, calls an OpenAI-compatible chat completions endpoint.

    Required env vars for real calls:
      - LLM_API_KEY
      - LLM_BASE_URL   (e.g., https://api.example.com)
      - LLM_MODEL      (e.g., gpt-4.1-mini or any model your provider supports)
    Optional:
      - LLM_TIMEOUT_S  (default 30)
      - STUB_MODE      (default true for development)
    """
    if _env_bool("STUB_MODE", True):
        return _stub_response(messages, prd)

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")

    if not api_key or not base_url or not model:
        raise RuntimeError("Missing LLM_API_KEY, LLM_BASE_URL, or LLM_MODEL in environment.")

    timeout_s = float(os.getenv("LLM_TIMEOUT_S", "30"))

    system_prompt = _build_system_prompt()
    user_context = _build_user_context(messages, prd)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_context},
        ],
        "temperature": 0.2,
    }

    url = base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
        if DEBUG_LLM_RAW:
            print("\n================ LLM RAW OUTPUT ================\n")
            print(content)
            print("\n================ END LLM RAW OUTPUT ============\n")
    except Exception as e:
        raise RuntimeError(f"Unexpected LLM response format: {data}") from e

    obj = _extract_json_object(content)

    new_prd = _ensure_prd_shape(obj.get("prd", {}))
    old_prd = _ensure_prd_shape(prd or {})

    merged = dict(old_prd)
    for k, v in new_prd.items():
        if k == "problem":
            if isinstance(v, str) and v.strip():
                merged[k] = v
        else:
            if isinstance(v, list) and len(v) > 0:
                merged[k] = v

    assistant_text = str(obj.get("assistant_text", "")).strip()
    questions_raw = obj.get("questions", [])
    prd_obj = obj.get("prd", {})

    if not isinstance(questions_raw, list):
        questions_raw = []

    questions = [str(x).strip() for x in questions_raw if str(x).strip()][:3]
    if not isinstance(prd_obj, dict):
        prd_obj = {}

    def _has_items(xs: Any) -> bool:
        if not isinstance(xs, list):
            return False
        for x in xs:
            if isinstance(x, str) and x.strip():
                return True
        return False

    is_complete = (
        _has_items(merged.get("goals")) and
        _has_items(merged.get("metrics")) and
        _has_items(merged.get("requirements"))
    )

    # If complete, stop asking
    if is_complete:
        assistant_text = ""
        questions = []
        merged["open_questions"] = []
    else:
        # Keep Open Questions consistent with the one question we asked
        merged["open_questions"] = list(questions)

    return ChatResponse(assistant_text=assistant_text, questions=questions, prd=merged)

