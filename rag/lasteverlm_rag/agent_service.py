"""The agent chat: plan, confirm, execute.

A chat message goes to a planning call first (``agent.PLANNER_SYSTEM``,
no passages). Tool calls become a plan the user sees with its estimate;
anything else is answered as before. On confirm, the steps that need
ingest run inside that request with its own bearer (rag stores no
tokens), an output is created as any other (its job waits for the
notebook's processing sources), and an explanation waits until its output
is ready. The worker moves waiting steps on (``advance``), fails an output
still waiting for a source after ``PLAN_TIMEOUT_S`` without charging, and
closes the plan with a summary message. Every call of a plan books under
its action_id.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from lasteverlm_core import Answer, ToolCallingLLM

from .agent import (
    ACTION_TOOLS,
    NO_ACTION,
    PLAN_TIMEOUT_S,
    PLANNER_MAX_TOKENS,
    PLANNER_SYSTEM,
    Context,
    Step,
    build_steps,
    separate,
    tool_specs,
    total,
)
from .citations import inline
from .ingest_client import Ingest, IngestError
from .models import Booking
from .options import OutputOptions
from .reading import reading_lines
from .service import (
    HISTORY_MESSAGES,
    ConversationNotFound,
    OutputService,
    RagService,
    complete_tools_billed,
    require_credit,
    require_notebook,
)
from .store import Store

log = logging.getLogger(__name__)

EXPLAIN_DEFAULT = "Explain this document: what it covers and its main points."
TIMEOUT_ERROR = "a source did not become ready within 30 minutes"
TERMINAL = ("done", "failed", "skipped")

EstimateStep = Callable[[Step, str], dict[str, float]]


class PlanNotFound(Exception):
    """No plan with that id in the caller's conversation."""


class PlanNotOpen(Exception):
    """The plan was confirmed or cancelled already."""


def public(plan: dict[str, Any]) -> dict[str, Any]:
    """The plan as answers, messages and the plan endpoint show it."""
    return {
        "plan_id": plan["id"],
        "status": plan["status"],
        "steps": plan["steps"],
        "estimate": {k: v for k, v in plan["estimate"].items() if k != "reading"},
        # ingest's own charges: pages a step adds, sources an output reads first
        "separate": separate(plan["steps"]) + plan["estimate"].get("reading", []),
    }


