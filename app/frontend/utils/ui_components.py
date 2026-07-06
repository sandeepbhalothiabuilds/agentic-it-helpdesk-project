from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from app.frontend.utils.ui_helpers import format_local_datetime, format_status


_TONE_ICONS = {
    "neutral": "•",
    "success": "✅",
    "warning": "⚠️",
    "danger": "🚨",
    "info": "ℹ️",
    "accent": "✨",
}


_TONE_LABELS = {
    "neutral": "Neutral",
    "success": "Healthy",
    "warning": "Attention",
    "danger": "Issue",
    "info": "Info",
    "accent": "Insight",
}

DEFAULT_CARD_HEIGHT = 142
DEFAULT_STEP_HEIGHT = 126
DEFAULT_TIMELINE_HEIGHT = 132


def _bordered_container(*, height: int | None = None):
    """Return a bordered Streamlit container with graceful fallback.

    Newer Streamlit versions support fixed-height containers. The fallback keeps
    the app compatible with older versions while still applying the equal-height
    layout when the runtime supports it.
    """
    try:
        if height is not None:
            return st.container(border=True, height=height)
        return st.container(border=True)
    except TypeError:
        return st.container(border=True)


def equal_container(*, height: int | None = DEFAULT_CARD_HEIGHT):
    """Public helper for custom same-height bordered sections."""
    return _bordered_container(height=height)


def safe_text(value: Any, default: str = "—") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def markdown_text(value: Any, default: str = "—") -> str:
    """Return text that is safe to put inside normal Streamlit Markdown."""
    return escape(safe_text(value, default))


def compact_status(value: Any) -> str:
    text = safe_text(value, "unknown").lower()
    if text in {"ok", "success", "completed", "complete", "healthy", "pass", "true"}:
        return "OK"
    if text in {"degraded", "warning", "warn", "pending", "waiting", "awaiting_confirmation"}:
        return "Needs Attention"
    if text in {"optional", "not_required", "not required"}:
        return "Optional"
    if text in {"failed", "failure", "error", "fail", "unhealthy", "false"}:
        return "Error"
    if text in {"enabled", "enable"}:
        return "Enabled"
    if text in {"disabled", "disable"}:
        return "Disabled"
    if text in {"unknown", "none", "null", ""}:
        return "Unknown"
    formatted = format_status(text)
    return formatted if len(formatted) <= 22 else formatted[:21] + "…"


def tone_for_status(value: Any) -> str:
    text = safe_text(value, "unknown").lower()
    if text in {"ok", "success", "completed", "complete", "healthy", "pass", "true", "enabled", "open"}:
        return "success"
    if text in {"degraded", "warning", "warn", "pending", "waiting", "awaiting_confirmation", "optional", "in_progress"}:
        return "warning"
    if text in {"failed", "failure", "error", "fail", "unhealthy", "false", "disabled", "cancelled", "closed_error"}:
        return "danger"
    return "neutral"


