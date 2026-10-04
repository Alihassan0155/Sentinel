"""LangGraph workflow for one watch check.

The graph holds only short-lived execution state. PostgreSQL remains the durable
record of snapshots, findings, recommendations, actions, and notifications.
"""

import hashlib
import logging
import operator
from datetime import datetime, timezone
from typing import Annotated, Callable, TypedDict
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ActionStep, Investigation, Recommendation, UserProfile, WatchChange,
    WatchSnapshot, WatchSource,
)
from app.services.ownership import profile_for
from app.services.action import build_action_plan
from app.services.diff import detect_changes
from app.services.investigation import investigate_change
from app.services.memory import finding_text, relevant_context, remember
from app.services.notification import (
    alert_decision, dispatch_notification, queue_notification,
)
from app.services.recommendation import recommend
from app.services.relevance import assess_relevance, qualifies_for_investigation
from app.services.semantic import analyze_change

logger = logging.getLogger(__name__)


class WatchState(TypedDict, total=False):
    watch_id: int
    content: str
    content_hash: str
    changed: bool
    new_finding: bool
    duplicate: bool
    diff: dict
    analysis: dict | None
    change_id: int | None
    relevance: dict
    memories: list[dict]
    recommendation: dict | None
    recommendation_persisted: bool
    investigation: dict | None
    investigated: bool
    actions: list[dict]
    notification: dict | None
    checked_at: datetime
    executed_steps: Annotated[list[str], operator.add]


EMPTY_DIFF = {
    "changed": False, "added": [], "removed": [], "replaced": [],
    "added_count": 0, "removed_count": 0,
}


