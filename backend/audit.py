"""Append-only audit trail for the Campus Customs agent team.

Every agent-loop step lands in output/audit_trail.json: the prompt that went
in, each model response, every tool call with its arguments and result, each
delegation between agents, and the final answer.

The file is appended to, never wiped. Each run gets its own record with a run
id, so several runs can sit in the same file and still be told apart.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
AUDIT_PATH = ROOT / "output" / "audit_trail.json"

# Long tool results are trimmed so the file stays readable, but never so much
# that the number an agent acted on is lost.
PREVIEW_CHARS = 1200

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip(value: Any, limit: int = PREVIEW_CHARS) -> Any:
    """Keep structured data as data. Only trim long strings.

    Scalars pass through untouched. Stringifying them would turn an int
    ticket_id into "101", which then never matches a database id.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str)
        if len(text) <= limit:
            return value
        return {"_truncated": True, "preview": text[:limit] + f"… (+{len(text) - limit} chars)"}
    text = str(value)
    return text if len(text) <= limit else text[:limit] + f"… (+{len(text) - limit} chars)"


class AuditTrail:
    """One run's worth of steps, flushed to disk as they happen."""

    def __init__(
        self, label: str, model: str, sink: Callable[[dict[str, Any]], None] | None = None
    ) -> None:
        """`sink` is called with each step as it happens, for live streaming.

        The file is still written either way. A sink that raises is ignored, so
        a dropped dashboard connection can never break an agent run.
        """
        self.run_id = f"run_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
        self.label = label
        self.model = model
        self.started_at = _now()
        self.steps: list[dict[str, Any]] = []
        self.sink = sink
        self._seq = 0
        self._write()

    def record(self, kind: str, agent: str, **data: Any) -> dict[str, Any]:
        """Add one step and flush. Returns the step for callers that want it.

        `kind` is what happened: run_start, prompt, model_response, tool_call,
        tool_result, delegation_start, delegation_end, answer, error, refusal.
        """
        self._seq += 1
        step = {
            "seq": self._seq,
            "at": _now(),
            "kind": kind,
            "agent": agent,
            **{k: _clip(v) for k, v in data.items()},
        }
        self.steps.append(step)
        self._write()
        if self.sink is not None:
            try:
                self.sink({"run_id": self.run_id, **step})
            except Exception:
                # A dashboard that hung up must not take the agent run with it.
                pass
        return step

    def _payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "label": self.label,
            "model": self.model,
            "started_at": self.started_at,
            "finished_at": _now(),
            "step_count": len(self.steps),
            "agents_involved": sorted({s["agent"] for s in self.steps if s.get("agent")}),
            "steps": self.steps,
        }

    def _write(self) -> None:
        """Append this run to the file, replacing only our own run record.

        Read, update, write. The whole file is rewritten each time because JSON
        is not appendable, but earlier runs are carried over untouched, so
        nothing is ever wiped.
        """
        with _lock:
            AUDIT_PATH.parent.mkdir(exist_ok=True)
            runs: list[dict[str, Any]] = []
            if AUDIT_PATH.exists():
                try:
                    existing = json.loads(AUDIT_PATH.read_text())
                    runs = existing.get("runs", []) if isinstance(existing, dict) else existing
                except (json.JSONDecodeError, OSError):
                    # Never lose a damaged file. Move it aside and start fresh.
                    AUDIT_PATH.replace(AUDIT_PATH.with_suffix(".corrupt.json"))
                    runs = []

            mine = self._payload()
            runs = [r for r in runs if r.get("run_id") != self.run_id] + [mine]

            tmp = AUDIT_PATH.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"runs": runs, "run_count": len(runs)}, indent=2, default=str) + "\n"
            )
            os.replace(tmp, AUDIT_PATH)