def apply_app_theme() -> None:
    """Apply shared CSS used by every Streamlit page."""
    st.markdown(
        """
        <style>
            :root {
                --app-ink: #182230;
                --app-muted: #475467;
                --app-subtle: #667085;
                --app-border: rgba(83, 99, 130, 0.20);
                --app-card: rgba(255,255,255,0.94);
                --app-card-soft: rgba(248,251,255,0.92);
                --app-blue: #2563eb;
                --app-purple: #7c3aed;
            }
            .stApp {
                color: var(--app-ink);
                background:
                    radial-gradient(circle at 12% 0%, rgba(37,99,235,0.08), transparent 28rem),
                    radial-gradient(circle at 82% 4%, rgba(124,58,237,0.08), transparent 30rem),
                    linear-gradient(180deg, #f8fbff 0%, #ffffff 18rem);
            }
            .block-container {
                padding-top: 5.85rem !important;
                padding-bottom: 2.4rem !important;
                max-width: 1480px;
            }
            header[data-testid="stHeader"] {
                background: rgba(255,255,255,0.0);
            }
            section[data-testid="stSidebar"] {
                width: 325px !important;
                background: linear-gradient(180deg, rgba(245,248,255,0.96), rgba(241,245,249,0.96));
            }
            h1, h2, h3, h4, h5, h6 {
                color: var(--app-ink) !important;
                letter-spacing: -0.018em;
            }
            p, li, label, span {
                color: var(--app-muted);
            }
            [data-testid="stCaptionContainer"] p {
                color: var(--app-subtle) !important;
            }
            .app-hero {
                border: 1px solid rgba(99,102,241,0.18);
                border-radius: 26px;
                padding: 1.55rem 1.7rem 1.45rem 1.7rem;
                margin: 0.15rem 0 1.15rem 0;
                background:
                    radial-gradient(circle at 6% 10%, rgba(14,165,233,0.18), transparent 20rem),
                    radial-gradient(circle at 88% 10%, rgba(168,85,247,0.17), transparent 22rem),
                    linear-gradient(135deg, rgba(255,255,255,0.96), rgba(244,248,255,0.95));
                box-shadow: 0 18px 50px rgba(15,23,42,0.07);
            }
            .app-hero-eyebrow {
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.26rem 0.72rem;
                border-radius: 999px;
                border: 1px solid rgba(37,99,235,0.20);
                background: rgba(37,99,235,0.08);
                color: #1d4ed8 !important;
                font-size: 0.78rem;
                font-weight: 700;
                margin-bottom: 0.58rem;
            }
            .app-hero-title {
                color: var(--app-ink) !important;
                font-size: clamp(2.0rem, 3.1vw, 3.25rem);
                line-height: 1.05;
                font-weight: 800;
                letter-spacing: -0.045em;
                margin: 0.12rem 0 0.58rem 0;
            }
            .app-hero-subtitle {
                max-width: 980px;
                color: var(--app-muted) !important;
                font-size: 1.02rem;
                line-height: 1.55;
                margin: 0;
            }
            .stTabs [data-baseweb="tab-list"] {
                gap: 0.35rem;
                flex-wrap: wrap;
            }
            .stTabs [data-baseweb="tab"] {
                border-radius: 999px;
                padding: 0.45rem 0.8rem;
                border: 1px solid var(--app-border);
                background: rgba(255,255,255,0.72);
            }
            div[data-testid="stDataFrame"] {
                border-radius: 14px;
                overflow: hidden;
                border: 1px solid var(--app-border);
                background: white;
            }
            div[data-testid="stExpander"] {
                border-radius: 14px !important;
                border: 1px solid var(--app-border) !important;
                background: rgba(255,255,255,0.72);
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-color: var(--app-border) !important;
                border-radius: 18px !important;
                background: var(--app-card) !important;
                box-shadow: 0 8px 26px rgba(15,23,42,0.035);
            }
            div[data-testid="stChatMessage"] {
                border: 1px solid var(--app-border);
                border-radius: 16px;
                padding: 0.15rem 0.25rem;
                background: rgba(255,255,255,0.62);
            }
            div[data-testid="stMetric"] {
                border: 1px solid var(--app-border);
                border-radius: 16px;
                padding: 0.82rem 0.95rem;
                background: var(--app-card);
            }
            button[kind="primary"], button[kind="secondary"] {
                border-radius: 999px !important;
            }
            .app-footer-note {
                font-size: 0.76rem;
                opacity: 0.68;
                line-height: 1.35;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

def page_header(title: str, subtitle: str, *, eyebrow: str | None = None, icon: str = "") -> None:
    """Render a colored hero header for every page.

    This is the only page-level HTML block. All text is escaped first and the
    markup is fully closed, which keeps the visual gradient without reintroducing
    the raw ``</div>`` leakage that happened in earlier card components.
    """
    eyebrow_html = ""
    if eyebrow:
        eyebrow_html = f'<div class="app-hero-eyebrow">{escape(safe_text(eyebrow))}</div>'
    heading = f"{safe_text(icon, '')} {safe_text(title)}".strip()
    st.markdown(
        f"""
        <div class="app-hero">
            {eyebrow_html}
            <div class="app-hero-title">{escape(heading)}</div>
            <p class="app-hero-subtitle">{escape(safe_text(subtitle))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def section_heading(title: str, caption: str | None = None) -> None:
    st.markdown(f"### {markdown_text(title)}")
    if caption:
        st.caption(safe_text(caption))


def _tone_prefix(tone: str) -> str:
    return _TONE_ICONS.get(tone, _TONE_ICONS["neutral"])


def kpi_card(label: str, value: Any, *, detail: str = "", tone: str = "neutral", height: int | None = DEFAULT_CARD_HEIGHT) -> None:
    display = safe_text(value, "0")
    heading = "##" if len(display) <= 9 else "###"
    with _bordered_container(height=height):
        st.caption(f"{_tone_prefix(tone)} {safe_text(label)}")
        st.markdown(f"{heading} {markdown_text(display, '0')}")
        if detail:
            st.caption(safe_text(detail))


def status_card(label: str, value: Any, *, detail: str = "", tone: str | None = None, height: int | None = DEFAULT_CARD_HEIGHT) -> None:
    """Render compact status cards for side panels and health summaries."""
    display = compact_status(value)
    actual_tone = tone or tone_for_status(value)
    with _bordered_container(height=height):
        st.caption(f"{_tone_prefix(actual_tone)} {safe_text(label)}")
        st.markdown(f"**{markdown_text(display)}**")
        if detail:
            st.caption(safe_text(detail))


def value_card(label: str, value: Any, *, detail: str = "", tone: str = "neutral", mono: bool = False, height: int | None = DEFAULT_CARD_HEIGHT) -> None:
    """Render compact value cards for metadata and side panels."""
    with _bordered_container(height=height):
        st.caption(f"{_tone_prefix(tone)} {safe_text(label)}")
        if mono:
            st.markdown(f"`{markdown_text(value)}`")
        else:
            st.markdown(f"**{markdown_text(value)}**")
        if detail:
            st.caption(safe_text(detail))


def chip(label: str, value: Any, *, tone: str = "neutral") -> str:
    """Return Markdown-only chip text.

    Several pages concatenate chips and pass them to ``st.markdown``. Returning
    Markdown instead of HTML removes the possibility of visible raw tag
    fragments while keeping the content compact.
    """
    icon = _TONE_ICONS.get(tone, _TONE_ICONS["neutral"])
    return f"{icon} **{markdown_text(label)}:** {markdown_text(value)}  \n"


def card(title: str, body: str = "", *, footer: str = "", tone: str = "neutral", mono: bool = False, height: int | None = None) -> None:
    with _bordered_container(height=height):
        st.markdown(f"#### {_tone_prefix(tone)} {markdown_text(title)}")
        if mono:
            st.code(safe_text(body), language=None)
        elif body:
            st.write(safe_text(body))
        if footer:
            st.caption(safe_text(footer))


def step_card(index: int, title: str, detail: str, *, height: int | None = DEFAULT_STEP_HEIGHT) -> None:
    """Render a same-height workflow step card."""
    with _bordered_container(height=height):
        st.caption(f"Step {index}")
        st.markdown(f"**{markdown_text(title)}**")
        st.caption(safe_text(detail))


def empty_state(title: str, text: str, *, height: int | None = None) -> None:
    with _bordered_container(height=height):
        st.markdown(f"#### {markdown_text(title)}")
        st.caption(safe_text(text))


def soft_divider() -> None:
    st.divider()


def format_records_for_table(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    for column in frame.columns:
        lower = str(column).lower()
        if lower.endswith("_at") or lower.endswith("_time") or lower in {"created_at", "updated_at", "last_updated", "last_indexed", "timestamp"}:
            frame[column] = frame[column].apply(format_local_datetime)
    return frame


def render_table(
    rows: list[dict[str, Any]],
    *,
    empty_title: str,
    empty_text: str,
    column_config: dict[str, Any] | None = None,
) -> None:
    if not rows:
        empty_state(empty_title, empty_text)
        return

    with st.container(border=True):
        st.dataframe(
            format_records_for_table(rows),
            use_container_width=True,
            hide_index=True,
            column_config=column_config,
        )


def timeline_item(index: int, title: str, subtitle: str = "", *, chips: str = "", details: str = "", height: int | None = DEFAULT_TIMELINE_HEIGHT) -> None:
    """Render a same-height timeline card with native widgets only."""
    with _bordered_container(height=height):
        top_cols = st.columns([0.12, 0.88])
        with top_cols[0]:
            st.markdown(f"### {markdown_text(index)}")
        with top_cols[1]:
            st.markdown(f"**{markdown_text(title)}**")
            if subtitle:
                st.caption(safe_text(subtitle))
            if chips:
                st.markdown(chips)
            if details:
                st.caption(safe_text(details))
