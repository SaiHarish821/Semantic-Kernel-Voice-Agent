"""
app/database/seed.py — Realistic Sainsbury's demo data.

Seeds products, stores, orders, offers, and FAQs if tables are empty.
Safe to call on every startup (idempotent via INSERT OR IGNORE).
"""

from __future__ import annotations

import aiosqlite

from app.logging_config import get_logger

logger = get_logger(__name__)


# ── Products ────────────────────────────────────────────────────────────────

PRODUCTS = [
    # Dairy
    ("P001", "Sainsbury's British Whole Milk 2L", "Dairy", "Milk", 1.35, "2L bottle", "Fresh whole milk from British farms.", 1, 250, 0, None, 5, "SKU-P001"),
    ("P002", "Sainsbury's Semi-Skimmed Milk 4 Pints", "Dairy", "Milk", 1.45, "4 pints", "Semi-skimmed milk, everyday essential.", 1, 300, 1, 1.25, 5, "SKU-P002"),
    ("P003", "Taste the Difference Butter 250g", "Dairy", "Butter", 2.50, "250g", "Rich, creamy British butter.", 1, 120, 0, None, 10, "SKU-P003"),
    ("P004", "Sainsbury's Greek Style Yogurt 500g", "Dairy", "Yogurt", 1.75, "500g", "Thick and creamy Greek-style yogurt.", 1, 80, 1, 1.50, 8, "SKU-P004"),
    ("P005", "Cathedral City Mature Cheddar 400g", "Dairy", "Cheese", 3.80, "400g", "Mature British cheddar, full-flavoured.", 1, 60, 0, None, 15, "SKU-P005"),
    ("P006", "Sainsbury's Free Range Eggs 12 Large", "Dairy", "Eggs", 2.75, "12 eggs", "Large free-range eggs from happy hens.", 1, 150, 0, None, 10, "SKU-P006"),

    # Bakery
    ("P007", "Sainsbury's Medium Sliced White Bread 800g", "Bakery", "Bread", 1.10, "800g loaf", "Classic white sliced bread.", 1, 200, 0, None, 3, "SKU-P007"),
    ("P008", "Warburtons Wholemeal Toastie 800g", "Bakery", "Bread", 1.60, "800g loaf", "Thick-sliced wholemeal bread.", 1, 130, 1, 1.40, 5, "SKU-P008"),
    ("P009", "Taste the Difference Sourdough Boule 400g", "Bakery", "Bread", 2.20, "400g", "Artisan sourdough with a crisp crust.", 1, 50, 0, None, 10, "SKU-P009"),
    ("P010", "Sainsbury's Croissants 4 Pack", "Bakery", "Pastries", 1.85, "4 pack", "All-butter croissants, freshly baked.", 1, 90, 0, None, 5, "SKU-P010"),

    # Produce
    ("P011", "Sainsbury's British Bananas per kg", "Produce", "Fruit", 0.89, "per kg", "Ripe, sweet Fairtrade bananas.", 1, 500, 0, None, 2, "SKU-P011"),
    ("P012", "Sainsbury's Braeburn Apples 6 Pack", "Produce", "Fruit", 1.50, "6 pack", "Crisp and tangy British apples.", 1, 180, 1, 1.25, 5, "SKU-P012"),
    ("P013", "Taste the Difference Strawberries 400g", "Produce", "Fruit", 3.00, "400g punnet", "British strawberries, perfectly ripe.", 1, 70, 0, None, 12, "SKU-P013"),
    ("P014", "Sainsbury's Baby Spinach 200g", "Produce", "Vegetables", 1.20, "200g bag", "Tender baby spinach leaves.", 1, 120, 0, None, 3, "SKU-P014"),
    ("P015", "Sainsbury's British Broccoli", "Produce", "Vegetables", 0.85, "each", "Tender-stem British broccoli crown.", 1, 200, 1, 0.70, 3, "SKU-P015"),
    ("P016", "Ainsbury's Mixed Salad Leaves 120g", "Produce", "Vegetables", 1.10, "120g bag", "Ready-to-eat mixed salad leaves.", 1, 100, 0, None, 3, "SKU-P016"),

    # Meat & Fish
    ("P017", "Sainsbury's British Chicken Breast Fillets 640g", "Meat & Fish", "Poultry", 4.50, "640g", "Boneless skinless chicken breast, 4 fillets.", 1, 80, 0, None, 15, "SKU-P017"),
    ("P018", "Taste the Difference 28-Day Aged Sirloin Steak 227g", "Meat & Fish", "Beef", 7.00, "227g", "Dry-aged British sirloin, exceptional flavour.", 1, 30, 0, None, 25, "SKU-P018"),
    ("P019", "Sainsbury's British Pork Sausages 8 Pack", "Meat & Fish", "Pork", 2.50, "8 pack", "Thick pork sausages, great for grilling.", 1, 90, 1, 2.00, 10, "SKU-P019"),
    ("P020", "Sainsbury's Scottish Salmon Fillets 240g", "Meat & Fish", "Fish", 4.25, "240g", "Scottish Atlantic salmon, skin-on fillets.", 1, 50, 0, None, 20, "SKU-P020"),

    # Frozen
    ("P021", "Sainsbury's Garden Peas 900g", "Frozen", "Vegetables", 1.25, "900g bag", "Sweet garden peas, frozen at their best.", 1, 200, 0, None, 5, "SKU-P021"),
    ("P022", "Taste the Difference Beef Lasagne 450g", "Frozen", "Ready Meals", 4.50, "450g", "Slow-cooked beef ragu with béchamel.", 1, 60, 1, 3.75, 15, "SKU-P022"),
    ("P023", "Sainsbury's Vanilla Ice Cream 1L", "Frozen", "Desserts", 2.25, "1L tub", "Classic vanilla ice cream.", 1, 100, 0, None, 8, "SKU-P023"),

    # Drinks
    ("P024", "Sainsbury's Pure Orange Juice 1.75L", "Drinks", "Juice", 2.10, "1.75L", "Freshly squeezed style orange juice.", 1, 150, 0, None, 8, "SKU-P024"),
    ("P025", "Coca-Cola Original Taste 8x330ml", "Drinks", "Fizzy Drinks", 4.50, "8 pack", "Classic Coca-Cola, chilled.", 1, 120, 1, 3.80, 15, "SKU-P025"),
    ("P026", "Sainsbury's Sparkling Water 12x500ml", "Drinks", "Water", 3.50, "12 pack", "Refreshing sparkling spring water.", 1, 200, 0, None, 5, "SKU-P026"),
    ("P027", "Yorkshire Tea 80 Bags", "Drinks", "Tea & Coffee", 3.00, "80 bags", "The proper brew — bold and malty.", 1, 180, 0, None, 10, "SKU-P027"),
    ("P028", "Sainsbury's Ground Coffee Colombian 227g", "Drinks", "Tea & Coffee", 3.75, "227g", "Rich Colombian arabica ground coffee.", 1, 90, 0, None, 12, "SKU-P028"),

    # Pantry
    ("P029", "Sainsbury's Fusilli Pasta 500g", "Pantry", "Pasta", 0.75, "500g", "Classic dried fusilli pasta.", 1, 300, 0, None, 2, "SKU-P029"),
    ("P030", "Heinz Baked Beans in Tomato Sauce 4x415g", "Pantry", "Tins & Cans", 2.95, "4 pack", "The classic baked beans, now multipack.", 1, 200, 1, 2.50, 10, "SKU-P030"),
    ("P031", "Sainsbury's Chopped Tomatoes 6x400g", "Pantry", "Tins & Cans", 3.00, "6 pack", "Ready-to-use chopped tomatoes.", 1, 250, 0, None, 8, "SKU-P031"),
    ("P032", "Kellogg's Corn Flakes 750g", "Pantry", "Cereals", 2.99, "750g", "Classic breakfast cereal.", 1, 130, 0, None, 10, "SKU-P032"),
    ("P033", "Sainsbury's British Honey 340g", "Pantry", "Condiments", 2.40, "340g jar", "Runny British wildflower honey.", 1, 80, 0, None, 8, "SKU-P033"),

    # Household
    ("P034", "Fairy Original Washing Up Liquid 900ml", "Household", "Cleaning", 2.75, "900ml", "Long-lasting washing-up liquid.", 1, 150, 1, 2.25, 8, "SKU-P034"),
    ("P035", "Andrex Classic White Toilet Tissue 9 Rolls", "Household", "Paper Products", 4.50, "9 rolls", "Soft and strong 3-ply toilet tissue.", 1, 200, 0, None, 12, "SKU-P035"),
    ("P036", "Ariel Liquitabs 30 Washes", "Household", "Laundry", 8.00, "30 pods", "Original stain-removing laundry pods.", 1, 100, 1, 7.00, 20, "SKU-P036"),

    # Health & Beauty
    ("P037", "Colgate Total Whitening Toothpaste 125ml", "Health & Beauty", "Oral Care", 2.50, "125ml", "Anti-bacterial whitening toothpaste.", 1, 120, 0, None, 8, "SKU-P037"),
    ("P038", "Dove Original Bar Soap 4x100g", "Health & Beauty", "Skin Care", 2.75, "4 pack", "Gentle moisturising bar soap.", 1, 100, 1, 2.25, 10, "SKU-P038"),

    # Baby & Toddler
    ("P039", "Pampers Baby-Dry Nappies Size 4 44 Pack", "Baby", "Nappies", 8.50, "44 pack", "Up to 12 hours of dryness.", 1, 60, 0, None, 20, "SKU-P039"),
    ("P040", "Ella's Kitchen Mango & Banana Smoothie 90g", "Baby", "Baby Food", 1.50, "90g pouch", "Organic fruit smoothie for babies.", 1, 80, 0, None, 5, "SKU-P040"),

    # Pet
    ("P041", "Whiskas Adult Cat Food in Jelly 12x100g", "Pet", "Cat Food", 4.25, "12 pack", "Complete cat food with chicken in jelly.", 1, 90, 1, 3.75, 15, "SKU-P041"),
    ("P042", "Pedigree Adult Dog Food Beef 4x400g", "Pet", "Dog Food", 5.50, "4 pack", "Complete adult dog food with beef.", 1, 70, 0, None, 18, "SKU-P042"),

    # Flowers
    ("P043", "Sainsbury's Seasonal Mixed Bouquet", "Flowers", "Fresh Flowers", 6.00, "bouquet", "A colourful mix of seasonal blooms.", 1, 40, 0, None, 0, "SKU-P043"),

    # Free From
    ("P044", "Sainsbury's Free From Gluten-Free Bread 400g", "Free From", "Bread", 2.50, "400g", "Soft gluten-free white sliced bread.", 1, 50, 0, None, 5, "SKU-P044"),
    ("P045", "Oat-ly Oat Drink Whole 1L", "Free From", "Plant-Based Milk", 1.80, "1L", "Barista-quality oat drink.", 1, 120, 1, 1.50, 8, "SKU-P045"),
]


