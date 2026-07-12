from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import datetime, timezone
from html import escape
from typing import Any

import streamlit as st

from app.frontend.utils.api_client import api_get, api_post
from app.frontend.utils.ui_components import (
    apply_app_theme,
    card,
    chip,
    empty_state,
    equal_container,
    page_header,
    section_heading,
    soft_divider,
    step_card,
    timeline_item,
)
from app.frontend.utils.ui_helpers import (
    format_label,
    format_local_datetime,
    format_status,
    format_workflow,
)


st.set_page_config(
    page_title="Agentic IT Service Desk",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_app_theme()


DEFAULT_EMPLOYEE_ID = "E10231"


CHAT_STATE_DEFAULTS = {
    "chat_messages": [],
    "last_message": "",
    "last_employee_id": DEFAULT_EMPLOYEE_ID,
    "last_response": None,
    "last_request_id": None,
    "awaiting_confirmation": False,
    "pending_chat_request": False,
    "pending_approval_request": False,
}
for key, value in CHAT_STATE_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value.copy() if isinstance(value, list) else value


WORKFLOW_STEPS = [
    ("Intent", "Classify the request"),
    ("Evidence", "Retrieve KB policy"),
    ("Context", "Load user/account"),
    ("Approval", "Confirm sensitive action"),
    ("Execution", "Run mock IAM tool"),
    ("Ticket", "Persist service record"),
]


QUICK_ACTIONS = [
    ("Reset password", "Please reset my password.", "Most common identity workflow."),
    ("Unlock account", "My account is locked. Please unlock it.", "Checks account status and policy."),
    ("Re-enable VPN", "My VPN access is disabled. Please re-enable it.", "Uses remote access evidence."),
    ("Explain policy", "What evidence applies to my access request?", "Good for audit demos."),
]


def _safe_text(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _first_present(*values: Any, default: str = "—") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def add_chat_message(role: str, content: str) -> None:
    st.session_state.chat_messages.append(
        {
            "role": role,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )


def _current_employee_id() -> str:
    return str(st.session_state.get("last_employee_id") or "").strip()


def _employee_required_message() -> str:
    return "Employee ID is required. Enter it in the sidebar before submitting or approving a request."


def call_backend(confirm_flag: bool) -> dict[str, Any]:
    employee_id = _current_employee_id()
    if not employee_id:
        raise ValueError(_employee_required_message())

    payload = {
        "message": st.session_state.last_message,
        "employee_id": employee_id,
        "confirm": confirm_flag,
        "request_id": st.session_state.last_request_id,
    }

    response = api_post("/chat", json=payload, timeout=90)
    response.raise_for_status()

    data = response.json()
    st.session_state.last_response = data
    st.session_state.last_request_id = data.get("request_id") or st.session_state.last_request_id

    status = (data.get("status") or data.get("response", {}).get("status") or "").lower()
    st.session_state.awaiting_confirmation = status in {
        "awaiting_confirmation",
        "waiting_for_confirmation",
    }
    return data


def fetch_workflow_history(request_id: str) -> dict[str, Any] | None:
    if not request_id or request_id == "unknown":
        return None
    try:
        response = api_get(f"/workflow/history/{request_id}", timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def extract_evidence(resp: dict[str, Any]) -> list[dict[str, Any]]:
    data = resp.get("data", {}) or {}
    if isinstance(data, dict):
        evidence_chunks = data.get("evidence_chunks") or data.get("retrieved_documents") or data.get("retrievals")
        if evidence_chunks:
            return [row for row in evidence_chunks if isinstance(row, dict)]

    evidence = resp.get("evidence", {}) or {}
    if isinstance(evidence, dict):
        results = evidence.get("results", [])
        if results:
            return [row for row in results if isinstance(row, dict)]
    return []


def _assistant_text(resp: dict[str, Any]) -> str:
    return resp.get("message") or resp.get("response", {}).get("message") or "No response returned."


def _current_status(resp: dict[str, Any] | None) -> str:
    if not resp:
        return "Ready"
    return format_status(resp.get("status") or resp.get("response", {}).get("status") or "unknown")


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### Session")
        st.caption("Set the user context before sending a request.")

        employee_value = st.text_input(
            "Employee ID",
            value=str(st.session_state.last_employee_id or ""),
            placeholder="Employee ID",
            help="Required. The backend uses only this field to load identity, IAM, and ticket context.",
        )
        st.session_state.last_employee_id = employee_value.strip()
        if not st.session_state.last_employee_id:
            st.warning("Employee ID is required before requests can be submitted.")

        st.markdown(
            chip("Status", _current_status(st.session_state.last_response), tone="info")
            + chip("Request", st.session_state.last_request_id or "new", tone="neutral")
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Clear", use_container_width=True):
                st.session_state.chat_messages = []
                st.session_state.last_message = ""
                st.session_state.last_response = None
                st.session_state.last_request_id = None
                st.session_state.awaiting_confirmation = False
                st.rerun()
        with c2:
            if st.button("Reload", use_container_width=True):
                st.rerun()

        st.divider()
        st.markdown("### Navigation")
        st.page_link("Streamlit_App.py", label="Chat Home")
        st.page_link("pages/1_Dashboard.py", label="Operations Dashboard")
        st.page_link("pages/2_Tickets.py", label="Tickets")
        st.page_link("pages/3_Audit.py", label="Audit Logs")
        st.page_link("pages/4_Architecture.py", label="Architecture & Agents")
        st.page_link("pages/4_Knowledge_Base.py", label="Knowledge Base")
        st.page_link("pages/5_Workflow_History.py", label="Workflow History")
        st.page_link("pages/6_System_Admin.py", label="System Admin")

        st.divider()
        card(
            "What this demo proves",
            "Intent classification, RAG evidence, approval gating, mock execution, audit, workflow history, and ticket creation in one flow.",
            tone="info",
        )


def render_workflow_strip() -> None:
    section_heading("Agent workflow", "The six governed stages stay visible and evenly sized across the page.")
    cols = st.columns(len(WORKFLOW_STEPS))
    for idx, (title, detail) in enumerate(WORKFLOW_STEPS):
        with cols[idx]:
            step_card(idx + 1, title, detail)


def render_chat_history() -> None:
    if not st.session_state.chat_messages:
        empty_state(
            "Start a request",
            "Use the composer at the bottom of this chat box or choose a quick action. Submitted messages appear in the conversation immediately.",
        )
        return

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            st.caption(format_local_datetime(message.get("ts")))


def render_quick_actions() -> str | None:
    if st.session_state.chat_messages:
        return None

    section_heading("Quick actions", "Use these to demo the most important workflows without typing.")
    prompt: str | None = None
    cols = st.columns(4)
    for idx, (label, text, detail) in enumerate(QUICK_ACTIONS):
        with cols[idx % 4]:
            with equal_container(height=154):
                st.markdown(f"**{label}**")
                st.caption(detail)
                if st.button("Use this", use_container_width=True, key=f"quick_action_{idx}"):
                    prompt = text
    return prompt


def render_progress(events: list[dict[str, Any]]) -> None:
    if not events:
        empty_state("No workflow progress yet", "Submit a request to see agent-by-agent progress.")
        return

    for index, event in enumerate(events[-8:], start=1):
        node = format_label(event.get("node_name"))
        stage = format_label(event.get("stage"))
        outcome = format_status(event.get("outcome"))
        created_at = format_local_datetime(event.get("created_at"))
        outcome_raw = str(event.get("outcome") or "").lower()
        tone = "success" if outcome_raw in {"completed", "confirmed", "ok", "success"} else "danger" if "error" in outcome_raw or "fail" in outcome_raw else "warning" if "pending" in outcome_raw or "waiting" in outcome_raw else "neutral"
        timeline_item(
            index,
            node,
            stage,
            chips=chip("Outcome", outcome, tone=tone) + chip("Time", created_at),
        )


def render_evidence(resp: dict[str, Any]) -> None:
    evidence_items = extract_evidence(resp)
    if not evidence_items:
        empty_state("No retrieved evidence", "The workflow did not return evidence chunks for this response.")
        return

    for i, item in enumerate(evidence_items, start=1):
        source = item.get("source") or item.get("document_name") or item.get("source_document") or "Unknown"
        workflow_name = format_workflow(item.get("workflow") or "Unknown")
        chunk_id = item.get("chunk_id") or item.get("id") or "Unknown"
        chunk_index = item.get("chunk_index", "Unknown")
        score = item.get("score", "N/A")
        confidence = item.get("confidence", "unknown")
        strategy = item.get("retrieval_strategy", "unknown")
        citation_label = item.get("citation_label") or item.get("citation", {}).get("label") or "N/A"
        matched_terms = item.get("matched_terms") or []
        text = item.get("text") or item.get("content") or item.get("chunk_text") or item.get("chunk") or ""

        with st.container(border=True):
            st.markdown(f"**Evidence {i}: {escape(_safe_text(source))}**")
            st.markdown(
                chip("Workflow", workflow_name, tone="info")
                + chip("Confidence", confidence, tone="success" if str(confidence).lower() == "high" else "warning")
                + chip("Score", score, tone="neutral")
                + chip("Strategy", strategy, tone="accent")
                + chip("Citation", citation_label, tone="neutral")
            )
            st.write(text)
            if matched_terms:
                st.caption("Matched terms: " + ", ".join(str(term) for term in matched_terms[:14]))
            with st.expander("Evidence metadata", expanded=False):
                st.json(
                    {
                        "chunk_id": chunk_id,
                        "chunk_index": chunk_index,
                        "score": item.get("score"),
                        "semantic_score": item.get("semantic_score"),
                        "lexical_score": item.get("lexical_score"),
                        "confidence": item.get("confidence"),
                        "match_reasons": item.get("match_reasons"),
                        "citation": item.get("citation"),
                        "metadata": item.get("metadata"),
                    }
                )


def _case_row(label: str, value: Any, helper: str = "") -> None:
    """Render a compact case metadata row inside the single cockpit card."""
    label_text = _safe_text(label, "Field")
    value_text = _safe_text(value, "—")
    left, right = st.columns([0.38, 0.62])
    with left:
        st.caption(label_text)
    with right:
        st.markdown(f"**{escape(value_text)}**")
        if helper:
            st.caption(helper)


def _confirmation_label(resp: dict[str, Any], status: str) -> str:
    status_raw = str(resp.get("status") or resp.get("response", {}).get("status") or "").lower()
    if "awaiting" in status_raw or "confirmation" in status_raw or st.session_state.awaiting_confirmation:
        return "Waiting for approval"
    if str(status).lower() in {"ok", "completed", "success"}:
        return "No approval pending"
    return _first_present(
        resp.get("confirmation_status"),
        resp.get("data", {}).get("confirmation_status") if isinstance(resp.get("data"), dict) else None,
        default="No approval pending",
    )


def render_case_summary() -> None:
    resp = st.session_state.last_response
    if not resp:
        empty_state("No active case", "The right panel will populate after the first assistant response.")
        return

    data = resp.get("data", {}) if isinstance(resp.get("data"), dict) else {}
    response_obj = resp.get("response", {}) if isinstance(resp.get("response"), dict) else {}

    status_raw = _first_present(resp.get("status"), response_obj.get("status"), default="unknown")
    status = format_status(status_raw)
    workflow_raw = _first_present(resp.get("workflow"), resp.get("intent"), data.get("workflow"), data.get("intent"), default="unknown")
    workflow = format_workflow(workflow_raw)
    request_id = _first_present(resp.get("request_id"), data.get("request_id"), st.session_state.last_request_id, default="unknown")
    ticket_id = _first_present(resp.get("ticket_id"), data.get("ticket_id"), response_obj.get("ticket_id"), default="Not created yet")

    history = fetch_workflow_history(str(request_id))
    session = history.get("session", {}) if isinstance(history, dict) and isinstance(history.get("session"), dict) else {}

    current_step = format_label(
        _first_present(
            resp.get("current_node"),
            data.get("current_node"),
            response_obj.get("current_node"),
            session.get("current_node"),
            "approval" if st.session_state.awaiting_confirmation else None,
            default="response",
        )
    )
    detected_intent = format_workflow(
        _first_present(
            resp.get("intent"),
            data.get("intent"),
            session.get("intent"),
            workflow_raw,
            default="unknown",
        )
    )
    confirmation_state = _confirmation_label(resp, status)

    with st.container(border=True):
        st.markdown("**Case overview**")
        st.caption("Live metadata for the active request.")
        st.divider()
        _case_row("Status", status, "Current request outcome from the workflow service.")
        _case_row("Workflow", workflow, "Business workflow selected by the intent agent.")
        _case_row("Current step", current_step, "Latest LangGraph node recorded for this request.")
        _case_row("Detected intent", detected_intent, "Intent value used for routing and evidence retrieval.")
        _case_row("Approval", confirmation_state, "Shows whether the request is waiting for user confirmation.")
        _case_row("Request ID", request_id, "Use this ID in Workflow History for full traceability.")
        _case_row("Ticket", ticket_id, "Created after approval/execution when applicable.")

    message = resp.get("message") or response_obj.get("message")
    if message:
        section_heading("Latest assistant response")
        st.write(message)

    llm_trace = resp.get("llm_trace") or data.get("llm_trace") or {}
    if llm_trace:
        st.markdown(
            chip("LLM", "Used" if llm_trace.get("used") else "Not used", tone="success" if llm_trace.get("used") else "warning")
            + chip("Status", format_status(llm_trace.get("status", "unknown")), tone="info")
            + chip("Fallback", "Yes" if llm_trace.get("fallback") else "No", tone="warning" if llm_trace.get("fallback") else "neutral")
            + chip("Model", llm_trace.get("model", "unknown"), tone="neutral")
        )
        with st.expander("AI trace", expanded=False):
            st.json(llm_trace)

    with st.expander("Retrieved evidence", expanded=True):
        render_evidence(resp)

    if history:
        events = history.get("events", []) or []
        with st.expander("Workflow progress", expanded=True):
            render_progress([row for row in events if isinstance(row, dict)])

        response_payload = session.get("response_payload") or {}
        if isinstance(response_payload, dict) and response_payload.get("llm_trace"):
            with st.expander("Final LLM proof", expanded=False):
                st.json(response_payload.get("llm_trace"))


def queue_user_message(user_text: str) -> None:
    """Queue a user message so it renders above the composer before backend work starts."""
    clean_text = str(user_text or "").strip()
    if not clean_text:
        return

    st.session_state.last_message = clean_text
    add_chat_message("user", clean_text)
    st.session_state.pending_chat_request = True
    st.session_state.pending_approval_request = False
    st.rerun()


def queue_approval() -> None:
    """Queue the approval action so the conversation stays above the composer."""
    st.session_state.pending_approval_request = True
    st.session_state.pending_chat_request = False
    st.rerun()


def _set_missing_employee_error() -> None:
    error_text = _employee_required_message()
    add_chat_message("assistant", error_text)
    st.session_state.last_response = {
        "status": "failed",
        "message": error_text,
        "error": "missing_employee_id",
    }
    st.session_state.awaiting_confirmation = False
    st.session_state.pending_chat_request = False
    st.session_state.pending_approval_request = False


def process_pending_chat_request() -> None:
    if not st.session_state.pending_chat_request:
        return

    if not _current_employee_id():
        _set_missing_employee_error()
        st.rerun()

    try:
        with st.chat_message("assistant"):
            with st.spinner("Routing through intent, retrieval, context, approval, execution, and response agents..."):
                resp = call_backend(confirm_flag=False)
            assistant_text = _assistant_text(resp)
            st.markdown(assistant_text)
            add_chat_message("assistant", assistant_text)
        st.session_state.pending_chat_request = False
        st.rerun()
    except Exception as exc:
        error_text = f"Request failed: {exc}"
        with st.chat_message("assistant"):
            st.error(error_text)
        add_chat_message("assistant", error_text)
        st.session_state.pending_chat_request = False
        st.rerun()


def process_pending_approval() -> None:
    if not st.session_state.pending_approval_request:
        return

    if not _current_employee_id():
        _set_missing_employee_error()
        st.rerun()

    try:
        with st.chat_message("assistant"):
            with st.spinner("Executing approved action and creating the service record..."):
                resp = call_backend(confirm_flag=True)
            assistant_text = _assistant_text(resp)
            st.markdown(assistant_text)
            add_chat_message("assistant", assistant_text)
        st.session_state.pending_approval_request = False
        st.rerun()
    except Exception as exc:
        error_text = f"Confirmation failed: {exc}"
        with st.chat_message("assistant"):
            st.error(error_text)
        add_chat_message("assistant", error_text)
        st.session_state.pending_approval_request = False
        st.rerun()


render_sidebar()
page_header(
    "Agentic IT Service Desk",
    "A polished service desk cockpit for governed IT actions: ask a request, review retrieved evidence, approve sensitive changes, and inspect the audit trail.",
    eyebrow="Chat Home • Agentic workflow",
    icon="🛠️",
)
render_workflow_strip()
soft_divider()

left, right = st.columns([1.86, 1], gap="large")

with left:
    with st.container(border=True):
        section_heading(
            "Conversation",
            "Messages render above the composer. The composer stays anchored at the bottom of this chat box.",
        )
        render_chat_history()
        process_pending_chat_request()
        process_pending_approval()

        if st.session_state.awaiting_confirmation and st.session_state.last_response:
            st.warning(st.session_state.last_response.get("message", "Please confirm to continue."))
            if st.button(
                "Approve and Continue",
                use_container_width=True,
                key="approve_continue_main",
                disabled=bool(st.session_state.pending_chat_request or st.session_state.pending_approval_request),
            ):
                queue_approval()

        quick_prompt = render_quick_actions()
        if quick_prompt:
            queue_user_message(quick_prompt)

        st.divider()
        st.caption("Message composer")
        typed_prompt = st.chat_input(
            "Describe your issue, for example: reset my password",
            disabled=bool(st.session_state.pending_chat_request or st.session_state.pending_approval_request),
        )
        if typed_prompt and typed_prompt.strip():
            queue_user_message(typed_prompt)

with right:
    with st.container(border=True):
        section_heading("Case cockpit", "Live status, evidence, request metadata, and workflow proof.")
        render_case_summary()
