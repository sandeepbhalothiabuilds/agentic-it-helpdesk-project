from __future__ import annotations

from typing import Any

import streamlit as st

from app.frontend.utils.api_client import api_get, api_patch, api_post
from app.frontend.utils.ui_components import (
    apply_app_theme,
    card,
    chip,
    empty_state,
    kpi_card,
    page_header,
    render_table,
    section_heading,
    soft_divider,
    status_card,
    value_card,
)
from app.frontend.utils.ui_helpers import format_local_datetime, format_workflow, shorten


WORKFLOW_OPTIONS = ["all", "general", "password_reset", "account_unlock", "vpn_reenable"]
WORKFLOW_EDIT_OPTIONS = ["general", "password_reset", "account_unlock", "vpn_reenable"]

st.set_page_config(page_title="Knowledge Base", page_icon="📚", layout="wide")
apply_app_theme()
page_header(
    "Knowledge Base",
    "Manage uploaded runbooks, document revisions, active vector chunks, and searchable evidence used by the retrieval agent.",
    eyebrow="RAG • Document lifecycle",
    icon="📚",
)


for key in ("kb_upload_result", "kb_refresh_result", "kb_action_result"):
    if key not in st.session_state:
        st.session_state[key] = None


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _get_json(path: str, *, params: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    response = api_get(path, params=params or {}, timeout=timeout)
    response.raise_for_status()
    return _safe_dict(response.json())


def _post_json(path: str, *, payload: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any]:
    response = api_post(path, json=payload or {}, timeout=timeout)
    response.raise_for_status()
    return _safe_dict(response.json())


def _patch_json(path: str, *, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    response = api_patch(path, json=payload, timeout=timeout)
    response.raise_for_status()
    return _safe_dict(response.json())


def _render_summary(summary: dict[str, Any]) -> None:
    cols = st.columns(6)
    cards = [
        ("Active Docs", summary.get("active_documents", 0), "logical sources", "info"),
        ("Active Revs", summary.get("active_revisions", 0), "searchable revisions", "success"),
        ("All Revs", summary.get("all_revisions", summary.get("total_document_versions", 0)), "history retained", "neutral"),
        ("Active Chunks", summary.get("active_chunks", 0), "retrieval target", "accent"),
        ("All Chunks", summary.get("all_chunks", summary.get("total_chunks", 0)), "indexed total", "neutral"),
        ("Workflows", summary.get("active_workflows", 0), "KB categories", "info"),
    ]
    for index, (label, value, detail, tone) in enumerate(cards):
        with cols[index % 6]:
            kpi_card(label, value, detail=detail, tone=tone)


with st.sidebar:
    st.markdown("### Knowledge Filters")
    search_query = st.text_input("Search", placeholder="document, filename, hash, or chunk text")
    selected_workflow = st.selectbox("Workflow", WORKFLOW_OPTIONS, index=0)
    active_filter = st.selectbox("Revision State", ["active only", "inactive only", "all"], index=0)
    chunk_limit = st.number_input("Max Chunks", min_value=10, max_value=500, value=50, step=10)

    st.divider()
    if st.button("Refresh Vector Store", use_container_width=True):
        try:
            result = _post_json("/knowledge-base/refresh", timeout=300)
            st.session_state.kb_refresh_result = result
            st.success(result.get("message", "Vector store refreshed."))
        except Exception as exc:
            st.error(f"Refresh failed: {exc}")

    if st.button("Reload Page", use_container_width=True):
        st.rerun()

workflow_param = None if selected_workflow == "all" else selected_workflow
active_param: bool | None
if active_filter == "active only":
    active_param = True
elif active_filter == "inactive only":
    active_param = False
else:
    active_param = None

request_params = {
    "chunk_limit": int(chunk_limit),
    "query": search_query.strip() or None,
    "workflow": workflow_param,
    "active_only": active_param,
}
request_params = {key: value for key, value in request_params.items() if value is not None}

try:
    payload = _get_json("/knowledge-base/summary", params=request_params, timeout=60)
except Exception as exc:
    st.error(f"Failed to load knowledge base: {exc}")
    st.stop()

summary = _safe_dict(payload.get("summary"))
documents = _records(payload.get("documents"))
revisions = _records(payload.get("revisions"))
chunks = _records(payload.get("chunks"))
workflow_breakdown = _records(payload.get("workflow_breakdown"))

if st.session_state.kb_refresh_result:
    st.success(st.session_state.kb_refresh_result.get("message", "Latest refresh completed."))
    with st.expander("Latest refresh result", expanded=False):
        st.json(st.session_state.kb_refresh_result)

if st.session_state.kb_action_result:
    st.info(st.session_state.kb_action_result.get("message", "Latest document action completed."))
    with st.expander("Latest document action result", expanded=False):
        st.json(st.session_state.kb_action_result)

_render_summary(summary)
st.caption(f"Last indexed: {format_local_datetime(summary.get('last_indexed')) if summary.get('last_indexed') else 'unknown'}")
soft_divider()

tabs = st.tabs(["Overview", "Upload", "Documents", "Revisions & Actions", "Search & Chunks"])

with tabs[0]:
    left, right = st.columns([1.25, 0.75])
    with left:
        section_heading("Workflow breakdown", "Document coverage by workflow tag.")
        render_table(workflow_breakdown, empty_title="No workflow breakdown", empty_text="No workflow coverage was returned.")
    with right:
        section_heading("Current filters", "The API request behind this page.")
        with st.container(border=True):
            st.json(summary.get("filters", request_params))
        section_heading("Retrieval source", "What the runtime retriever searches.")
        card(
            "Active document chunks",
            "Runtime retrieval searches only active chunks. Inactive revisions remain available for audit, rollback, download, and metadata review.",
            tone="accent",
        )

with tabs[1]:
    section_heading("Upload document", "Upload a new logical document or use the same logical document name to create a new revision.")
    left, right = st.columns([1.1, 0.9])
    with left:
        upload_file = st.file_uploader("Choose a document", type=["pdf", "docx", "txt", "md"], accept_multiple_files=False)
        workflow = st.selectbox("Workflow Tag", options=WORKFLOW_EDIT_OPTIONS, index=0)
        source_document_name = st.text_input(
            "Logical Document Name",
            value=upload_file.name if upload_file else "",
            placeholder="Use the same logical name when uploading a replacement revision",
        )
        uploaded_by = st.text_input("Uploaded By", value="streamlit")
        if st.button("Upload & Index", use_container_width=True):
            if not upload_file:
                st.warning("Please choose a file first.")
            else:
                try:
                    files = {
                        "file": (
                            upload_file.name,
                            upload_file.getvalue(),
                            upload_file.type or "application/octet-stream",
                        )
                    }
                    data = {
                        "workflow": workflow,
                        "uploaded_by": uploaded_by,
                        "source_document_name": source_document_name.strip(),
                    }
                    response = api_post("/knowledge-base/upload", files=files, data=data, timeout=180)
                    response.raise_for_status()
                    result = response.json()
                    st.session_state.kb_upload_result = result
                    st.success(result.get("message", "Upload completed successfully."))
                    st.rerun()
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")
    with right:
        with st.container(border=True):
            value_card("Supported formats", "PDF, DOCX, TXT, MD", detail="Text is extracted, chunked, embedded, and persisted.", tone="info")
            value_card("Revision behavior", "Latest active revision wins", detail="Older revisions remain available for rollback and audit.", tone="accent")
            if st.session_state.kb_upload_result:
                with st.expander("Latest upload result", expanded=True):
                    st.json(st.session_state.kb_upload_result)

with tabs[2]:
    section_heading("Documents", "Logical source documents grouped across revisions.")
    render_table(documents, empty_title="No documents", empty_text="No documents matched the current filters.")

with tabs[3]:
    section_heading("Revision history", "Activate, deactivate, download, or edit metadata for a specific revision.")
    render_table(revisions, empty_title="No revisions", empty_text="No revisions matched the current filters.")
    soft_divider()

    if not revisions:
        empty_state("No revision actions available", "No revision is currently available for activation, deactivation, or metadata editing.")
    else:
        revision_labels = {
            f"{row.get('source_document')} | rev {row.get('revision_number')} | {row.get('document_id')} | {'active' if row.get('is_active') else 'inactive'}": row.get("document_id")
            for row in revisions
        }
        selected_label = st.selectbox("Select Revision", list(revision_labels.keys()))
        selected_document_id = str(revision_labels[selected_label])
        selected_revision = next((row for row in revisions if str(row.get("document_id")) == selected_document_id), {})

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi_card("Revision", selected_revision.get("revision_number", "—"), detail="Selected revision number")
        with c2:
            status_card("Active", "ok" if selected_revision.get("is_active") else "disabled", detail="Visible to retrieval")
        with c3:
            kpi_card("Active Chunks", selected_revision.get("active_chunk_count", 0), detail="Active searchable chunks", tone="accent")
        with c4:
            value_card("Workflow", format_workflow(selected_revision.get("workflow")), detail="Workflow metadata tag", tone="info")

        with st.container(border=True):
            section_heading("Revision actions", "Changes are applied to the document registry and synchronized with chunks.")
            action_actor = st.text_input("Action Actor", value="streamlit")
            current_workflow = selected_revision.get("workflow") if selected_revision.get("workflow") in WORKFLOW_EDIT_OPTIONS else "general"
            new_workflow = st.selectbox("Update Workflow", options=WORKFLOW_EDIT_OPTIONS, index=WORKFLOW_EDIT_OPTIONS.index(current_workflow))
            new_uploaded_by = st.text_input("Update Uploaded By", value=str(selected_revision.get("uploaded_by") or action_actor))

            b1, b2, b3, b4 = st.columns(4)
            with b1:
                if st.button("Activate", use_container_width=True):
                    try:
                        st.session_state.kb_action_result = _post_json(
                            f"/knowledge-base/documents/{selected_document_id}/activate",
                            payload={"updated_by": action_actor},
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Activation failed: {exc}")
            with b2:
                if st.button("Deactivate", use_container_width=True):
                    try:
                        st.session_state.kb_action_result = _post_json(
                            f"/knowledge-base/documents/{selected_document_id}/deactivate",
                            payload={"updated_by": action_actor},
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Deactivation failed: {exc}")
            with b3:
                if st.button("Save Metadata", use_container_width=True):
                    try:
                        st.session_state.kb_action_result = _patch_json(
                            f"/knowledge-base/documents/{selected_document_id}",
                            payload={"workflow": new_workflow, "uploaded_by": new_uploaded_by, "updated_by": action_actor},
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Metadata update failed: {exc}")
            with b4:
                try:
                    download_response = api_get(f"/knowledge-base/documents/{selected_document_id}/download", timeout=60)
                    if download_response.status_code == 200:
                        st.download_button(
                            "Download",
                            data=download_response.content,
                            file_name=str(selected_revision.get("original_filename") or "knowledge_document"),
                            mime=str(selected_revision.get("mime_type") or "application/octet-stream"),
                            use_container_width=True,
                        )
                    else:
                        st.button("Download Missing", disabled=True, use_container_width=True)
                except Exception:
                    st.button("Download Error", disabled=True, use_container_width=True)

        with st.expander("Selected revision details", expanded=False):
            st.json(selected_revision)

with tabs[4]:
    section_heading("Search & chunks", "Search matching chunks and inspect the evidence text that retrieval can use.")
    search_payload = _safe_dict(
        _get_json(
            "/knowledge-base/search",
            params={
                "query": search_query.strip() or None,
                "workflow": workflow_param,
                "active_only": active_param if active_param is not None else True,
                "limit": int(chunk_limit),
            },
            timeout=60,
        )
    )
    search_summary = _safe_dict(search_payload.get("summary"))
    s1, s2, s3 = st.columns(3)
    with s1:
        kpi_card("Matched Documents", search_summary.get("document_count", 0), detail="Logical document sources")
    with s2:
        kpi_card("Matched Revisions", search_summary.get("revision_count", 0), detail="Document registry rows")
    with s3:
        kpi_card("Matched Chunks", search_summary.get("chunk_count", 0), detail="Chunk preview rows", tone="accent")

    matching_chunks = _records(search_payload.get("chunks")) or chunks
    render_table(matching_chunks, empty_title="No matching chunks", empty_text="Try changing the search query, workflow, or revision state filters.")

    if matching_chunks:
        section_heading("Chunk preview cards", "Readable evidence previews for demos and validation.")
        for item in matching_chunks[:8]:
            source = shorten(item.get("source_document"), 52)
            workflow_label = format_workflow(item.get("workflow"))
            revision = item.get("revision_number") or "—"
            active = "active" if item.get("is_active") else "inactive"
            with st.container(border=True):
                st.markdown(f"**{source}**")
                st.markdown(
                    chip("Workflow", workflow_label, tone="info")
                    + chip("Revision", revision, tone="neutral")
                    + chip("State", active, tone="success" if active == "active" else "warning")
                    + chip("Chunk", item.get("chunk_index"), tone="neutral")
                )
                st.write(item.get("chunk_preview") or "")
                st.caption(f"Chunk ID: {item.get('chunk_id')}")