# ── Stores ──────────────────────────────────────────────────────────────────

STORES = [
    ("ST001", "Sainsbury's Islington", "17-21 Liverpool Road", "London", "N1 0RW", "020 7226 4115", "islington@sainsburys.co.uk",
     "07:00-23:00", "07:00-23:00", "07:00-23:00", "07:00-23:00", "07:00-23:00", "07:00-22:00", "11:00-17:00",
     1, 1, 1, 150),
    ("ST002", "Sainsbury's Canary Wharf", "Canada Place, Canary Wharf", "London", "E14 5AH", "020 7513 2040", "canarywharf@sainsburys.co.uk",
     "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-21:00", "10:00-16:00",
     1, 0, 1, 0),
    ("ST003", "Sainsbury's Clapham", "32 Clapham High Street", "London", "SW4 7UR", "020 7622 5050", "clapham@sainsburys.co.uk",
     "06:00-23:00", "06:00-23:00", "06:00-23:00", "06:00-23:00", "06:00-23:00", "06:00-22:00", "10:00-17:00",
     0, 1, 1, 200),
    ("ST004", "Sainsbury's Manchester Piccadilly", "2-4 Piccadilly", "Manchester", "M1 1PJ", "0161 228 1234", "manchesterpic@sainsburys.co.uk",
     "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-21:00", "11:00-17:00",
     1, 1, 1, 100),
    ("ST005", "Sainsbury's Birmingham Grand Central", "New Street Station", "Birmingham", "B2 4BF", "0121 654 5678", "birminghamgc@sainsburys.co.uk",
     "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-22:00", "07:00-21:00", "10:00-16:00",
     1, 0, 1, 0),
]


