"""
app/plugins/store_plugin.py — Semantic Kernel plugin for store information.

Functions:
  - get_store_info(store_id)
  - get_opening_hours(store_id, day)
  - find_nearest_store(city_or_postcode)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from app.config import get_settings
from app.database.connection import fetchall, fetchone

_settings = get_settings()

_DAY_COLUMNS = {
    "monday": "monday_hours",
    "tuesday": "tuesday_hours",
    "wednesday": "wednesday_hours",
    "thursday": "thursday_hours",
    "friday": "friday_hours",
    "saturday": "saturday_hours",
    "sunday": "sunday_hours",
}

_ALL_DAYS = list(_DAY_COLUMNS.keys())


class StorePlugin:
    """Provides store information, opening hours, and location search."""

    @kernel_function(
        name="get_store_info",
        description=(
            "Get full information about a specific Sainsbury's store including address, "
            "phone number, services (café, pharmacy, click & collect), and parking. "
            "Use for questions about a particular branch."
        ),
    )
    async def get_store_info(
        self,
        store_id: Annotated[
            str,
            "Store ID (e.g. ST001). If unknown, use find_nearest_store first.",
        ] = "",
    ) -> str:
        sid = store_id or _settings.default_store_id
        row = await fetchone(
            """SELECT id, name, address, city, postcode, phone, email,
                      has_cafe, has_pharmacy, has_click_collect, parking_spaces,
                      monday_hours, saturday_hours, sunday_hours
               FROM stores WHERE id = ?""",
            (sid,),
        )
        if not row:
            return json.dumps({"found": False, "message": f"Store {sid} not found."})

        services = []
        if row["has_cafe"]:
            services.append("Café")
        if row["has_pharmacy"]:
            services.append("Pharmacy")
        if row["has_click_collect"]:
            services.append("Click & Collect")
        if row["parking_spaces"]:
            services.append(f"Free parking ({row['parking_spaces']} spaces)")

        return json.dumps({
            "found": True,
            "id": row["id"],
            "name": row["name"],
            "address": f"{row['address']}, {row['city']}, {row['postcode']}",
            "phone": row["phone"],
            "email": row["email"],
            "services": services,
            "typical_hours": {
                "weekdays": row["monday_hours"],
                "saturday": row["saturday_hours"],
                "sunday": row["sunday_hours"],
            },
        })

    @kernel_function(
        name="get_opening_hours",
        description=(
            "Get the opening hours for a Sainsbury's store on a specific day or all week. "
            "Use for questions like 'what time do you open on Sunday?', 'are you open late Friday?'"
        ),
    )
    async def get_opening_hours(
        self,
        store_id: Annotated[
            str,
            "Store ID (e.g. ST001). Defaults to the primary store if not provided.",
        ] = "",
        day: Annotated[
            str,
            "Day of the week (monday/tuesday/wednesday/thursday/friday/saturday/sunday) or 'today' or 'all'.",
        ] = "today",
    ) -> str:
        sid = store_id or _settings.default_store_id
        row = await fetchone(
            "SELECT name, monday_hours, tuesday_hours, wednesday_hours, thursday_hours, friday_hours, saturday_hours, sunday_hours FROM stores WHERE id = ?",
            (sid,),
        )
        if not row:
            return json.dumps({"found": False, "message": "Store not found."})

        day_input = (day or "today").lower().strip()

        if day_input == "today":
            day_input = datetime.now(timezone.utc).strftime("%A").lower()

        if day_input == "all":
            hours = {d: row[col] for d, col in _DAY_COLUMNS.items()}
            return json.dumps({
                "found": True,
                "store": row["name"],
                "hours": hours,
            })

        col = _DAY_COLUMNS.get(day_input)
        if not col:
            return json.dumps({
                "found": False,
                "message": f"Unknown day '{day}'. Please specify a day of the week or 'today'.",
            })

        return json.dumps({
            "found": True,
            "store": row["name"],
            "day": day_input.capitalize(),
            "hours": row[col],
        })

    @kernel_function(
        name="find_nearest_store",
        description=(
            "Find the nearest Sainsbury's store by city name or area. "
            "Use for questions like 'where is my nearest Sainsbury's', 'find a store in Manchester'."
        ),
    )
    async def find_nearest_store(
        self,
        city_or_area: Annotated[str, "City name or area to search near, e.g. 'London', 'Manchester', 'Birmingham'"],
    ) -> str:
        rows = await fetchall(
            """SELECT id, name, address, city, postcode, phone,
                      has_cafe, has_pharmacy, has_click_collect, monday_hours, sunday_hours
               FROM stores
               WHERE city LIKE ? OR postcode LIKE ? OR address LIKE ?
               ORDER BY name LIMIT 3""",
            (f"%{city_or_area}%", f"%{city_or_area}%", f"%{city_or_area}%"),
        )

        if not rows:
            # Return all stores if no location match
            rows = await fetchall(
                "SELECT id, name, address, city, postcode, phone, monday_hours, sunday_hours FROM stores LIMIT 3",
                (),
            )
            return json.dumps({
                "found": True,
                "note": f"No stores found in '{city_or_area}'. Showing available stores:",
                "stores": [_format_store_brief(r) for r in rows],
            })

        return json.dumps({
            "found": True,
            "stores": [_format_store_brief(r) for r in rows],
        })


def _format_store_brief(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "address": f"{row['address']}, {row['city']}, {row['postcode']}",
        "phone": row.get("phone"),
        "weekday_hours": row.get("monday_hours"),
        "sunday_hours": row.get("sunday_hours"),
    }
