"""
app/plugins/order_plugin.py — Semantic Kernel plugin for order management.

Functions:
  - get_order_status(order_id)
  - track_delivery(order_id)
  - initiate_return(order_id, reason)
"""

from __future__ import annotations

import json
from typing import Annotated

from semantic_kernel.functions import kernel_function

from app.database.connection import execute, fetchone

_STATUS_LABELS = {
    "processing": "Being prepared",
    "out_for_delivery": "Out for delivery",
    "ready_for_collection": "Ready to collect",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
    "return_requested": "Return requested",
    "refunded": "Refunded",
}


class OrderPlugin:
    """Handles order status, delivery tracking, and return requests."""

    @kernel_function(
        name="get_order_status",
        description=(
            "Look up the status of a customer's order by order ID. "
            "Use for questions like 'where is my order', 'has my delivery arrived', "
            "'what's happening with ORD-2024-88322'. Order IDs follow the format ORD-YYYY-NNNNN."
        ),
    )
    async def get_order_status(
        self,
        order_id: Annotated[str, "The order ID, e.g. ORD-2024-88322"],
    ) -> str:
        row = await fetchone(
            """SELECT o.id, o.customer_name, o.status, o.total_amount,
                      o.item_count, o.delivery_type, o.estimated_delivery,
                      o.tracking_number, o.placed_at, s.name AS store_name
               FROM orders o
               LEFT JOIN stores s ON o.store_id = s.id
               WHERE o.id = ?""",
            (order_id.upper().strip(),),
        )
        if not row:
            return json.dumps({
                "found": False,
                "message": f"No order found with ID {order_id}. Please double-check the order number.",
            })

        status_label = _STATUS_LABELS.get(row["status"], row["status"].replace("_", " ").title())
        result = {
            "found": True,
            "order_id": row["id"],
            "customer": row["customer_name"],
            "status": row["status"],
            "status_label": status_label,
            "total": f"£{row['total_amount']:.2f}",
            "items": row["item_count"],
            "delivery_type": row["delivery_type"].replace("_", " ").title(),
            "placed_at": row["placed_at"],
        }
        if row["estimated_delivery"]:
            result["estimated_delivery"] = row["estimated_delivery"]
        if row["store_name"]:
            result["store"] = row["store_name"]

        return json.dumps(result)

    @kernel_function(
        name="track_delivery",
        description=(
            "Get real-time delivery tracking for an order that is out for delivery or dispatched. "
            "Returns tracking number and estimated time window."
        ),
    )
    async def track_delivery(
        self,
        order_id: Annotated[str, "The order ID to track"],
    ) -> str:
        row = await fetchone(
            "SELECT id, status, tracking_number, estimated_delivery FROM orders WHERE id = ?",
            (order_id.upper().strip(),),
        )
        if not row:
            return json.dumps({"found": False, "message": "Order not found."})

        if row["status"] == "cancelled":
            return json.dumps({"found": True, "trackable": False, "message": "This order was cancelled and cannot be tracked."})

        if row["status"] == "processing":
            return json.dumps({
                "found": True,
                "trackable": False,
                "message": "Your order is still being prepared. Tracking will be available once it's dispatched.",
                "estimated_delivery": row["estimated_delivery"],
            })

        if row["status"] in ("delivered", "ready_for_collection"):
            label = _STATUS_LABELS.get(row["status"], row["status"])
            return json.dumps({"found": True, "trackable": False, "status": label, "message": row["estimated_delivery"]})

        return json.dumps({
            "found": True,
            "trackable": True,
            "order_id": row["id"],
            "tracking_number": row["tracking_number"],
            "status": _STATUS_LABELS.get(row["status"], row["status"]),
            "estimated_delivery": row["estimated_delivery"],
            "track_url": f"https://sainsburys.co.uk/track/{row['tracking_number']}",
        })

    @kernel_function(
        name="initiate_return",
        description=(
            "Log a return request for a delivered order. "
            "Use when the customer says they want to return something they've received. "
            "Only works for orders with status 'delivered'."
        ),
    )
    async def initiate_return(
        self,
        order_id: Annotated[str, "The order ID to return"],
        reason: Annotated[str, "Reason for the return, e.g. 'item damaged', 'wrong product', 'changed mind'"],
    ) -> str:
        row = await fetchone(
            "SELECT id, status, customer_name, total_amount FROM orders WHERE id = ?",
            (order_id.upper().strip(),),
        )
        if not row:
            return json.dumps({"success": False, "message": "Order not found."})

        if row["status"] not in ("delivered",):
            return json.dumps({
                "success": False,
                "message": f"Returns can only be requested for delivered orders. This order is currently: {_STATUS_LABELS.get(row['status'], row['status'])}.",
            })

        # Update order status to return_requested
        await execute(
            "UPDATE orders SET status = 'return_requested', updated_at = datetime('now') WHERE id = ?",
            (row["id"],),
        )

        return json.dumps({
            "success": True,
            "order_id": row["id"],
            "customer": row["customer_name"],
            "reason": reason,
            "message": (
                "Return request logged successfully. You'll receive a confirmation email within 2 hours "
                "with instructions for dropping off your items at any Sainsbury's store. "
                "Refunds are processed within 3-5 business days."
            ),
            "refund_amount": f"£{row['total_amount']:.2f}",
        })
