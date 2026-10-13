"""Model and MCP configuration for the Campus Customs agent team.

Calls OpenAI directly with OPENAI_API_KEY. The assignment names gpt-6-luna
through Portkey, but this project has no Portkey key and no access to that
model, so it runs on gpt-5.6-luna with the instructor's agreement. Changing
MODEL_NAME here is the only edit needed if that changes.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MCP_DIR = ROOT / "mcp"
PROMPTS = HERE / "prompts"

# Workspace convention: one .env at the repo root serves every project.
load_dotenv(find_dotenv(), override=False)

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-5.6-luna").strip() or "gpt-5.6-luna"

# A ticket can fan out across several agents, so leave room, but not unlimited.
MAX_MODEL_REQUESTS = 24


def require_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set (put it in the root .env file).")
    return key


@lru_cache(maxsize=1)
def build_model() -> OpenAIResponsesModel:
    """One model for every agent on the team."""
    client = AsyncOpenAI(api_key=require_api_key())
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


@lru_cache(maxsize=1)
def mcp_toolset() -> MCPToolset:
    """Attach the Campus Customs FastMCP server in-process.

    Same process as the backend, so no separate MCP terminal is needed. Every
    agent shares this one toolset, which is what makes the shop rules apply
    uniformly across the team.
    """
    if str(MCP_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_DIR))
    from mcp_server import mcp as campus_mcp

    return MCPToolset(campus_mcp)


def read_prompt(name: str) -> str:
    """Load one agent's system prompt from backend/prompts/<name>.md."""
    path = PROMPTS / f"{name}.md"
    if not path.exists():
        raise RuntimeError(f"No prompt file at {path}.")
    return path.read_text(encoding="utf-8")