# ── Orders ──────────────────────────────────────────────────────────────────

ORDERS = [
    ("ORD-2024-88321", "James Harrison", "james.h@example.com", "delivered", 47.85, 12, "ST001", "home_delivery", "Delivered 21 Jul 2026", "TRK-88321-GB"),
    ("ORD-2024-88322", "Sarah Williams", "sarah.w@example.com", "out_for_delivery", 32.60, 8, "ST001", "home_delivery", "Today between 14:00-16:00", "TRK-88322-GB"),
    ("ORD-2024-88323", "Mohammed Al-Rashid", "m.alrashid@example.com", "processing", 91.20, 23, "ST002", "home_delivery", "24 Jul 2026", "TRK-88323-GB"),
    ("ORD-2024-88324", "Emily Chen", "emily.chen@example.com", "ready_for_collection", 22.40, 6, "ST003", "click_collect", "Ready now at Clapham store", None),
    ("ORD-2024-88325", "Oliver Thompson", "o.thompson@example.com", "cancelled", 15.75, 4, "ST001", "home_delivery", None, None),
    ("ORD-2024-88326", "Priya Patel", "priya.p@example.com", "delivered", 63.10, 18, "ST004", "home_delivery", "Delivered 20 Jul 2026", "TRK-88326-GB"),
    ("ORD-2024-88327", "David O'Brien", "david.ob@example.com", "processing", 28.95, 7, "ST005", "home_delivery", "25 Jul 2026", "TRK-88327-GB"),
    ("ORD-2024-88328", "Fatima Malik", "fatima.m@example.com", "out_for_delivery", 55.30, 14, "ST001", "home_delivery", "Today between 16:00-18:00", "TRK-88328-GB"),
    ("ORD-2024-88329", "Thomas Baker", "t.baker@example.com", "delivered", 18.60, 5, "ST002", "click_collect", "Collected 19 Jul 2026", None),
    ("ORD-2024-88330", "Anna Kowalski", "anna.k@example.com", "processing", 74.45, 20, "ST003", "home_delivery", "26 Jul 2026", "TRK-88330-GB"),
]


