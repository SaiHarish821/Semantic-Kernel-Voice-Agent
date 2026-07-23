"""
app/plugins/product_plugin.py — Semantic Kernel plugin for product queries.

Functions:
  - search_products(query, category, on_offer_only)
  - get_product_details(product_id)
  - check_stock(product_id)
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from app.database.connection import fetchall, fetchone


class ProductPlugin:
    """Provides product search, details, and stock information."""

    @kernel_function(
        name="search_products",
        description=(
            "Search the Sainsbury's product catalogue. Use this for queries like "
            "'do you have organic milk', 'show me bread offers', 'what chicken do you sell'. "
            "Returns up to 5 matching products with price, availability, and offer status."
        ),
    )
    async def search_products(
        self,
        query: Annotated[str, "Search term (product name, brand, or keyword)"],
        category: Annotated[
            str,
            "Optional category filter: Dairy, Bakery, Produce, Meat & Fish, Frozen, Drinks, Pantry, Household, Health & Beauty, Baby, Pet, Free From, Flowers",
        ] = "",
        on_offer_only: Annotated[
            bool, "Set true to return only products currently on offer/promotion"
        ] = False,
    ) -> str:
        conditions = ["(name LIKE ? OR description LIKE ? OR subcategory LIKE ?)"]
        params: list = [f"%{query}%", f"%{query}%", f"%{query}%"]

        if category:
            conditions.append("category = ?")
            params.append(category)

        if on_offer_only:
            conditions.append("on_offer = 1")

        where = " AND ".join(conditions)
        sql = f"""
            SELECT id, name, category, price, unit, on_offer, offer_price,
                   in_stock, stock_quantity, nectar_points
            FROM products
            WHERE {where}
            ORDER BY on_offer DESC, name
            LIMIT 5
        """

        rows = await fetchall(sql, tuple(params))
        if not rows:
            return json.dumps({"found": False, "message": f"No products found matching '{query}'."})

        results = []
        for r in rows:
            item = {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "price": f"£{r['price']:.2f}",
                "unit": r["unit"],
                "in_stock": bool(r["in_stock"]),
            }
            if r["on_offer"] and r["offer_price"]:
                item["offer_price"] = f"£{r['offer_price']:.2f}"
                item["on_offer"] = True
            if r["nectar_points"]:
                item["nectar_points"] = r["nectar_points"]
            results.append(item)

        return json.dumps({"found": True, "count": len(results), "products": results})

    @kernel_function(
        name="get_product_details",
        description=(
            "Get full details for a specific product by its ID. "
            "Use after search_products to get more information about a particular item."
        ),
    )
    async def get_product_details(
        self,
        product_id: Annotated[str, "The product ID (e.g. P001)"],
    ) -> str:
        row = await fetchone(
            """SELECT id, name, category, subcategory, price, unit, description,
                      in_stock, stock_quantity, on_offer, offer_price,
                      nectar_points, sku
               FROM products WHERE id = ?""",
            (product_id,),
        )
        if not row:
            return json.dumps({"found": False, "message": f"Product {product_id} not found."})

        result = {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "subcategory": row["subcategory"],
            "price": f"£{row['price']:.2f}",
            "unit": row["unit"],
            "description": row["description"],
            "in_stock": bool(row["in_stock"]),
            "stock_quantity": row["stock_quantity"],
            "nectar_points": row["nectar_points"],
        }
        if row["on_offer"] and row["offer_price"]:
            result["offer_price"] = f"£{row['offer_price']:.2f}"
            savings = row["price"] - row["offer_price"]
            result["savings"] = f"£{savings:.2f}"

        return json.dumps({"found": True, "product": result})

    @kernel_function(
        name="check_stock",
        description=(
            "Check whether a specific product is currently in stock. "
            "Use for questions like 'is the sourdough bread available?' or 'do you have any left?'"
        ),
    )
    async def check_stock(
        self,
        product_id: Annotated[str, "The product ID to check"],
    ) -> str:
        row = await fetchone(
            "SELECT name, in_stock, stock_quantity FROM products WHERE id = ?",
            (product_id,),
        )
        if not row:
            return json.dumps({"found": False, "message": "Product not found."})

        in_stock = bool(row["in_stock"])
        qty = row["stock_quantity"]
        status = "In stock" if in_stock else "Out of stock"
        level = "good" if qty > 50 else ("low" if qty > 5 else "very low")

        return json.dumps({
            "found": True,
            "name": row["name"],
            "in_stock": in_stock,
            "status": status,
            "stock_level": level if in_stock else "none",
        })
