"""
app/plugins/faq_plugin.py — Semantic Kernel plugin for FAQs and policy queries.

Functions:
  - answer_faq(question)
  - get_return_policy()
  - get_delivery_policy()
"""

from __future__ import annotations

import json
from typing import Annotated

from semantic_kernel.functions import kernel_function

from app.database.connection import fetchall, fetchone


class FaqPlugin:
    """Answers policy questions and FAQs from the Sainsbury's knowledge base."""

    @kernel_function(
        name="answer_faq",
        description=(
            "Search the FAQ database to answer common customer questions about "
            "policies, services, and store information. Use for questions about "
            "returns, refunds, Nectar points, delivery, payment, student discount, "
            "pharmacy, café, cashback, and online account issues."
        ),
    )
    async def answer_faq(
        self,
        question: Annotated[str, "The customer's question in natural language"],
    ) -> str:
        # Search by keywords and question text similarity
        words = [w.lower() for w in question.split() if len(w) > 3]
        if not words:
            return json.dumps({"found": False, "message": "Please provide a more specific question."})

        # Try keyword match first
        keyword_conditions = " OR ".join(["keywords LIKE ?" for _ in words])
        question_conditions = " OR ".join(["question LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words] + [f"%{w}%" for w in words]

        rows = await fetchall(
            f"""SELECT question, answer, category
                FROM faqs
                WHERE {keyword_conditions} OR {question_conditions}
                ORDER BY
                  CASE WHEN keywords LIKE ? THEN 0 ELSE 1 END,
                  question
                LIMIT 2""",
            tuple(params + [f"%{words[0]}%"]),
        )

        if not rows:
            return json.dumps({
                "found": False,
                "message": (
                    "I don't have a specific answer for that, but I can help you with "
                    "returns, delivery, Nectar points, opening hours, and more. "
                    "Or I can connect you to our customer service team."
                ),
            })

        results = [{"question": r["question"], "answer": r["answer"]} for r in rows]
        return json.dumps({"found": True, "answers": results})

    @kernel_function(
        name="get_return_policy",
        description=(
            "Get the full Sainsbury's returns and refund policy. "
            "Use when customers ask about how to return items, refund timelines, "
            "whether they need a receipt, or the returns window."
        ),
    )
    async def get_return_policy(self) -> str:
        rows = await fetchall(
            "SELECT question, answer FROM faqs WHERE category = 'returns' ORDER BY id",
            (),
        )
        policy = {
            "standard_return_window": "30 days",
            "perishables_window": "3 days",
            "receipt_required": False,
            "without_receipt": "Exchange or store credit at current selling price",
            "refund_timeline": "3-5 business days for card payments",
            "in_store_cash_refund": "Immediate at customer service desk",
            "online_return_options": ["Drop off at any Sainsbury's store", "Schedule a collection online"],
            "details": [{"q": r["question"], "a": r["answer"]} for r in rows],
        }
        return json.dumps({"found": True, "return_policy": policy})

    @kernel_function(
        name="get_delivery_policy",
        description=(
            "Get full details about Sainsbury's delivery options, costs, and Delivery Pass. "
            "Use for questions about delivery fees, slots, same-day delivery, and subscriptions."
        ),
    )
    async def get_delivery_policy(self) -> str:
        rows = await fetchall(
            "SELECT question, answer FROM faqs WHERE category IN ('delivery', 'click_collect') ORDER BY id",
            (),
        )
        policy = {
            "standard_delivery_cost": "£3.50 - £7.50",
            "same_day_delivery_cost": "From £7.50 (order by 1pm)",
            "free_delivery_threshold": "Orders over £40 qualify for reduced fees",
            "delivery_hours": "7am - 10pm, 7 days a week",
            "advance_booking": "Up to 3 weeks ahead",
            "delivery_pass": {
                "monthly_cost": "£7.99/month",
                "annual_cost": "£65/year",
                "benefits": ["Unlimited free deliveries", "Mid-week discounts", "Priority slot booking"],
            },
            "click_collect": {
                "cost": "Free for orders over £40 (£2 for smaller baskets)",
                "how_it_works": "Order online, choose a slot, drive to store",
            },
            "details": [{"q": r["question"], "a": r["answer"]} for r in rows],
        }
        return json.dumps({"found": True, "delivery_policy": policy})
