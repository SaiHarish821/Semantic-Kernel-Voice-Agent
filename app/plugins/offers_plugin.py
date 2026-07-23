"""
app/plugins/offers_plugin.py — Semantic Kernel plugin for promotions and Nectar.

Functions:
  - get_current_offers(category)
  - get_nectar_deals()
  - get_category_deals(category)
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from app.database.connection import fetchall


class OffersPlugin:
    """Provides current promotions, price cuts, and Nectar point deals."""

    @kernel_function(
        name="get_current_offers",
        description=(
            "Get current promotions and special offers at Sainsbury's. "
            "Use for questions like 'what's on offer?', 'any deals today?', "
            "'what are the latest promotions?'. Returns up to 8 active offers."
        ),
    )
    async def get_current_offers(
        self,
        category: Annotated[
            str,
            "Optional category to filter by, e.g. Dairy, Bakery, Frozen, Household. Leave blank for all.",
        ] = "",
    ) -> str:
        if category:
            rows = await fetchall(
                """SELECT title, description, category, offer_type,
                          discount_pct, valid_until, is_nectar_deal, nectar_points_bonus
                   FROM offers
                   WHERE (category = ? OR category LIKE ?)
                     AND (valid_until >= date('now') OR valid_until IS NULL)
                   ORDER BY discount_pct DESC LIMIT 8""",
                (category, f"%{category}%"),
            )
        else:
            rows = await fetchall(
                """SELECT title, description, category, offer_type,
                          discount_pct, valid_until, is_nectar_deal, nectar_points_bonus
                   FROM offers
                   WHERE valid_until >= date('now') OR valid_until IS NULL
                   ORDER BY is_nectar_deal DESC, discount_pct DESC LIMIT 8""",
                (),
            )

        if not rows:
            return json.dumps({"found": False, "message": "No current offers found."})

        offers = []
        for r in rows:
            item = {
                "title": r["title"],
                "description": r["description"],
                "category": r["category"],
                "valid_until": r["valid_until"],
            }
            if r["discount_pct"]:
                item["discount"] = f"{r['discount_pct']:.0f}% off"
            if r["is_nectar_deal"]:
                item["nectar_deal"] = True
                if r["nectar_points_bonus"]:
                    item["bonus_points"] = r["nectar_points_bonus"]
            offers.append(item)

        return json.dumps({"found": True, "count": len(offers), "offers": offers})

    @kernel_function(
        name="get_nectar_deals",
        description=(
            "Get Nectar loyalty programme special deals and bonus points offers. "
            "Use for questions like 'any Nectar deals?', 'how do I earn more points?', "
            "'what are the Nectar promotions this week?'"
        ),
    )
    async def get_nectar_deals(self) -> str:
        rows = await fetchall(
            """SELECT title, description, category, nectar_points_bonus, valid_until
               FROM offers
               WHERE is_nectar_deal = 1
                 AND (valid_until >= date('now') OR valid_until IS NULL)
               ORDER BY nectar_points_bonus DESC""",
            (),
        )

        if not rows:
            return json.dumps({
                "found": False,
                "message": "No Nectar bonus deals are running right now. Check back soon!",
            })

        deals = [
            {
                "title": r["title"],
                "description": r["description"],
                "category": r["category"],
                "bonus_points": r["nectar_points_bonus"],
                "valid_until": r["valid_until"],
            }
            for r in rows
        ]

        return json.dumps({
            "found": True,
            "count": len(deals),
            "nectar_deals": deals,
            "redeem_info": "500 Nectar points = £2.50 off your shopping",
        })

    @kernel_function(
        name="get_category_deals",
        description=(
            "Get all deals in a specific product category. "
            "Use for focused questions like 'any deals on frozen food?', 'what dairy offers do you have?'"
        ),
    )
    async def get_category_deals(
        self,
        category: Annotated[
            str,
            "Product category to search, e.g. 'Dairy', 'Frozen', 'Drinks', 'Household', 'Meat & Fish'",
        ],
    ) -> str:
        rows = await fetchall(
            """SELECT o.title, o.description, o.offer_type, o.discount_pct,
                      o.valid_until, o.is_nectar_deal,
                      p.name AS product_name, p.price AS original_price, o.nectar_points_bonus
               FROM offers o
               LEFT JOIN products p ON o.product_id = p.id
               WHERE (o.category LIKE ? OR o.category = ?)
                 AND (o.valid_until >= date('now') OR o.valid_until IS NULL)
               ORDER BY o.discount_pct DESC""",
            (f"%{category}%", category),
        )

        if not rows:
            return json.dumps({
                "found": False,
                "category": category,
                "message": f"No current deals found in the {category} category.",
            })

        deals = []
        for r in rows:
            item = {
                "title": r["title"],
                "description": r["description"],
                "valid_until": r["valid_until"],
            }
            if r["discount_pct"]:
                item["discount"] = f"{r['discount_pct']:.0f}% off"
            if r["product_name"]:
                item["product"] = r["product_name"]
            if r["is_nectar_deal"]:
                item["nectar_deal"] = True
            deals.append(item)

        return json.dumps({
            "found": True,
            "category": category,
            "count": len(deals),
            "deals": deals,
        })