# ── Offers ──────────────────────────────────────────────────────────────────

OFFERS = [
    ("OFF001", "Half Price Semi-Skimmed Milk", "Get 4 pints of semi-skimmed milk for just £1.25", "Dairy", "P002", "price_cut", 14.0, "2026-07-20", "2026-07-27", 0, 0),
    ("OFF002", "3 for 2 on Selected Yogurts", "Mix and match any 3 yogurts and pay for 2", "Dairy", None, "multibuy", 33.0, "2026-07-20", "2026-07-31", 0, 0),
    ("OFF003", "Taste the Difference Lasagne — Was £4.50 Now £3.75", "Save 75p on our premium frozen beef lasagne", "Frozen", "P022", "price_cut", 17.0, "2026-07-21", "2026-07-28", 0, 0),
    ("OFF004", "Nectar: Double Points on Pet Food", "Earn double Nectar points on all pet food this week", "Pet", None, "nectar_bonus", 0, "2026-07-22", "2026-07-28", 1, 100),
    ("OFF005", "25% Off Fairy Washing Up Liquid", "900ml bottle down to £2.25", "Household", "P034", "price_cut", 25.0, "2026-07-21", "2026-07-27", 0, 0),
    ("OFF006", "Braeburn Apples 6 Pack — Save 25p", "British apples now £1.25", "Produce", "P012", "price_cut", 17.0, "2026-07-20", "2026-07-27", 0, 0),
    ("OFF007", "Coca-Cola 8 Pack — Was £4.50 Now £3.80", "Save 70p on 8x330ml Coca-Cola", "Drinks", "P025", "price_cut", 16.0, "2026-07-22", "2026-07-29", 0, 0),
    ("OFF008", "Nectar: 500 Extra Points on £20 Spend", "Shop online and earn 500 bonus Nectar points on a £20+ basket", "Online", None, "nectar_bonus", 0, "2026-07-22", "2026-07-31", 1, 500),
    ("OFF009", "Warburtons Wholemeal — Save 20p", "Now just £1.40 for 800g", "Bakery", "P008", "price_cut", 13.0, "2026-07-20", "2026-07-27", 0, 0),
    ("OFF010", "Pork Sausages — Was £2.50 Now £2.00", "8-pack British pork sausages", "Meat & Fish", "P019", "price_cut", 20.0, "2026-07-21", "2026-07-28", 0, 0),
    ("OFF011", "Heinz Baked Beans 4-Pack — Save 45p", "Now £2.50 for 4x415g", "Pantry", "P030", "price_cut", 15.0, "2026-07-22", "2026-07-29", 0, 0),
    ("OFF012", "Buy 2 Get 1 Free: Ariel Liquitabs", "Save £8 when you buy 2 packs", "Household", "P036", "multibuy", 33.0, "2026-07-20", "2026-07-31", 0, 0),
    ("OFF013", "Oat-ly Oat Drink — Save 30p", "1L now £1.50", "Free From", "P045", "price_cut", 17.0, "2026-07-21", "2026-07-28", 0, 0),
    ("OFF014", "Nectar: Triple Points on Wine & Beer", "Earn 3x points on all alcohol this weekend", "Drinks", None, "nectar_bonus", 0, "2026-07-26", "2026-07-27", 1, 0),
    ("OFF015", "Greek Yogurt 500g — Was £1.75 Now £1.50", "Save 25p on our creamy Greek-style yogurt", "Dairy", "P004", "price_cut", 14.0, "2026-07-22", "2026-07-28", 0, 0),
]