class AgentService:
    def __init__(
        self,
        store: Store,
        rag: RagService,
        outputs: OutputService,
        llm: Any,
        ingest: Ingest | None,
        estimate_step: EstimateStep,
        default_voice: str,
    ) -> None:
        self._store = store
        self._rag = rag
        self._outputs = outputs
        # without complete_tools (a text-only LLM) the chat answers as before
        self._llm: ToolCallingLLM | None = (
            cast(ToolCallingLLM, llm) if hasattr(llm, "complete_tools") else None
        )
        self._ingest = ingest
        self._estimate = estimate_step
        self._default_voice = default_voice

    # -- planning ----------------------------------------------------------

    def ask(
        self,
        user_id: str,
        notebook_id: str,
        question: str,
        conversation_id: str,
        bearer: str | None,
        output_id: str | None = None,
        source_ids: list[str] | None = None,
        url_refresh: list[str] | None = None,
    ) -> Answer:
        """A plan when the message asks for actions; the usual answer otherwise.
        A scoped question (about one output) is always answered."""
        booking = Booking.new(user_id, notebook_id, "chat_answer")
        if self._llm is not None and bearer and output_id is None:
            planned = self._plan(user_id, notebook_id, question, conversation_id, bearer, booking)
            if planned is not None:
                return planned
        return self._rag.ask(
            user_id,
            notebook_id,
            question,
            conversation_id,
            output_id,
            source_ids,
            booking,
            bearer=bearer,
            url_refresh=url_refresh,
        )

    def _plan(
        self,
        user_id: str,
        notebook_id: str,
        question: str,
        conversation_id: str,
        bearer: str,
        booking: Booking,
    ) -> Answer | None:
        assert self._llm is not None
        require_notebook(self._store, user_id, notebook_id)
        conversation = self._store.get_conversation(conversation_id)
        if conversation is None or conversation.owner != user_id:
            raise ConversationNotFound(conversation_id)
        if conversation.notebook_id != notebook_id:
            raise ConversationNotFound(conversation_id)
        require_credit(self._store, user_id)
        question = question.strip()
        outputs = {
            r.id: r.title for r in self._store.list_outputs(notebook_id) if r.status == "ready"
        }
        # the planner sees names and the user's own words, never a passage
        earlier = [
            m.content
            for m in self._store.list_messages(conversation_id, last=HISTORY_MESSAGES)
            if m.role == "user"
        ]
        documents = self._store.notebook_documents(notebook_id)
        context = "\n".join(
            ["Earlier questions:"]
            + [f"- {inline(q)}" for q in earlier]
            + ["", "Documents in this notebook:"]
            + [f"- {inline(d.name)} ({d.output_kind or d.kind})" for d in documents]
            + ["", "Outputs (id: title):"]
            + [f"- {oid}: {inline(title)}" for oid, title in outputs.items()]
            + ["", "The user's message:", question]
        )
        result = complete_tools_billed(
            self._store,
            self._llm,
            booking,
            PLANNER_SYSTEM,
            [{"role": "user", "content": context}],
            tool_specs(),
            PLANNER_MAX_TOKENS,
        )
        if not result.tool_calls or result.text.strip() == NO_ACTION:
            return None
        calls = [(c.name, c.arguments) for c in result.tool_calls]
        if not any(name in ACTION_TOOLS for name, _ in calls):
            # reading or explaining alone is what an answer does: a question that
            # the planner met with read tools only is answered, never turned into a plan
            return None
        library = (
            self._library(bearer, notebook_id)
            if any(n == "add_from_library" for n, _ in calls)
            else {}
        )
        steps = build_steps(calls, Context(question, library, outputs, self._default_voice))
        for step in steps:
            if not step.valid:
                continue
            if step.tool == "add_url":
                # linking the page costs the plan nothing; ingest charges its processing
                # under its own action, the price /prices shows for "add a web page"
                step.processing = {
                    "label": "Process the web page",
                    "estimate": self._estimate(step, bearer),
                }
            else:
                step.estimate = self._estimate(step, bearer)
        estimate: dict[str, Any] = dict(total(steps))
        if self._ingest is not None and any(s.valid and s.tool == "create_output" for s in steps):
            # an output reads the notebook's sources not read yet: ingest's charge
            estimate["reading"] = reading_lines(
                self._store, self._ingest, bearer, notebook_id, None, []
            )
        plan_id = str(uuid.uuid4())
        plan = {
            "id": plan_id,
            "conversation_id": conversation_id,
            "notebook_id": notebook_id,
            "owner": user_id,
            "status": "proposed",
            "steps": [s.as_json() for s in steps],
            "estimate": estimate,
            "action_id": str(booking.action_id),
        }
        text = "Here is my plan. Nothing runs until you confirm it.\n\n" + "\n".join(
            f"{s.n}. {s.label}" + ("" if s.valid else f" (not possible: {s.invalid_reason})")
            for s in steps
        )
        self._store.insert_message(notebook_id, conversation_id, "user", question, None)
        message = self._store.insert_message(
            notebook_id, conversation_id, "assistant", text, [], None, None, public(plan)
        )
        self._store.create_plan({**plan, "message_id": str(message.id)})
        return Answer(message_id=message.id, answer=text, plan=public(plan))

    def _library(self, bearer: str, notebook_id: str) -> dict[str, str]:
        """The user's library by id and name, without what the notebook has."""
        if self._ingest is None:
            return {}
        try:
            items = self._ingest.library(bearer)
        except IngestError as exc:
            log.warning("agent: the library could not be read: %s", exc)
            return {}
        return {
            str(i["id"]): str(i.get("name", ""))
            for i in items
            if notebook_id not in [str(n.get("id", n)) for n in i.get("notebooks") or []]
        }

    # -- confirm, cancel, read ------------------------------------------------

    def get(self, user_id: str, conversation_id: str, plan_id: str) -> dict[str, Any]:
        return public(self._owned(user_id, conversation_id, plan_id))

    def cancel(self, user_id: str, conversation_id: str, plan_id: str) -> dict[str, Any]:
        plan = self._owned(user_id, conversation_id, plan_id)
        if plan["status"] != "proposed":
            raise PlanNotOpen(plan_id)
        for step in plan["steps"]:
            step["state"] = "skipped"
        self._save(plan, status="cancelled", finished_at=datetime.now(UTC))
        return public(plan)

    def confirm(
        self, user_id: str, conversation_id: str, plan_id: str, bearer: str
    ) -> dict[str, Any]:
        """Run the plan: ingest steps now with this request's bearer, outputs
        created now (their jobs wait for sources), explanations when their
        output is ready (the worker)."""
        plan = self._owned(user_id, conversation_id, plan_id)
        if plan["status"] != "proposed":
            raise PlanNotOpen(plan_id)
        self._save(plan, status="running", confirmed_at=datetime.now(UTC))
        notebook_id = plan["notebook_id"]
        booking = Booking(user_id, notebook_id, "chat_answer", uuid.UUID(plan["action_id"]))
        for step in plan["steps"]:
            if not step["valid"]:
                step["state"] = "skipped"
                continue
            step["state"] = "running"
            try:
                self._run_now(plan, step, user_id, notebook_id, bearer, booking)
            except Exception as exc:  # a step's failure never stops the others
                step["state"], step["error"] = "failed", _public_error(exc)
            self._save(plan)
        self._store.insert_message(
            notebook_id,
            conversation_id,
            "assistant",
            "Running the plan. Its steps show their progress; I will report when it is done.",
            [],
        )
        self.advance_plan(plan)
        return public(plan)

    def _run_now(
        self,
        plan: dict[str, Any],
        step: dict[str, Any],
        user_id: str,
        notebook_id: str,
        bearer: str,
        booking: Booking,
    ) -> None:
        tool, args = step["tool"], step["args"]
        if tool in ("add_url", "add_from_library"):
            require_credit(self._store, user_id)
            if self._ingest is None:
                raise IngestError(0, "ingest is not configured")
            if tool == "add_url":
                source = self._ingest.add_url(bearer, notebook_id, args["url"])
                step["result"] = {"source_id": source.get("id"), "status": source.get("status")}
            else:
                added = self._ingest.add_library(bearer, notebook_id, args["library_ids"])
                step["result"] = added
            step["state"] = "done"
        elif tool == "create_output":
            output = self._outputs.create(
                user_id,
                notebook_id,
                args["kind"],
                OutputOptions.model_validate(
                    {k: v for k, v in args["options"].items() if k != "sources"}
                ),
                booking_id=plan["action_id"],
                bearer=bearer,  # its sources not read yet are read now, as the user
            )
            step["result"] = {"output_id": str(output.id)}
            step["state"] = "waiting"
        elif tool == "explain_output":
            step["state"] = "waiting"  # runs once its output is ready
        elif tool == "list_sources":
            step["result"] = {
                "sources": [
                    {"name": s.name, "kind": s.kind}
                    for s in self._store.notebook_documents(notebook_id)
                ]
            }
            step["state"] = "done"
        elif tool == "list_outputs":
            step["result"] = {
                "outputs": [
                    {"output_id": r.id, "title": r.title, "kind": r.kind, "status": r.status}
                    for r in self._store.list_outputs(notebook_id)
                ]
            }
            step["state"] = "done"

    # -- the worker's part ----------------------------------------------------

    def advance(self) -> int:
        """Move every running plan on; returns how many finished."""
        finished = 0
        for plan in self._store.running_plans():
            try:
                if self.advance_plan(plan):
                    finished += 1
            except Exception:
                log.exception("agent: plan %s could not be advanced", plan["id"])
        return finished

    def advance_plan(self, plan: dict[str, Any]) -> bool:
        """Outputs that became ready or failed, explanations whose output is
        ready, the timeout; the summary when nothing waits any more."""
        steps = plan["steps"]
        confirmed = plan.get("confirmed_at") or datetime.now(UTC)
        timed_out = (datetime.now(UTC) - _aware(confirmed)).total_seconds() > PLAN_TIMEOUT_S
        changed = False
        for step in steps:
            if step["state"] != "waiting":
                continue
            if step["tool"] == "create_output":
                changed |= self._advance_output(step, timed_out)
            elif step["tool"] == "explain_output":
                changed |= self._advance_explain(plan, step)
        if changed:
            self._save(plan)
        if any(s["state"] not in TERMINAL for s in steps):
            return False
        done = [s for s in steps if s["state"] == "done"]
        self._save(plan, status="done" if done else "failed", finished_at=datetime.now(UTC))
        lines = [
            f"{'✓' if s['state'] == 'done' else '✗'} {s['n']}. {s['label']}"
            + (f": {s['error']}" if s.get("error") else "")
            for s in steps
            if s["state"] != "skipped"
        ]
        self._store.insert_message(
            plan["notebook_id"],
            plan["conversation_id"],
            "assistant",
            "The plan is done.\n\n" + "\n".join(lines),
            [],
        )
        return True

    def _advance_output(self, step: dict[str, Any], timed_out: bool) -> bool:
        output_id = step["result"]["output_id"]
        row = self._store.get_output(output_id)
        if row is None or row.deleted_at is not None:
            step["state"], step["error"] = "failed", "the output was deleted"
            return True
        if row.status == "ready":
            step["state"] = "done"
            step["result"] = {"output_id": output_id, "title": row.title}
            return True
        if row.status == "failed":
            step["state"], step["error"] = "failed", row.error or "the output failed"
            return True
        if row.status == "waiting" and timed_out:
            # nothing ran, so nothing is charged; the user sees why it stopped
            self._store.update_output(output_id, status="failed", error=TIMEOUT_ERROR)
            step["state"], step["error"] = "failed", TIMEOUT_ERROR
            return True
        return False

    def _advance_explain(self, plan: dict[str, Any], step: dict[str, Any]) -> bool:
        args = step["args"]
        if "step" in args:
            source = plan["steps"][args["step"] - 1]
            if source["state"] in ("failed", "skipped"):
                step["state"], step["error"] = "failed", f"step {args['step']} did not finish"
                return True
            if source["state"] != "done":
                return False
            output_id = source["result"]["output_id"]
        else:
            output_id = args["output_id"]
        user_id, notebook_id = plan["owner"], plan["notebook_id"]
        booking = Booking(user_id, notebook_id, "chat_answer", uuid.UUID(plan["action_id"]))
        try:
            require_credit(self._store, user_id)
            answer = self._rag.ask(
                user_id,
                notebook_id,
                args.get("question") or EXPLAIN_DEFAULT,
                plan["conversation_id"],
                output_id,
                None,
                booking,
            )
        except Exception as exc:
            step["state"], step["error"] = "failed", _public_error(exc)
            return True
        step["state"] = "done"
        step["result"] = {"output_id": output_id, "message_id": str(answer.message_id)}
        return True

    # -- helpers -------------------------------------------------------------

    def _owned(self, user_id: str, conversation_id: str, plan_id: str) -> dict[str, Any]:
        plan = self._store.get_plan(plan_id)
        if plan is None or plan["owner"] != user_id or plan["conversation_id"] != conversation_id:
            raise PlanNotFound(plan_id)
        return plan

    def _save(self, plan: dict[str, Any], **fields: Any) -> None:
        for key in ("status", "confirmed_at", "finished_at"):
            if key in fields:
                plan[key] = fields[key]
        self._store.save_plan(plan["id"], steps=plan["steps"], plan=public(plan), **fields)


def _aware(value: Any) -> datetime:
    when = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def _public_error(exc: Exception) -> str:
    if isinstance(exc, IngestError):
        return f"ingest: {exc}" if exc.status else str(exc)
    from .service import public_error

    return public_error(exc)
