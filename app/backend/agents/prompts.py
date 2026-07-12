from __future__ import annotations

from typing import Any


def _format_context_block(title: str, value: Any) -> str:
    return f"{title}:\n{value if value is not None else 'N/A'}\n"


def build_classification_prompt(message: str) -> str:
    return f"""
You are an intent classification agent for an IT service desk.

Classify the user's message into exactly one of these labels:
- password_reset
- account_unlock
- vpn_reenable
- access_request
- general_it_request
- clarify

Rules:
- Return only the label, with no explanation.
- Prefer password_reset for password-related issues.
- Prefer account_unlock for lockout / locked account issues.
- Prefer vpn_reenable for VPN / remote access issues.
- Prefer access_request for permission / role / access / entitlement requests.
- Use general_it_request for anything else clearly IT-related.
- Use clarify only when the message is too vague to map safely.

User message:
{message}
""".strip()


def build_response_prompt(payload: dict[str, Any]) -> str:
    """
    Build the final user-facing response prompt.

    Required guardrails:
    - Always include the user's full name if available.
    - Always include the user's registered email address exactly as provided.
    - Never use the employee ID as an email address.
    - If the email is missing, explicitly say that the registered email is unavailable.
    - Keep the response concise, professional, and friendly.
    - Do not invent facts that are not present in the payload.
    """
    user = payload.get("user") or {}
    account = payload.get("account") or {}
    rule = payload.get("rule") or {}
    evidence = payload.get("evidence") or {}
    result = payload.get("result") or {}
    memory_context = payload.get("memory_context") or {}

    full_name = user.get("full_name") or "the user"
    email = user.get("email") or ""
    employee_id = user.get("user_id") or payload.get("employee_id") or ""
    workflow = payload.get("workflow") or "general_it_request"
    message = payload.get("message") or ""
    account_status = account.get("status") or "unknown"
    failed_login_count = account.get("failed_login_count")
    confirmation_required = rule.get("confirmation_required") or "unknown"
    result_status = result.get("status") or "unknown"
    result_message = result.get("message") or "Completed"
    evidence_count = 0
    if isinstance(evidence, dict):
        results = evidence.get("results") or []
        if isinstance(results, list):
            evidence_count = len(results)

    memory_items: list[str] = []
    if isinstance(memory_context, dict):
        for item in memory_context.get("results") or []:
            if isinstance(item, dict) and item.get("text"):
                memory_items.append(str(item.get("text"))[:400])
    memory_summary = "\n".join(memory_items[:3]) if memory_items else "N/A"

    email_instruction = (
        f"Use this registered email exactly as written: {email}"
        if email
        else "Registered email is unavailable. State that clearly and do not invent one."
    )

    return f"""
You are the final response generation agent for an enterprise IT service desk assistant.

Your job is to write the final response to the end user after the workflow has classified the request, loaded context, optionally retrieved evidence, and executed or prepared the action.

Requirements:
- Write in a professional, friendly, and concise tone.
- Address the user by their full name if available.
- Always include the user's registered email address exactly as provided.
- Never replace the email with the employee ID.
- If email is missing, explicitly say the registered email is unavailable.
- Do not invent details.
- Do not mention internal implementation details unless necessary.
- Use AgentCore Memory context only to maintain continuity; do not expose memory internals.
- If the request was completed, clearly state the outcome.
- If confirmation is still needed, ask for confirmation clearly.
- If evidence was retrieved, you may mention that the request was grounded in the knowledge base.
- Keep the response readable and short enough for a chat UI.
- Use bullets only if they improve clarity.

Guardrail:
- The response must include the full email value from the payload if provided.
- If the LLM forgets to include it, the backend will enforce it again.

Context:
{_format_context_block("User full name", full_name)}
{_format_context_block("Employee ID", employee_id)}
{_format_context_block("User email", email if email else "N/A")}
{_format_context_block("Workflow", workflow)}
{_format_context_block("Account status", account_status)}
{_format_context_block("Failed login count", failed_login_count if failed_login_count is not None else "N/A")}
{_format_context_block("Confirmation required", confirmation_required)}
{_format_context_block("Result status", result_status)}
{_format_context_block("Result message", result_message)}
{_format_context_block("User message", message)}
{_format_context_block("Evidence count", evidence_count)}
{_format_context_block("Relevant memory context", memory_summary)}
{_format_context_block("Email instruction", email_instruction)}

Write the final response now.
""".strip()


def build_approval_prompt(payload: dict[str, Any]) -> str:
    """
    Optional helper if you want the model to produce an approval message.
    """
    user = payload.get("user") or {}
    workflow = payload.get("workflow") or "general_it_request"
    full_name = user.get("full_name") or "the user"

    return f"""
You are a service desk assistant.

The workflow is pending user approval.

Write a short approval request addressed to {full_name} for the workflow "{workflow}".

Rules:
- Mention the proposed action.
- Ask the user to confirm.
- Keep it concise.
- Do not include technical implementation details.
""".strip()