# ── FAQs ────────────────────────────────────────────────────────────────────

FAQS = [
    # Returns & Refunds
    ("Can I return a product I bought in store?", "Yes, you can return most unopened products within 30 days with a valid receipt. Simply bring the item to the customer service desk at any Sainsbury's store. Perishable items like fresh food must be returned within 3 days.", "returns", "return,refund,receipt,in store"),
    ("How do I return an online order?", "For online orders, you can return items within 30 days. You can either drop off at your local Sainsbury's store, or schedule a collection via our website. Refunds are processed within 3-5 business days to your original payment method.", "returns", "return,online,refund,collection"),
    ("How long does a refund take?", "Refunds typically appear within 3-5 business days for card payments. PayPal refunds may take up to 3 days. If you paid by cash in store, you'll receive a cash refund immediately at the customer service desk.", "returns", "refund,how long,days,payment"),
    ("Can I get a refund without a receipt?", "Without a receipt, we can offer an exchange or store credit for the current selling price of the item. We may ask for ID. This applies to non-perishable goods only.", "returns", "refund,no receipt,exchange,credit"),

    # Delivery
    ("What are your delivery slots?", "We offer same-day delivery (order by 1pm), next-day, and scheduled slots up to 3 weeks ahead. Slots are available from 7am to 10pm, 7 days a week. Check availability by entering your postcode on our website.", "delivery", "delivery,slot,same day,next day,times"),
    ("How much does delivery cost?", "Delivery costs vary: standard delivery is £3.50-£7.50 depending on slot. Same-day delivery starts at £7.50. Orders over £40 qualify for reduced delivery fees. Sainsbury's Delivery Pass members enjoy free or reduced-price delivery.", "delivery", "delivery,cost,price,fee,charge"),
    ("What is Sainsbury's Delivery Pass?", "The Delivery Pass gives you unlimited free deliveries for a monthly or annual fee. Monthly costs £7.99, annual is £65. You also get mid-week slot discounts and priority booking up to 3 weeks ahead.", "delivery", "delivery pass,subscription,unlimited,annual,monthly"),
    ("Can I track my delivery?", "Yes! Once your order is on its way, you'll receive an email with a tracking link. You can also log into the Sainsbury's app or website and go to 'My Orders' to see real-time tracking updates.", "delivery", "track,tracking,where is my order,delivery"),

    # Click & Collect
    ("How does Click & Collect work?", "Order online and select a Click & Collect slot at your nearest store. Your groceries will be packed and ready for collection at the agreed time. Just drive up to the dedicated bay and our colleague will load your car.", "click_collect", "click collect,collection,pick up,store"),
    ("Is Click & Collect free?", "Click & Collect is free for orders over £40. For smaller baskets, a £2 fee applies. Bring your order confirmation and a form of ID when you collect.", "click_collect", "click collect,free,cost,price"),

    # Nectar
    ("What is Nectar?", "Nectar is Sainsbury's loyalty scheme. You earn points every time you shop in store or online — 1 point per £1 spent. Points can be redeemed against your shopping, or exchanged for vouchers with partner brands like eBay, Argos, and BP.", "nectar", "nectar,points,loyalty,reward"),
    ("How do I check my Nectar points balance?", "You can check your balance on the Nectar app, the Sainsbury's website, or by asking at the customer service desk in store. I can also look that up for you if you provide your Nectar card number.", "nectar", "nectar,points,balance,check"),
    ("How do I use my Nectar points?", "At checkout, simply tap your Nectar card or app, then tell the cashier you'd like to use points. Online, you'll see the option to redeem points at the payment stage. 500 points = £2.50 off your shop.", "nectar", "nectar,redeem,use,spend,cashier"),

    # Payment & Finance
    ("What payment methods do you accept?", "We accept Visa, Mastercard, American Express, contactless, Apple Pay, Google Pay, PayPal, and Sainsbury's gift cards. We also accept cash in all stores.", "payment", "payment,card,cash,contactless,apple pay,paypal"),
    ("Do you offer a student discount?", "Yes! Students get 10% off every Tuesday in store with a valid NUS Extra or TOTUM card. The discount applies to most grocery items, excluding tobacco, alcohol, fuel, and certain other products.", "discount", "student,discount,NUS,tuesday,percentage"),

    # Store Services
    ("Do your stores have a cafe?", "Many larger Sainsbury's stores have a café serving hot food, sandwiches, drinks, and snacks. Opening times vary by store. You can find cafés at our Islington, Manchester Piccadilly, and Birmingham Grand Central branches.", "store_services", "cafe,coffee,food,eat"),
    ("Do you have a pharmacy?", "Selected stores have an in-store pharmacy. Our Islington, Clapham, and Manchester Piccadilly stores all offer pharmacy services with a qualified pharmacist, prescription dispensing, and over-the-counter medicines.", "store_services", "pharmacy,medicine,prescription,health"),
    ("Can I get cash back in store?", "Yes, you can get cashback of up to £50 when you pay by debit card at a staffed checkout. No minimum purchase required.", "store_services", "cashback,cash back,money,debit card"),

    # Online & App
    ("How do I register for online shopping?", "Visit sainsburys.co.uk or download the Sainsbury's app, then click 'Register'. You'll need an email address and to create a password. You can link your Nectar card during registration.", "online", "register,account,online,website,app"),
    ("I've forgotten my password. What do I do?", "On the login page, click 'Forgot password' and enter your email address. We'll send you a reset link within a few minutes. If you don't receive it, check your spam folder.", "online", "password,forgot,reset,login,email"),
]