def build_watch_graph(db: Session, fetch_page: Callable[[str], str], *,
                      content_override: str | None = None,
                      allow_investigation: bool = True,
                      allow_notification: bool = True):
    def monitor(state: WatchState) -> dict:
        watch = db.get(WatchSource, state["watch_id"])
        if watch is None or watch.account_id is None:
            raise ValueError(f"Watch {state['watch_id']} not found")
        try:
            content = content_override if content_override is not None else fetch_page(watch.url)
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            previous = (
                db.query(WatchSnapshot)
                .filter(WatchSnapshot.watch_source_id == watch.id)
                .order_by(WatchSnapshot.fetched_at.desc(), WatchSnapshot.id.desc())
                .first()
            )
            changed = previous is not None and previous.content_hash != content_hash
            diff = detect_changes(previous.content_text, content) if changed else dict(EMPTY_DIFF)
            duplicate = bool(changed and db.query(WatchChange.id).join(
                WatchSnapshot, WatchSnapshot.id == WatchChange.snapshot_id,
            ).filter(
                WatchChange.watch_source_id == watch.id,
                WatchSnapshot.content_hash == content_hash,
            ).first())
            if not changed or duplicate:
                if previous is None or duplicate:
                    db.add(WatchSnapshot(
                        watch_source_id=watch.id, content_hash=content_hash,
                        content_text=content,
                    ))
                watch.last_checked_at = datetime.utcnow()
                db.commit()
            return {
                "content": content, "content_hash": content_hash,
                "changed": changed, "new_finding": changed and not duplicate,
                "duplicate": duplicate, "diff": diff,
                "checked_at": watch.last_checked_at if not changed or duplicate else datetime.utcnow(),
                "executed_steps": ["monitor"],
            }
        except Exception:
            db.rollback()
            raise

    def analyze(state: WatchState) -> dict:
        watch = db.get(WatchSource, state["watch_id"])
        diff = state["diff"]
        analysis = analyze_change(
            source_name=watch.name, category=watch.category,
            added=diff["added"], removed=diff["removed"],
            replaced=diff["replaced"],
        )
        try:
            snapshot = WatchSnapshot(
                watch_source_id=watch.id,
                content_hash=state["content_hash"],
                content_text=state["content"],
            )
            db.add(snapshot)
            db.flush()
            change = WatchChange(
                watch_source_id=watch.id, snapshot_id=snapshot.id,
                content_hash=state["content_hash"],
                importance=analysis.importance, change_type=analysis.change_type,
                summary=analysis.summary, why_it_matters=analysis.why_it_matters,
                should_notify=analysis.should_notify, entities=analysis.entities,
            )
            db.add(change)
            db.flush()
            change_id = change.id
            watch.last_checked_at = datetime.utcnow()
            db.commit()
            return {
                "analysis": analysis.model_dump(), "change_id": change_id,
                "checked_at": watch.last_checked_at,
                "executed_steps": ["analyze"],
            }
        except Exception:
            db.rollback()
            raise

    def relevance(state: WatchState) -> dict:
        watch = db.get(WatchSource, state["watch_id"])
        profile = profile_for(db, db.get(WatchSource, state["watch_id"]).account_id)
        analysis = state["analysis"]
        arguments = dict(
            category=watch.category, summary=analysis["summary"],
            why_it_matters=analysis["why_it_matters"],
            entities=analysis["entities"], importance=analysis["importance"],
            change_type=analysis["change_type"],
        )
        initial = assess_relevance(profile, **arguments)
        memories = []
        if (profile is not None
                and analysis["change_type"] != "cosmetic"
                and (initial["relevance_score"] >= 10
                     or analysis["importance"] in {"high", "critical"})):
            memories = relevant_context(db, finding_text(
                watch.category, analysis["summary"],
                analysis["why_it_matters"], analysis["entities"],
            ), account_id=watch.account_id)
        result = assess_relevance(profile, memories=memories, **arguments) if memories else initial
        return {"relevance": result, "memories": memories,
                "executed_steps": ["relevance"]}

    def recommendation(state: WatchState) -> dict:
        profile = profile_for(db, db.get(WatchSource, state["watch_id"]).account_id)
        investigation = state.get("investigation") or {}
        result = recommend(
            profile=profile, relevance=state["relevance"],
            memories=state.get("memories", []),
            investigation=investigation.get("result") if investigation.get("status") == "completed" else None,
            investigation_status=investigation.get("status"),
        )
        # Persist only the final decision. The first pass is used to route work.
        persisted = False
        if state.get("investigated") or not _investigate_next(state, result):
            try:
                db.add(Recommendation(watch_change_id=state["change_id"], **result))
                db.commit()
                persisted = True
            except Exception:
                db.rollback()
                logger.exception("Could not persist recommendation for change %s", state["change_id"])
        return {"recommendation": result, "recommendation_persisted": persisted,
                "executed_steps": ["recommendation"]}

    def investigation(state: WatchState) -> dict:
        watch = db.get(WatchSource, state["watch_id"])
        change = db.get(WatchChange, state["change_id"])
        profile = profile_for(db, db.get(WatchSource, state["watch_id"]).account_id)
        try:
            result = investigate_change(
                change, watch.url, watch.category, profile,
                memories=state.get("memories", []),
            )
            record = Investigation(
                watch_change_id=change.id, status="completed",
                result=result.model_dump(mode="json"),
            )
            db.add(record)
            db.commit()
        except Exception as error:
            db.rollback()
            logger.exception("Investigation failed for change %s", change.id)
            record = Investigation(
                watch_change_id=change.id, status="failed", error=str(error)[:1000],
            )
            try:
                db.add(record)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Could not persist failed investigation for change %s", change.id)
        persisted = (
            db.query(Investigation)
            .filter(Investigation.watch_change_id == change.id).first()
        )
        return {
            "investigation": (
                {"status": persisted.status, "result": persisted.result,
                 "investigated_at": persisted.investigated_at}
                if persisted else {"status": "failed", "result": None}
            ),
            "investigated": True,
            "executed_steps": ["investigation"],
        }

    def action(state: WatchState) -> dict:
        watch = db.get(WatchSource, state["watch_id"])
        profile = profile_for(db, db.get(WatchSource, state["watch_id"]).account_id)
        investigation = state.get("investigation") or {}
        plan = build_action_plan(
            investigation.get("result") if investigation.get("status") == "completed" else None,
            profile, watch.url,
        )
        try:
            records = [
                ActionStep(watch_change_id=state["change_id"], **item)
                for item in plan
            ]
            db.add_all(records)
            db.commit()
            return {"actions": [
                {"id": step.id, "position": step.position, "title": step.title,
                 "status": step.status, "resource": step.resource,
                 "resource_status": step.resource_status,
                 "source_urls": step.source_urls, "deadline": step.deadline}
                for step in records
            ], "executed_steps": ["action"]}
        except Exception:
            db.rollback()
            logger.exception("Could not persist action plan for change %s", state["change_id"])
            return {"actions": [], "executed_steps": ["action"]}

    def notify(state: WatchState) -> dict:
        watch = db.get(WatchSource, state["watch_id"])
        change = db.get(WatchChange, state["change_id"])
        investigation = state.get("investigation") or {}
        steps = (
            db.query(ActionStep)
            .filter(ActionStep.watch_change_id == change.id)
            .order_by(ActionStep.position).all()
        )
        try:
            record = queue_notification(
                db, change, watch, state["recommendation"],
                investigation.get("result") if investigation.get("status") == "completed" else None,
                steps,
            )
            if record is not None:
                record = dispatch_notification(db, record)
            return {"notification": (
                {"id": record.id, "status": record.status, "reason": record.reason}
                if record else None
            ), "executed_steps": ["notify"]}
        except Exception:
            db.rollback()
            logger.exception("Could not queue notification for change %s", change.id)
            return {"notification": None, "executed_steps": ["notify"]}

    def memory(state: WatchState) -> dict:
        watch = db.get(WatchSource, state["watch_id"])
        change = db.get(WatchChange, state["change_id"])
        try:
            remember(
                db, account_id=watch.account_id, kind="finding", source_key=f"finding:change:{change.id}",
                source_url=watch.url,
                content=finding_text(watch.category, change.summary,
                                     change.why_it_matters, change.entities),
                metadata={"change_id": change.id, "watch_id": watch.id},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not remember change %s", change.id)
        return {"executed_steps": ["memory"]}

    def _investigate_next(state: WatchState, result: dict) -> bool:
        score = state["relevance"]["relevance_score"]
        return (
            allow_investigation
            and not state.get("investigated")
            and result["recommendation"] == "recommended"
            and (
                qualifies_for_investigation(
                    score, state["relevance"]["priority"],
                    settings.investigation_threshold,
                )
                or (score >= 60 and state["analysis"]["change_type"] == "deadline")
            )
        )

    def after_monitor(state: WatchState) -> str:
        return "analyze" if state["new_finding"] else END

    def after_relevance(state: WatchState) -> str:
        return "recommendation" if state["relevance"]["priority"] != "ignore" else END

    def after_recommendation(state: WatchState) -> str:
        result = state["recommendation"]
        if _investigate_next(state, result):
            return "investigation"
        if not state.get("recommendation_persisted"):
            return "memory"
        return "action" if result["recommendation"] == "recommended" else "memory"

    def after_action(state: WatchState) -> str:
        if not allow_notification:
            return "memory"
        change = db.get(WatchChange, state["change_id"])
        investigation = state.get("investigation") or {}
        result = investigation.get("result") if investigation.get("status") == "completed" else None
        today = datetime.now(ZoneInfo(settings.notification_timezone)).date()
        should_alert, _ = alert_decision(
            change, state["recommendation"], result, today=today,
        )
        return "notify" if should_alert else "memory"

    graph = StateGraph(WatchState)
    graph.add_node("monitor", monitor)
    graph.add_node("analyze", analyze)
    graph.add_node("relevance", relevance)
    graph.add_node("recommendation", recommendation)
    graph.add_node("investigation", investigation)
    graph.add_node("action", action)
    graph.add_node("notify", notify)
    graph.add_node("memory", memory)
    graph.add_edge(START, "monitor")
    graph.add_conditional_edges("monitor", after_monitor, ["analyze", END])
    graph.add_edge("analyze", "relevance")
    graph.add_conditional_edges("relevance", after_relevance, ["recommendation", END])
    graph.add_conditional_edges("recommendation", after_recommendation,
                                ["investigation", "action", "memory"])
    graph.add_edge("investigation", "recommendation")
    graph.add_conditional_edges("action", after_action, ["notify", "memory"])
    graph.add_edge("notify", "memory")
    graph.add_edge("memory", END)
    return graph.compile()


def run_watch_graph(watch: WatchSource, db: Session,
                    fetch_page: Callable[[str], str], *,
                    content_override: str | None = None,
                    allow_investigation: bool = True,
                    allow_notification: bool = True) -> dict:
    graph = build_watch_graph(
        db, fetch_page, content_override=content_override,
        allow_investigation=allow_investigation,
        allow_notification=allow_notification,
    )
    state = graph.invoke({"watch_id": watch.id, "executed_steps": []})
    diff = state.get("diff", EMPTY_DIFF)
    analysis = state.get("analysis")
    notification = state.get("notification")
    if analysis is not None:
        analysis = dict(analysis)
        analysis["should_notify"] = bool(
            analysis["should_notify"] and notification
            and notification["status"] in {"pending", "sent"}
        )
    relevance = state.get("relevance", {
        "relevance_score": 0, "reasons": ["No profile preferences configured."],
        "priority": "ignore",
    })
    return {
        "watch_id": watch.id, "name": watch.name, "url": watch.url,
        "changed": state.get("changed", False),
        "duplicate": state.get("duplicate", False),
        "added_count": diff["added_count"], "removed_count": diff["removed_count"],
        "added": diff["added"], "removed": diff["removed"],
        "replaced": diff["replaced"], "semantic_analysis": analysis,
        **relevance,
        "recommendation": state.get("recommendation"),
        "investigation": state.get("investigation"),
        "actions": state.get("actions", []),
        "notification": notification,
        "content_length": len(state["content"]),
        "checked_at": state["checked_at"],
        "workflow_steps": state["executed_steps"],
    }
