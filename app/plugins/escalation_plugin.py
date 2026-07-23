"""
app/plugins/escalation_plugin.py — Semantic Kernel plugin for human handoff.

Functions:
  - escalate_to_human(reason, urgency)
  - log_complaint(session_id, issue, contact_preference)
  - send_callback_request(name, phone, preferred_time)
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from app.database.connection import execute


class EscalationPlugin:
    """Handles human agent handoff, complaints, and callback requests."""

    @kernel_function(
        name="escalate_to_human",
        description=(
            "Transfer the customer to a human agent or provide contact details. "
            "Use when the customer asks to speak to a person, says 'I want to talk to someone', "
            "'connect me to customer service', or when the query is too complex to resolve."
        ),
    )
    async def escalate_to_human(
        self,
        reason: Annotated[str, "Brief reason for escalation, e.g. 'complex complaint', 'account issue'"],
        urgency: Annotated[
            str,
            "Urgency level: 'low', 'normal', or 'high'. Use 'high' for safety, fraud, or urgent delivery issues.",
        ] = "normal",
    ) -> str:
        contact_info = {
            "phone": "0800 636 262",
            "phone_hours": "8am - 8pm, 7 days a week",
            "online_chat": "sainsburys.co.uk/help",
            "in_store": "Speak to any colleague or go to the Customer Service desk",
        }

        wait_time = {
            "high": "Priority queue — average wait under 2 minutes",
            "normal": "Average wait time: 5-10 minutes",
            "low": "Average wait time: 10-15 minutes",
        }.get(urgency, "Average wait time: 5-10 minutes")

        return json.dumps({
            "escalated": True,
            "reason": reason,
            "urgency": urgency,
            "message": (
                "I'm connecting you to our customer service team now. "
                "They'll be able to help you further."
            ),
            "contact": contact_info,
            "estimated_wait": wait_time,
        })

    @kernel_function(
        name="log_complaint",
        description=(
            "Log a formal customer complaint to the system and provide a reference number. "
            "Use when a customer wants to make a complaint about products, service, or an experience."
        ),
    )
    async def log_complaint(
        self,
        session_id: Annotated[str, "Current session ID for tracking"],
        issue: Annotated[str, "Description of the customer's complaint"],
        contact_preference: Annotated[
            str,
            "How the customer prefers to be contacted: 'email', 'phone', or 'none'",
        ] = "email",
    ) -> str:
        row_id = await execute(
            """INSERT INTO escalations (session_id, reason, user_message, status)
               VALUES (?, 'complaint', ?, 'pending')""",
            (session_id, issue),
        )

        reference = f"CMP-2026-{row_id:05d}"

        return json.dumps({
            "logged": True,
            "reference_number": reference,
            "issue_summary": issue[:100],
            "contact_preference": contact_preference,
            "message": (
                f"Your complaint has been logged with reference {reference}. "
                "Our customer relations team will review it within 2 working days "
                "and get back to you. We're sorry for any inconvenience caused."
            ),
            "further_help": "Call 0800 636 262 or visit sainsburys.co.uk/help",
        })

    @kernel_function(
        name="send_callback_request",
        description=(
            "Register a callback request so a Sainsbury's agent calls the customer back. "
            "Use when the customer doesn't want to wait on hold but still needs to speak with someone."
        ),
    )
    async def send_callback_request(
        self,
        session_id: Annotated[str, "Current session ID"],
        name: Annotated[str, "Customer's name"],
        phone: Annotated[str, "Customer's phone number"],
        preferred_time: Annotated[
            str,
            "Preferred callback time, e.g. 'this afternoon', 'tomorrow morning', 'anytime'",
        ] = "anytime",
    ) -> str:
        row_id = await execute(
            """INSERT INTO escalations (session_id, reason, user_message, status)
               VALUES (?, 'callback_request', ?, 'scheduled')""",
            (session_id, f"Name: {name}, Phone: {phone}, Preferred: {preferred_time}"),
        )

        ref = f"CB-2026-{row_id:05d}"

        return json.dumps({
            "scheduled": True,
            "reference": ref,
            "name": name,
            "phone": phone,
            "preferred_time": preferred_time,
            "message": (
                f"Perfect, {name}. I've arranged a callback for you — reference {ref}. "
                f"One of our team will call {phone} {preferred_time}. "
                "Is there anything else I can help you with in the meantime?"
            ),
        })