# ── Seed function ─────────────────────────────────────────────────────────────

async def seed_all(db: aiosqlite.Connection) -> None:
    """Insert sample data if tables are empty. Idempotent."""
    await _seed_products(db)
    await _seed_stores(db)
    await _seed_orders(db)
    await _seed_offers(db)
    await _seed_faqs(db)
    await _seed_admin_user(db)
    await db.commit()
    logger.info("database_seeded")


async def _seed_products(db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT COUNT(*) FROM products") as cur:
        count = (await cur.fetchone())[0]
    if count > 0:
        return
    await db.executemany(
        """INSERT OR IGNORE INTO products
           (id, name, category, subcategory, price, unit, description,
            in_stock, stock_quantity, on_offer, offer_price, nectar_points, sku)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        PRODUCTS,
    )
    logger.info("seeded_products", count=len(PRODUCTS))


async def _seed_stores(db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT COUNT(*) FROM stores") as cur:
        count = (await cur.fetchone())[0]
    if count > 0:
        return
    await db.executemany(
        """INSERT OR IGNORE INTO stores
           (id, name, address, city, postcode, phone, email,
            monday_hours, tuesday_hours, wednesday_hours, thursday_hours,
            friday_hours, saturday_hours, sunday_hours,
            has_cafe, has_pharmacy, has_click_collect, parking_spaces)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        STORES,
    )
    logger.info("seeded_stores", count=len(STORES))


async def _seed_orders(db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT COUNT(*) FROM orders") as cur:
        count = (await cur.fetchone())[0]
    if count > 0:
        return
    await db.executemany(
        """INSERT OR IGNORE INTO orders
           (id, customer_name, customer_email, status, total_amount,
            item_count, store_id, delivery_type, estimated_delivery, tracking_number)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ORDERS,
    )
    logger.info("seeded_orders", count=len(ORDERS))


async def _seed_offers(db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT COUNT(*) FROM offers") as cur:
        count = (await cur.fetchone())[0]
    if count > 0:
        return
    await db.executemany(
        """INSERT OR IGNORE INTO offers
           (id, title, description, category, product_id, offer_type,
            discount_pct, valid_from, valid_until, is_nectar_deal, nectar_points_bonus)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        OFFERS,
    )
    logger.info("seeded_offers", count=len(OFFERS))


async def _seed_faqs(db: aiosqlite.Connection) -> None:
    async with db.execute("SELECT COUNT(*) FROM faqs") as cur:
        count = (await cur.fetchone())[0]
    if count > 0:
        return
    await db.executemany(
        "INSERT INTO faqs (question, answer, category, keywords) VALUES (?,?,?,?)",
        FAQS,
    )
    logger.info("seeded_faqs", count=len(FAQS))


async def _seed_admin_user(db: aiosqlite.Connection) -> None:
    """Create a default admin user if no admin exists. Idempotent."""
    async with db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'") as cur:
        count = (await cur.fetchone())[0]
    if count > 0:
        return

    try:
        import bcrypt as _bcrypt
        pw_hash = _bcrypt.hashpw(b"Admin@123", _bcrypt.gensalt()).decode("utf-8")
    except ImportError:
        logger.warning("bcrypt_not_installed_skipping_admin_seed")
        return

    await db.execute(
        "INSERT OR IGNORE INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Admin", "admin@sainsburys.co.uk", pw_hash, "admin"),
    )
    logger.info("seeded_admin_user", email="admin@sainsburys.co.uk")
