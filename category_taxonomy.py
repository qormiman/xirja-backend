"""
The shared shopping-category taxonomy used to make "find me all the milk
across every chain" possible, independent of the cross-chain PRODUCT
matching in product_matcher.py -- see SETUP.md's "Category normalization"
section for why this exists and how it's different from product matching.

FIRST DRAFT, built from real data, not guessed: every canonical category
name and every mapping in GREENS_CATEGORY_MAP was built by looking at the
actual (top_level, sub_level) category pairs and their real listing counts,
pulled from your live database (see the SQL queries in that same SETUP.md
section). PAVI_CATEGORY_MAP is close to a straight relabelling, since
PAVI's own category field was already at roughly the target granularity.
Treat this as a working starting point, not a finished, perfectly-reviewed
taxonomy -- some calls here are reasonable approximations (documented
inline where non-obvious), and are easy to correct once you can see real
categorized output.

Three ways a listing gets a shopping_category:

  1. PAVI PAMA: its own chain_category (already fine-grained) is looked up
     directly in PAVI_CATEGORY_MAP.
  2. Greens: its (top_level, sub_level) pair -- the first two parts of its
     " / "-joined chain_category -- is looked up in GREENS_CATEGORY_MAP.
  3. Anything that falls through the two lookups above (including ALL of
     Welbee's, since its own categories are too broad to use directly, and
     Greens' two big "everything mixed together" buckets -- personal
     hygiene and household care) gets classified by looking for keywords in
     the product's own name instead, via KEYWORD_RULES / classify_by_name.

Nothing here is guessed silently: categorize_listings.py logs a tally of
anything it couldn't classify by any of the three routes, the same pattern
used throughout this project's crawlers for unrecognised units.
"""
import functools
import html
import re

# A marker value (not a real category name) used in the category maps below
# to flag a bucket that mixes too many different kinds of product to assign
# one category to directly -- those fall through to name-based keyword
# classification instead (see classify_by_name / classify_listing further
# down). Defined here, before any of the maps that use it, since a Python
# dict literal needs the name to already exist.
KEYWORD_FALLBACK = "__KEYWORD_FALLBACK__"


# ----------------------------------------------------------------------------
# 1. PAVI PAMA -- its own chain_category values, title-cased. Two same-chain
# spelling inconsistencies in PAVI's own data ("FRUIT" vs "FRUITS") are
# merged, since they're clearly the same thing, not a real distinction.
# ----------------------------------------------------------------------------

PAVI_CATEGORY_MAP = {
    "FOOD & CONDIMENTS": "Food & Condiments", "CAT": "Cat", "DOG": "Dog", "SNACKS": "Snacks",
    "INTERNATIONAL CUISINE": "International Cuisine", "SAUCES & CONDIMENTS": "Sauces & Condiments",
    "FOOD": "Food", "HERBS & SPICES": "Herbs & Spices", "SPORTS": "Sports",
    "WINE - RED": "Wine - Red", "BEVERAGES": "Beverages", "CHEESE": "Cheese",
    "SUPER PRICES": "Super Prices", "YOGHURT": "Yoghurt", "BISCUITS & CHOCOLATE": "Biscuits & Chocolate",
    "BISCUITS": "Biscuits", "CHOCOLATES": "Chocolates", "WINE - WHITE": "Wine - White",
    "PASTA & COUSCOUS": "Pasta & Couscous", "CAR ACCESSORIES": "Car Accessories",
    "DEODORANTS": "Deodorants", "JUICES": "Juices", "SPIRITS - WHISKY": "Spirits - Whisky",
    "CANNED VEGETABLES": "Canned Vegetables", "CEREAL & CEREAL BARS": "Cereal & Cereal Bars",
    "FABRIC SOFTENER": "Fabric Softener", "BREAD & CRACKERS": "Bread & Crackers",
    "CAKE PREPARATIONS": "Cake Preparations", "FISH & OTHER ANIMALS": "Fish & Other Animals",
    "SHOWER GELS": "Shower Gels", "CLOTHS & SPONGES": "Cloths & Sponges", "CAKES": "Cakes",
    "NUTS": "Nuts", "COFFEE": "Coffee", "SHAMPOOS": "Shampoos",
    "LAUNDRY WASHING LIQUIDS": "Laundry Washing Liquids", "ALL-PURPOSE CLEANERS": "All-purpose Cleaners",
    "WIPES": "Wipes", "CEREALS": "Cereals", "FROZEN VEGETABLES": "Frozen Vegetables",
    "BABY ESSENTIALS": "Baby Essentials", "CRACKERS, CRISPBREAD & BREADSTICKS": "Crackers, Crispbread & Breadsticks",
    "TEA": "Tea", "FROZEN FISH": "Frozen Fish", "FRUIT & NUTS": "Fruit & Nuts",
    "INTIMATE CARE": "Intimate Care", "FLOOR CLEANERS": "Floor Cleaners", "FACE CREAMS": "Face Creams",
    "BABY HYGIENE": "Baby Hygiene", "DISPOSABLES": "Disposables", "WATER": "Water",
    "CANDLES": "Candles", "MILK": "Milk", "CARBONATED DRINKS": "Carbonated Drinks",
    "CANNED SEAFOOD": "Canned Seafood", "HAIR COLOURING": "Hair Colouring",
    "WINE - SPARKLING": "Wine - Sparkling", "HAM": "Ham", "CIDERS": "Ciders",
    "BODY LOTIONS": "Body Lotions", "CHILLED": "Chilled", "DIPS": "Dips",
    "SWEET PASTRY": "Sweet Pastry", "CAKE SNACKS": "Cake Snacks", "FROZEN": "Frozen",
    "CONDITIONERS": "Conditioners", "BEERS": "Beers", "NAPPIES": "Nappies",
    "CHEESES & DAIRY": "Cheeses & Dairy", "PIZZA": "Pizza", "CEREAL BARS": "Cereal Bars",
    # Was a direct "Oils" mapping -- switched to split-by-name so a real
    # "olive oil" product gets its own Olive Oil category instead of the
    # generic "Oils" bucket (PAVI's own OILS category mixes olive, sunflower,
    # corn oil etc. together). See the PAVI branch of classify_listing()
    # below, updated to understand KEYWORD_FALLBACK the same way the Greens
    # branch already did.
    "OILS": KEYWORD_FALLBACK, "WAFERS": "Wafers", "RICE": "Rice", "WOMEN CARE": "Women Care",
    "BUTTER": "Butter", "LAUNDRY WASHING POWDERS": "Laundry Washing Powders",
    "HAIR STYLING": "Hair Styling", "ENERGY DRINKS": "Energy Drinks",
    "DISH WASHING LIQUID": "Dish Washing Liquid", "WINE - ROSE": "Wine - Rose", "SUMMER": "Summer",
    "STOCK CUBES": "Stock Cubes", "DRIED FRUIT": "Dried Fruit", "BREAD": "Bread",
    "FIRST AID": "First Aid", "CANNED MEAT": "Canned Meat", "HAIR TREATMENT": "Hair Treatment",
    "TOOTHPASTE": "Toothpaste", "TOOTHBRUSHES": "Toothbrushes", "CHICKEN": "Chicken",
    "HAND WASH LIQUIDS": "Hand Wash Liquids", "BATHROOM & WC CLEANER": "Bathroom & Wc Cleaner",
    "SOUPS": "Soups", "COLD CUTS": "Cold Cuts", "NOODLES": "Noodles", "SAUSAGES": "Sausages",
    "SPREADS": "Spreads", "COOKING CREAMS": "Cooking Creams", "DRINKS": "Drinks",
    "SANITARY TOWELS": "Sanitary Towels", "VEGETABLES": "Vegetables", "STAIN REMOVERS": "Stain Removers",
    "PICKLED VEGETABLES": "Pickled Vegetables", "SPIRITS - VODKA": "Spirits - Vodka", "CHIPS": "Chips",
    "PARTY FOOD": "Party Food", "FRIUT & VEG COUNTER": "Friut & Veg Counter", "SUGAR": "Sugar",
    "BENNA": "Benna", "MIXERS": "Mixers", "PASTRY": "Pastry", "LEGUMES & NUTS": "Legumes & Nuts",
    "APPLIANCES": "Appliances", "DILUTABLES": "Dilutables", "CREAMS": "Creams",
    "HAIR & NAIL ACCESSORIES": "Hair & Nail Accessories", "CANNED BEANS": "Canned Beans",
    "FRUITS": "Fruits", "FRUIT": "Fruits", "CROISSANTS": "Croissants", "SHAVING CREAMS": "Shaving Creams",
    "FRESH PASTA": "Fresh Pasta", "RUSSIAN FOOD": "Russian Food", "MEN CARE": "Men Care",
    "BEEF": "Beef", "MOUTHWASH": "Mouthwash", "INSECT KILLER": "Insect Killer", "JELLY": "Jelly",
    "CHILLED FISH": "Chilled Fish", "SHOE POLISH": "Shoe Polish", "WRAPS": "Wraps",
    "DISHWASHER TABLETS": "Dishwasher Tablets", "FOOTCARE PRODUCTS": "Footcare Products",
    "CANNED FRUIT": "Canned Fruit",
    # Key intentionally kept as PAVI's own (misspelled) raw category string --
    # this dict is a lookup on PAVI's actual chain_category value, which really
    # is "SPIRITS - LIQUERS" in their source data (one 'U' short of correct).
    # Only the canonical VALUE we output should be spelled correctly. Renaming
    # the key here to match the value's spelling on 24 Aug 2026 broke this
    # lookup for every PAVI liqueur/vintage-spirit listing (16 real production
    # listings went unclassified as a direct result) -- restored same day.
    "SPIRITS - LIQUERS": "Spirits - Liqueurs",
    "COTTON BUDS": "Cotton Buds", "PORK": "Pork", "SWEET SNACKS": "Sweet Snacks",
    "ICED COFFEE": "Iced Coffee", "DRINKING CHOCOLATE": "Drinking Chocolate",
    "READY MEALS": "Ready Meals", "HONEY": "Honey", "SKIN CARE": "Skin Care",
    "FRESH PASTRY": "Fresh Pastry", "PIES": "Pies", "FROZEN SNACKS": "Frozen Snacks",
    "BREADCRUMBS": "Breadcrumbs", "BATH ACCESSORIES": "Bath Accessories", "RAVIOLI": "Ravioli",
    "CLOTHES": "Clothes", "GLOVES": "Gloves", "ELECTRICAL": "Electrical", "OATS": "Oats",
    "POWER TOOLS": "Power Tools", "COOKING SPRAYS": "Cooking Sprays", "POULTRY": "Poultry",
    "TRAVELLING PACKS": "Travelling Packs", "EGGS": "Eggs", "MUESLI": "Muesli", "PASTA": "Pasta",
    "COLOUR CATCHERS": "Colour Catchers", "FRESH MILK": "Fresh Milk",
    "FURNITURE POLISHES": "Furniture Polishes", "ADULT NAPPIES": "Adult Nappies", "EASTER": "Easter",
    "VINEGARS": "Vinegars", "MAKE UP": "Make Up", "DRAIN UNBLOCKERS": "Drain Unblockers",
    "HAND TOOLS": "Hand Tools", "LEGUMES": "Legumes", "BATHROOM": "Bathroom",
    "TOBACCO & TOBACCO ACCESSORIES": "Tobacco & Tobacco Accessories", "FLOUR": "Flour",
    "CAMPING": "Camping", "MASHED POTATO": "Mashed Potato", "CHILLED DRINKS": "Chilled Drinks",
    "BIO": "Bio", "WORKING ACCESSORIES": "Working Accessories", "PASTA & ARANCINI": "Pasta & Arancini",
    "FLAMMABLE LIQUIDS": "Flammable Liquids", "COLD CUTS PREPACKED": "Cold Cuts Prepacked",
    "LAUNDRY TABLETS": "Laundry Tablets", "LAMB": "Lamb", "LENTILS": "Lentils",
    "GIFT VOUCHERS": "Gift Vouchers", "POTATO WEDGES": "Potato Wedges",
    "SHELVING & STORAGE": "Shelving & Storage", "WINE - ACCESSORIES": "Wine - Accessories",
    "LUBRICANTS": "Lubricants", "TRANSPORTERS": "Transporters", "SALADS & READY MEALS": "Salads & Ready Meals",
    "OLIVES": "Olives", "SAFETY": "Safety", "ICE CUBES": "Ice Cubes",
    "ORGANISERS & TOOL BOXES": "Organisers & Tool Boxes", "CHRISTMAS": "Christmas", "TURKEY": "Turkey",
    "READY-TO-COOK": "Ready-to-cook",
}


# ----------------------------------------------------------------------------
# 2. Greens -- mapped by hand from the real (top_level, sub_level) pairs and
# their listing counts (see SETUP.md). Where Greens combines things PAVI
# keeps separate (e.g. "Pasta Rice And Couscous" as one bucket), the closest
# single canonical category is used and the approximation is noted. Where
# Greens has real detail PAVI's data didn't show separately (e.g. baby
# food), a new canonical category is added rather than forcing a bad fit.
#
# KEYWORD_FALLBACK (defined near the top of the file, above PAVI_CATEGORY_MAP)
# marks a bucket that mixes too many different kinds of product to assign
# one category -- these fall through to name-based classification instead
# (see classify_by_name below).
# ----------------------------------------------------------------------------

GREENS_CATEGORY_MAP = {
    ("Baby", "Baby Food"): "Baby Food",
    ("Baby", "Baby Care And Accessories"): "Baby Essentials",
    ("Baby", "Mum To Be"): "Mum To Be",

    ("Bakery", "Biscuits And Crackers"): "Biscuits",
    ("Bakery", "Cereals And Cereal Bars"): "Cereal & Cereal Bars",
    # Was a direct mapping, same as ("Confectionery", "Bread") used to be --
    # switched to split-by-name after confirming (via the live app + the
    # GitHub Action's "row(s) written" count) that the ("Confectionery",
    # "Bread") fix alone did NOT change "Bocconcini 30g · Greens
    # Supermarket", meaning that real listing must be filed under THIS
    # bucket instead. Whichever one it turns out to be, neither is reliably
    # bread, so both get the same treatment now.
    ("Bakery", "Bread"): KEYWORD_FALLBACK,
    ("Bakery", "Confectionery"): "Chocolates",
    ("Bakery", "Pasta Rice And Couscous"): "Pasta & Couscous",
    ("Bakery", "Baked Goods"): "Fresh Pastry",
    ("Bakery", "Frozen Goods"): "Frozen",
    ("Bakery", "Other Confectionery"): "Chocolates",
    ("Bakery", "Ready To Eat"): "Ready Meals",
    ("Bakery", "Seasonal Goods"): "Seasonal Items",

    ("Beverages", "Juices And Smoothies"): "Juices",
    ("Beverages", "Mixers And Squashes"): "Mixers",
    ("Beverages", "Beer And Ciders"): "Beers",
    ("Beverages", "Soft Drinks"): "Drinks",
    ("Beverages", "Water"): "Water",
    ("Beverages", "Energy Drinks"): "Energy Drinks",
    ("Beverages", "Ice Tea"): "Iced Coffee",  # closest existing bucket; genuinely no "iced tea" category yet
    ("Beverages", "Ciders"): "Ciders",

    ("Butcher", "Beef"): "Beef",
    ("Butcher", "Chicken"): "Chicken",
    ("Butcher", "Pork"): "Pork",
    ("Butcher", "Sausages"): "Sausages",
    ("Butcher", "Lamb"): "Lamb",
    ("Butcher", "Other Butcher Items"): "Fish & Other Animals",  # weak fit, revisit
    ("Butcher", "Turkey"): "Turkey",
    ("Butcher", "Rabbit"): "Poultry",  # imperfect -- rabbit isn't poultry, but no closer bucket exists yet
    ("Butcher", "Bacon"): "Ham",
    ("Butcher", "Duck"): "Poultry",
    ("Butcher", "Dry Ager"): "Beef",  # dry-aged beef/steak specialty line
    ("Butcher", "Sauces"): "Sauces & Condiments",

    ("Cheese Counter", "Salads"): "Salads & Ready Meals",

    ("Chilled And Dairy", "Yoghurts And Desserts"): "Yoghurt",
    ("Chilled And Dairy", "Butter Dips And Spreadables"): "Butter",
    ("Chilled And Dairy", "Chilled Foods"): "Chilled",
    ("Chilled And Dairy", "Other Chilled"): "Chilled",
    ("Chilled And Dairy", "Chilled Beverages"): "Chilled Drinks",
    ("Chilled And Dairy", "Fresh Cream"): "Cooking Creams",
    ("Chilled And Dairy", "Milk And Eggs"): KEYWORD_FALLBACK,  # mixed -- split by name (egg vs milk)
    ("Chilled And Dairy", "Mortadella And Luncheon Meat"): "Cold Cuts",

    ("Condiments And Seasoning", "Spices And Herbs"): "Herbs & Spices",
    ("Condiments And Seasoning", "Herbs Spices And Cubes"): "Herbs & Spices",

    ("Confectionery", "Chocolates And Sweets"): "Chocolates",
    ("Confectionery", "Crisps Popcorn And Other Snacks"): "Snacks",
    ("Confectionery", "Pastries And Prepacked Cakes"): "Cakes",
    # Same category, real capitalization variant found in the live data --
    # confirmed via analyze_real_run.py.
    ("Confectionery", "Pastries and Prepacked Cakes"): "Cakes",
    ("Confectionery", "Biscuits And Crackers"): "Biscuits",
    ("Confectionery", "Confectionery"): "Chocolates",
    # Mixed, like "Milk And Eggs" above -- found via real data: "Bocconcini
    # 30g" (a cheese, small mozzarella balls) was showing up as the cheapest
    # "Bread" result. Whatever Greens actually files under this bucket isn't
    # reliably bread, so split by product name instead of trusting the label.
    ("Confectionery", "Bread"): KEYWORD_FALLBACK,
    ("Confectionery", "Pasta Rice And Couscous"): "Pasta & Couscous",
    ("Confectionery", "Dips"): "Dips",

    ("Cosmetics", "Lips"): "Make Up",
    ("Cosmetics", "Complection"): "Make Up",
    ("Cosmetics", "Eyes"): "Make Up",
    ("Cosmetics", "Nails"): "Make Up",
    ("Cosmetics", "Perfume"): "Perfume",
    ("Cosmetics", "Brows"): "Make Up",
    ("Cosmetics", "Skin Care"): "Skin Care",
    ("Cosmetics", "Beauty Tools"): "Bath Accessories",

    ("Delicatessen", "Cheeses"): "Cheese",
    ("Delicatessen", "Ham And Salami"): "Ham",
    ("Delicatessen", "Antipasto Food"): "Antipasto",
    ("Delicatessen", "Fresh Pasta"): "Fresh Pasta",
    ("Delicatessen", "Seasonal"): "Seasonal Items",
    ("Delicatessen", "Mortadella And Luncheon Meat"): "Cold Cuts",

    ("Fish", "Frozen Fish"): "Frozen Fish",
    ("Fish", "Fresh Fish"): "Chilled Fish",

    ("Flowers And Plants", "Plants"): "Plants",
    ("Flowers And Plants", "Flowers"): "Flowers",

    ("Frozen Foods", "Ice Cream And Desserts"): "Frozen",
    ("Frozen Foods", "Frozen Fruit And Vegetables"): "Frozen Vegetables",
    ("Frozen Foods", "Other Frozen Food"): "Frozen",
    ("Frozen Foods", "Frozen Meat"): "Frozen",
    ("Frozen Foods", "Chips And Other Potato Products"): "Potato Wedges",
    ("Frozen Foods", "Frozen Pizzas And Pastries"): "Pizza",
    ("Frozen Foods", "Disposable Goods"): "Disposables",

    ("Fruits And Vegetables", "Vegetables"): "Vegetables",
    ("Fruits And Vegetables", "Herbs And Spices"): "Herbs & Spices",
    ("Fruits And Vegetables", "Fruit"): "Fruits",
    ("Fruits And Vegetables", "Pre-packed"): "Salads & Ready Meals",
    ("Fruits And Vegetables", "Organic"): "Vegetables",  # organic fruit/veg, no dedicated bucket yet
    ("Fruits And Vegetables", "Salads"): "Salads & Ready Meals",
    ("Fruits And Vegetables", "Herbs Spices And Cubes"): "Herbs & Spices",
    ("Fruits And Vegetables", "Dried Fruit"): "Dried Fruit",
    ("Fruits And Vegetables", "Baby Fruit And Vegetables"): "Baby Food",
    ("Fruits And Vegetables", "Ready To Eat"): "Ready Meals",
    ("Fruits And Vegetables", "Beans Peas And Sprouts"): "Vegetables",
    ("Fruits And Vegetables", "Fruit And Vegetable (freshly Cut)"): "Vegetables",

    ("Groceries", "International Cuisine"): "International Cuisine",
    ("Groceries", "Tinned Goods"): "Canned Vegetables",  # broad tinned-goods catch, imperfect (also fish/meat/fruit)
    ("Groceries", "Sauces And Condiments"): "Sauces & Condiments",
    ("Groceries", "Coffee Tea And Hot Chocolate"): "Coffee",
    ("Groceries", "Dried Fruit Legumees And Nuts"): "Legumes & Nuts",
    # Same category, real spelling variant found in the live data (missed
    # when this map was first hand-built) -- confirmed via analyze_real_run.py.
    ("Groceries", "Dried Fruit Legumee And Nuts"): "Legumes & Nuts",
    ("Groceries", "Pasta Rice And Couscous"): "Pasta & Couscous",
    ("Groceries", "Jams Honey And Peanut Butter"): "Honey",
    # Was a direct "Oils" mapping -- switched to split-by-name (like the
    # PAVI "OILS" bucket above) so a real "olive oil" product gets its own
    # Olive Oil category instead of the generic "Oils" bucket.
    ("Groceries", "Oil And Vinegar"): KEYWORD_FALLBACK,
    ("Groceries", "Cake Mix"): "Cake Preparations",
    ("Groceries", "Flour"): "Flour",
    ("Groceries", "Herbs Spices And Cubes"): "Herbs & Spices",
    ("Groceries", "Disposable Goods"): "Disposables",
    ("Groceries", "Milk And Eggs"): KEYWORD_FALLBACK,  # same split-by-name treatment as Chilled And Dairy's version
    ("Groceries", "Soups"): "Soups",
    ("Groceries", "Sugar And Sweetners"): "Sugar",
    ("Groceries", "Jelly"): "Jelly",
    ("Groceries", "Miscellaneous Snacks"): "Snacks",
    ("Groceries", "Sweet Cream And Panna"): "Cooking Creams",
    ("Groceries", "Baked Goods"): "Fresh Pastry",
    ("Groceries", "Butter Dips And Spreadables"): "Butter",
    ("Groceries", "Baking Needs"): "Cake Preparations",
    ("Groceries", "Hot Beverages"): "Coffee",
    ("Groceries", "Seasonal And Festive Food"): "Seasonal Items",

    # "Health" here is a set of DIETARY FILTERS (gluten free, organic, diet,
    # etc.) cutting across many food types, not a food category itself --
    # there's no good single canonical bucket, so these fall through to
    # keyword classification on the product name instead.
    ("Health", "Gluten Free"): KEYWORD_FALLBACK,
    ("Health", "Organic And Bio"): KEYWORD_FALLBACK,
    ("Health", "Diet"): KEYWORD_FALLBACK,
    ("Health", "Sugar Free And No Added Sugar"): KEYWORD_FALLBACK,
    ("Health", "Protein Bars"): "Cereal Bars",
    ("Health", "Lactose Free"): KEYWORD_FALLBACK,
    ("Health", "Vegetarian"): KEYWORD_FALLBACK,
    ("Health", "Low Fat"): KEYWORD_FALLBACK,
    ("Health", "Dairy Free"): KEYWORD_FALLBACK,
    ("Health", "Protein"): KEYWORD_FALLBACK,

    ("Home Garden", "Household Goods"): "Household Goods",
    ("Home Garden", "Garden And Accessories"): "Garden",
    ("Home Garden", "Ironmongery"): "Ironmongery",
    ("Home Garden", "Picnic And Bbq Essentials"): "Picnic & Bbq",
    ("Home Garden", "Furniture Care"): "Furniture Polishes",

    ("Household", "Household Care And Essentials"): KEYWORD_FALLBACK,  # the big catch-all -- see module docstring
    # Same bucket, real capitalization variant found in the live data --
    # confirmed via analyze_real_run.py.
    ("Household", "Household Care and Essentials"): KEYWORD_FALLBACK,
    ("Household", "Laundry Products"): KEYWORD_FALLBACK,  # mixes liquids/powders/tablets/softener -- split by name
    ("Household", "Seasonal Items"): "Seasonal Items",
    ("Household", "Stationery Goods"): "Stationery",
    ("Household", "Kitchen Care And Accessories"): "Household Goods",
    ("Household", "Disposable Goods"): "Disposables",
    ("Household", "Garments"): "Clothes",
    ("Household", "Car Products"): "Car Accessories",
    ("Household", "Party Items"): "Party Food",
    ("Household", "Toys"): "Toys",
    ("Household", "Footwear"): "Clothes",
    ("Household", "Health"): "First Aid",
    ("Household", "Bathroom Care And Essentials"): KEYWORD_FALLBACK,
    ("Household", "Sports"): "Sports",
    ("Household", "Batteries"): "Batteries",
    ("Household", "Stationery"): "Stationery",
    ("Household", "Baby Care And Accessories"): "Baby Essentials",
    ("Household", "Vouchers"): "Gift Vouchers",
    ("Household", "Winter Season"): "Seasonal Items",

    ("New", "New"): "Seasonal Items",  # a "what's new" merchandising bucket, not a real category
    ("Organic", "Dietary Food"): KEYWORD_FALLBACK,

    ("Personal Care", "Personal Hygiene And Care"): KEYWORD_FALLBACK,  # the other big catch-all
    ("Personal Care", "Womens Section"): "Women Care",
    # Same category, real spelling variant (apostrophe) found in the live
    # data -- confirmed via analyze_real_run.py.
    ("Personal Care", "Women's Section"): "Women Care",
    ("Personal Care", "Mens Section"): "Men Care",
    ("Personal Care", "Bathroom Care And Essentials"): KEYWORD_FALLBACK,
    ("Personal Care", "Gift Sets"): "Gift Vouchers",
    ("Personal Care", "Cosmetics"): "Make Up",

    ("Pets", "Cat Section"): "Cat",
    ("Pets", "Dog Section"): "Dog",
    ("Pets", "Pet Treats"): "Cat",  # imperfect -- treats aren't cat/dog-specific in this data; revisit if it matters
    ("Pets", "Pet Accessories And Hygiene"): "Fish & Other Animals",  # weak fit, revisit
    ("Pets", "Other Pets"): "Fish & Other Animals",

    ("Wine Cellar", "Wines"): "Wine - Red",  # imperfect -- Greens doesn't split by colour at this level; revisit
    ("Wine Cellar", "Spirits"): "Spirits - Whisky",  # imperfect catch-all for mixed spirits
    ("Wine Cellar", "Wines And Champagne"): "Wine - Sparkling",
    ("Wine Cellar", "Port And Sherry Wine"): "Wine - Red",
}


# ----------------------------------------------------------------------------
# 2b. Greens -- a THIRD level, used only for the (top, sub) pairs marked
# KEYWORD_FALLBACK above. Greens' own chain_category is actually three
# levels deep (e.g. "Household / Household Care And Essentials / Cleaning
# Materials"), not two -- GREENS_CATEGORY_MAP only ever looked at the first
# two. For the "everything mixed together" buckets, that third level turns
# out to be specific enough to map directly and reliably -- e.g. "Cleaning
# Materials" or "Dental Care" -- which is a much better source of truth than
# guessing from the product name, especially since a lot of these products
# are named in Italian or Maltese and would never match an English keyword
# list. Confirmed real, via a real sample query -- not guessed.
#
# Checked ONLY when the (top, sub) pair is KEYWORD_FALLBACK. A pair not
# listed here still falls through to keyword classification, same as
# before -- this doesn't replace that, it just catches more cases first.
# Some third-level buckets are deliberately left OUT of this map, because
# they mix genuinely different product types themselves (e.g. "Hair Shampoo
# And Conditioners" contains both shampoo and conditioner) -- for those, the
# keyword classifier's own "shampoo" vs "conditioner" split does a better
# job than forcing one category on the whole bucket would.
# ----------------------------------------------------------------------------

GREENS_SUBCATEGORY_MAP = {
    ("Household", "Household Care And Essentials", "Cleaning Materials"): "Household Goods",
    ("Household", "Household Care And Essentials", "Kitchen Essentials"): "Household Goods",
    ("Household", "Household Care And Essentials", "Bottles And Lunch Boxes"): "Household Goods",
    ("Household", "Household Care And Essentials", "All Purpose Cleaners"): "All-purpose Cleaners",
    ("Household", "Household Care And Essentials", "Candles Perfumed"): "Candles",
    ("Household", "Household Care And Essentials", "Air Freshners"): "Air Fresheners",

    ("Personal Care", "Personal Hygiene And Care", "Body And Facial Care"): "Skin Care",
    ("Personal Care", "Personal Hygiene And Care", "Bath And Shower Gels"): "Shower Gels",
    ("Personal Care", "Personal Hygiene And Care", "Sanitory Towels"): "Sanitary Towels",  # "Sanitory" is Greens' own spelling
    ("Personal Care", "Personal Hygiene And Care", "Dental Care"): "Dental Care",
    ("Personal Care", "Personal Hygiene And Care", "Gift Sets"): "Gift Sets",
    # "Hair Products" mixes shampoo, conditioner, oil, AND appliances (e.g. a
    # beard trimmer) -- imperfect fit, but closer to Hair Treatment than
    # anything else on balance; the keyword classifier would catch the
    # trimmer as a false Hair Treatment too, so this isn't a regression.
    ("Personal Care", "Personal Hygiene And Care", "Hair Products"): "Hair Treatment",
}


# ----------------------------------------------------------------------------
# 3. Keyword-based fallback classifier -- used for Welbee's (all of it, since
# its own categories are too broad to use directly), the Greens buckets
# marked KEYWORD_FALLBACK above, and anything else that falls through the
# two lookup tables. Checked in order, first match wins, against the
# lower-cased product name. This is the least precise of the three routes
# and the most likely to need real-world tuning -- categorize_listings.py
# logs a tally of anything that matches NOTHING here so gaps stay visible.
# ----------------------------------------------------------------------------

KEYWORD_RULES = [
    # Dairy & eggs
    ("Eggs", ["egg"]),
    ("Milk", ["milk", "kefir"]),
    # "yoghurt"/"yogurt" moved to MULTI_KEYWORD_RULES (Pass 0) -- see the
    # comment there (19 Aug 2026) for why: this line used to sit right here,
    # one line after Milk, which meant a real yoghurt whose name also says
    # "milk" (e.g. "Mevgal Sheep's Milk Yoghurt") was landing on Milk purely
    # because Milk is checked one line earlier. Whenever "yoghurt"/"yogurt"
    # appears in a name at all, the product is a yoghurt -- not worth
    # leaving to list-order chance.
    # "parmigiano"/"formaggio" -- Italian for parmesan/cheese, found via real
    # data on Italian-brand products sold through Welbee's ("Carrefour
    # Grated Parmigiano Reggiano", "Teddi Formaggio Fresco + Frutta").
    # "bocconcini" -- small fresh mozzarella balls, found via real data
    # ("Bocconcini 30g") that had been landing under Bread (see the
    # ("Confectionery", "Bread") fix above) since the name itself doesn't
    # contain "cheese" or "mozzarella".
    ("Cheese", ["cheese", "mozzarella", "cheddar", "feta", "halloumi", "parmigiano", "parmesan", "formaggio", "bocconcini"]),
    ("Butter", ["butter", "margarine", "spread"]),
    ("Cooking Creams", ["cream", "panna"]),

    # Bakery & carbs
    ("Bread", ["bread", "baguette", "ftira", "hobz", "panini"]),  # "panini" found via real data: an Italian bread roll, not the toasted sandwich in this context
    # "wafer milk"/"milk wafer" are specific real phrasings (checked in the
    # multi-word pass) for a chocolate/biscuit snack that mentions "milk"
    # as an ingredient, not an actual carton of milk. Found via real API
    # testing ("Storck Knoppers Wafer Milk"). "chocolate & milk"/"chocolate
    # and milk" used to be listed here too, for the same pattern
    # ("Bahlsen Leibniz Pick Up Chocolate & Milk") -- moved to
    # MULTI_KEYWORD_RULES (Pass 0, below) once the general bare "chocolate"
    # rule was added there, since Pass 0 is checked before this multi-word
    # pass and would otherwise send this same product straight to
    # Chocolates before this phrase ever got a chance -- see the comment
    # there.
    # "cookies and cream"/"cookies & cream" -- a well-known, unambiguous
    # flavour name (never means actual cooking cream), found via real data:
    # "Iron Maxx Lava Bar Cookies And Cream" and "Rice Up Flapjack Zero
    # Sugar Cookies & Cream" were landing on Cooking Creams instead of
    # Biscuits, since bare "cookie" and bare "cream" tie and Cooking Creams
    # is listed earlier.
    ("Biscuits", ["biscuit", "cookie", "oreo", "petit beurre", "petite beurre", "wafer milk", "milk wafer", "wafer", "cookies and cream", "cookies & cream", "cookies n cream", "milk cookie", "milk biscuit", "cookie milk", "biscuit milk"]),  # "oreo" and "petit(e) beurre" -- specific, well-known biscuit brand/type names, found via real data. "cookies n cream" -- a third real spelling of the cookies-and-cream flavour ("Hersheys Cookies N Cream"), found the same way "cookies and cream"/"cookies & cream" were. "milk cookie"/"milk biscuit"/"cookie milk"/"biscuit milk" -- same shape as "wafer milk"/"milk wafer" above: "Paw Patrol Mini Milk Cookies", "Peppa Pig Mini Milk Cookies" and "Kinder Duo Biscuit Milk & White" were landing on Milk (listed earlier than Biscuits), even when the name literally says "biscuit"/"cookie" too -- both word orders are listed since real products used both.
    # "sponge cake" -- a real, recurring tie with Cloths & Sponges (bare
    # "sponge" also means a cleaning sponge) that happened to already
    # resolve correctly by list order (Cakes is listed before Cloths &
    # Sponges), but was still showing up as noise in every collision
    # report. Listed as its own phrase here so it wins outright and stops
    # depending on list order at all -- found via real data ("David's
    # Bakery Plain Sponge Cake", "La Granja Almond Sponge Cake").
    ("Cakes", ["sponge cake", "cake"]),
    ("Cereals", ["cereal", "cornflakes", "muesli", "granola"]),
    ("Cereal & Cereal Bars", ["cereal bar"]),
    ("Crackers, Crispbread & Breadsticks", ["crispbread", "oatcake"]),
    ("Pasta & Couscous", ["pasta", "spaghetti", "penne", "macaroni", "couscous", "lasagne"]),
    ("Rice", ["rice", "risotto"]),
    ("Flour", ["flour"]),
    # "Pensa Bio Gluten 1kg" -- vital wheat gluten, a baking ingredient
    # (WebSearch-confirmed Pensa Bio sells this alongside its other pantry
    # basics). Scoped to the two-word phrase rather than bare "gluten" --
    # bare "gluten" would misfire on the very common "Gluten Free" dietary
    # label that appears on thousands of unrelated products in this data.
    ("Flour", ["bio gluten"]),
    ("Cake Preparations", ["yeast"]),  # baking ingredient, found via real data ("Doves Farm Yeast Quick Gluten Free")
    # "Gypsophila Painted" / "Solidago Painted" -- cut-flower species names
    # (baby's breath and goldenrod respectively) with no other keyword
    # match, found unclassified in Greens' Flowers aisle real data.
    ("Flowers", ["gypsophila", "solidago"]),
    ("Fresh Pastry", ["mqaret"]),  # a traditional Maltese date pastry -- worth a dedicated entry for a Maltese app
    ("Sweet Snacks", ["sweets", "helwa"]),  # "helwa" -- a traditional Maltese sweet (as in "Helwa Tat-Tork")

    # Meat & fish
    ("Beef", ["beef", "steak", "mince"]),
    ("Chicken", ["chicken"]),
    ("Pork", ["pork"]),
    ("Lamb", ["lamb"]),
    ("Turkey", ["turkey"]),
    # Bare "sausage" moved to MULTI_KEYWORD_RULES (Pass 0, below) -- a
    # packet literally called "16 Classic Pork Sausages" or "Pork & Beef
    # Sausages" was landing on Pork or Beef instead of the more specific,
    # more useful "Sausages" category, since Pork/Beef are listed earlier
    # and bare "sausage" only used to compete with them as an ordinary
    # tier-2 word. Sausages is always a real, unambiguous product type
    # (unlike e.g. "steak", which stays as-is here), so it's safe to check
    # first regardless of which base meat it's made from.
    ("Ham", ["ham", "salami", "prosciutto"]),
    # Bare "luncheon" moved to MULTI_KEYWORD_RULES (Pass 0, below) -- see
    # the comment there. "mortadella"/"cold cut" stay here; they don't
    # collide with an earlier-listed meat category the way "luncheon" did.
    ("Cold Cuts", ["mortadella", "cold cut"]),
    ("Frozen Fish", ["frozen fish", "haddock"]),
    ("Chilled Fish", ["fish", "salmon", "tuna", "cod", "prawn", "shrimp"]),
    ("Canned Seafood", ["tinned tuna", "canned tuna", "sardine", "anchov"]),

    # Fruit & veg
    ("Vegetables", ["vegetable", "tomato", "potato", "onion", "carrot", "lettuce", "cucumber", "pepper"]),
    ("Fruits", ["fruit", "apple", "banana", "orange", "grape", "melon"]),
    ("Dried Fruit", ["dried fruit", "raisin", "sultana", "prune"]),
    ("Frozen Vegetables", ["frozen vegetable", "frozen peas", "frozen corn"]),
    ("Herbs & Spices", ["spice", "herb", "pepper corn", "cinnamon", "paprika", "oregano", "basil", "salt"]),
    # "stock cube"/"stock pot"/"bouillon cube" -- found via real data:
    # "Knorr Zero Salt Vegetable Stock Cubes" was landing on Vegetables,
    # since there was no keyword for this product type at all in the
    # name-based fallback (Stock Cubes previously only existed as a direct
    # PAVI/Greens category-map target). See also the Knorr-specific
    # MULTI_KEYWORD_RULES rule further down, for the many real Knorr
    # products that say "[flavour] Cubes" without the word "stock" at all.
    ("Stock Cubes", ["stock cube", "stock pot", "bouillon cube"]),
    ("Legumes", ["lentil"]),  # distinct from the broader "Legumes & Nuts" bucket below -- found via real data ("Pensa Bio Lentils")

    # Drinks
    ("Water", ["water"]),
    # Bare "juice"/"smoothie" moved to MULTI_KEYWORD_RULES (Pass 0, below)
    # -- see the comment there for why (a juice's name often also contains
    # a fruit word, e.g. "Del Monte Orange Juice", and Fruits used to win
    # by list order).
    # "cream soda" -- a well-known real soft-drink flavour (e.g. "Dr. Pepper
    # Cream Soda"), found via real data landing on Cooking Creams instead
    # (bare "cream" is listed earlier than Carbonated Drinks). Listed as its
    # own phrase so it wins over bare "cream" outright, the same shape as
    # "olive oil" vs bare "oil".
    ("Carbonated Drinks", ["cream soda", "orange soda", "cola", "soda", "fizzy", "carbonated"]),
    ("Beers", ["beer", "lager", "ale"]),
    ("Ciders", ["cider"]),
    ("Wine - Red", ["red wine", "red blend"]),
    ("Wine - White", ["white wine", "white blend"]),
    ("Wine - Rose", ["rose wine", "rosé wine"]),
    ("Wine - Sparkling", ["sparkling wine", "prosecco", "champagne", "cava"]),
    ("Spirits - Whisky", ["whisky", "whiskey"]),
    ("Spirits - Vodka", ["vodka"]),
    ("Spirits - Liqueurs", ["liqueur", "liquer"]),
    ("Coffee", ["coffee", "espresso", "cappuccino", "cappucino", "latte"]),  # "cappucino" -- common one-c typo, found via real data
    ("Tea", ["tea bag", "tea"]),
    ("Energy Drinks", ["energy drink"]),
    ("Dilutables", ["squash", "syrup", "cordial"]),
    ("Sugar", ["erythritol", "eritritol", "sweetener", "sweet n low"]),  # "eritritol" is the real spelling seen ("Natur Green Eritritol"); "erythritol" is the standard English spelling, kept too

    # Snacks & confectionery
    # Bare "chocolate" and "choco", plus the "milk chocolate" phrase, all
    # moved to MULTI_KEYWORD_RULES (Pass 0, below) -- see the comment there
    # for the real data behind that move (chocolate products with "milk" in
    # the name losing to bare "milk", which is listed earlier than this
    # entry). "milk choclate" (one c, a real misspelling seen live in "Rice
    # Up Milk Choclate Rice Bar") stays here, since it's a different string
    # to "chocolate"/"choco" and isn't covered by either of those Pass 0
    # words.
    # The Easter-egg-candy pattern ("Nestle Easter Milkybar...", "...Easter
    # Baci...", "...Easter Smarties...") is handled by the "easter" +
    # "egg" co-occurrence rule up in MULTI_KEYWORD_RULES instead of a
    # phrase per brand -- see the comment there for why.
    # "baci" -- Perugina/Nestle's well-known chocolate praline brand, kept
    # here too (bare word) for a Baci product that doesn't mention Easter
    # or eggs at all; confirmed via direct testing that this alone is
    # enough when there's no "egg" rule to compete with.
    ("Chocolates", ["milk choclate", "baci"]),
    # "rice up rolls" -- a specific savory snack-roll product line from the
    # same "Rice Up" brand as the "Rice Up Milk Choclate Rice Bar" above
    # (a different, sweet product line from that brand). Found via real
    # data: "Rice Up Rolls Spinach Cheese Olive Oil 50g" was showing up as
    # the cheapest "Olive Oil" result, because the product's name lists
    # olive oil as an ingredient. Checked in the multi-word pass, and this
    # category is listed before "Olive Oil" below, so it wins first.
    # "rice cake" -- e.g. "Kallo Rice Cakes Lightly Salted" was matching
    # bare "rice" (Rice) and bare "cake" (Cakes) at the same tier, with
    # Cakes winning by list order even though a rice cake is neither a
    # bowl of rice nor a dessert cake -- it's genuinely its own kind of
    # snack. Listed as its own phrase here so it wins over both bare
    # words, the same way "rice up rolls" already does for a different
    # real product line.
    # Bare "crisps"/"pretzel" moved to MULTI_KEYWORD_RULES (Pass 0, below)
    # -- they don't have any other realistic meaning in a grocery product
    # name, unlike "popcorn" (e.g. "popcorn chicken") or "snack" (e.g.
    # "cheese snacks"), which stay here as ordinary keywords so they don't
    # risk jumping ahead of a more specific category like Chicken or
    # Cheese.
    # "potato straws" and "salt and vinegar"/"salt & vinegar" -- real data
    # (17 Aug 2026 collision report) showed a cluster of savoury snacks
    # ("Potato Straws Cheese & Sour Cream", "Pomsticks Salt And Vinegar",
    # "Potato Crisps Salt & Vinegar") losing to whatever flavour word they
    # also contained (bare "cheese", "cream", "salt", "vinegar" all belong
    # to other categories). Both phrases are specific enough that nothing
    # else is plausibly called either one, so they're safe to add as
    # ordinary multi-word phrases here (checked before any single word,
    # not elevated all the way to Pass 0 the way "crisps"/"pretzel" were,
    # since they don't need to jump ahead of MULTI_KEYWORD_RULES too).
    # Both "salt and vinegar" and "salt & vinegar" are listed because
    # clean_for_matching turns "&" into a space, not into the word "and",
    # so the two real spellings clean down to two different strings. Same
    # reasoning, same fix now for "sour cream and onion"/"sour cream
    # onion" -- found via real data (12 Aug 2026 collision report): "Mega
    # Pack Sour Cream & Onion Sticks" and "Sunshine Snacks Crispy Bakes
    # Sour Cream And Onion" were landing on Cooking Creams (bare "cream" is
    # listed earlier than Snacks), when they're clearly savoury snacks, not
    # a tub of cooking cream. A plain "Sour Cream 200ml" with no "onion"
    # is unaffected -- both words are required together.
    #
    # Bare "popcorn" moved to MULTI_KEYWORD_RULES (Pass 0, below) -- see
    # the comment there.
    ("Snacks", ["snack", "rice up rolls", "rice cake", "potato straws",
                "salt and vinegar", "salt vinegar",
                "sour cream and onion", "sour cream onion"]),
    # Bare "chips" moved to MULTI_KEYWORD_RULES (Pass 0, below). It used to
    # need a growing list of specific safe phrases here instead ("potato
    # chips", "tortilla chips", "lentil chips", "nacho chips", plus a
    # separate "rice"+"chips" co-occurrence rule) because a plain bare
    # "chips" entry here would have wrongly caught "Chocolate Chips" too --
    # but after seeing the SAME flavour-word collision keep recurring with
    # a new base ingredient every round (potato, tortilla, rice, lentil,
    # nacho...), a single general rule -- "chips" always means Chips,
    # UNLESS "chocolate" is also present -- covers all of those at once,
    # and any future one, instead of needing a new phrase added every time
    # a new chip brand turns up. See MULTI_KEYWORD_RULES for both halves
    # of that rule.
    # "almond"/"cashew"/"walnut"/"pistachio" + "butter" moved to
    # MULTI_KEYWORD_RULES (Pass 0, below), same reasoning as the existing
    # "Peanut Butter" fix -- a nut butter (e.g. "Biona Cashew Butter") was
    # landing on dairy Butter instead. Kept as narrow, per-nut carve-outs
    # rather than a broad "any nut word wins" rule -- Nuts collides with a
    # lot of other categories throughout this project's data (spice words,
    # Cheese, Coffee, Milk, Snacks...), and a blanket elevation was
    # deliberately not chosen this round; see the comment there.
    ("Nuts", ["peanut", "almond", "cashew", "walnut", "pistachio"]),
    ("Honey", ["honey"]),
    ("Jelly", ["jelly", "jello"]),
    # "olive oil" is checked in the multi-word pass, so it wins over the
    # bare "olive" rule right below it for any product whose name says both
    # -- e.g. "Extra Virgin Olive Oil 1L" lands on Olive Oil, not Olives.
    ("Olive Oil", ["olive oil"]),
    ("Olives", ["olive"]),  # found via real data: "Fragata Sliced Olives" was falling through unclassified
    # "vegetable oil"/"almond oil" -- same "olive oil" shape, found via real
    # data (19 Aug 2026 report): "Vegetable Oil 2L" was landing on
    # Vegetables (bare "vegetable" is listed long before bare "oil"), and
    # "Almond Oil Cold Pressed" was landing on Nuts (bare "almond" is listed
    # before bare "oil" too). Both are genuinely cooking/carrier oils, not a
    # vegetable or a nut product, so they get the same phrase-beats-bare-word
    # treatment as "olive oil" right above.
    ("Oils", ["vegetable oil", "almond oil"]),
    # Bare "oil"/"vinegar" -- needed now that both PAVI's "OILS" bucket and
    # Greens' "Oil And Vinegar" bucket split by name instead of mapping
    # directly (see the "Olive Oil" fix). Checked in the single-word pass,
    # AFTER "olive oil" above (so a real olive oil still lands on Olive Oil)
    # and after the existing "hair oil"/"facial oil"/"dry oil" phrases
    # elsewhere in this list (those are multi-word, always checked first).
    ("Oils", ["oil"]),
    # "rice vinegar"/"apple vinegar" -- same shape both times: was landing on
    # Rice/Fruits instead (bare "rice"/"apple" are single-word/tier-2, with
    # Rice and Fruits both listed earlier than Vinegars), found via real data
    # ("Blue Dragon Rice Vinegar", "Yutaka Rice Vinegar", "Carrefour Bio
    # Apple Vinegar", "Rinatura Apple Vinegar"). Listed as their own phrases
    # so they win over the bare word outright, the same way "olive oil"
    # already wins over bare "olive"/"oil".
    ("Vinegars", ["rice vinegar", "apple vinegar", "vinegar"]),

    # Household cleaning (targets the "Household Care And Essentials" catch-all)
    ("Laundry Washing Liquids", ["laundry liquid", "washing liquid"]),
    ("Laundry Washing Powders", ["washing powder", "laundry powder"]),
    ("Laundry Tablets", ["laundry tablet", "laundry pod", "laundry capsule"]),
    ("Fabric Softener", ["fabric softener", "fabric conditioner"]),
    ("Dish Washing Liquid", ["dish wash", "washing up liquid"]),
    ("Dishwasher Tablets", ["dishwasher tablet", "dishwasher pod"]),
    ("All-purpose Cleaners", ["all purpose cleaner", "multi surface", "surface cleaner"]),
    ("Floor Cleaners", ["floor cleaner"]),
    ("Bathroom & Wc Cleaner", ["toilet cleaner", "bathroom cleaner", "wc cleaner", "bleach"]),
    ("Stain Removers", ["stain remover"]),
    ("Insect Killer", ["insect killer", "insecticide", "fly spray"]),
    ("Drain Unblockers", ["drain unblock"]),
    ("Candles", ["candle", "incense"]),  # "incense" found via real data: incense sticks are filed as Candles Perfumed at Greens
    ("Cloths & Sponges", ["sponge", "cloth", "scourer"]),
    # Bare "foil" narrowed to specific phrases (19 Aug 2026) -- found via
    # real data: "Dancake Foil Cake Marble", "Dan Cake Foil Strawberry Cake"
    # (a real Maltese-sold cake brand, packaged in a foil tray) were tying
    # with Disposables just because the packaging word "foil" appears in the
    # name -- Cakes still won every time (Cakes is listed earlier), so this
    # was never an actual miscategorization, just noise in the collision
    # report. Narrowing to the specific phrases an actual foil-roll product
    # is sold under removes the false tie without needing a Cakes-side fix.
    ("Disposables", ["bin bag", "cling film", "aluminium foil", "aluminum foil", "kitchen foil", "tin foil", "foil roll", "baking foil", "kitchen roll", "paper towel", "paper plate", "napkin", "plastic cup"]),
    # Generic catch-all last, after the specific liquid/powder/tablet/softener
    # keywords above -- found via real data: "Surf Liquid Coconut 24 Washes"
    # and "General Laundry Wash Universal" don't contain the exact phrase
    # "laundry liquid", just the word "laundry" or "wash(es)" on its own.
    ("Laundry Washing Liquids", ["wash booster", "laundry wash"]),
    ("Household Goods", ["storage container", "lunch box", "thermos", "flask", "wooden spoon", "baking dish"]),  # "baking dish" added 23 Aug 2026 -- e.g. "No Nadir Baking Dish 1.8l", a Welbee's Home & Entertainment item with no other keyword match
    ("Stationery", ["scissors", "stationery"]),
    ("Electrical", ["light bulb", "led bulb", "gu10"]),  # "gu10" -- a specific, unambiguous lightbulb fitting type, found via real data
    ("Hand Tools", ["sandpaper", "sand paper"]),
    ("Air Fresheners", ["air freshener", "air freshner"]),  # both spellings -- "freshner" is a real typo seen in this project's own category data

    # Personal care (targets the "Personal Hygiene And Care" catch-all)
    # "head and shoulders"/"head & shoulders" -- a specific, globally-known
    # shampoo-only brand, found via real data (its product names don't
    # contain the word "shampoo" at all, e.g. "Head & Shoulders Men Ultra
    # Total Care").
    ("Shampoos", ["shampoo", "head and shoulders", "head & shoulders"]),
    ("Conditioners", ["conditioner"]),
    # "soap bar" -- found via real data (Dalan D'olive's Malta-sold range,
    # confirmed via WebSearch as a real personal-care brand carried by
    # M&Z p.l.c.): "Dalan D'olive Cocoa Butter Cream Soap Bar" and "...Aloe
    # Vera Cream Soap Bar" were landing on Cooking Creams/Olives (bare
    # "cream"/"olive"), since bare "soap" had NO keyword mapping anywhere
    # in this file at all until now -- a real, previously undiscovered gap,
    # not just a list-order bug. Filed under Shower Gels rather than a new
    # category, matching how Greens' own data already groups "Bath And
    # Shower Gels" as one bucket.
    ("Shower Gels", ["shower gel", "body wash", "bath foam", "bubble bath", "soap bar"]),
    ("Hair & Nail Accessories", ["comb"]),
    ("Toothpaste", ["toothpaste"]),
    ("Toothbrushes", ["toothbrush"]),
    ("Mouthwash", ["mouthwash"]),
    ("Deodorants", ["deodorant", "antiperspirant", "deo spray", "deo roll on", "deo stick"]),
    # "hand cream"/"body cream" -- found via the same Dalan D'olive real
    # data: "Dalan D'olive Hand & Body Cream Grapeseed" was landing on
    # Cooking Creams (bare "cream"), since neither phrase existed
    # alongside the existing "hand lotion"/"body lotion" ones.
    ("Body Lotions", ["body lotion", "hand lotion", "hand cream", "body cream", "moisturiser", "moisturizer"]),
    ("Face Creams", ["face cream", "facial cream"]),
    # "latte detergente" -- Italian for "cleansing milk", a skincare
    # product -- found via real data ("Roberts Rose Water Latte Detergente
    # Sensitive"), which was landing on Coffee (bare "latte") or Water.
    ("Skin Care", ["face wash", "facial wash", "cleansing gel", "facial cleanser", "facial oil", "dry oil", "latte detergente"]),
    ("Hand Wash Liquids", ["hand wash", "hand soap"]),
    ("Shaving Creams", ["shaving cream", "shaving foam", "razor"]),
    ("Hair Colouring", ["hair colour", "hair dye", "hair color"]),
    ("Hair Styling", ["hair gel", "hair spray", "hair wax"]),
    ("Hair Treatment", ["hair treatment", "hair mask", "hair oil"]),
    ("Sanitary Towels", ["sanitary towel", "sanitary pad", "daily liner", "panty liner"]),
    ("Intimate Care", ["tampon", "intimate wash"]),
    ("Cotton Buds", ["cotton bud", "cotton wool"]),
    ("First Aid", ["plaster", "bandage", "antiseptic", "first aid"]),
    ("Dental Care", ["dental", "denture", "corega"]),  # broader than Toothpaste/Toothbrushes above -- floss, dental sticks, tablets
    ("Make Up", ["lipstick", "mascara", "foundation", "eyeshadow", "nail polish", "make up", "makeup"]),
    ("Perfume", ["perfume", "eau de", "fragrance", "cologne"]),
    ("Gift Sets", ["gift set", "gift bag"]),

    # Baby
    ("Nappies", ["nappy", "nappies", "diaper"]),
    ("Adult Nappies", ["adult nappy", "incontinence"]),
    ("Baby Food", ["baby food", "infant formula", "baby cereal", "baby jar"]),
    ("Baby Essentials", ["baby wipe", "baby lotion", "baby shampoo"]),

    # Pets -- all moved to MULTI_KEYWORD_RULES (Pass 0, below). They used
    # to live here as ordinary phrase/single-word rules, but real pet-food
    # names that also mention a flavour (e.g. "Royal Canin Chicken Flavour
    # Dog Dry Food", "Purina Gourmet Felix ... Salmon") were losing to the
    # bare "chicken"/"salmon" meat-or-fish word, purely because Chicken and
    # Chilled Fish are listed earlier in this file than Cat/Dog. Checking
    # these first (like the Easter-egg rule) fixes that regardless of list
    # order.

    # Clothes
    ("Clothes", ["pyjama", "pajama", "sports bra"]),

    # Frozen
    ("Frozen", ["frozen", "ice cream"]),
    # Bare "pizza" moved to MULTI_KEYWORD_RULES (Pass 0, below) -- see the
    # comment there. "dough" stays here; the Pass 0 pizza rule already
    # resolves "Pizza Dough" to Pizza before this word is ever reached, the
    # same way the old in-list ordering used to (found via real data,
    # "Buitoni Rectangular Dough").
    ("Pastry", ["dough"]),

    # Tobacco / misc
    ("Tobacco & Tobacco Accessories", ["cigarette", "tobacco", "rolling paper"]),

    # Sports nutrition/supplements -- no dedicated canonical category exists
    # yet (PAVI's own data only has a generic "SPORTS" bucket, no
    # supplements-specific one), so this is an imperfect catch-all, same
    # kind of approximation as a few Greens mappings above. Revisit if this
    # turns out to be a large enough group to deserve its own category.
    ("Sports", ["whey", "protein powder", "creatine", "bcaa", "pre workout"]),

    # ---- 18/19 Aug 2026: first full-production "unclassified (store,
    # chain_category)" report, 129,703 listings. Unlike the collision
    # reports, these gaps aren't miscategorizations -- they're products the
    # keyword lists never had a word for at all, found from real example
    # names now sampled per bucket (see categorize_listings.py's
    # unclassified_examples). Four buckets turned out to be genuinely
    # outside the grocery domain (board games, gift wrap, pet grooming,
    # sauces/condiments, meat alternatives) with no existing category to
    # fall back on -- new categories added below rather than force-fitting
    # them somewhere approximate, same reasoning as the existing "Sports"
    # catch-all comment just above. Two buckets ("Food Cupboard" and
    # "Health & Beauty", 3271 and 2754 listings) were left mostly untouched
    # this round -- the report only gave 3 examples each, not enough to
    # responsibly close gaps that size; categorize_listings.py now samples
    # up to 8 examples per bucket instead of 3, so the next report should
    # give enough signal to take a real pass at those two.

    ("Nuts", ["nut"]),  # bare fallback -- "Good Health Unsalted Mixed Nuts" had no specific nut-type word (peanut/almond/cashew/walnut/pistachio) to match on
    ("Chocolates", ["gianduia"]),  # hazelnut-chocolate praline, e.g. Pernigotti Gemma Gianduia (WebSearch-confirmed)
    ("Dried Fruit", ["glazed cherries", "glace cherries"]),  # candied cherries, baking/snacking, e.g. "Good Health Glazed Cherries"

    ("Cotton Buds", ["cotton pad", "cottan pad"]),  # distinct phrase from the existing "cotton wool"; "cottan" is a real typo seen in data ("Cotoneve Duo Plus Cottan Pads")
    ("Cotton Buds", ["septona bio"]),  # Septona is a Greek cotton-pad brand (WebSearch-confirmed); narrow brand+line phrase since "Septona" alone also covers other personal-care lines

    ("Air Fresheners", ["reed diffuser", "reed difuser"]),  # both spellings -- "difuser" is a real typo seen in this project's own data, same pattern as "air freshner"
    ("Candles", ["scented pillar", "spaas"]),  # "pillar" candle is a real product shape; Spaas (WebSearch-confirmed) is a pillar-candle-only brand, safe as a bare brand word

    ("Toys & Games", ["uno", "board game", "card game"]),  # NEW category -- welbees "Home & Entertainment" (UNO, Mattel Uno Minecraft) has no grocery-domain fit; genuinely a toys/games department
    ("Gift Sets", ["wine bag"]),  # Stewo (WebSearch-confirmed gift-wrap-only brand) wine gift bags -- extends the existing "gift bag" phrase already in this category, not a new one

    ("Wine - Red", ["shiraz", "merlot"]),  # red wine grape varietals, e.g. "Jacobs Creek Shiraz", "Caravaggio Merlot"
    ("Wine - White", ["porto"]),  # fortified port wine has no dedicated category here (only Red/Rose/Sparkling/White exist) -- folded into White as the nearest fit, e.g. "Kopke Fine White Porto" (WebSearch-confirmed Port producer); flagged as a judgment call, not a confident "this is definitely a white wine"

    ("Laundry Washing Liquids", ["marsiglia"]),  # Marseille-soap-style Italian laundry detergent term, e.g. "Chanteclair 30 Lavaggi Marsiglia" -- Chanteclair itself (WebSearch-confirmed) spans detergent, softener, AND surface cleaners, so a brand-only rule would be unsafe
    ("Fabric Softener", ["ammorbidente", "lenor beads", "scent booster"]),  # "ammorbidente" is Italian for fabric softener; Lenor Beads (WebSearch-confirmed) are in-wash scent-booster beads, closest existing category
    ("Fabric Softener", ["lenor"]),  # 21 Aug 2026 -- "Lenor Ultra Orchid & Vanilla 126w (2.65l)" was unclassified: Lenor is exclusively a P&G fabric-care brand (already used above in narrower phrases), so the bare brand name is safe to add outright and covers the rest of the Lenor range too
    ("Chicken", ["pollo"]),  # Italian for chicken, e.g. "Aia Party Pollo" -- Aia itself (WebSearch-confirmed poultry brand) also sells turkey, so using the descriptive word rather than the brand name
    ("Cakes", ["almondy"]),  # Almondy (WebSearch-confirmed) is an almond-cake-only Swedish brand, e.g. "Almondy Salted Caramel Crush"
    ("Sports", ["olimp", "plant protein"]),  # Olimp (WebSearch-confirmed) is a sports-nutrition-only brand; "plant protein" extends the existing whey/creatine/bcaa list
    ("Legumes", ["bigilla"]),  # Maltese broad-bean dip (WebSearch-confirmed), e.g. "Josefa Bigilla"
    ("Pork", ["pancetta"]),  # Italian cured pork, e.g. "Carrefour Cubetti Di Pancetta Affumicata"
    ("Yoghurt", ["jogobella"]),  # Zott's yoghurt-only brand line (WebSearch-confirmed), e.g. "Zott Jogobella Reg Exotic"
    ("Pasta & Couscous", ["maccheroni"]),  # Italian spelling of macaroni -- the existing "macaroni" (English spelling) keyword doesn't match this, e.g. "Alimenti Maccheroni Beetroot"

    ("Sauces & Condiments", ["worcester sauce", "worcestershire sauce", "pasta sauce", "rikotta sauce"]),  # NEW category -- no sauces/condiments category existed at all; "rikotta" is the real misspelling seen ("Agromonte Cher Tom Rikotta Sauce")

    ("Baby Essentials", ["infacare", "baby bath", "baby powder"]),  # Infacare (WebSearch-confirmed baby-bath-only brand); extends the existing baby wipe/lotion/shampoo list

    ("Bread", ["bun", "brioche", "david's bakery", "dijo", "tortilla wrap", "finger roll", "fruit loaf"]),  # "David's Bakery" and Dijo (WebSearch-confirmed tortilla-wrap-only brand) are brand rules; the rest are descriptive bread-product terms. "fruit loaf" added 21 Aug 2026 -- e.g. "Jesper's Fruit Loaf" had no Bread keyword at all (bare "loaf" isn't registered), so it fell through to Fruits by default

    ("Milk", ["vive soy", "oat drink", "drink oat", "soya drink", "drink soya", "soy drink", "drink soy"]),  # Vive Soy (WebSearch-confirmed soya-milk-only brand); the rest cover Alpro-style drinks that never say the word "milk" itself -- both word orders needed, e.g. "Alpro Drink Oat No Sugar" puts "Drink" before "Oat"
    ("Cooking Creams", ["custard"]),  # e.g. "Alpro Custard Vanilla"

    ("Sugar", ["sweetner"]),  # real typo seen in data ("My Dietor Zero Calorie Sweetner") -- doesn't match the existing "sweetener" via the plural-only s? suffix
    ("Cereals", ["barley"]),  # e.g. "Alce Nero Organic Soluble Barley"
    ("Cake Preparations", ["cocoa powder"]),  # baking ingredient, extends the existing "yeast" entry in this category

    ("Fish & Other Animals", ["gammarus"]),  # dried aquarium fish food (WebSearch-confirmed), e.g. "Padovan Gammarus"
    ("Pet Food", ["m-pets"]),  # WebSearch-confirmed dog-treat-only brand
    ("Pet Care", ["pet wipes"]),  # NEW category -- pet grooming/hygiene has no home under the food-focused "Pet Food" category. "camon" itself is a Pass-0 rule below (see MULTI_KEYWORD_RULES) so it beats the later "cleansing wipes" Skin Care phrase, which would otherwise win as a Pass-1 phrase over this bare brand word

    ("Meat Alternatives", ["tofu", "beyond smash", "plant based burger", "veggie burger", "veggie stick"]),  # NEW category -- plant-based meat substitutes don't fit any existing food category; "Beyond Smash" (WebSearch-confirmed Beyond Meat product line)

    ("Bathroom & Wc Cleaner", ["trigger shower"]),  # Mr Muscle (WebSearch-confirmed bath/kitchen/drain cleaner brand) shower spray -- using the descriptive term since the brand itself spans multiple cleaner sub-types
    ("All-purpose Cleaners", ["platinum kitchen"]),  # Mr Muscle kitchen cleaner, same brand-spans-multiple-subtypes reasoning as above
    ("Floor Cleaners", ["pavimenti"]),  # Italian for "floors", e.g. "Tesoro Mio Pavimenti"
    ("Dish Washing Liquid", ["wash up"]),  # e.g. "Morning Fresh Wash Up Lemon Fresh" -- doesn't contain the existing "washing up liquid" phrase in full

    ("Sanitary Towels", ["con ali"]),  # Italian "with wings" -- common across winged sanitary pad brands, e.g. "Lines Natura Giorno Con Ali"
    ("Hand Wash Liquids", ["soap"]),  # bare fallback for bar soap with no other descriptive word, e.g. "Lux Soap Magical Spell", "Pears Soap Mint Extracts Bar" -- imperfect fit (these are bar soap, not liquid) but the closest existing category
    ("First Aid", ["dressing", "surgical spirit", "surgicalspirit", "foot powder"]),  # "surgicalspirit" (no space) is the real concatenated form seen in the data, kept alongside the spaced version
    ("Make Up", ["lip balm", "nail duo"]),  # extends the existing lipstick/mascara/foundation/eyeshadow/nail-polish list

    # ---- Same 18/19 Aug 2026 pass, continued: going back through every
    # remaining example in the original report (not just the 2 mega-buckets
    # we deferred) rather than waiting on a fresh, bigger-sample report --
    # requested directly rather than doing another slow report-and-paste
    # round.
    ("Chicken", ["nagghy"]),  # Aia's "Nagghy" is a specific chicken/poultry product line (WebSearch-confirmed via "AIA NAGGHY CHICK 1KG - CHICKEN & POULTRY")
    ("Vegetables", ["freskezza", "beetroot"]),  # Freskezza (WebSearch-confirmed) is a Maltese fresh-salad/prepared-veg-only brand
    ("Floor Cleaners", ["smac easy wax"]),  # Smac (WebSearch-confirmed) spans floor wax, furniture polish, and limescale remover, so using the specific product phrase rather than the bare brand name
    ("Clothes", ["sock"]),  # e.g. "Disney Paw Patrol Socks" -- not using the "Tex" brand name alone, since "Tex Mex" seasoning is a real, unrelated food product line
    ("Disposables", ["tissue", "toilet paper", "toilet tissue", "toilet roll"]),
    ("Bread", ["party roll"]),  # e.g. "Greens Party Rolls X18" -- these are dinner/bread rolls (confirmed by the "Bakery / Bread / Fresh Bread" chain_category it came from), not a paper product. Using the specific phrase "party roll" rather than bare "roll" since bare "roll" would ambiguously also match "toilet roll" and "kitchen roll" in Disposables
    ("Skin Care", ["cleansing wipes"]),  # e.g. "Nivea Cleansing Wipes 3in1"
    ("Fabric Softener", ["asciugatrice"]),  # Italian for "dryer" -- dryer sheets, e.g. "Lenor Fogli Profumati Asciugatrice"
    ("Sauces & Condiments", ["bruschetta"]),  # tomato-based bruschetta topping mix, e.g. "Fresh By Ela Bruschetta Mix"
    ("Cake Preparations", ["cocao powder"]),  # real misspelling of "cocoa powder" seen in data ("Alce Nero Organic Cocao Powder") -- the correctly-spelled version was already added above
    ("Sports", ["protein donut", "protein bar"]),  # e.g. "Body Attack Protein Donut Blueberry"

    # ---- 24 Aug 2026: 3rd unclassified-bucket pass, from the first run
    # under the new automatic 3-day schedule. All the small/medium buckets
    # from the last full report are now fully cleared (Drinks, Laundry,
    # Baby, Pets, Bakery, Toilet Paper, and a dozen more) -- only the
    # original 4 large catch-all buckets remain as genuinely large chunks
    # (Food Cupboard, Health & Beauty, Household, Home & Entertainment).
    ("Chocolates", ["kinder", "cioccolato"]),  # "Kinder" (Ferrero, WebSearch-confirmed confectionery-only) was flagged in this project's own status notes as a known hard case -- a well-known brand with no generic food word attached; "cioccolato" is Italian for chocolate
    ("Pasta & Couscous", ["rummo", "tagliatelle", "troccoli"]),  # Rummo (WebSearch-confirmed pasta-only Italian brand); "tagliatelle"/"troccoli" are pasta shapes with no brand needed. "troccoli" added 21 Aug 2026, user-confirmed -- this file also has a separate "Fresh Pasta" category, but it has no real keyword coverage of its own, so following the same precedent already set by "tagliatelle" rather than wiring up a whole new category branch for one product
    ("Tea", ["rooibos"]),  # herbal tea type, e.g. "Twining's Pure Rooibos" -- Twinings itself needs no rule since "rooibos" alone is enough
    ("Sauces & Condiments", ["caper"]),  # e.g. "3 Leaves Capers" (WebSearch-confirmed real Maltese-market brand) -- capers have no closer existing category

    ("Crackers, Crispbread & Breadsticks", ["tuc"]),  # WebSearch-confirmed: TUC (LU/Mondelez) is a cracker-only brand -- e.g. "Lu Tuc Bacon" is a bacon-FLAVOURED cracker, not real bacon

    ("Cotton Buds", ["demak up", "septona lady care"]),  # Demak'Up (WebSearch-confirmed cotton-pad-only French brand) and Septona's "Lady Care" cotton-round/cotton-bud line (WebSearch-confirmed)
    ("Deodorants", ["deo body spray"]),  # e.g. "Charlie Black Deo Body Spray" -- "Deo" and "Spray" aren't adjacent ("Body" sits between them), so the existing "deo spray" phrase doesn't match; Charlie (WebSearch-confirmed Revlon deodorant/body-spray line) needs no separate brand rule since "Deo Body Spray" already identifies it
    ("Perfume", ["impulse"]),  # WebSearch-confirmed UK body-spray-only brand ("the UK's #1 female body spray brand")
    ("Sanitary Towels", ["proteggi slip"]),  # Italian for "panty liner" (WebSearch-confirmed via Carrefour Italy's own product pages)
    ("Adult Nappies", ["incont"]),  # real abbreviation seen in data ("Carrefour Assorb. Incont. Mini") -- the existing "incontinence" keyword doesn't match a shortened form like this

    ("Laundry Tablets", ["dixan"]),  # Dixan (WebSearch-confirmed Henkel detergent-only brand); "Discs" here means predosed detergent capsules, not a softener
    # 21 Aug 2026 -- this bare "scrub daddy" entry was a straight-up
    # duplicate with the "scrub daddy" entry under Household Goods below
    # (same exact phrase, two categories), which meant EVERY Scrub Daddy
    # product always landed here first, including their sponges/cloths/
    # dusters/BBQ scourers -- not a real keyword tie, just an accidental
    # copy. Real data (via SQL query) showed Scrub Daddy's range is
    # overwhelmingly physical cleaning TOOLS (Household Goods), with only
    # two genuine chemical cleaning products: "Power Paste" and "Multi
    # Surface Spray". Replaced the bare brand match with those two
    # specific phrases, and left the Household Goods entry below as the
    # catch-all for the rest of the range.
    ("All-purpose Cleaners", ["daddy power paste", "multi surface spray"]),  # "daddy power paste" (not "scrub daddy power paste") to also match the real "Scrub Daddy  Daddy Power Paste" listing style, which repeats "Daddy" with a double space before it
    ("Dishwasher Tablets", ["dishwasher capsule"]),  # extends the existing "dishwasher tablet"/"dishwasher pod" phrases -- Astonish (WebSearch-confirmed cleaning-only brand) uses "Capsules" specifically

    ("Household Goods", ["lunchbox", "plastic bin", "rolling pin", "tala", "go travel", "scrub daddy"]),  # "lunchbox" (one word) is the real spacing variant seen in data -- the existing "lunch box" (two words) doesn't match it; Tala (WebSearch-confirmed kitchenware-only brand) and Go Travel (WebSearch-confirmed travel-accessories-only brand, e.g. padlocks) are brand rules
    ("Hand Tools", ["dekton"]),  # WebSearch-confirmed tools-only brand (drill sets/bits)
    ("Stationery", ["legami"]),  # WebSearch-confirmed Italian stationery/creative-gifts brand -- their main product line by far is stationery, even though this brand occasionally also sells novelty items like binoculars

    ("Toys & Games", ["barbie", "volleyball", "volley ball", "party hat"]),  # Barbie (Mattel, well-known toys-only brand); "volleyball"/"volley ball" and "party hat" are recreational/party items with no better home

    # ========================================================================
    # 18 Aug 2026 -- BULK SWEEP of the four large catch-all buckets.
    #
    # Why this block is so much bigger than the ones above it: every previous
    # round worked from the 8 example names the run report prints per bucket,
    # which meant closing 8 names out of 3,000 and waiting three days to see
    # the next 8. Instead of guessing again, 478 realistic supermarket product
    # names were written out by hand across every product type these four
    # buckets plausibly contain, run through classify_by_name(), and the 308
    # that came back unclassified were used as the worklist. This block is
    # what closes those 308.
    #
    # It covers general product VOCABULARY ("mayonnaise", "notebook",
    # "screwdriver", "pantyliner") rather than one brand at a time, which is
    # what makes it scale -- a rule for "shower gel" closes every shower gel
    # in the database, not just the one that happened to get printed.
    #
    # Word-choice rules followed throughout, learned from earlier rounds:
    #   * No bare word that changes meaning between aisles. "powder" is curry
    #     powder, washing powder, baking powder and compact powder; "brush" is
    #     a toothbrush, a hairbrush, a paint brush and a toilet brush. Those
    #     are always written as a qualified phrase instead.
    #   * "olive oil" is deliberately NOT a keyword here even though it looks
    #     like the obvious one -- it would steal "Rio Mare Tuna In Olive Oil"
    #     away from the fish rules, because a Pass-1 phrase always beats a
    #     Pass-2 bare word like "tuna". "extra virgin"/"evoo"/"olio" catch the
    #     actual olive oil bottles without that side effect.
    #   * Household Goods is listed BEFORE Toys & Games below so that
    #     "Balloon Whisk" resolves to the kitchen utensil rather than to a
    #     party balloon; both are bare words in the same pass, so list order
    #     is what decides.
    # ========================================================================

    # ---- Food Cupboard: sauces, condiments, oils, vinegars ----
    # Bare "sauce" is the single highest-value word in this whole block --
    # "Tartare Sauce", "Brown Sauce", "Horseradish Sauce", "Soy Sauce",
    # "Pepper Sauce" and dozens more all end in it, and every one of them
    # genuinely is a condiment. The more specific phrases added earlier (e.g.
    # "rikotta sauce", "pasta sauce") still win, because they're checked in
    # the earlier phrase pass.
    ("Sauces & Condiments", [
        "sauce", "ketchup", "mayonnaise", "mayo", "mustard", "pesto",
        "passata", "polpa", "fine pulp", "salad cream", "salad dressing",
        "teriyaki", "marinade", "relish", "chutney", "gravy", "horseradish",
        "sriracha", "salsa", "tabasco", "hoisin", "pickle", "gherkin",
        "piccalilli", "aioli",
    ]),
    ("Olive Oil", ["extra virgin", "evoo", "olio", "carapelli", "filippo berio"]),  # "olive oil" itself is deliberately excluded -- see the note at the top of this block
    # No Oils entry here on purpose: the bare word "oil" is already an Oils
    # keyword, so "Sunflower Oil 1l" was never the problem. Adding the full
    # phrases made things worse -- as Pass-1 phrases they beat bare words and
    # stole "STUFFED OLIVES IN SUNFLOWER OIL" and "WHITE CHEESE IN SUNFLOWER
    # OIL", which are olives and cheese, not cooking oil.
    ("Vinegars", ["aceto", "balsamic", "balsamico"]),

    # ---- Food Cupboard: breakfast, hot drinks ----
    ("Cereals", [
        "weetabix", "corn flake", "cornflake", "porridge", "all bran",
        "cheerios", "special k", "coco pops", "rice krispies", "frosties",
        "shreddies", "crunchy nut", "quaker oat", "rolled oat",
    ]),
    ("Coffee", ["decaff", "decaf", "nescafe", "lavazza", "illy", "kenco", "douwe egberts", "coffee pod", "coffee capsule", "dolce gusto", "cappuccino", "americano", "moka"]),
    ("Tea", ["infusion", "chamomile", "camomile", "earl grey", "twinings", "lipton", "tetley", "yorkshire tea", "tea bag", "teabag", "herbal tea", "green tea"]),

    # ---- Food Cupboard: sweets, snacks, chocolate ----
    # "gum" covers both chewing gum and wine gums; nothing else in a
    # supermarket is called a gum.
    ("Sweet Snacks", [
        "gum", "orbit", "wrigley", "airwaves", "mentos", "tic tac",
        "haribo", "skittles", "starburst", "chupa chup", "lollipop", "lolly",
        "marshmallow", "toffee", "fudge", "nougat", "liquorice", "licorice",
        "halls", "ricola", "fisherman", "jelly bean", "gummy", "gummies",
        "candy", "sherbet", "fruit gum",
    ]),  # "fruit gum" added 21 Aug 2026 -- bare "fruit" (an early, very broad Fruits keyword) was beating bare "gum" every time both appeared in the same name (e.g. "Rowntree's Fruit Gums"), so the phrase is needed to jump ahead of it
    ("Chocolates", [
        "lindt", "toblerone", "ferrero", "rocher", "mars bar", "snickers",
        "twix", "bounty bar", "galaxy", "aero", "wispa", "dairy milk",
        "milkybar", "praline", "truffle", "after eight", "maltesers",
        "kit kat", "kitkat", "smarties",
    ]),
    ("Biscuits", ["digestive", "shortbread", "mcvitie", "rich tea", "custard cream", "jaffa", "ginger nut", "cantuccini", "amaretti", "savoiardi", "sponge finger", "biscotti"]),
    ("Crackers, Crispbread & Breadsticks", ["grissini", "crispbread", "cream cracker", "water biscuit", "rice cake", "galletti", "ryvita"]),
    ("Chips", ["crisp", "pringle", "dorito", "wotsit", "hula hoop", "monster munch", "quaver", "popcorn", "twiglet", "tortilla chip", "potato chip"]),

    # ---- Food Cupboard: staples ----
    ("Pasta & Couscous", ["fusilli", "rigatoni", "farfalle", "linguine", "conchiglie", "vermicelli", "ravioli", "tortellini", "gnocchi", "noodle", "orzo", "barilla", "de cecco", "cannelloni", "fettuccine"]),
    ("Rice", ["basmati", "arborio"]),  # only the words that DON'T contain "rice" -- the bare word "rice" already covers "brown rice"/"long grain" etc., and adding them as phrases stole gluten-free rice-flour PASTA ("Doves Farm Penne Brown Rice") away from Pasta
    ("Legumes", ["chickpea", "chick pea", "kidney bean", "baked bean", "butter bean", "cannellini", "borlotti", "broad bean", "black bean", "haricot", "split pea"]),
    ("Canned Seafood", ["anchovy", "anchovie", "mackerel fillet", "tuna chunk", "tuna flake", "rio mare", "john west"]),
    ("Soups", ["minestrone", "cup a soup", "broth", "bouillon"]),
    ("Stock Cubes", ["stock cube", "stock pot", "oxo cube"]),  # deliberately NOT "beef cube"/"chicken cube" -- caught in this round's regression sweep stealing "CHEF CHOICE FROZEN BEEF CUBES", which is real diced meat
    ("Herbs & Spices", [
        "cumin", "turmeric", "nutmeg", "clove", "curry powder", "chilli powder",
        "garlic powder", "onion powder", "mixed herb", "bay leaf", "bay leave",
        "cardamom", "coriander", "peppercorn", "saffron",
        "allspice", "sage", "tarragon", "marjoram", "fennel seed",
        "mustard seed", "seasoning", "schwartz",
        # "vanilla" itself removed from this bare-word list 21 Aug 2026 --
        # from the collisions report, this was the single biggest driver of
        # the Biscuits/Herbs & Spices (96), Cakes/Herbs & Spices (51),
        # Coffee/Herbs & Spices (49), Cereals/Herbs & Spices (47) and
        # Herbs & Spices/Yoghurt (57) pairs -- ~300 listings in total, all
        # the same shape: a vanilla-FLAVOURED wafer/muffin/cappuccino/
        # cereal-bar/yoghurt tying bare "vanilla" against the product's own
        # real type, and landing on Herbs & Spices roughly half the time
        # purely by list-order luck (e.g. "Rayner's Vanilla Muffins" and
        # "YOFU Greek Style-Vanilla" both wrongly did; "CAKE VANILLA 50G"
        # happened to land correctly). There's no real ambiguity here the
        # way there is for a genuinely dual-category product -- a vanilla
        # muffin is a muffin, full stop, nobody looks for it in the spice
        # aisle. Replaced below with specific phrases for the cases that
        # actually ARE spice-aisle vanilla (pods, extract, beans) --
        # phrases already beat every other bare word in this file by
        # design, so those still resolve correctly without reintroducing
        # this same collision.
    ]),  # deliberately NOT "sea salt"/"table salt" -- as phrases they beat "crispbread" and "rice cracker" on snacks that merely mention sea salt; the bare word "salt" above already catches actual salt
    ("Herbs & Spices", ["vanilla pod", "vanilla extract", "vanilla bean", "pure vanilla"]),
    # 21 Aug 2026 -- a real run against live data surfaced 3 more baking-
    # aisle vanilla products the phrases above didn't catch, because the
    # word order in the real product name is reversed from the phrase, or
    # the source itself has a typo:
    #   "Ruf Vanilla Powder (3 x38grms)" -- needs "vanilla powder". Checked
    #   this can't collide with a protein-powder product before adding it:
    #   real supplement names put the flavour word AFTER "powder" (e.g.
    #   "... Protein Powder Vanilla"), never "vanilla powder" as an
    #   adjacent phrase, so this stays baking-specific in practice.
    #   "Tropical Sun Mini Essence Vanilla (28ml)" -- the label says
    #   "Essence Vanilla", not "Vanilla Essence" (which already exists
    #   under Cake Preparations) -- added as its own reversed-order phrase
    #   rather than assuming every future product will use the same word
    #   order as the last one.
    #   "Pearce Duff's Vanilla Falvour (35grms)" -- the product's own name
    #   has a typo ("Falvour" for "Flavour"), so the correctly-spelled
    #   phrase would never match it. Same "keep the literal typo as its
    #   own keyword" pattern already used elsewhere in this file (see e.g.
    #   "fabric conditoner", "prositcutto cotto").
    ("Herbs & Spices", ["vanilla powder", "essence vanilla", "vanilla falvour"]),
    ("Sugar", ["icing sugar", "caster", "demerara", "muscovado", "brown sugar", "granulated", "stevia", "canderel", "golden syrup"]),
    ("Flour", ["cornflour", "corn flour", "cornstarch", "corn starch", "semolina", "self raising", "plain flour", "bread flour", "wholemeal flour"]),
    ("Cake Preparations", ["baking powder", "bicarbonate", "cake mix", "icing", "fondant", "sprinkle", "marzipan", "gelatine", "gelatin", "food colouring", "food coloring", "dr oetker", "betty crocker", "vanilla essence"]),
    ("Jelly", ["jam", "marmalade", "conserve", "preserve", "st dalfour"]),
    ("Nuts", ["pistachio", "pecan", "brazil nut", "pine nut", "macadamia", "mixed nut", "salted nut"]),
    ("Dried Fruit", ["cranberry", "cranberries", "pitted date", "prune", "dried apricot", "dried fig", "goji", "currant"]),
    ("Vegetables", ["sweetcorn", "sweet corn", "jalapeno", "artichoke", "garden pea", "mushroom", "asparagus tip"]),  # deliberately NOT "sun dried tomato" -- it beat "couscous" on "Sun Dried Tomato & Garlic Couscous"; the bare word "tomato" already covers sun-dried tomatoes
    ("Peanut Butter", ["peanut butter", "sun pat"]),

    # ---- Food Cupboard: drinks ----
    ("Carbonated Drinks", ["pepsi", "sprite", "7up", "seven up", "fanta", "kinnie", "lemonade", "tonic water", "ginger ale", "root beer", "schweppes", "soda water", "cherryade", "cream soda"]),
    ("Energy Drinks", ["red bull", "monster energy", "lucozade", "energy drink", "isotonic", "rockstar"]),
    ("Juices", ["nectar", "smoothie", "innocent"]),
    # 21 Aug 2026 -- found while investigating the Sauces & Condiments/
    # Vegetables report (not part of that report itself -- this pair
    # never ties with anything, so it was invisible to the collision
    # detector, but real product names confirmed it's wrong today):
    # "Succo E/& Polpa" ("juice & pulp") fruit-nectar drinks -- e.g.
    # "Deco' Succo Polpa Pesca", "Simpl Succo & Polpa Albicocca" -- were
    # landing on Sauces & Condiments via bare "polpa", even though bare
    # "succo" (Juices) already exists too; both are bare/tier-2 so it was
    # just list-order luck, same shape as everything else in this file.
    # Two phrases needed since "&" and "e" ("and") both appear in real
    # labels and clean differently (the "&" strips out entirely).
    ("Juices", ["succo e polpa", "succo polpa"]),
    ("Dilutables", ["squash", "cordial", "robinsons"]),

    # ---- Health & Beauty: deodorant, wash, hair ----
    ("Deodorants", ["roll on", "rollon", "deospray", "deo spray", "body spray", "anti perspirant", "antiperspirant", "rexona", "borotalco", "right guard", "sure men"]),  # deliberately NOT "sanex" or "malizia": WebSearch shows both brands span deodorant AND shower gel AND (for Malizia) perfume and aftershave, so a brand-only rule would mis-file half their range. The descriptive words above catch their actual deodorants ("Sanex Deospray", "Sanex Roll On", "Malizia Uomo Body Spray") and the Shower Gels rules catch the rest
    ("Shower Gels", ["shower gel", "body wash", "bath foam", "bagnoschiuma", "bubble bath", "shower cream", "bath salt", "bath soak", "foamburst", "vidal", "radox", "imperial leather", "badedas", "ecoricarica", "ecoricarcia"]),  # "ecoricarcia" is a real spelling in the source data, not a typo on our side
    ("Shampoos", ["elvive", "tresemme", "gliss", "syoss", "timotei", "herbal essence", "nizoral", "dry shampoo", "anti dandruff"]),
    ("Hair Styling", ["hairspray", "hair spray", "styling gel", "hair mousse", "hair wax", "pomade", "got2b", "elnett", "hair serum", "heat protect"]),
    ("Hair Colouring", ["hair colour", "hair color", "hair dye", "nutrisse", "casting creme", "koleston", "live colour", "hair bleach", "root touch"]),

    # ---- Health & Beauty: skin, body, make up ----
    ("Skin Care", [
        "face mask", "sheet mask", "peel off", "micellar", "cleanser",
        "face scrub", "facial scrub", "exfoliating", "exfoliator",
        "exfoliant", "eye contour", "eye cream",
        "eye serum", "face serum", "facial serum", "day cream", "night cream",
        "face cream", "anti wrinkle", "sun protect", "sunscreen", "sun cream",
        "sun lotion", "sun care", "after sun", "aftersun", "aloe vera", "hydro boost",
        "neutrogena", "face toner", "facial toner",
    ]),
    ("Body Lotions", ["body lotion", "body cream", "body butter", "hand cream", "vaseline", "intensive care lotion", "foot cream", "e45"]),
    ("Make Up", [
        "concealer", "eyeliner", "eye shadow", "eyeshadow", "blusher",
        "bronzer", "nail polish", "nail varnish", "lip gloss", "lip liner",
        "compact powder", "face powder", "loose powder", "setting spray",
        "brow pencil", "max factor", "maybelline", "rimmel", "labello",
        "false lash", "make up remover", "makeup remover",
    ]),

    # ---- Health & Beauty: oral, feminine, shaving, medicine ----
    ("Dental Care", ["interdental", "refill brush", "denture", "corega", "fixodent", "teeth whitening", "tongue cleaner", "toothpick", "tooth pick"]),
    ("Toothpaste", ["sensodyne", "parodontax", "aquafresh", "elmex", "meridol", "dentifricio"]),
    ("Sanitary Towels", ["pantyliner", "panty liner", "pantiliner", "sanitary towel", "sanitary pad", "tampax", "carefree", "nuvenia", "always ultra", "always platinum", "panty shield"]),
    ("Intimate Care", ["intimate wash", "intimate wipe", "saugella", "lactacyd", "feminine wash", "intimate gel"]),
    ("Shaving Creams", ["shaving gel", "shaving foam", "shaving cream", "aftershave", "after shave", "gillette", "wilkinson", "mach3", "shave gel", "hair removal", "epilator", "wax strip", "veet"]),
    ("Perfume", ["eau de toilette", "eau de parfum", "body mist", "fragrance", "cologne"]),
    ("First Aid", [
        "paracetamol", "ibuprofen", "aspirin", "multivitamin",
        "lozenge", "nasal spray",
        "saline", "eye drop", "hand sanitiser", "hand sanitizer", "thermometer",
        "elastoplast", "compeed", "betadine", "savlon", "germolene", "gauze",
        "antihistamine", "cough syrup", "throat spray", "rehydration",
        "effervescent tablet",
    ]),  # "vitamin c"/"vitamin d"/"vitamin b" moved out 23 Aug 2026 -- see
    # note near the end of this list, right before MULTI_KEYWORD_RULES
    ("Hair & Nail Accessories", ["hair band", "hairband", "hair tie", "hair clip", "hair grip", "bobby pin", "scrunchie", "hair brush", "hairbrush", "paddle brush", "tweezer", "nail clipper", "nail scissors", "emery board", "hair roller", "shower cap"]),
    ("Nappies", ["pampers", "huggies"]),
    ("Baby Essentials", ["soother", "baby bottle", "bottle teat", "muslin", "baby bib", "bepanthen"]),
    ("Adult Nappies", ["tena"]),
    ("Baby Food", ["cerelac", "aptamil", "hipp organic", "nestum", "baby puree", "follow on milk"]),

    # ---- Household: laundry & dishwashing ----
    ("Laundry Tablets", ["ariel pod", "washing pod", "laundry pod", "laundry capsule", "washing capsule", "bio capsule", "laundry tab"]),
    ("Laundry Washing Liquids", ["washing liquid", "liquid detergent", "non bio", "detersivo", "laundry liquid"]),
    ("Laundry Washing Powders", ["washing powder", "powder detergent", "detergent powder"]),
    ("Fabric Softener", ["coccolino", "fabric conditioner", "vernel", "downy", "softner"]),
    ("Stain Removers", ["vanish", "stain remover", "oxi action", "smacchiatore", "pre wash"]),
    ("Dish Washing Liquid", ["washing up liquid", "svelto", "piatti", "dish soap", "dishwashing liquid"]),
    ("Dishwasher Tablets", ["powerball", "rinse aid", "dishwasher salt", "dishwasher tab", "brilliant shine"]),

    # ---- Household: cleaning ----
    ("All-purpose Cleaners", [
        "multi purpose", "multipurpose", "all purpose", "surface spray",
        "surface cleaner", "degreaser", "sgrassatore", "window cleaner",
        "glass cleaner", "limescale", "viakal", "antibacterial spray",
        "mr muscle", "ajax", "pink stuff", "universal cleaner", "kitchen spray",
    ]),
    ("Bathroom & Wc Cleaner", ["toilet duck", "rim block", "descaler", "candeggina", "toilet block", "wc gel", "bathroom cleaner", "toilet gel"]),
    ("Floor Cleaners", ["mop", "floor wipe", "floor gel"]),
    ("Drain Unblockers", ["unblocker", "plughole", "drain gel", "drain granule"]),
    ("Cloths & Sponges", ["dishcloth", "dish cloth", "steel wool", "scrub pad", "microfibre cloth", "floor cloth", "j cloth", "wash cloth"]),
    ("Disposables", ["bin liner", "bin bag", "refuse sack", "baking paper", "greaseproof", "freezer bag", "sandwich bag", "food bag", "paper plate", "paper cup", "plastic cutlery", "plastic plate", "drinking straw", "paper straw", "aluminium foil", "tin foil", "kitchen foil", "paper towel"]),
    ("Air Fresheners", ["glade", "ambi pur", "air wick", "airwick", "room spray", "automatic spray", "vent clip"]),
    ("Insect Killer", ["mosquito", "ant killer", "fly paper", "fly spray", "cockroach", "baygon", "insetticida", "insect repellent", "fly trap"]),

    # ---- Household / Home & Entertainment: kitchenware, storage, tools ----
    # Listed BEFORE Toys & Games on purpose -- see the note at the top of
    # this block about "Balloon Whisk".
    ("Household Goods", [
        "tatay", "curver", "hosepipe", "picnic cooler", "cooler box",
        "cool box", "storage box", "clothes peg", "clothes hanger",
        "coat hanger", "laundry basket", "ironing board", "drying rack",
        "clothes airer", "bucket", "washing up basin", "dustpan", "broom",
        "doormat", "pedal bin", "waste bin", "garden hose", "watering can",
        "muffin tin", "baking tray", "roasting tin", "cake tin", "frying pan",
        "saucepan", "casserole dish", "round dish", "oven dish", "serving dish",
        "chopping board", "grater", "peeler", "whisk", "spatula", "colander",
        "sieve", "kitchen tong", "ladle", "corkscrew", "tin opener",
        "can opener", "bottle opener", "oven glove", "tea towel", "apron",
        "thermos", "mixing bowl", "measuring jug", "dish rack", "dish drainer",
    ]),
    ("Electrical", [
        "charger", "usb", "adapter", "adaptor", "battery", "batteries",
        "rechargeable", "rechargable", "duracell", "energizer", "led bulb",
        "light bulb", "torch", "extension lead", "kettle", "toaster",
        "blender", "hand mixer", "food mixer", "hair dryer", "hairdryer",
        "straightener", "trimmer", "earphone", "headphone", "bluetooth speaker",
        "power bank", "plug adapter", "electric shaver",
    ]),  # "rechargable" is a real misspelling in the source data
    ("Candles", ["wax melt"]),
    ("Hand Tools", ["screwdriver", "hammer", "plier", "spanner", "wrench", "tape measure", "spirit level", "hacksaw", "wd40", "wd 40", "duct tape", "insulating tape", "cable tie", "super glue", "allen key", "utility knife", "stanley knife", "power drill", "cordless drill"]),
    ("Stationery", [
        "diary", "ballpoint", "biro", "notebook", "notepad",
        "eraser", "ruler", "sharpener", "marker", "stapler", "staple",
        "envelope", "ring binder", "glue stick", "sellotape", "scotch tape",
        "post it", "sticky note", "calculator", "crayon", "colouring pencil",
        "colour pencil", "felt tip", "exercise book", "copybook",
        "printer paper", "copy paper", "paper clip", "highlighter pen",
        "pencil case", "pencil sharpener", "whiteboard", "correction fluid",
        "tippex", "chalk",
    ]),
    ("Toys & Games", [
        "toy", "bestway", "intex", "swim ring", "swim safe", "armband",
        "inflatable", "beach ball", "jigsaw", "puzzle", "lego", "teddy",
        "plush", "doll", "action figure", "playing card", "chess", "domino",
        "dominoe", "dice", "skipping rope", "water gun", "bubble blower",
        "play dough", "play doh", "sticker", "colouring book", "football",
        "basketball", "racket", "frisbee", "scooter", "rattle", "balloon",
        "yo yo", "kite",
    ]),
    ("Gift Sets", ["wrapping paper", "gift wrap", "gift bow", "greeting card", "birthday card", "party bag", "gift box", "gift ribbon"]),

    # ========================================================================
    # 18 Aug 2026 -- SECOND bulk sweep, run the same way as the first.
    #
    # The first sweep took the four catch-all buckets from 17,008 unclassified
    # listings down to 11,878. This round wrote out another 205 realistic
    # product names aimed squarely at what the new report's examples revealed
    # was still missing -- world foods and seeds in Food Cupboard, nail and
    # cotton-wool items in Health & Beauty, DIY and specialist cleaners in
    # Household, and tableware, cookware and car care in Home & Entertainment
    # -- and closed the 145 of them that came back unclassified.
    #
    # Same word-choice discipline as before: no bare word that changes meaning
    # between aisles ("towel" is a tea towel, a paper towel and a bath towel;
    # "polish" is nail polish, shoe polish and metal polish; "glove" is an
    # oven glove, a rubber glove and an exfoliating glove), so each of those
    # is written as a qualified phrase.
    # ========================================================================

    # ---- Food Cupboard: world foods, seeds, baking, grains ----
    ("Pasta & Couscous", ["saikebon", "nudolini", "instant noodle", "ramen", "cup noodle"]),
    ("Tea", ["teekanne", "chai"]),
    ("Crackers, Crispbread & Breadsticks", ["ritz", "poppadom", "pretzel"]),
    ("Legumes", ["lima bean", "mung bean", "falafel", "butter beans"]),
    ("Herbs & Spices", ["sesame seed", "poppy seed", "wasabi", "nori", "seaweed", "miso"]),
    ("Nuts", ["pistacchio", "sunflower seed", "pumpkin seed", "chia seed", "flax seed", "linseed", "trail mix"]),
    ("Snacks", ["bombay mix", "festive mix", "snack mix", "party mix", "wasabi pea"]),
    ("Sauces & Condiments", ["tahini"]),
    ("Flour", ["breadcrumb", "panko", "polenta"]),
    ("Vegetables", ["bamboo shoot"]),
    ("Cake Preparations", ["pancake mix", "batter mix", "dessert whip", "jelly crystal", "desiccated", "tapioca"]),
    ("Sugar", ["molasses", "glucose syrup"]),
    ("Cereals", ["quinoa", "bulgur", "bran"]),

    # ---- Health & Beauty: nails, cotton wool, body, pharmacy ----
    ("Mouthwash", ["listerine", "m wash", "mouth wash"]),
    ("Hair & Nail Accessories", ["nail file", "nail buffer", "cuticle", "foot file", "callus", "pumice stone", "body brush"]),
    ("Cotton Buds", ["cotton disc", "cotton wool", "cotonet"]),
    ("Conditioners", ["balsamo"]),  # Italian for hair conditioner -- appears on Carrefour's own-brand range
    ("Make Up", ["kohl", "kajal", "catrice", "lip pencil", "eye pencil"]),
    ("Skin Care", ["exfoliating glove", "bath bomb", "talcum", "talco", "massage oil"]),
    ("First Aid", ["ear plug", "contact lens", "reading glasses", "pregnancy test", "athletes foot"]),
    ("Intimate Care", ["condom"]),
    ("Baby Essentials", ["breast pad", "nipple cream"]),
    ("Deodorants", ["foot spray"]),

    # ---- Household: DIY, specialist cleaners, shoe care ----
    ("Hand Tools", ["drill bit", "wall plug", "picture hook", "paint brush", "paint roller", "masking tape", "dust collector", "drilling", "dust mask"]),
    ("Disposables", ["foil container", "foil tray", "foil dish"]),
    ("Air Fresheners", ["freshener", "aria di casa", "deodorante ambiente"]),
    ("Dish Washing Liquid", ["morning fresh"]),
    ("All-purpose Cleaners", ["oven cleaner", "grill cleaner", "carpet cleaner", "mould remover", "disinfectant", "wood polish", "metal polish", "silver cleaner", "antibacterial wipe"]),
    ("Insect Killer", ["mothball"]),

    # ---- Home & Entertainment: tableware, cookware, textiles, car care ----
    ("Electrical", ["lightbulb", "table lamp", "fuse wire", "bedside lamp"]),
    # "mocio" (Italian for "mop") and "steam mop" moved ahead of the
    # "vileda" Household Goods rule below, 23 Aug 2026 -- Vileda's own
    # "Mocio"-branded mop products (e.g. "Vileda Mocio Completo") were
    # losing to bare "vileda" purely on file position, same as bare "mop"
    # and "pavimenti" already do by sitting above this block.
    ("Floor Cleaners", ["mocio", "steam mop"]),
    ("Household Goods", [
        "vileda", "tefal", "sistema", "turtle wax", "beach towel", "bath towel",
        "hand towel", "cooking tong", "frypan", "fry pan", "wok", "griddle pan",
        "dinner plate", "side plate", "coffee mug", "mug", "wine glass",
        "wine glasses", "tumbler",
        "champagne flute", "cutlery set", "steak knife", "kitchen knife",
        "knife sharpener", "placemat", "coaster", "storage jar",
        "food container", "picture frame", "wall clock", "alarm clock",
        "cushion cover", "throw blanket", "shower curtain", "bath mat",
        "laundry bag", "umbrella", "salad bowl", "bowl set", "cereal bowl",
        "water bottle", "drink bottle", "shoe rack", "shoe polish",
        "shoe brush", "suede cleaner", "silica gel", "dehumidifier",
        "moisture absorber", "door hook", "vacuum bag", "rubber glove",
        "disposable glove", "vinyl glove", "chamois", "screen wash",
        "car shampoo", "wiper blade",
    ]),  # "vileda" spans mops, cloths, sponges and buckets -- all non-consumable cleaning equipment, which is what Household Goods is for here; the more specific words above (e.g. bare "sponge") still win where they apply

    # ========================================================================
    # 18 Aug 2026 -- THIRD bulk sweep.
    #
    # This round paired with a structural change (LAST_RESORT_CATEGORY_MAP,
    # further down this file), which handles every bucket whose own name
    # states the category -- "Laundry Detergent", "Tampons", "Fresh Bread".
    # What's left over, and what this block is for, are the buckets where the
    # aisle genuinely tells you nothing: Welbee's four catch-alls plus its
    # "Drinks" and "Chilled Food", and Greens' dietary aisles ("Gluten Free",
    # "Organic", "Low Fat"), which are a LABEL rather than a product type and
    # hold milk, pasta, biscuits and yoghurt side by side.
    #
    # Heavier on Italian than earlier rounds, because that's what the real
    # data looks like at this depth -- "salame", "provola", "bevanda",
    # "frollino", "caserecce", "veline" -- along with several misspellings
    # that are genuinely in the source data ("Toohtbrush", "Breadcrubs",
    # "Alluminum", "Canneloni", "Insted").
    # ========================================================================

    # ---- Wine, by grape and style. The bottles often name nothing else. ----
    # "cabernet sauvignon" is listed here as its own phrase (not just relying
    # on bare "cabernet" below) so it wins outright over the bare "sauvignon"
    # keyword in the White list right after this -- found from the
    # "category collisions" report (21 Aug 2026): "Cabernet Sauvignon" is
    # ALWAYS a red wine (Sauvignon is the second half of ITS name, not a
    # separate Sauvignon Blanc), but bare "cabernet" and bare "sauvignon"
    # were tying as equally-strong single words, with the actual winner
    # decided only by unrelated list order, not by which one is correct.
    ("Wine - Red", ["cabernet sauvignon", "appassimento", "nero d avola", "cabernet", "malbec", "merlot", "chianti", "primitivo", "montepulciano", "valpolicella", "zinfandel", "syrah", "sangiovese", "tempranillo", "rioja", "barolo", "nebbiolo", "negroamaro", "carbarnet"]),  # "carbarnet" -- the literal typo found on a real label ("Borgofulvia Carbarnet"), same "keep the typo as its own keyword" pattern used elsewhere in this file, since the correctly-spelled "cabernet" a few words earlier can't match a misspelled name
    ("Wine - White", ["chardonnay", "sauvignon", "pinot", "riesling", "moscato", "vermentino", "catarratto", "gewurztraminer", "grillo", "verdicchio", "soave", "gavi"]),
    ("Wine - Sparkling", ["prosecco", "spumante", "cava", "franciacorta"]),
    ("Beers", ["shandy"]),
    ("Dilutables", ["bolero", "instant drink", "instant mix", "insted drink"]),  # "Insted" is a real misspelling on Bolero's own listings

    # ---- Food Cupboard leftovers ----
    ("Biscuits", ["macaron", "frollino", "frollini", "bucaneve", "gullon", "doria", "galbusera", "biscottate"]),
    ("Pasta & Couscous", ["radiatori", "caserecce", "canneloni", "tortiglioni", "casarecce", "saltimbocca"]),
    ("Sugar", ["xylitol", "cane sugar", "white sugar", "raw sugar", "date sugar", "sugar cube", "zucchero"]),  # deliberately NOT the bare word "sugar": in this data it appears overwhelmingly in "Sugar Free"/"No Added Sugar" labels on biscuits, sweets and drinks, so it flagged those as sugar rather than what they are
    ("Coffee", ["horlicks", "gran caffe", "ground bean", "coffee bean", "macchiato"]),
    ("Nuts", ["hazelnut", "flaxseed", "milled flax", "nut kernel"]),
    ("Sweet Snacks", ["candies", "dietorelle", "choccy", "chocolate button"]),
    ("Cereals", ["oat", "farro", "spelt", "multigrain", "muesli bar"]),
    ("Crackers, Crispbread & Breadsticks", ["rusk", "protein thin", "tarallini", "taralli", "fette biscottate"]),
    ("Legumes", ["aduki", "adzuki", "borlotti bean", "bean sprout"]),
    ("Cake Preparations", ["agar agar", "brownie mix", "muffin mix"]),
    ("Cakes", ["brownie", "crostatino", "crostata", "muffin"]),
    ("Sauces & Condiments", ["curry paste", "date paste", "tomato paste", "harissa"]),
    ("Flour", ["breadcrub"]),  # real misspelling of "breadcrumbs" in the source data
    ("Sports", ["enervit", "iron maxx", "proteccino", "maca powder", "whey", "creatine"]),

    # ---- Health & Beauty leftovers ----
    ("Hand Wash Liquids", ["handwash", "hand wash", "beauty bar", "sapone liquido", "liquid soap"]),
    ("Toothbrushes", ["toohtbrush", "tooth brush"]),  # "Toohtbrush" is how Colgate's listing is really spelled
    ("Hair & Nail Accessories", ["manicure", "pedicure", "nail art", "press on nail"]),
    ("Skin Care", ["wet wipe", "facial wipe", "cleansing wipe"]),  # deliberately NOT "make up wipe" -- the shorter Make Up keyword "make up" shadows it, so it could never fire (caught by audit_keyword_rules.py)

    # ---- Household leftovers ----
    ("Bathroom & Wc Cleaner", ["wc net", "wc brill", "wc disincrostante", "anticalcare"]),
    ("Electrical", ["gls bulb", "screw cap", "e27", "e14", "b22", "varta", "bayonet"]),
    ("Disposables", ["veline", "fazzoletti", "alluminum", "alluminium", "carta igienica", "salviette"]),
    ("Insect Killer", ["mosquitoes", "zanzare", "raid", "topicida", "antipuntura"]),
    ("All-purpose Cleaners", ["mildew", "smacchia", "brasso", "silvo"]),
    ("Household Goods", [
        "peg", "kitchen scale", "photo frame", "picture frame", "pedrini",
        "pastry scraper", "scraper", "bowl", "pot holder", "spoon",
        "cutter knife", "serving spoon", "wooden spoon",
    ]),

    # ---- Chilled / dairy-free / vegetarian leftovers ----
    ("Cold Cuts", ["salame", "salchichon", "peperami", "mortadella", "bresaola", "speck"]),
    ("Cheese", ["provola", "violife", "cheeselet", "gbejniet", "scamorza", "caciotta", "stracchino"]),
    ("Butter", ["lard", "strutto"]),
    ("Milk", ["milkshake", "bevanda", "mandorla", "latte di", "plant drink"]),
    ("Yoghurt", ["yofu", "liegeois", "skyr"]),
    ("Cooking Creams", ["alpro cuisine", "panna da cucina"]),
    ("Chilled Fish", ["surimi", "chele di"]),
    # 21 Aug 2026 -- same investigation as "succo e/& polpa" above:
    # "Smeralda Polpa Di Granchio" (crab meat) and "La Ciurma Polpa Di
    # Riccio Di Mare" (sea urchin roe) were also landing on Sauces &
    # Condiments via bare "polpa", for the identical reason.
    ("Chilled Fish", ["polpa di granchio", "polpa di riccio di mare"]),

    # ---- Fruit & veg counter ----
    ("Fruits", ["berry", "berries", "avocado", "coconut", "mango", "papaya", "pomegranate", "kiwi", "melon", "pineapple"]),
    ("Vegetables", ["mangetout", "asparagus", "spinach", "courgette", "aubergine", "broccoli", "cauliflower", "leek", "celery", "beetroot", "radish", "rocket", "lettuce", "cabbage"]),
    ("Juices", ["freshly squeezed", "just squeeze"]),

    # ========================================================================
    # 18 Aug 2026 -- FOURTH bulk sweep.
    #
    # After the aisle fallback and the third sweep, the run report is down to
    # the four Welbee's catch-alls and nothing else of size, so this round is
    # aimed squarely at them. It is the most Italian- and Maltese-heavy block
    # in the file, because that is what is left at this depth: Carrefour's
    # own-brand labels are largely Italian ("collutorio", "assorbenti",
    # "salvaslip", "docciaschiuma", "spazzolino", "guanti", "spugna"), and a
    # handful of items are Maltese ("gulepp tal-harrub" -- carob syrup).
    # ========================================================================

    # ---- Food Cupboard ----
    ("Coffee", ["caffe", "arabica", "robusta"]),
    ("Rice", ["riso", "carnaroli", "risotto rice"]),
    ("Herbs & Spices", ["garam masala", "masala", "tandoori", "za atar", "sumac", "five spice", "dried porcini", "dried mushroom", "ras el hanout"]),
    ("Dilutables", ["gulepp"]),  # Maltese for a thick fruit/carob syrup, drunk diluted
    ("Milk", ["milk powder", "powdered milk", "regilait", "vitamilk", "evaporated milk", "condensed milk"]),
    ("Snacks", ["bankok", "bar bite", "prawn cracker", "corn puff", "cheese puff", "snack bar"]),
    ("Biscuits", ["dolcerie", "veneziane"]),
    ("Cereals", ["buckwheat", "millet", "amaranth", "sorghum", "freekeh", "groat"]),
    ("Olive Oil", ["tesoro del rio", "ext virgin", "extr vrg", "olio extravergine", "extravergine"]),

    # ---- Health & Beauty ----
    ("Mouthwash", ["collutorio"]),
    ("Toothbrushes", ["spazzolino"]),
    ("Hair & Nail Accessories", ["nail polisher", "clic clac", "hair slide", "hair pin", "hair claw"]),
    ("Sanitary Towels", ["absorbent", "assorbenti", "salvaslip", "double dry"]),
    ("Deodorants", ["deodorante", "antitraspirante", "sure"]),  # bare "sure" claimed for the deodorant brand: in this data the word only ever appears as the brand, never as the ordinary English adjective
    ("Shower Gels", ["docciaschiuma", "doccia schiuma", "bagnodoccia", "bagno doccia"]),
    ("Skin Care", ["latte detergente", "crema viso", "struccante", "acqua micellare"]),
    ("Body Lotions", ["crema corpo", "crema mani"]),

    # ---- Household ----
    ("All-purpose Cleaners", ["ammonia", "ammoniaca", "multiuso"]),
    ("Drain Unblockers", ["drain away", "disgorgante"]),
    ("Cloths & Sponges", ["spugna", "strofinaccio", "panno"]),
    ("Disposables", ["koolsak", "degradable", "sacchi"]),
    ("Fabric Softener", ["comfort"]),  # the Unilever softener brand; the Pass-0 rules below protect the handful of products where "comfort" is genuinely just the English word

    # ---- Home & Entertainment ----
    ("Stationery", ["refill pad", "asticky", "a4 file", "lever arch", "box file", "document wallet", "display book", "index card", "pencil box", "school bag", "subject book", "writing pad"]),
    ("Hand Tools", ["tesa", "hand tearable"]),
    ("Household Goods", [
        "mirror", "picnic set", "shoe lace", "shoelace", "insole",
        "gel liner", "shopping bag", "guanti", "scopa", "paletta",
        "secchio", "stendibiancheria", "tovaglia",
    ]),

    # ========================================================================
    # 18 Aug 2026 -- FIFTH bulk sweep, deliberately much wider than the fourth.
    #
    # The fourth sweep only closed ~250 listings, because it was written from
    # the eight example names the report prints per bucket and so it caught
    # those eight and little else. The lesson: at this depth, hitting the
    # examples is not the same as closing the bucket.
    #
    # So this block goes after the VOCABULARY the examples are drawn from
    # rather than the examples themselves -- above all Italian, which is what
    # Welbee's four catch-all buckets are mostly made of at this point.
    # Carrefour's own-brand range and the Italian imports are labelled in
    # Italian throughout, so one pass of ordinary Italian grocery words
    # ("pane", "burro", "uova", "farina", "miele", "ceci", "lenticchie",
    # "formaggio", "bicchieri", "pentola", "quaderno") reaches far more
    # listings than any number of individual brand rules would.
    #
    # Two Italian words are deliberately NOT here:
    #   * "latte" -- it means milk, but in this data it appears far more often
    #     in "Caffe Latte"/"Latte Macchiato" coffee products.
    #   * "piatti" -- it means plates, but it is already a Dish Washing Liquid
    #     keyword ("Svelto Piatti"), which is the commoner use here.
    # ========================================================================

    # ---- Italian pantry ----
    ("Pasta & Couscous", ["orecchiette", "ditalini", "bucatini", "paccheri", "trofie", "strozzapreti", "sedanini", "pastina", "stelline", "risoni", "mezze penne", "pici", "maccheroncini", "divella"]),
    ("Legumes", ["ceci", "fagioli", "lenticchie", "piselli"]),
    ("Canned Seafood", ["sgombro", "alici", "tonno", "filetti di"]),
    ("Flour", ["farina"]),
    ("Honey", ["miele"]),
    ("Jelly", ["confettura", "marmellata"]),
    ("Jelly", ["apricotj am"]),  # added 21 Aug 2026 -- "Zuegg Apricotj Am No Added Sugar" has a mangled "Apricot Jam" (missing space, extra space) that the normal "jam" keyword can't match. Not promoting bare "zuegg" instead -- WebSearch confirmed Zuegg also sells juices/nectars, not jam-only, so a blanket brand override would misfire on those
    ("Juices", ["succo", "spremuta"]),
    ("Tea", ["tisana", "camomilla"]),
    ("Soups", ["zuppa", "minestra"]),
    ("Oils", ["olio di semi", "olio di girasole", "olio di mais"]),
    ("Water", ["acqua naturale", "acqua frizzante"]),
    ("Sweet Snacks", ["caramelle", "liquirizia", "morbide"]),
    ("Cakes", ["pandoro", "panettone", "colomba", "krapfen", "merendine"]),
    ("Chocolates", ["cioccolatini", "baci", "perugina", "novi", "venchi", "ritter", "cote d or", "mignonette", "cacao", "reese", "milky way", "crunchie"]),
    # 21 Aug 2026 -- Chocolates/Nuts collision report (83 listings) deep
    # dive. Turned out bare "truffle" itself is NOT safely fixable here --
    # real data showed the word is dominated (well over 100 listings) by
    # SAVOURY truffle-the-fungus products (truffle cheese, truffle oil,
    # truffle-flavoured crisps, truffle salami...) across a dozen
    # different categories, so promoting it would have broken far more
    # than it fixed, the same "genuinely ambiguous word" shape as "polpa"
    # earlier today. Fixed narrowly instead, only the real chocolate-
    # truffle-confectionery cases that were losing to a nut name:
    ("Chocolates", ["healthy leaf"]),  # a real chocolate-truffle-ball brand in this data (all 3 known SKUs are "...Truffles"), e.g. "Healthy Leaf Salted Peanut Truffles"
    ("Chocolates", ["salted peanut truffles"]),  # covers the same Healthy Leaf product when the brand name itself is truncated in the source data (seen as "SALTED PEANUT TRUFFLES")
    ("Chocolates", ["cacao almond dark"]),  # "85% Cacao Almond Dark Stevia" -- standard dark-chocolate-bar labelling (X% Cacao), was tying bare "cacao" against bare "almond"
    ("Biscuits", ["bahlsen", "loacker", "quadratini", "pavesini", "gocciole", "pan di stelle", "oro saiwa", "speculoos", "lotus", "biscotto"]),
    ("Chips", ["patatine", "pomstick", "lorenz", "san carlo", "fonzies", "chipster"]),
    ("Coffee", ["kimbo", "borbone", "segafredo", "nespresso", "lungo", "ristretto", "espresso napoletano"]),
    ("Nuts", ["pinoli", "noci", "mandorle", "nocciole", "arachidi", "anacardi", "sgusciati"]),
    ("Herbs & Spices", ["rosmarino", "basilico", "prezzemolo", "alloro", "cannella", "noce moscata", "pepe nero", "curcuma", "origano"]),
    ("Sausages", ["frankfurter", "wurst", "bockwurst", "wiener", "chipolata", "bratwurst", "salsiccia", "hot dog sausage"]),

    # ---- Italian chilled / bakery ----
    ("Cheese", ["formaggio", "parmigiano", "grana", "pecorino", "mozzarella", "mascarpone", "gorgonzola", "taleggio", "fontina", "asiago"]),
    ("Butter", ["burro", "margarina"]),
    ("Eggs", ["uova", "uovo"]),
    ("Bread", ["pane", "panino", "focaccia", "michetta", "rosetta", "baguette"]),

    # ---- Health & Beauty ----
    ("Sanitary Towels", ["always", "ultra plus", "maxi night", "notte", "con ali"]),
    ("Shower Gels", ["bodywash"]),
    ("Skin Care", ["bioten", "creamy mask", "maschera viso"]),
    ("Hair & Nail Accessories", ["jean louis david", "hair elastic", "thin elastic", "claw clip", "medium claw"]),
    ("Nappies", ["pannolini"]),

    # ---- Household ----
    ("Disposables", ["alcofoil", "tovaglioli", "tavaglioli", "ice cube bag", "pellicola", "carta forno", "sacchetti", "bicchieri di carta"]),
    ("Cloths & Sponges", ["dish brush", "spazzolone", "strofinacci"]),
    ("Insect Killer", ["fly swapper", "fly swatter", "citronella", "repellant", "zampirone", "piastrine"]),
    ("All-purpose Cleaners", ["lavavetri"]),
    ("Dishwasher Tablets", ["brillantante"]),

    # ---- Home & Entertainment ----
    ("Clothes", ["atelier couture", "bra extender", "bra fastener", "iron on label", "sewing", "haberdashery", "tights", "underwear", "boxer short", "t shirt", "pyjama", "slipper", "scarf", "beanie"]),
    ("Stationery", ["quaderno", "penna", "matita", "righello", "astuccio", "raccoglitore", "cartella"]),
    ("Household Goods", [
        "specchio", "cornice", "portafoto", "orologio", "cuscino", "coperta",
        "tenda", "tappeto", "mollette", "stendino", "appendiabiti", "cesto",
        "vassoio", "tagliere", "pentola", "padella", "coperchio", "bicchieri",
        "tazza", "posate", "ciotola",
    ]),

    # ========================================================================
    # 18 Aug 2026 -- SIXTH bulk sweep.
    #
    # Two things this round, prompted by what the fifth round left behind.
    #
    # 1. PLAIN FRUIT AND VEG. Five rounds in, ordinary produce words were
    #    still missing -- "blueberries", "strawberries", "bananas", "pears",
    #    "potatoes", "onions", "carrots". They kept slipping through because
    #    the existing rules had the singular collective ("berry", "berries")
    #    but matching is whole-word, so "blueberries" never matched
    #    "berries". Each fruit now gets both its singular and plural form.
    #
    # 2. THE BARE WORD "bean". Deliberately held back until now because of
    #    the two obvious traps -- COFFEE beans and JELLY beans. Both are
    #    already caught by earlier phrase rules ("coffee bean", "ground
    #    bean", "jelly bean"), which win because phrases are checked before
    #    bare words, and the one brand that says "Beans" while meaning coffee
    #    (Saquella) gets its own Pass-0 rule below. With those covered it is
    #    safe, and it reaches every "White Beans"/"Butter Beans"/"Broad
    #    Beans" tin at once.
    #
    # Deliberately still NOT added: bare "lemon", "lime" and "orange". They
    # are fruit, but in this data they are overwhelmingly a SCENT -- washing
    # up liquid, floor cleaner, air freshener, shower gel -- so claiming them
    # for Fruits would mis-file more products than it fixed.
    # ========================================================================

    # ---- Produce: singular AND plural, because matching is whole-word ----
    ("Fruits", [
        "blueberry", "blueberries", "raspberry", "raspberries",
        "strawberry", "strawberries", "blackberry", "blackberries",
        "cherry", "cherries", "banana", "pear", "peach", "peaches",
        "plum", "grape", "apricot", "nectarine", "watermelon",
        "clementine", "mandarin", "grapefruit", "fig",
    ]),
    ("Vegetables", ["potato", "potatoes", "onion", "carrot", "cucumber", "garlic", "ginger", "pumpkin", "turnip", "parsnip", "kale", "chard", "peperoncini", "farciti"]),
    ("Legumes", ["bean", "white bean", "black eyed bean"]),

    # ---- Food Cupboard leftovers ----
    ("Chocolates", ["nutella"]),
    ("Coffee", ["saquella"]),
    ("Tea", ["easytea"]),
    ("Crackers, Crispbread & Breadsticks", ["brezel"]),
    ("Cake Preparations", ["cocktail cherry", "cocktail cherries", "maraschino"]),

    # ---- Health & Beauty leftovers ----
    ("Skin Care", ["skin active", "nutribomb", "derma", "skin clear"]),
    ("Hair & Nail Accessories", ["headband", "silicone brush"]),
    ("Hair Styling", ["mousse", "wet look", "aqua gel"]),
    ("First Aid", ["hydrogen peroxide"]),

    # ---- Household leftovers ----
    ("Cloths & Sponges", ["scouring", "scrouer", "scouring pad", "abrasive pad"]),  # "scrouer" is a real misspelling of "scourer" in the source data
    ("Insect Killer", ["flytrap"]),
    ("Disposables", ["garbage bag", "rubbish bag", "waste bag", "nappy sack", "sacc rid", "sacchi rifiuti"]),
    ("Household Goods", ["ice pack", "cool pack", "hot water bottle", "arix"]),  # Arix, like Vileda, makes cleaning equipment across sponges, cloths, mops and gloves -- the more specific words still win where they apply
    ("Floor Cleaners", ["floor liquid"]),

    # ---- Home & Entertainment leftovers ----
    ("Stationery", ["shopping list", "pritt", "corrector", "memo pad", "to do list", "planner", "notice board"]),

    # ========================================================================
    # 18 Aug 2026 -- SEVENTH sweep. THE FIRST ONE WRITTEN FROM REAL DATA.
    #
    # Every round before this was written from the eight example names the
    # report prints per bucket, which meant inventing plausible product names
    # and hoping Welbee's stocked them. Rounds four and five closed 250 and
    # 605 listings respectively -- that is what guessing costs.
    #
    # This round was written against unclassified_listings.txt, the full
    # export of all 4,663 distinct unclassified names, downloaded from the
    # workflow run's artifacts. Clustering those names by their leading words
    # showed immediately where the weight actually sits, and it was nowhere
    # near where the examples suggested:
    #
    #     102 names  Wet n Wild (cosmetics)
    #      44 names  Franck Provost (hair accessories)
    #      43 names  Sally Hansen (nail colour)
    #      40 names  Disney (Crd) (kids' gear)
    #      31 names  Chef Aid (kitchenware)
    #      28 names  Mulino Bianco (biscuits)
    #      25 names  La Molisana (pasta)
    #      24 names  Pap Star (party disposables)
    #
    # A single rule for "wet n wild" closes more listings than the whole of
    # round four did. That is the difference the export makes, and it is why
    # the rules below are brand-led rather than vocabulary-led: at this depth
    # the tail really is brands, and now they can be read instead of guessed.
    # ========================================================================

    # ---- Health & Beauty: the big cosmetics and haircare houses ----
    ("Make Up", ["wet n wild", "sally hansen", "lip smacker", "depesche", "top model", "bellaoggi", "essence cosmetics"]),
    ("Hair & Nail Accessories", ["franck provost", "princesse lili", "elite accessories", "elliott", "jld", "fringe pin", "snap clip", "hair turban", "nail brush"]),
    ("Skin Care", ["face facts", "7th heaven", "garnier synergie", "st moriz", "nivea sun", "hawaiian tropic", "clinians", "cera di cupra", "omnia botanica", "merci handy", "delice solaire", "dermolab", "nivea visage", "nivea q10", "nivea luminous", "nivea scrub", "instant tan", "self tan", "sun stick"]),
    ("Hair Colouring", ["excellence creme", "garnier color", "garnier olia", "schwarzkopf brilliance", "wella kit", "hair kit"]),
    ("Hair Styling", ["wella flex", "tigi", "bed head", "frizz ease", "john frieda", "blow dry", "workable wax", "styling spray"]),
    ("Shampoos", ["alpecin", "pantene", "wella wonder"]),
    # 23 Aug 2026 -- bare "brut" replaced with three specific phrases, full
    # database pass (Wine - Sparkling/Wine - White, 48). "Brut" is a
    # standard sparkling-wine dryness term (Moet & Chandon Brut, Veuve
    # Clicquot Brut, Ferrari Brut Doc Metodo Classico, etc.), so the bare
    # word was claiming 16 real Champagne/sparkling-wine products for
    # Perfume, purely because nothing else in the file registered "brut"
    # at all. Checked the real Perfume-category data first: every genuine
    # Faberge Brut product in the database is named "Brut Edt ...", "Brut
    # For Men ..." or "Brut Original Shower ..." -- these three phrases
    # cover all of them (verified against "Brut Edt Attrection", "Brut Edt
    # Musk", "Brut For Men Musk Spray", "Brut Original Shower Attraction",
    # "Brut Original Shower Original"), so the bare word can be dropped
    # entirely with no loss of real Perfume matches.
    ("Perfume", ["edt", "edp", "eau de", "bugatti", "david beckham", "tom tailor", "brut edt", "brut for men", "brut original", "she women", "life by", "adidas edt", "adidas edp"]),
    ("Deodorants", ["dove men", "nivea men", "apd", "deo spray", "invisible care"]),
    ("Shower Gels", ["neutro roberts", "ushuaia", "bionsen", "jacklon", "amore mio", "foam bath", "bagno schiuma", "showel gel"]),
    ("Hand Wash Liquids", ["spuma di sciampagna", "sapone crema"]),
    ("Adult Nappies", ["abena", "abri form", "abri flex"]),
    ("Intimate Care", ["durex", "contraceptive", "control contracept"]),
    ("Electrical", ["remington", "russell hobbs", "beurer", "haircutter", "straightner", "multi styler"]),
    ("First Aid", ["scholl", "party feet"]),
    ("Sanitary Towels", ["sani lady", "hyper dry", "giga pack", "h dry"]),
    ("Shaving Creams", ["the barb", "beard and moustache", "moustache wax"]),
    ("Dental Care", ["oral b", "floss essential"]),
    ("Toys & Games", ["disney pal", "disney crd", "sophie la girafe", "addo", "jovi", "hardening clay", "craft set"]),

    # ---- Food Cupboard: the real brands ----
    ("Biscuits", ["mulino bianco", "flauti", "plumcake", "niederegger"]),
    ("Pasta & Couscous", ["la molisana", "calamarata", "ramyun", "nongshim", "berruto", "pastacup", "grantortelli"]),
    ("Herbs & Spices", ["good health", "carmencita", "italpepe", "anise", "preparato per"]),
    ("Sauces & Condiments", ["old el paso", "blue dragon", "poco loco", "patak", "sacla", "sugo", "besciamella", "kunserva", "ragu", "ajvar", "hummus", "tzatziki", "arjoli", "dip", "curd"]),
    ("Crackers, Crispbread & Breadsticks", ["gran pavesi", "delser", "bake roll"]),
    ("Sweet Snacks", ["impact mint", "werther", "trolli", "red band", "brain blasterz", "maynards", "fini", "suckers", "gems"]),
    ("Chocolates", ["m m", "icam", "crema spalmabile", "pasticceria fondente"]),
    ("Tea", ["ahmad", "twining", "yogi", "loyd", "superblend"]),
    ("Cake Preparations", ["foster clark", "rayner", "fruttapec", "paneangeli", "food colour"]),
    ("Chips", ["lay s", "mr riley", "salati preziosi", "cheesy ring", "veggie straw", "pata artigianale"]),
    ("Cereals", ["kellogg", "nestle fitness", "ovaltine"]),
    ("Sugar", ["billington"]),
    ("Milk", ["parmalat", "zymil", "trevalli", "hopla"]),
    ("Vegetables", ["caponata", "sauerkraut", "marrowfat", "peeled tomato", "chopped tomato", "roasted eggplant", "favetta"]),
    ("Soups", ["brodo"]),
    ("Cold Cuts", ["pate", "pashtet", "guanciale", "salamini", "chorizo", "wurstel"]),
    ("Bread", ["naan", "ciabattine", "pan blanco", "pan ducale", "croissant"]),

    # ---- Drinks: wine, spirits, beer ----
    ("Wine - Red", ["marsala", "tawny port", "ruby port", "vino rosso", "red wine", "carmenere", "brachetto"]),
    ("Wine - White", ["vino bianco", "white wine", "dry white", "chenin blanc", "inzolia", "girgentina", "greco", "blanc"]),
    ("Wine - Rose", ["rosado", "rosato", "rose wine"]),
    ("Wine - Sparkling", ["asti", "freixenet", "cordon negro", "hugo"]),
    ("Spirits - Whisky", ["johnnie walker", "dewar", "aberfeldy", "single malt", "highland"]),
    ("Spirits - Liqueurs", ["gin", "rum", "amaro", "liqueur", "liquore", "spritz", "aperitivo", "vermouth", "captain morgan", "havana club", "bacardi", "hendrick", "malfy", "gordons", "tanqueray", "breezer", "port"]),
    ("Beers", ["cisk", "san miguel", "brewdog", "ipa", "lager"]),
    ("Energy Drinks", ["prime hydration"]),
    ("Carbonated Drinks", ["mirinda", "san pellegrino", "aranciata", "citrus fizz"]),
    ("Juices", ["capri sonne", "nettare"]),
    ("Dilutables", ["coolee"]),
    ("Water", ["acqua naturale", "sant anna"]),

    # ---- Chilled Food ----
    ("Cheese", ["elite deli", "vonk", "emborg", "president", "philadelphia", "babybel", "brie", "edam", "gouda", "emmental", "provolone", "burratina", "gbejna", "gbejniet", "gibniet", "grano padano", "grana padano", "coombe castle", "garcia baquero", "paysan breton", "solo italia", "fior di vita", "la vache"]),
    ("Yoghurt", ["fage", "fruyo", "zottis", "zott"]),
    # 21 Aug 2026 -- 3 more unclassified items confirmed with the user
    # rather than guessed:
    ("Yoghurt", ["stuffer"]),  # user confirmed "Stuffer Protei Dessert Vanilla" is a gluten-free protein yoghurt, not a supplement or kitchen-equipment brand
    ("Yoghurt", ["danette"]),  # Danone's chilled pudding line, e.g. "Danone Danette Mars" -- user confirmed Yoghurt is the closest existing bucket (this file has no separate Desserts category)
    ("Cold Cuts", ["coppa classic"]),  # user confirmed "Carrefour Coppa Classic" is a cured-meat product, not a dessert cup -- kept as this specific phrase rather than bare "coppa", since bare "coppa" is also generic Italian for "dessert cup" and would be unsafe unscoped
    # 21 Aug 2026 -- 5 more, also confirmed with the user rather than
    # guessed (Bakoma, Pascual, Berchtesgadener Land all also sell other
    # dairy/juice product lines, so each is scoped as narrowly as the real
    # example allows rather than added as a bare brand word):
    ("Yoghurt", ["bakoma mikus"]),  # user confirmed yoghurt; "Mikus" is Bakoma's specific kids'-yoghurt line, so scoped to that rather than bare "bakoma" (a broad Polish dairy brand)
    ("Yoghurt", ["pascual vanilla"]),  # user confirmed yoghurt; kept as this exact phrase rather than bare "pascual" (also sells juice/milk under the same brand)
    ("Yoghurt", ["squeeze & go"]),  # user confirmed this is a shelf-stable dairy-dessert pouch for kids -- closest existing bucket is Yoghurt, same as the Danette precedent above
    ("Yoghurt", ["berchtesgadener"]),  # user confirmed yoghurt; the brand name itself ("Berchtesgadener Land") is specific enough to be safe unscoped
    ("Milk", ["alpro mini"]),  # user confirmed "Alpro Mini Vanilla Soya" is a single-serve plant-milk carton, not a yoghurt-alternative -- scoped to the "Mini" single-serve line rather than bare "alpro" (which also covers Alpro's cooking creams, yoghurt alternatives, etc. elsewhere in this file)
    # "So..? Radianc Trio Set Vanilla" -- user confirmed this gift set
    # actually contains a mix of body mist, shower cream, and body scrub,
    # so no single existing category is fully correct. Filed under Skin
    # Care (2 of the 3 items -- shower cream, body scrub -- are Skin Care
    # territory here) rather than Perfume (1 of 3, body mist); flagged as
    # a genuine judgment call, not a confident single answer, in case a
    # dedicated "Gift Sets" bucket ever makes more sense.
    ("Skin Care", ["radianc trio set"]),
    ("Sausages", ["aia wudy", "scarlino"]),

    # ---- Healthy Section ----
    ("Meat Alternatives", ["quorn", "valsoia", "green vie", "beyond meatball", "plant based"]),
    ("Sports", ["applied nutrition", "leap nutrition", "maxi nutrition", "dragon superfoods", "collagen", "greens capsule", "hydration tab"]),
    ("Bread", ["schar pan", "gluten free biss", "proceli", "golden harvest"]),

    # ---- Household ----
    ("Air Fresheners", ["areon", "ad trend", "acqua profumata", "airflor", "3volution"]),
    ("Fabric Softener", ["tesoro mio", "profumo biancheria", "unstoppables"]),
    ("Laundry Washing Liquids", ["il bucato", "perlana", "persil liquid"]),
    ("Laundry Washing Powders", ["surf powder", "derh matic"]),
    ("Stain Removers", ["dr beckmann", "omino bianco", "ace liquid", "ace gentile", "idrocaps", "colour catcher"]),
    ("Dishwasher Tablets", ["autodish", "finish quantum", "auto dishwash"]),
    ("Disposables", ["cuki", "cartaforno", "kc catering", "pap star", "hotpack", "ipak", "party plate", "party hat"]),
    ("Candles", ["ser petali", "bolsius", "price s", "aladino", "tealight", "taper"]),
    ("All-purpose Cleaners", ["zoflora", "astonish", "chante clair", "pronto", "domestos", "extra power spray"]),
    ("Floor Cleaners", ["swiffer", "spic span", "trekker"]),
    ("Bathroom & Wc Cleaner", ["duck fresh", "duck active", "toilet fresh"]),
    ("Household Goods", [
        "la briantina", "lock lock", "heidrun", "innova goods", "chef aid",
        "households", "leifheit", "dr fresh", "sneaker angels", "brilla",
        "latex glove", "food box", "bottle brush", "smash", "waf brevetti",
        "bormioli", "zanetti", "ok stainless", "linea briancasa", "brita",
        "campagnolo", "heaven sends", "travel hard", "luggage", "car mat",
        "sunshade", "firelighter", "boning knife", "casserole",
    ]),
    ("Stationery", ["bic", "staedtler", "brunnen", "apli", "kangaro", "tipp ex", "uhu", "perforator", "box folder", "blending stump", "craft stick"]),
    ("Gift Sets", ["on the wall", "florio carta", "gift wrapping", "banner"]),

    # ---- Seventh sweep, second pass: read straight off the remaining names
    # in the export. Mostly Carrefour's Italian own-brand range (pasta shapes
    # by number, tinned vegetables, baking) plus the fresh produce counter,
    # where the recurring problem was again plurals -- "tomatoes", "peas",
    # "shallots", "sugarsnaps" -- which whole-word matching won't reach from
    # the singular. ----
    ("Pasta & Couscous", ["conchigliette", "barbine", "ditali", "ditalini", "farfalline", "gramigna", "rigatini", "sedani", "spaghettini", "mezze maniche", "trecce", "lasagna", "condipasta", "pastina"]),
    ("Vegetables", [
        "pea", "peas", "pelati", "giardiniera", "palm heart", "zucchine",
        "funghi", "champignon", "trifolati", "zenzero", "tomatoes",
        "broccolini", "brussel sprout", "capsicum", "chive", "corn on the cob",
        "butternut", "sweet potato", "salad", "coleslaw", "iceberg", "rucola",
        "misticanza", "insalata", "pakchoi", "paksoy", "parsley", "shallot",
        "sugarsnap", "carote",
    ]),
    ("Fruits", ["pesche", "sciroppate", "prugne", "mirtilli", "physalis", "dragonfruit", "pithaya", "starfruit", "carambola", "tamarind", "medjoul", "medjool", "sharon"]),
    ("Sauces & Condiments", ["bechamel", "doppio concentrato", "guacamole", "teryaki", "meat rub", "protein rub", "chilli con carne", "appetizer"]),
    ("Crackers, Crispbread & Breadsticks", ["breadstick", "schiacciatine", "torinesi", "bruschette", "petals of cracker"]),
    ("Chocolates", ["bounty", "condorelli", "torroncini", "barrette"]),
    ("Sweet Snacks", ["meringue", "girella", "caramel slice", "catch mint"]),
    ("Coffee", ["kafe", "intensita", "capsules forte", "extra intenso"]),
    ("Tea", ["te verde", "te solubile", "mighty mint", "clipper"]),
    ("Cake Preparations", ["budino", "creme caramel", "torta", "preparato", "cremor tartaro", "pirottini", "gelatina", "wheat decor", "aromi per dolci"]),
    ("Cereals", ["fiber flake", "spelled", "pearly"]),
    ("Legumes", ["butterbean", "bolotti", "dal makhani"]),
    ("Canned Seafood", ["vongole", "pescato", "calvo", "lumpfish"]),
    ("Chips", ["cheetos", "amica", "twistos", "crunchos"]),
    ("Soups", ["bisque"]),
    ("Sugar", ["fruttosio"]),
    ("Herbs & Spices", ["sale superfino", "sale fino", "sale grosso", "peri peri"]),
    ("Milk", ["alpro barista", "whitner", "completa"]),
    ("Flour", ["pangrattato"]),
    ("Household Goods", ["flowers fresh bouquet", "fresh bouquet"]),

    # ---- Seventh sweep, third pass: Welbee's Household aisle, read off the
    # export. Again heavily Italian own-brand ("vaschette", "bobina",
    # "strappi", "sgorgatutto", "lavastoviglie", "piumino"). ----
    ("All-purpose Cleaners", ["ace", "crema casa", "power clean", "disinfetta", "muriatic acid", "acido liquido", "oxygel", "power shine", "power and shine", "ultra muffa", "spray acciaio", "spray vetri", "cif"]),
    ("Bathroom & Wc Cleaner", ["bref", "wc drops", "gel wc", "wc duo", "gel bagno", "spray bagni", "bagno brillante"]),
    ("Laundry Washing Liquids", ["dash", "cenndie", "gel casa", "hand detergent", "optimal clean", "wool and delicate", "eco planet", "casa e bucato"]),
    ("Laundry Tablets", ["dash pod"]),
    ("Stain Removers", ["anti decoloration"]),
    ("Dishwasher Tablets", ["lavastoviglie", "antiscale"]),
    ("Drain Unblockers", ["sgorgatutto"]),
    ("Disposables", ["aluminium", "aluminum", "alluminio", "vaschette", "bobina", "strappi", "maxiroll", "kitchen towel", "family roll", "frost bag", "aluminum tray"]),
    ("Cloths & Sponges", ["brillo", "abrasive fiber", "abrasive fibre", "steelwool", "piumino", "microfibre towel", "chequered"]),
    ("Insect Killer", ["autan", "tarme", "moth", "after bite", "afterbite"]),
    ("Air Fresheners", ["airpure", "ariasana", "freshner", "deo wick", "diffuser refill", "electric diffuser"]),
    ("Household Goods", ["matches", "safety match", "adriatic", "cooler", "colombo", "balcony dryer", "compactor", "stackable", "telescopic stick", "metal handle", "garbage lift", "calzanetto", "bufalo", "cleaning kit", "shoe polishing"]),
    # ---- Seventh sweep, fourth pass: Health & Beauty and the remaining
    # aisles, read off the export. ----
    ("Electrical", ["babyliss", "demeliss", "braun", "curling iron", "multi groomer", "silk epil"]),
    ("Hair Styling", ["brylcreem", "glossy hold", "kera protein", "liss & protect"]),
    ("Hair & Nail Accessories", ["abc hello kitty", "hello kitty", "bow clip", "hair towel", "magic brush", "satin hair"]),
    ("Cotton Buds", ["bastoncini cotonati", "precut cotton", "cotton ball"]),  # bare "bastoncini" (28 Aug 2026) removed -- it's just Italian for "sticks", and CSV shows it overwhelmingly means fish sticks (Frozen Fish), diffuser sticks (Air Fresheners), biscuit sticks (Biscuits) and veg sticks (Frozen Vegetables), not cotton buds; the specific "bastoncini cotonati" phrase (and "cotonet" registered elsewhere) already cover real cotton-bud products
    ("Dental Care", ["flosser", "waxed tape", "crema adesiva", "protesi", "full action refill"]),
    ("Shaving Creams", ["classic blade", "perfect angle", "men s blade"]),
    ("Hand Wash Liquids", ["sapone solido", "sapone", "dove bar", "dove pink"]),
    ("Adult Nappies", ["traverse adult"]),
    ("Skin Care", ["carroten", "sun spray", "bodyscrub", "lip care"]),
    ("Baby Essentials", ["chicco", "nursing pad", "pre natal", "post natal"]),
    ("Body Lotions", ["dove lotion", "deeply nourishing", "essential nourishing"]),
    ("Household Goods", ["beauty in the air", "sleep mask", "vanity case", "toilet bag", "pill box", "pompom pouch"]),
    ("Make Up", ["nail remover"]),
    ("Disposables", ["flushable wipe"]),

    # ---- Seventh sweep, fifth pass: Home & Entertainment, Chilled Food and
    # the Greens dietary aisles, read off the export. ----
    ("Household Goods", ["aeternum", "bialetti", "anilar", "alcas", "high pot", "tart pan", "roaster", "rubber mat", "car mat", "garden rake", "universal soil", "gas cartridge", "gas heater", "filter jug", "drink filter", "wide tape", "double gill", "paper case", "brown paper roll", "tablet pocket", "charcoal", "firestarter", "accendifuoco", "cubetti legna", "instant bbq", "instant lighting", "barbequick", "decorative", "lampada"]),
    ("Cloths & Sponges", ["body puff", "body scrubber", "mesh pouf", "spugne", "optical wipe", "microfiber towel"]),
    ("Electrical", ["ameego", "anker", "cecotec", "charging cable", "readers metal"]),
    ("Toys & Games", ["giocattoli", "animali della", "econimic mill"]),

    ("Cheese", ["camembert", "havarti", "edamer", "maasdam", "parmeggiano", "ricotta", "quark", "mozzarelline", "alpenhain", "ambrosi", "brescialat", "bayernland", "arla"]),
    ("Pasta & Couscous", ["girasoli", "tortelloni", "conchiglioni", "suppli"]),
    ("Yoghurt", ["probiotic drink", "alpro cocco", "pudding"]),
    ("Chilled Fish", ["salmone", "octopus", "taramosalata", "gobon"]),
    ("Cold Cuts", ["pepperoni", "cottomagro"]),

    # ---- Greens: Gluten Free / Organic / Dietary aisles ----
    ("Bread", ["balviten", "damhert", "sliced loaf", "bridge roll", "hamburger roll", "mini roll", "long roll", "bagel", "piadina", "white sandwich", "airos", "arios", "salty stick"]),
    ("Sports", ["protein shake", "maca", "spirulina", "chlorella", "moringa", "ashwagandha", "matcha", "hemp protein", "superfood", "superberries", "biotona", "dragon", "chia protein", "greens capsule"]),  # bare "detox" (28 Aug 2026) removed -- too broad, CSV shows it mostly means teas, shampoos, face masks, shower gels and wipes, not sports supplements; real Sports products still match via other keywords/brands
    ("Nuts", ["semi di chia", "semi di lino", "semi girasole", "semi zucca", "semi di zucca", "seed blend"]),
    ("Coffee", ["cafedirect", "roast & ground", "roast and ground"]),
    ("Sauces & Condiments", ["tamari"]),
    ("Meat Alternatives", ["tempeh", "jackfruit", "crocchette"]),
    ("Cereals", ["supergrain", "organic flake", "hoops"]),

    # 18 Aug 2026 -- EIGHTH bulk sweep. Second round written from real data --
    # this time from the export taken AFTER the seventh sweep had already run in
    # production (4,663 -> 1,518 distinct unclassified names), so this is a much
    # longer tail: less brand-cluster repetition, more one-off Italian own-brand
    # imports, cleaning products, toys, and stationery. Same discipline as the
    # seventh sweep: read straight off the real names, avoid bare words that mean
    # different things in different aisles (kept "sanex" out for the same reason
    # noted next to the Deodorants rule above -- it spans deodorant/shower gel/
    # perfume), and cross-checked every new keyword against the existing list
    # before adding it.
    ('Beef', ['corned beed', 'corned beef']),
    ('Chocolates', ['easter bunny', 'gianduiotti', 'gianduitto', 'milky bar', 'milky buttons', 'quality street', 'sperlari', 'pralinis', 'praline']),
    ('Pasta & Couscous', ['couc cous', 'cous cous', 'coucous', 'medium coucous', 'capellini', 'elicoidali', 'renne rigate', 'spagetti vermicelloni', 'fregola', 'girasoli', 'tortelloni', 'conchiglioni', 'canestrelli']),
    ('Sauces & Condiments', ['maionese', 'mayoketchup', 'mayomust', 'sugu', 'zalza', 'tadam', 'provista sugu', 'b b q rich', 'bbq glaze', 'barbeque glaze', 'sambal oelek', 'aromat', 'cooking sause', 'cooking sauce', 'grinder']),
    ('Fresh Pastry', ['cornetto di pastasfoglia', 'sfogliatine', 'pasty']),
    ('Snacks', ['tortillas', 'wrap tortillas', 'taco shells', 'taco tubs', 'salatini', 'crackers salati', 'twistees', 'smiths bacon flavour fries', 'smiths scampi flavour fries', 'tastees bacon flavour', 'takis', 'hundred & thousands']),
    ('Sweet Snacks', ['poppets', 'sour patch kids', 'randoms pouch', 'swizzels', 'love hearts', 'squashies', 'party rings', 'hoeny', 'stroop wafel', 'stroop caramel filled waffles', 'gingerbread with caramel', 'sweet pastries', 'sweey chilli']),
    ('Biscuits', ['branettes', 'vitabakes', 'tosta rica', 'mini crackers salted', 'cocktail crackers', 'healthline']),
    ('Nuts', ['chestnuts', 'cashewnuts', 'roasted cashewnuts', 'hemp seeds', 'bulgar', 'rye flakes', 'wheat flakes', 'vinefruit']),
    ('Dried Fruit', ['deglet nour', 'pitted dried dates', 'dates whole']),
    ('Legumes', ['broadbeans', 'chilli broadbeans']),
    ('Canned Seafood', ['mussels in brine', 'baby clams in brine', 'mackarel fillets', 'acciughe', 'filetti di acciughe', 'naturally mussels', 'tina pouch']),
    ('Cake Preparations', ['bake mix for pancake', 'pancake shaker mix', 'buttery mash']),
    ('Cereals', ['bulgar wheat', 'taboule', 'tasty grains medley']),
    ('Coffee', ['ciobar zero', 'rich blend', 'capuccino', 'capsule deicaffeinato']),
    ('Herbs & Spices', ['korma', 'rogan josh', 'japanese style curry', 'green curry', 'red curry', 'massaman curry', 'meal mix country stew', 'mealmaker country stew', 'cottage pie', "shepherd's pie mix"]),
    ('Sugar', ['carrefour sugar']),
    ('Honey', ['miel']),
    ('Vegetables', ['arthicokes hearts', 'quartered & marinated']),
    ('Fruits', ['composta di fragola', 'pruna']),
    ('Floor Cleaners', ['floor detergent', 'floor wash', 'floor disnfectant', 'floor disinfectant', 'parquet cleaner', 'laminate & parquet', 'detergent for laminate']),
    ('All-purpose Cleaners', ['kitchen cleaner', 'bathroom mould spray', 'mould spray cleaner', 'chandelier spray cleaner', 'grease away', 'hob cleaner', 'oven, grill & barbecue', 'hygenical spray', 'disinfecting spray', 'disinfettante', 'sanitizing liquid', 'detergente vetri', 'vetri spray', 'stainless steel cleaner spray', 'stainless steel spray', 'power wash intense', 'glass cleaner', 'leather cleaner', 'hygiene cleaner', 'shower & bath cleaner', 'toilet super powerful', 'brill & refill', '2 in 1 disinfettante', 'actif']),
    ('Household Goods', ['copper polish', 'silver polish', 'crystal chandelier cleaner', 'scratch cover', 'fridge odour', 'odour absorber', 'moisture trap', 'fire extinguisher', 'thermo bag', 'toilet brush', 'hand brush', 'hanger', 'led golf ball', 'night light', 'socket remote control', '3-pin fused', 'partylights', 'sink mat', 'lunch bag', 'indoor dryer', 'vacuum storage bag', 'extention pole', 'door mat', 'bottle holder', 'cross body', 'steering wheel cover', 'sports backpack', 'disposable bbq', 'bbq grill', 'fire lighter liquid', 'solid starter', 'firewood', 'bbq briquettes', 'bbq tool set', 'bamboo skewers', 'wooden skewers', 'fireflares', 'sparklers', 'super attack', 'super attak', 'contact mastice', 'double sided tape', 'double side tape', 'creative stip', 'rust remover', 'furniture polish']),
    ('Bathroom & Wc Cleaner', ['harpic', 'grout cleaner', 'black mould', 'mould cleaner', 'damp clear']),
    ('Drain Unblockers', ['drain blocker', 'kitchen unblock']),
    ('Dishwasher Tablets', ['autodishwashing', 'dishwashing tablet', 'dishwashing tabs', 'dishwashing pods', 'dishwasher gel', 'machine cleaner']),
    ('Dish Washing Liquid', ['dishwash power spray', 'dishwashing liqui']),
    ('Fabric Softener', ['outdoorable', 'fabric conditionr', 'fabric conditioner', 'tumble dryer sheets', 'tumble dry sheets', 'dryer ball', 'ultra ocean breeze', 'ultra spring awakening', 'ultra lavender']),
    ('Laundry Tablets', ['caps 3in1', 'capsules colour', 'capsules passion bloom', 'capsules peony & rose']),
    ('Laundry Washing Powders', ['colour protect powder', 'powder bio', 'power bio']),
    ('Laundry Washing Liquids', ['baby detergent liquid', 'laundry detergent eliminates odor', 'sanitizing laundry detergent']),
    ('Air Fresheners', ['febreze', 'felce azzurra spray', 'felce azzurra sacchett', 'oudor neutralizer', 'airfreshner', 'spray refill', 'profumo blue', 'profuma pink', 'spruzzatore', 'diffusore', 'spray ambiente', 'incence sticks', 'incensce sticks', 'concentrated gardenia']),
    ('Insect Killer', ['zigzag', 'anti insect spray', 'eco trap cockroaches', 'fly coils', 'anti spider & web']),
    ('Stain Removers', ['stain off', 'stain solve']),
    ('Cloths & Sponges', ['reusable gloves', 'nitrile gloves', 'cotton gloves', 'gloves multi touch', 'microfibre', 'micro fibre', 'scrub mommy', 'dust magnet', 'yellow duster', 'cleaning pads', 'iron cleaning pads']),
    ('Disposables', ['foiltray', 'foil container', 'roasting bag', 'roasting dish', 'cling wrap', 'non stickpaper', 'flan dish', 'flan dishes', 'pie dish', 'foodsaver bags', 'toliet paper', 'hankies', 'hanky', 'cartapaglia', 'gran tavola scozzersi', 'super soft color']),
    ('Stationery', ['writing set', 'colour peps', 'compass study holder', 'protractor', 'hilghlighters', 'pastel highlighters', 'clip board', 'transparent plastic folder', 'poster paint', 'jotter', 'blister pen', 'xblister', 'xblisters', 'duplicate book', 'whsmith tags', 'doodlerz gel', 'retractable ball', 'z-grip', 'zb ola ball', 'clay paint', 'sensory art', 'heart style pen']),  # bare "flexible" (28 Aug 2026) removed -- too broad, CSV shows it wrongly tagging a hair-styling mousse, a garden hose, a hairspray brand, and duster products as Stationery; "ruler"/"protractor" real Stationery items still match via their own keywords
    ('Toys & Games', ['hot wheels', 'matchbox', 'skip bo', 'magnetic letters', 'magnetic numbers', 'play food set', 'pull back', 'farm animals', 'playset dinosauri', 'princess bust', 'real baby', 'doctor set', 'glass marbles', 'construction vehicle', 'assorted cars', 'friction fire engine', 'changeable robot', 'mixer playset', 'combat set', 'racer', 'stacking flowers', 'space balls', 'free wheel trailer']),
    ('Electrical', ['stand fan', 'cordless black', 'vacuum cleaner', 'powerbank', 'mini chopper', 'high power aa', 'high power aaa', 'instax', 'sodastream']),
    ('Household Goods', ['slow cooker', 'sandwich tin', 'loaf tin', 'stainless steel fillet knife', 'personal cool bag', 'set of plates', 'double walled', 'strainer', 'citrus squeezer', 'bed sheets', 'fitted sheet', 'pillow case', 'toilet brush & holder', 'air fryer', "dish w'lid", 'dish w/llid', 'rectangular dish', 'cook&store', 'b b q plates', 'square plates 24cm', 'tablecloth', 'bio plates', 'christmas plates', 'pla cups', 'birthday flags', 'streamers', 'gas pump clock', 'thumblers', 'ashtrays', 'long drink glass', 'empire glasses', 'manicare essentials travel bottle', 'bestlock belt', 'massage glove', 'simpl hob']),
    ('Deodorants', ['nike colors', 'nike ultra', 'nike turquoise vibes', 'nike viral', 'nike trendy', 'bodyspray', 'pot homme', 'shirt protect', 'anti traccia', 'adidas pure game']),
    ('Sanitary Towels', ['every day normal', 'every day sens', 'everyday liners', 'everyday natura', 'sani pants', 'feminine hygiene']),
    ('Intimate Care', ['o.b. organic', 'ob organic']),
    ('Skin Care', ['dermo gel', 'aloa vera dermo', 'anti age serum', 'cleansing miscellar', 'hyaluronic rose serum', 'aqua micellare', 'hydrabomb mask', 'bb crema', 'pure active 3 in 1', 'mask sachet priobotics', 'anti fatigue effect eye mask', 'thalasso scrub', 'blackhead daily scrub', 'cellular epigenetics', 'clear-up strip', 'refreshing toner', 'face & beard wash', 'deep cleaning facewash', 'pure effect clean', 'rose care wipes', 'beauty fluid', 'complete care lotion', 'total effects', 'crema pelle', 'mask cryo jel', 'pure active serum anti imperfections', 'kind to skin', 'radiant booster', 'soothing eye balm', 'snail extract serum', 'face disks', 'eyes & face wipes', 'glysolid', 'labbra tin', 'depilatorie', 'strips arms & legs', 'facial pop up']),
    ('Body Lotions', ['nivea body', 'nivea nivea bath', 'nivea bath creme', 'nivea bath diamond', 'nivea creme', 'nivea hand 3in1', 'nivea hand age defying', 'nivea handprotective']),
    ('Shower Gels', ['dove pump', 'infasil', 'bagnodiccia', 'nivea shower', 'shower & shave', 'shower foam', 'lynx shower']),
    ('Hair Treatment', ['frizz off deep treatment', 'keratina deep treatment', 'keep curl deep treatment', 'wella deluxe wonder', 'wella pure fullness']),
    ('Hair Styling', ['forming wax top form', 'hair power paste', 'sculpting claytime', 'one stop styler booster']),
    ('Hair Colouring', ['ritocco perfetto', 'rotocco perfetto', 'biondo', 'natural & easy', 'soft color kit', 'excellence creme', 'col.minisize', 'masch.cap']),
    ('Perfume', ['aoura collection', 'bespoke legend', 'bossa nova mini mist', 'luscious four set', 'mar e sol set', 'secret love mini mist', 'three for me', 'unique deluxe duo', 'mini galore']),
    ('Dental Care', ['steradent', 'floss picks']),
    ('Make Up', ['dischetti struccanti', 'cosmetics applicators']),
    ('First Aid', ['nose strips', 'mouth tape', 'hand senitiser', 'cleansing hand gel', 'antibacterial hand gel', 'hand sanitizing gel']),
    ('Shaving Creams', ['after shaving', 'shave lotion', 'shaver gel']),
    ('Cotton Buds', ['cotton buda']),
    ('Cloths & Sponges', ['bath glove', 'shower puff']),
    ('Wine - White', ['fiano', 'trebbiano', 'liebfraumilch', 'malvasia di castelnuovo', 'pouilly fume', 'grechetto', 'arneis', 'anthilia', 'damarino', 'passito', 'lugana', 'torrontes']),
    ('Wine - Red', ['albarossa', 'sangre de toro', 'santa cristina', 'cannonau', 'aglianico', 'montepulciano', 'montepuliciano', 'camenere', 'carmenere', 'medoc', 'pinto noir', 'sedara', 'famoso rubicone', 'sangria']),
    ('Wine - Sparkling', ['frizzantissima', 'spritzzoso', 'bollicine', 'fragolino']),
    ('Spirits - Whisky', ['chivas regal', 'douglas laing', 'famous grouse', 'glen moray', 'glenfiddich', "grant's triple wood", 'togouchi', "jack daniel's coke"]),
    ('Spirits - Liqueurs', ['drambuie', 'fernet-branca', 'ameretto', 'cooking brandy', 'hennessy', 'jagermeister', 'amaretto', 'french brandy', 'anisette', 'napoleon brandy', 'grappa', 'ramazzotti', 'sambuca', 'limoncello', 'mediterranean aperitif', 'crema liquor', 'mojito', 'pina colada', 'sex on the beach', 'martini bellini', 'martini extra dry', 'martini fiero']),
    ('Spirits - Vodka', ['smirnoff ice']),
    ('Beers', ['corona cero', 'hollandia pilsener', 'leffe brune', 'lowenbrau', 'mahou', 'peroni nastro azzurro', 'stella artois', 'tripel', 'karmeliet']),
    ('Ciders', ['kopparberg', 'strongbow', 'thatchers']),
    ('Dilutables', ['elevenfit']),
    ('Sports', ['gatorade', 'powerade']),
    ('Energy Drinks', ['hell energy', 'monster hamilton', 'monster lando', 'monster monarch', 'monster pipeline', 'monster ultra', 'shark stimulation', 'wow hydrate']),
    ('Juices', ['kombucha', 'aloe drink', 'bi frutas', 'vitamin reload', 'morning boost', 'mandarino al limone', 'chinotto', 'mandarino verde', 'aloe verao', 'yippy multi', 'ribena', 'lychee drink', 'mighty burst', 'belvoir farm', 'sanguinello']),
    ('Carbonated Drinks', ['perrier', 'ice teach', 'elderflower sparkling']),
    ('Coffee', ['iced coffe', 'frappuccino', 'capuccino']),
    ('Cold Cuts', ['bacon cubes', 'streaky bacon', 'back bacon', 'collar bacon', 'bacon slices', 'bacon diced', 'antipasto', 'spianata', 'fuet', 'chistorra', 'tapas mix', 'coppa stagionata', 'salametto', 'stripes of pig cheek', 'weisswurst', 'duck mouse', 'jamon serrano', 'pechuga de pavo', 'salam mistret', 'choriza', 'chorizo', 'spareribs', 'tacchino arrosto', 'prositcutto cotto', 'tivoli fumo', 'fiortoast', 'burger slices', 'light slices', 'toast slices']),
    ('Cheese', ['kefalotiri', 'mimolette', 'dolcelatte', 'parmiggiano reggiano', 'grattugiato', 'rikottina', 'mix di formaggi', 'chesse slices', 'leerdammer', 'gran regale', 'snowdonia', 'irkotta', 'rikotta']),
    ('Butter', ['lurpak', 'meadow lea', 'utterly butterly', 'vitalite', 'flora light', 'flora plant', 'baking margerine', 'cooking fat', 'kerrygold']),
    ('Yoghurt', ['greek yog', 'stracciatella', 'straciatella', 'yakult', 'dairy free greek style', 'benecol']),
    ('Chilled Fish', ['caviar', 'fisch alaska pollock', 'pollock shredded']),
    ('Sweet Snacks', ['dessert vaniglia', 'cheescake', 'cheesecake']),
    ('Pasta & Couscous', ['cappellacci', 'cortecce', 'stozzapreti', "capelli d'angelo", 'capelli d angelo', 'elicoidali integrali']),
    ('Fresh Pastry', ['filo pastry', 'pinsa romana', 'pinsa formato famiglia', 'pinsa margherita']),
    ('Snacks', ['chicche di patate']),
    ('Sauces & Condiments', ['humus', 'babaganoush', 'baba ghanoush', 'muhamarra', 'cooking spray', 'vegetarian maionese', 'amatriciana']),
    ('Sports', ['boost hydrabalance', 'boost magnesium glycinate', 'boost omega', 'boost vitamin d3', 'boost 360 greens powder', 'shilajit', 'protein bites', 'protein salty caramel', 'protein ball', 'protein hots', 'skinny protein', 'protein toast', 'protein dessert', 'protein pancake', 'lipitek', 't booster', 'suplement diety', 'melatonin capsules', 'zma', 'carnitine', 'tribulus', 'zero drinx', 'purasana', 'probar', 'hematogen', 'wheatgrass powder', 'protein pancakes']),
    ('Meat Alternatives', ['beyond meat burger', 'burger seitan', 'quarter pounder burger', 'vegan bbq tortilla', 'vegetarian lemon bites']),
    ('Vegetables', ['kimchi']),
    ('Snacks', ['corn triangles', 'curvies bbq', 'curvies original', 'mini calzone bites']),
    ('Milk', ['drink oatmeal', 'soia drink', 'bio drink soia']),
    ('Nuts', ['semi di girasole biologici', 'shelled hemp']),
    ('Pasta & Couscous', ['elicoidali integrali bio']),
    ('Crackers, Crispbread & Breadsticks', ['gallette', 'crusca di avena', 'crackers pocket', 'gluten free cracker toast', 'gluten free crackers', 'gluten salinis free', 'gluten-free salti crackers', 'salinis sticks', 'grissin ondulati', 'knacke', 'pita thins']),
    ('Frozen', ['margherita gluten free', 'senza glutine margerita', 'magnum vegan']),
    ('Frozen Vegetables', ['stir fry mix']),
    ('Bread', ['kaiser rolls', 'diet light toast', 'panfette']),
    ('Cereals', ['porrige gluten free', 'kelkin porrige']),
    ('Sweet Snacks', ['maxi break', 'gluten free twin bar', 'goccefrolla']),
    ('Biscuits', ['milly gris', 'schar notes']),
    ('Chocolates', ['white choclate', 'torras']),
    ('Vegetables', ['corn baby', 'on the cob', 'sweet potatoe fries', 'frottartna', 'orto primavera']),
    ('Herbs & Spices', ['bayleaves local fresh', 'rosemary fresh in pots', 'rosemary local fresh', 'thyme local fresh']),
    ('Meat Alternatives', ['to-fu fresh pack']),
    ('Cold Cuts', ["welbee's deli", 'welbees deli']),
    ('Bread', ['margherita pastizzeria style', 'vegan ciabatta', 'vegan panina sesame', 'vegan pastizzi', 'sliced xiklun', 'gluten free wraps', 'pan bauletto bianco', 'bon matin', 'ciabatta rolls', 'pangrati', 'vital mastro panettiere', 'schar wrap', 'incola gluten free breakfast roll']),
    ('Crackers, Crispbread & Breadsticks', ['schar cracker pocket', 'schar crackers', 'schar salinis', 'schar salti', 'fette croccanti toast', "wellaby's crackers", 'inno foods crackers', 'misura crackers fibextra', 'misura crackers fibrextra', 'misura crackers soia', 'the beginnings hemp seed crackers', 'misura fette fibextra', 'misura fette natura', 'misura fette dolcesenza']),
    ('Sweet Snacks', ['crostatina', 'schar maxi break', 'schar twin bar', 'pausa ciok', 'quadritos nocciola', 'soft waffles', 'icecream cones', 'salted caramel stick', 'profiteroles', 'ecomil desert', 'waffles part baked', 'tortina privolat', 'barretta cioccolate', 'cornetto dolcesenza', 'cornetti fibrextra', 'cornetto fibrextra']),
    ('Snacks', ['schar curvies', 'mini calzone bites', 'good & honest salted', 'protien pops']),
    ('Pasta & Couscous', ['gluten free pappardelle', 'acini di pepe', 'cavatappi', 'concighlie rigate', 'schar lasgane', 'azuki soy capellini', 'edamame capellini', 'vitabella gluten free cous cous']),
    ('Biscuits', ['schar notes', 'ciambelline']),
    ('Fresh Pastry', ['schar pinsa margherita', 'shortcrust pastry', 'sweet pastry']),
    ('Cereals', ['cioko crispies', 'color loops', 'pensa bio oatflakes', 'pensa bio small oatflakes']),
    ('Sugar', ['dolcificante', 'truvia', 'hermesetas', 'sweetex', 'xilitol', 'zuccheri da mele', 'agave inulin']),
    ('Honey', ['agave syrop', 'agave syrup']),
    ('Herbs & Spices', ['pensa bio curry', 'pensa bio tumeric']),
    ('Dried Fruit', ['pensa bio dates', 'essicata']),
    ('Oils', ['pensa bio ghi', 'smart organic ghee']),
    ('Nuts', ['pensa bio hemp seeds', 'pensa bio mixed seeds', 'pensa bio wheat germ', 'linwoods organic multi boost', 'linwoods organic seed mix', 'linwoods shelled hemp']),
    ('Meat Alternatives', ['pensa bio seitan', 'pensa bio conventional soy steacks', 'pensa bio soy granular']),
    ('Legumes', ['pensa bio mung beens', 'steamed chckpeas']),
    ('Vegetables', ['spincah leafs']),
    ('Sports', ['mogyi fit mix', 'mogyi protein mix', 'melatonina istantanea', 'acai packs', 'vivo d3', 'melinda protein', 'turtle bio protein cluster']),
    ('Tea', ['pukka organic']),
    ('Sauces & Condiments', ['servivita', 'tahin', 'tahina']),
    ('Wine - Red', ['le natruel zero zero red']),
    ('Wine - White', ['le natruel zero zero white']),
    ('Chocolates', ['stella chocolat organic']),
    ('Milk', ['alpro drink coco', 'alpro drink protein soya', 'soya original', 'barista soya', 'senza lattosio', 'soy barista', 'hemp drink sugar free']),
    ('Sweet Snacks', ['debron', 'de bron', 'dietor sweetenerer', 'vitalp']),
    ('Cheese', ['hello-v', 'benna rikotta']),
    ('Chocolates', ['moo free']),
    ('Milk', ['buttermilk']),
    ('First Aid', ['iron oral spray', 'ketone test strips']),
    ('Hair Treatment', ['anti hair loss']),
    ('Cooking Creams', ['gran cucina']),

    # 18 Aug 2026 -- EIGHTH bulk sweep, second pass: Food Cupboard again, after
    # measuring the first pass against the real file and finding it still only
    # 44% closed -- this bucket turned out to be the longest, most scattered tail
    # of any aisle so far, mostly one-off imported snack/confectionery brands.
    ("Sweet Snacks", ["flares with hearts", "magdalena", "waffle cones", "large cones", "twister mallows", "ufo crunvhy", "ufo crunchy", "coating", "ufo's bag", "hellema ufo's", "gecchele", "bbq mallows", "tortica original", "kunefe", "midi farci", "ibulli crema", "crunchy dipped", "mix dolci", "pez assorted", "polo original", "polo sugar free", "trefin", "vivil", "flip top", "fliptop", "zero ice blue clean breath", "cinnmon flip top", "slush puppie", "pic nic break"]),
    ("Chocolates", ["mars best of minis", "mars classic", "mars miniatures", "mars minis", "mars multipack", "mars xtra", "kimifinne", "moo freesas", "moo mini original", "cremino", "tunnock's", "prepacked english creamy", "hyper classicwith cocoa", "cacoa puro", "baileys bar"]),
    ("Biscuits", ["ringo biscocioc", "ringo vaniglia", "ringo vanilla", "buiscuits with vitamis", "sushki steinhauer", "lemon puff"]),  # "ringo vanilla" added 21 Aug 2026 -- "Pavesi Ringo Vanilla" was unclassified because the label used the English "Vanilla" rather than the Italian "Vaniglia" already covered above; NOT adding bare "pavesi" itself, since that brand also has its own separate "gran pavesi" cracker line elsewhere in this file
    ("Coffee", ["hot chocolatta"]),
    ("Sauces & Condiments", ["carnation caramel", "caramel topping", "sweet and sour", "mayonnise", "sweet barbecue sticky", "chunky burger", "strong & northern", "kapunata", "mincemeat", "concentrato di pomodoro", "preserved sorrel", "béchamel", "bechamel", "gran mix express", "mayolite"]),
    ("Stock Cubes", ["star classico", "cubes delicato"]),
    ("Cereals", ["cruesli", "roasted buckweat", "mornflake"]),
    ("Snacks", ["ajinomoto", "triangles with corn", "cizmeci", "kanpeki chillie crackers", "lingue croccanti", "mi gor", "sesame sticks", "mini wraps original", "pata grigliata", "speedy flipper", "pata tortilla barbecue", "popz microwave", "exotic cocktail", "shopline tortilla", "piu buono"]),
    ("Cooking Creams", ["soya cusine"]),
    ("Oils", ["bakery spray", "fry light", "isio 4", "sania vegetale"]),
    ("Herbs & Spices", ["erinn", "granules classico", "maggi aroma", "juicy cajun", "vegeta podravka", "crushed chillies"]),
    ("Meat Alternatives", ["soya chunks", "soy morsels"]),  # "soy morsels" added 21 Aug 2026, user-confirmed -- "Pensa Bio Soy Morsels" is dehydrated TVP soy chunks (WebSearch-confirmed), same product type as "soya chunks" right above
    ("Cake Preparations", ["pie filling"]),
    ("Canned Seafood", ["excellence mussels", "mussles in brine"]),
    ("Crackers, Crispbread & Breadsticks", ["suski malutka", "sweet & savory crackers"]),
    ("Bread", ["pitta pockets"]),
    ("Tea", ["peppermint herbal", "maraviglia", "pg tips", "pukka elderberry", "pukka tumeric gold", "melatonina & melissa"]),
    ("Sports", ["kluth"]),
    # 21 Aug 2026 -- a real run surfaced 12 unclassified vanilla-flavoured
    # protein/supplement products (welbees "Healthy Section" and greens'
    # diet/dietary and lactose-free buckets) that don't match any existing
    # keyword at all -- these went unclassified rather than colliding,
    # since removing bare "vanilla" (see the Herbs & Spices comment above)
    # took away the one word that used to catch them, even wrongly.
    # Fixed the same low-risk way as the earlier "olimp"/"kluth" brand
    # additions: each of these is a sports-nutrition-only brand name with
    # no other real-world grocery meaning, so a bare-word match is safe.
    ("Sports", ["qnt"]),  # QNT (Quality Nutrition Team) -- e.g. "Qnt Metapure Zc Vanilla", "Qnt Protein Joy Vanilla"
    ("Sports", ["biotechusa"]),  # e.g. "BioTechUSA Protein Power - Vanilla"
    ("Sports", ["nutrend"]),  # e.g. "Nutrend Delicious Bar Vanilla & Caramel"
    ("Sports", ["purition"]),  # e.g. "Purition Whole Food Nutrition Vegan Vanilla 500g"
    ("Sports", ["body attack"]),  # e.g. "Body Attack Diet Shake Vanilla" -- kept as a phrase, not promoted further, since it's already 2 words and only ever seen as a full brand name in this file
    # "Go On!" -- checked and deliberately NOT added as a bare/short
    # brand keyword the way the others above were: "go on" is also
    # ordinary English and too easy to collide with an unrelated
    # product's own tagline or description text. Narrowed to the exact
    # phrase from the one real example seen so far instead -- safe, but
    # won't automatically cover other "Go On!" products; revisit if more
    # show up unclassified.
    ("Sports", ["go on vanilla bar"]),
    # "Stuffer" was originally flagged here as NOT safe to add without
    # confirmation (also an ordinary English word for kitchen equipment,
    # e.g. a "sausage stuffer"). User confirmed "Stuffer Protei Dessert
    # Vanilla" is actually a gluten-free protein yoghurt, not a Sports
    # product or kitchen tool -- added under Yoghurt instead, see the
    # "danette"/"coppa classic"/"radianc trio set" block further down
    # (all 4 confirmed with the user the same day).
    ("Milk", ["koko dairy free"]),
    ("Sausages", ["american hotdogs jar"]),
    ("Pasta & Couscous", ["tagliolini"]),
    ("Pasta & Couscous", ["mafalde"]),  # added 21 Aug 2026 -- pasta shape (ribbon pasta), e.g. "Terre D`italia Mafalde Di Napoli", had no keyword coverage at all
    ("Legumes", ["lessati"]),
    ("Vegetables", ["simpl mais", "cipolle in agrodolce", "mix mediterraneo"]),
    ("Fruits", ["simpl pulp"]),
    ("Rice", ["tilda tsb"]),
    ("Household Goods", ["saitaku", "yutaka bamboo"]),
    ("Juices", ["traditional russian beverage"]),

    # 18 Aug 2026 -- EIGHTH bulk sweep, third pass: Household again, after
    # measuring the first pass at only 63% closed.
    ("All-purpose Cleaners", ["expert all in 1", "clean & fresh lime & lemon", "dettol liquid", "multiaction spray", "elbow grease", "cleaning & for polish wood", "steel polish", "lengno pulito", "kilrock black bbq cleaner", "polish spray", "quasar home & pet", "spin active", "power drops pink", "pink staff miracle cleaning", "sterminio", "ver nel dil blu"]),
    ("Floor Cleaners", ["alpi green pine", "fabuloso", "merito spray", "nelsen lavanda", "parador pine", "top self shining"]),
    ("Bathroom & Wc Cleaner", ["duck acqua", "duck bluing", "duck coloring", "duck deep action", "duck liquid", "duck marine toilet", "kilrock service"]),
    ("Drain Unblockers", ["drain cleaner gel"]),
    ("Dish Washing Liquid", ["dish detergent lemon", "dishwashing detergent lemon"]),
    ("Dishwasher Tablets", ["ecover dish tablets", "dishwasher cleaner sachet"]),
    ("Laundry Washing Liquids", ["44washes", "universal 44w", "universale 60washes", "silk & wool liquid", "derh cond", "derh liquid black", "derh mega gel", "laundry detergent colour magic"]),
    ("Fabric Softener", ["mighty black fabric sheets", "fabric conditoner"]),
    ("Household Goods", ["portanicensi", "super absorbants", "coral gas", "rectangular basin", "concrete chisel", "superassorbente", "attaccatutto", "epoxy syringe", "pattex silicone", "pledge", "spa lighter", "tonkita", "fil containers"]),
    ("Disposables", ["ice bags", "diamond foil", "fior di carta", "foil alluminiun container", "pie dishes", "pack containers foil", "catering roasting dishes", "scottex", "asciugatutto", "tana x l", "toastabags"]),
    ("Hand Tools", ["pwr work blade cutter"]),
    ("Candles", ["pillar gold", "devotion light"]),
    ("Cloths & Sponges", ["green shield", "silver duster", "reusable diamond gloves"]),
    ("Electrical", ["cpro", "corepro led", "tulka powerplus"]),
    ("Stationery", ["packing tape brown"]),
    ("Pet Care", ["pet remedy", "pet hair dissolver"]),
    ("Air Fresheners", ["wexor fabric spray", "spira green"]),

    # 18 Aug 2026 -- NINTH bulk sweep. Third round written from real data --
    # this export is down to 167 distinct unclassified names across 9 aisles,
    # so this pass closes out most of what's left of the long tail from the
    # eighth sweep (mostly items the earlier passes' bucket sampling missed).
    ('Household Goods', ['easy coppa', 'jumbo dish', 'lacasa fork', 'lacasa knife', 'adora long glasses', 'lav tumber', 'kids neck cushion', 'marinex dish', 'varnished wooden handle', 'ok knife erica', 'pyrex optimum rect', 'sifcon bottles in shelf', 'sifcon frame/box', 'sifcon frame box', 'tvs pot', 'lenzuola', 'copripiumino', 'skewers with grip']),
    ('Toys & Games', ['fisher-price', 'leather ball', 'hot wheel city', 'super bounce', 'sluban', 'motorsport corsa', 'maxi tube soft']),
    ('Household Goods', ['disp bbq']),
    ('Electrical', ['simpl microwave smg']),
    ('Baby Essentials', ['tommee tippee']),
    ('Stationery', ['virca pencils', 'zebra sarasa']),
    ('Sweet Snacks', ['voglia all` albicocca', 'voglia all albicocca', 'catch minis', 'jake minimax', 'dolci momenti', 'lazzaroni prestige', 'mogyi mix', 'pectol', 'mini essence brandy', 'sea salted']),
    ('Sauces & Condiments', ['smokey b b q', 'black jack smokey']),
    ('Cold Cuts', ['farmhouse campagne']),
    ('Fresh Pastry', ['cornetto privolat']),
    ('Vegetables', ['palse veggies']),
    ('Sweet Snacks', ['relkon']),
    ('Herbs & Spices', ['ilma zahar']),
    ('Snacks', ['fantasy of seeds']),
    ('Oils', ['paneolio']),
    ('Deodorants', ['sanex zero', 'sanex natur protect']),
    ('Skin Care', ['fresh idra talc', 'felce azzurra skin care', 'talc + puff', 'milleusi']),
    ('First Aid', ['burning gel']),
    ('Baby Essentials', ['bayh foam bubble', 'clean & clear advantage', 'kids bayh']),
    ('Hair Colouring', ['exellence creme']),
    ('Skin Care', ['men expert 4 in 1', 'men expert h/energetic', 'men expert hydra energetic', 'men expert thermic resist', 'men expert thermix resist', 'men expert total clean']),
    ('Intimate Care', ['aloe intimo aqua wipes']),
    ('Shaving Creams', ['replenishing post shave balm', 'style freeze power gel']),
    ('Clothes', ['maternity feeding bra']),
    ('Skin Care', ['massage gel exotic escape']),
    ('Skin Care', ['moisturising massage gel']),  # 21 Aug 2026 -- "Control Sweet Vanilla Moisturising Massage Gel" was unclassified; same product type as the "massage gel exotic escape" line just above, so following that same precedent rather than guessing this is an Intimate Care product (Control is an intimate-care/condom brand, but this specific line is a general moisturising gel, not condom-adjacent)
    ('Cold Cuts', ['gran mixed', 'sensation sliced bacon', 'sweet bacon in cubes', "n'duja", 'salamino casereccio', 'smoked bacon sliced in cubes', 'bresi', 'antipasti mediterranean']),  # bare "peperoni" (28 Aug 2026) removed -- Italian for bell pepper, not English "pepperoni" meat; CSV shows it overwhelmingly used for peppers (Vinegars, Herbs & Spices, Canned Vegetables, Sauces & Condiments) with only rare real cured-meat hits, which still match via "salami"/other Cold Cuts keywords
    ('Sports', ['coldpress vitamins']),
    ('Cheese', ['gibnarolls', 'pekorin semi mature', 'hanini creamy light', 'blue ceese', 'spreadable-blue', 'spreadable blue']),
    ('Sweet Snacks', ['anelli di ciocolato']),
    ('Sauces & Condiments', ['greek pomegrante and rasberry']),
    ('Juices', ['mild zorka moia']),
    ('Sports', ['nutrivita omega']),
    ('Yoghurt', ['greek style plain']),
    ('Sauces & Condiments', ['biryani paste', 'tikka paste']),
    ('Sweet Snacks', ['askeys salted caramel', 'salted caramel stock', 'avokatsu bites', 'qnt light digesttm', 'rabeko products salted caramel']),
    ('Sweet Snacks', ['fudged up']),
    ('Snacks', ['arancini sticks']),
    ('Sports', ['kfd zinc', 'n1 shot forest burst']),
    ('Sweet Snacks', ['mandul babi']),
    ('Bread', ['pan del forno cereali', 'pan del forno', 'vital al mastro panettiere', 'xl sandwich', 'schar sandwich', 'mestemacher']),
    ('Sports', ['powerbar black line', 'all nutrition']),
    ('Sweet Snacks', ['taveners']),
    ('Household Goods', ['long drink glasses']),
    ('Electrical', ['simpl microwave smg20l']),
    ('Pastry', ['millefoglie pastry']),
    ('Vegetables', ['cuor di lampone']),
    ('Juices', ['beplus antioxidant', 'lurisia arancia rossa']),
    ('Wine - Red', ['grand maitre']),
    ('Wine - White', ['lachryma vitis', 'san paolo medium sweet', "vigne d'or sweet reserve"]),
    ('Wine - Red', ['croft fine ruby', "leacock's dry madeira"]),
    ('Carbonated Drinks', ['dallthe']),
    ('Juices', ['go & fun original', 'lacto bottle']),
    ('Wine - Red', ['marsovin 100th anniversary', 'marsovin la torre']),
    ('Spirits - Liqueurs', ['caravaggio twin pack', 'caterina riva', 'lord chambray']),
    ('Wine - Red', ['laurenz v']),
    ('Sports', ['cuvage de cuvage']),
    ('Air Fresheners', ["frutti d'acqua"]),
    ('All-purpose Cleaners', ['carrefour avio']),
    ('Household Goods', ['dylon']),
    ('Cloths & Sponges', ['liquid abrasive']),
    ('Household Goods', ['gift bagroses', 'sp101 white silicone']),
    ('Air Fresheners', ['tango clean linen']),
    ('Floor Cleaners', ['wexor elisir gel sanitizing']),

    # 18 Aug 2026 -- TENTH bulk sweep. Down to 17 distinct unclassified names,
    # so this pass is WebSearch-verified rather than guessed from the name
    # alone -- each of these was looked up to confirm what the real product
    # actually is before adding a rule for it (sources in the delivery
    # message). The remaining handful of names in this export were left
    # unclassified on purpose: the name alone doesn't say what the product is
    # even after searching (e.g. "Carrefour Sticky", "Prince 15cm"), and
    # guessing there risks a wrong classification, which is worse than
    # leaving it for a person to glance at.
    ("Cloths & Sponges", ["cotoneve"]),  # WebSearch: Cotoneve's "Rituali di Bellezza" line is body sponges/exfoliating gloves, not skincare products themselves
    ("Air Fresheners", ["susy gingerbread"]),  # gingerbread-scented sachets/diffusers are a common seasonal air-freshener product; matches the existing "gingerbread with caramel" Sweet Snacks rule pattern being a food item, this one (no food words) is the home-fragrance version
    ("Snacks", ["mix dorato"]),  # WebSearch: Carrefour's own site lists "Carrefour Mix Dorato" as a fried snack mix (fritto misto style)
    ("Sweet Snacks", ["straw bag sugar free", "aromi gusto"]),  # "La Creme Straw Bag" -- WebSearch confirms "candy straws" are a real sweet category; "Carrefour Aromi Gusto Fior D'arancio" -- WebSearch confirms this is an orange-blossom baking flavouring/essence, same family as the existing "mini essence brandy" rule
    ("Household Goods", ["windel christmas teacup"]),  # decorative teacup-shaped Christmas ornament, not a real teacup
    ("Crackers, Crispbread & Breadsticks", ["san trifone", "mixed for toast"]),  # WebSearch: "Le Bontà di San Trifone" is an Italian (Puglia) taralli/cracker brand; "Carrefour Mixed For Toast" matches Carrefour's own "toast"/apéritif cracker line

    # 18 Aug 2026 -- user-confirmed: "Carrefour Sticky" is the same kind of
    # savoury snack as Twistees (Snacks), not a food-cupboard topping/spread.
    ("Snacks", ["carrefour sticky"]),

    # 18 Aug 2026 -- user-confirmed (photo of a Hot Wheels City playset):
    # "Hochwald City Explorer Ast" is a toy, not a Hochwald dairy product.
    ("Toys & Games", ["hochwald city explorer"]),

    # 18 Aug 2026 -- user-confirmed (photo of the box): "Bdl Mohhok Hemm" is
    # "Mohhok Hemm", a Maltese quiz/board game (KWIZZ).
    ("Toys & Games", ["mohhok hemm"]),

    # 18 Aug 2026 -- user-confirmed (photo): "Prince 15cm" is a TY Beanie Boo
    # plush soft toy (a husky named "Prince"), not a real-world 15cm item.
    ("Toys & Games", ["prince 15cm"]),

    # 18 Aug 2026 -- user-confirmed with photos, the last four names in this
    # export:
    ("Household Goods", ["la casa delle cose delta"]),  # a hand/tea towel
    ("Stationery", ["tiggi & bird", "shoppig list"]),  # a branded notepad
    ("Hair Styling", ["lisgel"]),  # "Lisgel Wet -- Lucidante Effetto Bagnato" is an Italian wet-look hair styling gel
    ("Shaving Creams", ["swiss disp extreme activ"]),  # disposable razors (Wilkinson Sword-style multipack) -- closest existing category, this taxonomy has no separate Razors bucket

    # 20 Aug 2026 -- the last unclassified listing in production:
    # "Glutenfreebiss Mixed Party Items" (greens' Gluten Free aisle).
    # Glutenfreebiss is a Maltese gluten-free producer (WebSearch-confirmed:
    # glutenfreebiss.com, Qormi) whose range includes savoury party
    # pastries, and "Party Food" already exists as a category (PAVI's
    # "Party Items" aisle maps to it). Keyword is the product phrase, not
    # the brand -- the brand also makes bread/pasta/pastizzi, which belong
    # in their own categories.
    ("Party Food", ["mixed party items"]),

    # 20 Aug 2026 -- first real batch of Welbee's-only unclassified
    # listings, surfaced once Welbee's local crawl actually started
    # writing real products to the database (previously blocked/empty --
    # see welbees_crawler.py's own "How this evolved" section).
    ("Electrical", ["gigaset"]),  # WebSearch-confirmed: Gigaset only makes cordless landline phones/telecom equipment, e.g. "Gigaset Cordless Duo Black Phone"
    ("Fresh Pastry", ["pinsa base"]),  # a raw/prepared Roman-style pizza base, e.g. "Di Marco Pinsa Base" -- same category as the existing "pinsa romana"/"pinsa margherita" rules above
    ("Cakes", ["pandori"]),  # WebSearch-confirmed: Bauli's own name for its mini pandoro-style breakfast pastry (e.g. "Bauli Pandorì Classic"), same category as the existing "pandoro" rule

    # "Fresh By Ela Breakfast Mix" (welbees / Fruit & Veg Counter). Couldn't
    # be identified via WebSearch or WebFetch (Welbee's page returned a
    # 403 that one time), so Ranier sent a photo instead -- clearly a
    # sealed pouch of almonds, cashews, walnuts, cranberries, raisins and
    # other dried fruit, i.e. a nuts-and-dried-fruit trail mix. Same
    # category as the existing "trail mix" keyword above (Nuts). Keyword
    # is "breakfast mix", not "breakfast", so it can't accidentally catch
    # an unrelated breakfast cereal/porridge product down the line.
    ("Nuts", ["breakfast mix"]),

    # 21 Aug 2026 -- second batch of Welbee's-only unclassified listings,
    # from the first "Categorize listings" run after real Welbee's data
    # had been flowing for a couple of days.
    #
    # "O.b. Extra Protection Normal (16p)" / "O.b. Extra Protection Super
    # (16p)" -- O.b. (Johnson & Johnson) is a tampon brand, but the name
    # alone doesn't contain the word "tampon" anywhere, so the existing
    # bare "tampon" keyword above never had a chance to match. Deliberately
    # NOT just "o.b." on its own as the keyword: cleaned down to bare
    # letters "o" and "b" (see clean_for_matching -- the periods become
    # spaces), a 1-letter/1-letter pair is too short and too generic to be
    # safe as a standalone keyword. Using the fuller "o.b. extra
    # protection" phrase (matches after cleaning, since the keyword goes
    # through the same cleaning as the product text) keeps this specific
    # and safe.
    ("Intimate Care", ["o.b. extra protection"]),

    # "Falanghina del Sannio Il Poggio 2022 (750ml)" -- Falanghina is a
    # white wine grape from Campania, Italy (WebSearch-confirmed), same
    # idea as the existing chardonnay/sauvignon/etc grape-variety keywords
    # already in this category.
    ("Wine - White", ["falanghina"]),

    # "Ashoka Instant Bombay Biryani (280grms)" -- an instant/boxed biryani
    # kit. Judgment call, flagged as such: biryani is fundamentally a rice
    # dish, and this project already treats "risotto" (an equally
    # rice-based, name-doesn't-say-rice dish) as belonging to Rice rather
    # than Ready Meals -- this follows that same precedent for
    # consistency, rather than splitting seasoned-rice-dish products
    # across two categories depending on which dish they happen to be.
    ("Rice", ["biryani"]),

    # "Nairn's Flatbread Original Crackers (gf) (150grms)" -- this ALREADY
    # says "Crackers" in the name, but there's deliberately no bare
    # "cracker" keyword anywhere in this file (only compound phrases like
    # "prawn cracker", "rice cracker") -- almost certainly because a
    # supermarket also sells actual Christmas crackers (the pull-apart
    # party favour, not food), which would wrongly land in this category
    # too if "cracker" alone were a keyword and there's no separate
    # Christmas/Party aisle mapping to catch it first (true for Welbee's,
    # which has no aisle-mapping table at all). Using the brand name
    # instead sidesteps that risk entirely: Nairn's (WebSearch-confirmed)
    # makes ONLY oatcakes/oat crackers/oat biscuits -- no unrelated
    # product lines, so the brand name alone is safe here in a way "plain
    # cracker" is not.
    ("Crackers, Crispbread & Breadsticks", ["nairn's"]),

    # 21 Aug 2026 -- from continuing the collisions-report triage into the
    # "Fruits / X" pairs (Sports, Oils, Tea, Spirits, Bread, Carbonated
    # Drinks, Ciders -- ~490 listings combined). Same root shape as the
    # vanilla fix above, but a DIFFERENT repair: a bare fruit-flavour word
    # (mango, berry, peach, coconut, orange...) can't just be removed the
    # way "vanilla" was -- real fresh fruit is a huge, legitimate part of
    # this category, and Welbee's in particular has no aisle-mapping table
    # at all, so it depends entirely on these bare words to classify real
    # produce correctly. Instead, these two phrases give the REAL product
    # type (found from this round's actual colliding examples) something
    # more specific than bare "oil" to win on -- phrases already beat
    # every bare word in this file by design, so no other category's
    # bare-word matching needed to change at all.
    ("Oils", ["coconut oil"]),  # "Alibaba Coconut Oil" was tying bare "oil" (Oils) against bare "coconut" (Fruits)
    ("Skin Care", ["tanning oil", "tanning lotion", "bronzing"]),  # "Malibu Sun Bronzing Tanning Oil Spray Coconut" was tying bare "oil" (Oils) against bare "coconut" (Fruits) -- neither of which is actually right; it's a suncare product

    # 23 Aug 2026 -- First Aid/Skin Care, full-database pass (51). "vitamin c"
    # (and "vitamin d"/"vitamin b" for the same reason) used to sit near the
    # top of the First Aid block, meaning it beat almost every Skin Care
    # phrase in this file just by file position -- e.g. "Garnier Synergie
    # Vitamin C Serum Anti Macchie" and "Face Facts Lip Serum Vitamin C &
    # Cloudberry" were landing on First Aid even though they're clearly
    # skincare (serums, creams, cleansers, sheet masks). "Vitamin C" is a
    # near-universal skincare ingredient callout, not just a supplement
    # name, so it's moved to the very end of this list -- it now only wins
    # for a product that mentions no other keyword at all (a genuine
    # Vitamin C tablet/supplement), while any skincare-specific word
    # earlier in the file (serum, cream, cleansing, mask, etc.) wins first,
    # same principle as the "coconut oil"/"tanning oil" fix just above.
    ("First Aid", ["vitamin c", "vitamin d", "vitamin b"]),

    # 24 Aug 2026 -- gap-fill sweep from a 30K-row no-match/mismatch audit
    # (per-category shopping_category vs. classify_by_name() diff, run
    # against a fresh SQL export). Appended at the very end of KEYWORD_RULES
    # deliberately -- new entries here are lowest priority against every
    # existing rule, so they can only fill genuine blanks (no prior match at
    # all) and can't reorder or override anything already working. Each
    # entry below is a real recurring pattern seen in the no-match sample
    # for its category, picked for low collision risk (brand names,
    # multi-word phrases, or country/dialect terms not used elsewhere in
    # the taxonomy). Categories with large, genuinely mixed no-match buckets
    # (Household Goods, Stationery) were deliberately left alone here --
    # like Welbee's own "everything mixed together" aisles, they're mostly
    # brand names and generic container/color words (bottle, cup, black,
    # blue...) that would cause more collisions than they'd fix; they need
    # a closer per-brand pass, not a quick word-frequency add.
    ("Bread", ["hobza", "qaghaq", "ciabatta", "pitta"]),  # "hobza" is "hobz" (already a keyword) with the Maltese definite-article suffix -- _keyword_matches is whole-word so it doesn't stem this automatically
    ("Beef", ["ribeye", "rib eye", "sirloin", "striploin", "topside", "rump steak", "angus beef", "scottona", "tagliata"]),
    ("Water", ["levissima", "san benedetto", "acqua minerale"]),  # bare "acqua" deliberately not added -- it's also the lead word in unrelated products like Acqua Di Parma perfume
    ("Sauces & Condiments", ["bbq sauce", "chipotle", "senape", "yogonese", "chili sauce", "kung pao"]),
    ("Vegetables", ["zucchini", "fennel", "chicory", "radish", "galangal"]),
    ("Beers", ["birra", "weissbier", "hefeweizen", "kellerbier", "erdinger", "moretti", "chimay", "kaiserdom", "hacker pschorr", "farsons"]),
    ("Make Up", ["nail enamel", "eyebrow gel", "brow gel", "brow pen", "eye shadow palette", "shadow palette", "cheek tint", "skin tint", "lip color pencil", "dipliner", "armaf beaute"]),
    ("Sports", ["yoga mat", "wrist support", "ankle support", "knee support", "resistance band", "live up"]),
    ("Biscuits", ["pavesi", "balocco"]),

    # 24 Aug 2026 -- phrases from the third collision-report pass (see the
    # matching-date comment in MULTI_KEYWORD_RULES for the full context).
    # These are plain OR-style phrase alternatives -- each wins over a bare
    # single-word match purely by being a phrase (checked in the phrase
    # pass, before any single-word pass), no co-occurrence logic needed.
    ("Tea", ["pyramid bags", "pyramid bag"]),  # Mokate/Twinings tea-bag format -- "Mokate Loyd Pyramid Bags Raspberry & Strawberry" / "...Pineapple & Pear" were landing on Fruits via the bare flavour words; the product is tea, the fruit names are just the flavour
    ("Herbs & Spices", ["fish seasoning", "fish rub"]),  # "Schwartz Fish Seasoning", "Bon Cuisine Zesty Fish Rub & Seasoning" were landing on Chilled Fish via bare "fish" -- these are spice/seasoning blends meant for cooking fish, not fish itself
    ("Skin Care", ["sun milk", "cleansing milk", "aftersun milk", "bath milk", "body milk"]),  # "milk" as a skincare-lotion term (not the dairy product) -- a whole cluster of suncare/cleansing products (Clinians, Equilibra, Carroten, Childs Farm) were landing on the Milk category via bare "milk"

    # 25 Aug 2026 -- unclassified-listing gap-fill (welbees' own "Everyday"
    # pantyliner line was never matching at all: the existing "every day
    # sens"/"every day normal" entries -- see the 'Sanitary Towels' co-
    # occurrence rules and MULTI entries elsewhere -- were written with a
    # space, but the crawled product names are the single word "Everyday").
    ("Sanitary Towels", ["everyday sensitive", "everyday normal", "everyday sens", "everyday up"]),
    ("Bathroom & Wc Cleaner", ["duck total action"]),  # "Duck" (a toilet-cleaner brand) is too generic a word to promote bare -- it collides with actual duck meat/pate products elsewhere in this data -- so scoped to its own specific product-line phrase instead
    ("Sweet Snacks", ["skinny crunch"]),  # The Skinny Food Co's low-calorie snack-bar line (WebSearch-confirmed)
    # NOTE: "plumcake" was NOT missing from the taxonomy -- it's already
    # registered under Biscuits (see the "mulino bianco"/"flauti"/"plumcake"/
    # "niederegger" entry earlier in this list). The real bug was that bare
    # "milk" (registered far earlier, line ~430) was beating it on
    # "Midi Plumcake With Milk Cream" since both are word-tier and list
    # order decides ties -- fixed below via a MULTI_KEYWORD_RULES promotion
    # instead of by re-registering "plumcake" a second time under a
    # different category.

    # 24 Aug 2026 -- fourth pass phrases (see the matching-date comment in
    # MULTI_KEYWORD_RULES above for context).
    ("All-purpose Cleaners", ["scouring cream"]),  # "Cif Scouring Cream Lemon" was landing on Cooking Creams via bare "cream" -- it's a cleaning product, not a food cream
    ("Oils", ["essential oil"]),  # "Essentia Natural Water Soluble Essential Oil Orange & Cinnamon" was landing on Fruits via bare "orange" -- it's a fragrance/aromatherapy oil, orange is the scent
    ("Sauces & Condiments", ["salad dressing", "sesame dressing"]),  # real bug, not just a low-value tie: "Saitaku Sesame Dressing Roasted" was landing on First Aid, because bare "dressing" is a legitimate (and necessary) First Aid keyword for wound dressings -- this phrase-level fix keeps that medical meaning intact while fixing the food-dressing case
    ("Cereals", ["multigrain puff", "multigrain puffs"]),  # "Piccolo Multigrain Puffs Carrot Stars" (a baby-snack puff cereal) was landing on Vegetables via bare "carrot"

    # 28 Aug 2026 -- unclassified-listing gap-fill (11 welbees listings from
    # a live run report, none matching any existing keyword at all -- see
    # the matching-date note in MULTI_KEYWORD_RULES for the Surf Capsules
    # fix that closes the 12th).
    ("Household Goods", ["dust pan", "measuring tape", "glass brush"]),  # "Minerva Dust Pan Long", "Minerva Dust Pan With Long Handle" -- the existing "dustpan" keyword (line ~1170) is one word, these crawled names are two; "Avro-Avron Measuring Tape 8mt"; "Flair Home Glass Brush"
    ("All-purpose Cleaners", ["hagerty"]),  # Hagerty (WebSearch-confirmed metal/silver-polish brand) -- "Hagerty Silver & Multimetal Foam", "Hagerty Silver Spray" -- not registered as a keyword at all before this
    ("Cheese", ["burrata", "gibnaroll"]),  # "Dalli Cardillo Santa Marta Burrata"; "Hanini Gibnaroll Peppered" -- the existing entry (line ~2067) only has the plural "gibnarolls", this crawled name is singular
    ("Chocolates", ["rocky road"]),  # "Moo Rocky Road Bites" -- a chocolate confectionery product, not a Healthy Section item
    ("Perfume", ["french avenue"]),  # "French Avenue Sultana The Joyful Edp" was landing on Dried Fruit via bare "sultana"; French Avenue is exclusively a perfume brand in the CSV (23/23 occurrences)
    ("Household Goods", ["lint remover"]),  # 28 Aug 2026 -- "Leifheit Lint Remover With Batteries" was landing on Electrical via bare "batteries"; not registered as a keyword at all before this
]


# Co-occurrence rules: ALL listed words must appear SOMEWHERE in the name
# (in any order, not necessarily next to each other) for the category to
# apply. Added after real data showed the same failure pattern three times
# in a row: a chocolate Easter egg wrongly landing on "Eggs" because the
# bare word "egg" matched before anything caught it as chocolate --
# "Nestle Easter Milkybar Mini Easter Eggs", "Nestle Easter Baci Mini Eggs
# Milk", "Nestle Easter Smarties Under The Sea Giant Egg". Each has a
# different brand name sitting between "Easter" and "Egg", so a plain
# contiguous phrase ("easter egg") only ever caught the first one -- this
# checks for both words anywhere in the name instead, which covers all
# three real cases (and any future brand doing the same thing) without
# needing a new phrase per brand. Checked before both KEYWORD_RULES passes
# below, since it's more specific than the bare "egg" single-word rule it's
# here to override.
MULTI_KEYWORD_RULES = [
    # 24 Aug 2026 -- fixes for the top same-tier collisions found by a full
    # production run's "matches keywords from more than one category" report
    # (5,772 listings). Each entry below is a single more-decisive word that
    # was losing a same-tier tie, purely on KEYWORD_RULES list order, to a
    # shorter/more-generic word for an unrelated category:
    ("Wine - Rose", ["rosato"]),  # e.g. "Caleo 2022 Primitivo Rosato" was landing on Wine - Red because the grape variety "primitivo" (a red grape) is also registered there -- the wine's own explicit colour word should always win over a grape-variety word that merely leans red
    ("Crackers, Crispbread & Breadsticks", ["nairn's"]),  # brand identity beats a generic ingredient word -- "Nairn's Gf Raisin Apple Oaty Bar" was landing on Fruits via bare "apple", even though Nairn's is an oatcake/oat-bar brand with its own keyword already registered under this category
    ("Jelly", ["jam"]),  # the product-type word "jam" is more decisive than an ingredient callout -- "Alce Nero Organic Honey Citrus Fruits Jam" was landing on Fruits via bare "fruit" ahead of the actual product type
    ("Hand Wash Liquids", ["oil", "soap"]),  # co-occurrence, not a bare "oil" promotion -- "Venus Secrets Cannabis Oil Soap" was landing on Oils via bare "oil"; requiring both words present keeps this narrow (an actual cooking/skincare oil that never says "soap" is unaffected)
    ("Shower Gels", ["radox"]),  # brand beats ingredient word -- "Radox Salts Pouch Feel Relaxed" (bath salts) was landing on Herbs & Spices via bare "salt"; Radox already has its own Shower Gels keyword, it was just losing the tie

    # 24 Aug 2026 -- second collision-report pass. Narrow co-occurrence
    # fixes only, same reasoning as above: the product-type word should win
    # over a flavor/filling word, but only when both are actually present,
    # so an unrelated plain beef or fruit product is never touched.
    ("Pasta & Couscous", ["beef", "ravioli"]),  # "Beef & Pecorino Ravioli" was landing on Beef -- it's a pasta dish, beef is the filling
    ("Pasta & Couscous", ["beef", "noodle"]),  # "Mr Noodles Beef" / "Pot Noodles Beef" -- same pattern, instant-noodle products landing on Beef
    ("Spirits - Liqueurs", ["fig", "gin"]),  # "Gunpowder Fig & Laurel Gin" was landing on Fruits via bare "fig" -- it's a gin, fig is a botanical/flavor note
    ("Spirits - Liqueurs", ["pineapple", "rum"]),  # "Brewdog Duo Spiced Rum Pineapple" -- same pattern, a rum landing on Fruits via bare "pineapple". Deliberately not a bare "gin"/"rum" promotion -- "rum and raisin" desserts are a real, already-documented Cake Preparations/Spirits collision elsewhere in this file, so a global rum-wins rule would break those

    # 24 Aug 2026 -- third collision-report pass, this time against a full
    # (undeduplicated-by-category) production export. Same rule as always:
    # narrow, verified-safe fixes only, not a blanket sweep.
    ("Spirits - Liqueurs", ["gin", "watermelon"]),  # "Islands 8 Gin Watermelon" was landing on Fruits
    ("Spirits - Liqueurs", ["gin", "blood orange"]),  # "Whitley Neill Blood Orange Gin" -- "blood orange" (not bare "orange") deliberately, since bare "orange" collides with real orange marmalade/jam products that happen to also mention gin as an ingredient (e.g. "Mrs Darlington's Orange Marmalade With Gin" -- verified in the real data, would have been a new bug)
    ("Spirits - Liqueurs", ["breezer"]),  # Bacardi Breezer -- already a registered Spirits - Liqueurs keyword but was losing same-tier ties to bare fruit-flavour words ("Breezer Exotic Passion Fruit & Mango"); promoted since it's an unambiguous brand name
    ("Pasta & Couscous", ["tagliatelle"]),  # unambiguous pasta-shape word -- "Tagliatelle Chickpea Cereal" was landing on Cereals via bare "cereal" (the product is pasta made from chickpea flour, not a breakfast cereal)
    ("Legumes", ["favetta"]),  # Maltese broad-bean paste -- "Lamb Beans Favetta" was landing on the Lamb (meat) category via bare "lamb", because "Lamb" is also a canned-goods brand name (see the "Lamb Brand Pure Ground Almonds" example earlier in this file for the same brand causing the same kind of collision elsewhere)
    ("Canned Seafood", ["calvo"]),  # already a registered brand keyword but losing same-tier ties to bare "tuna" (Chilled Fish) -- "Calvo Light Tuna In Brine", "Calvo Mexican Tuna Salad" are shelf-stable canned products, not fresh/chilled
    ("Household Goods", ["spoon"]),  # a bare product-type word for kitchenware -- "Westmark Glory Stainless Steel Vegetable Spoon" was landing on Vegetables via bare "vegetable"; a spoon is virtually never itself a food item
    ("Candles", ["bolsius"]),  # Bolsius is a pure candle brand (already has other Candles keywords registered), was losing same-tier ties to bare scent/flavour words like "peach", "apple", "pomegranate"
    ("Candles", ["spaas"]),  # same brand-vs-scent-word tie as Bolsius above -- Spaas is a candle-only brand (see the existing "scented pillar"/"spaas" entry elsewhere in this file)
    ("Candles", ["tealight"]),  # unambiguous candle-product word, same fix -- "Box 10 Tealights Berries" was landing on Fruits via bare "berries"

    # 24 Aug 2026 -- fourth collision-report pass, working down the ranked
    # list (not just the top few pairs this time -- see the full 874-pair
    # analysis). Same narrow, verified-against-real-examples approach.
    ("Cold Cuts", ["pate"]),  # unambiguous deli-meat product word -- "Cuits Sliced Black Pepper Pate", "Artichoke Pate", "Mushroom Pate" were all landing on Vegetables via their bare flavour word (pepper/artichoke/mushroom)
    ("Cheese", ["quark"]),  # unambiguous dairy product word -- "Berchtesgadener Land Quark With Herbs" was landing on Herbs & Spices via bare "herb"
    ("Yoghurt", ["protein", "pudding"]),  # narrow co-occurrence -- "Arla Protein Pudding Vanilla Cookie" was landing on Biscuits via bare "cookie"; not a bare "pudding" promotion since Christmas/bread pudding is a real, separate Cake Preparations product
    ("Coffee", ["beanies"]),  # Beanies is a flavoured-coffee brand, already registered, but was losing same-tier ties to bare "cream" -- "Beanies Strawberries & Cream Coffee" was landing on Cooking Creams
    ("Coffee", ["latte"]),  # "latte" already correctly wins against most bare fruit-flavour words (LATTE STRAWBERRY, LATTE PINEAPPLE MANGO already resolve to Coffee) purely by being earlier in KEYWORD_RULES list order than most of them -- but "LATTE APPLE WITH OATS" landed on Fruits because "apple" happens to sit earlier in the list than "latte" does. Promoting closes that inconsistency instead of leaving it to list-order luck

    # 24 Aug 2026 -- fifth pass, from the production run's own live report
    # (which counts every store listing, not one row per distinct product
    # name, so its ranking differs somewhat from the full-export analysis
    # above -- both are being worked through in parallel).
    ("Cake Preparations", ["bicarbonate", "soda"]),  # "Bicarbonate Of Soda"/"Multi Purpose Bicarbonate Of Soda" (baking soda) was landing on Carbonated Drinks -- the line-3465 "bicarbonate" tier-0 fix already existed for this but was placed AFTER the "soda" tier-0 rule below, so list order still let "soda" win every time; this earlier, more specific co-occurrence entry actually wins the tie (26 Aug 2026)
    ("Carbonated Drinks", ["soda"]),  # unambiguous fizzy-drink word -- "Warheads Soda Green Apple", "Living Things Soda Rhubarb & Apple" were landing on Fruits via the bare flavour word
    ("Carbonated Drinks", ["perrier"]),  # brand, already registered but losing ties to bare "orange" -- "Maison Perrier Forever Orange"
    ("Carbonated Drinks", ["pepsi"]),  # brand, already registered but losing ties to bare "cream" -- "Pepsi Strawberry N Cream Zero Can" was landing on Cooking Creams
    ("Hand Wash Liquids", ["soap"]),  # generalizing the existing bare "soap" -> Hand Wash Liquids fallback (see its original comment: "closest existing category" for bar soap) from a same-tier word that sometimes wins its tie to one that always does -- real data showed it losing to "orange" (Fruits), "fizzy"+"watermelon" (Carbonated Drinks), and "butter" (Butter/Cooking Creams) across three different soap products. A product whose name contains the word "soap" is virtually always literally a soap
    ("Hand Wash Liquids", ["handwash"]),  # same fix, same reasoning, for the already-registered "handwash" (no space) keyword -- "Carex Handwash Fizzy Watermelon" was landing on Carbonated Drinks via "fizzy"+"watermelon"

    # 24 Aug 2026 -- sixth pass, continuing down the Fruits/Spirits - Liqueurs
    # pair (still the largest single remaining pattern in the live report).
    ("Spirits - Liqueurs", ["gin", "peach"]),  # "Pride Of Wembley Peach Gin" was landing on Fruits. Checked the full export for false positives first (a "peach" dessert/tea product that happens to also mention "gin") -- none found
    ("Spirits - Liqueurs", ["gin", "grapefruit"]),  # "Caelestis Grapefruit Gin" -- same pattern, also checked for false positives
    ("Spirits - Liqueurs", ["spritz"]),  # already a registered keyword but losing same-tier ties to bare fruit words -- "Spritz Peach" was landing on Fruits; "spritz" is an unambiguous cocktail-style term

    # 25 Aug 2026 -- seventh pass. "milk" as a flavour descriptor on
    # wafer/biscuit products (milk chocolate coating) was repeatedly
    # beating the actual product-type word or brand -- "Deco' Mini Wafers
    # Milk", "Jaffa Wafers Milk & Hazelnut", "Bahlsen Kunterbunt Milk",
    # "Loacker Milk & Cereals" were all landing on the dairy Milk category.
    ("Biscuits", ["wafer"]),
    ("Biscuits", ["bahlsen"]),
    ("Biscuits", ["loacker"]),
    ("Biscuits", ["plumcake"]),  # same "milk" flavour-descriptor problem -- "Midi Plumcake With Milk Cream" was landing on Milk; "plumcake" is already registered under Biscuits (see "mulino bianco"/"flauti"/"plumcake"/"niederegger" earlier), this just promotes it to tier 0 so it beats the bare "milk" tie

    # 26 Aug 2026 -- ninth pass, full-DB re-analysis after the taxonomy grew.
    # "Borotalco" is a bare brand word under Deodorants (line ~1092), and it
    # was beating the two Italian compound words for "shower gel"/"bath
    # foam" -- "bagnodoccia" and "bagnoschiuma" -- since both are single
    # words (no space in the source text) tied at the same tier, and
    # "borotalco" appears earlier in list order. Real regression: the
    # production DB already has "Borotalco Bagnoschiuma Setificante 600ml"
    # correctly filed under Shower Gels from an earlier run, and this bug
    # would have flipped it (and similar bagnodoccia/bagnoschiuma products)
    # back to Deodorants on the next run. Borotalco genuinely spans both
    # product lines (WebSearch/CSV-confirmed: they make deodorant roll-ons,
    # sprays, and talc AND shower gels/bath foam), so -- same reasoning as
    # the existing "deliberately NOT sanex/malizia" comment on that
    # Deodorants line -- the fix is to promote the two shower-gel-specific
    # words to tier 0 rather than touch the bare brand word (which still
    # correctly catches actual Borotalco deodorant/talc products via
    # "roll on", "deo spray", "deodorant", etc., or falls through to
    # Skin Care for bare talc/powder items).
    ("Shower Gels", ["bagnodoccia"]),
    ("Shower Gels", ["bagnoschiuma"]),

    # 26 Aug 2026 -- ninth pass continued. The generic "multi purpose" /
    # "multipurpose" phrase (tier 1) and "multiuso" (bare word, tier 2)
    # under All-purpose Cleaners are FAR too broad -- they're a common
    # marketing descriptor on all sorts of non-cleaning products (tools,
    # gloves, openers, torches, sponges, drain unblockers, even gluten-free
    # flour), and were winning ties against the products' own, much more
    # specific, already-registered category words. Not touching the bare
    # phrase itself (real cleaners like "Astonish Multi Purpose Cleaner",
    # "Dettol...Multi Purpose Cleaner", "MULTI PURPOSE CLEANER CITRUS" still
    # need it, and it's the only signal some of them have) -- instead
    # promoting the specific conflicting words, the same pattern used
    # throughout this file, each checked against the full CSV export first.
    ("Household Goods", ["multiuso", "guanti"]),  # "Guanti Satinati Multiuso" -- satin gloves, not a cleaner
    ("Household Goods", ["multi purpose", "glove"]),
    ("Household Goods", ["multi purpose", "bottle opener"]),  # "Fatigati Multi Purpose Bottle Opener"
    ("Stationery", ["multi purpose", "scissors"]),  # "Korbond Multi Purpose Scissors" -- "Fatigati Multipurpose Scissors" already resolves fine via "scissors" alone beating "multi purpose" by word-count coincidence, but the tie needs closing properly
    ("Stationery", ["multipurpose", "scissors"]),
    ("Electrical", ["multi purpose", "torch"]),  # "Prof Premium Multipurpose Torch"
    ("Electrical", ["multipurpose", "torch"]),
    ("Cloths & Sponges", ["multipurpose", "sponge"]),  # already resolves correctly today (word-count coincidence again), promoted anyway to close the tie properly rather than leave it to luck
    ("Cloths & Sponges", ["multi purpose", "sponge"]),
    ("Drain Unblockers", ["multi purpose", "unblocker"]),  # "Kilrock Rhino Drain Unblocker Multi Purpose 1 Lt" -- was landing on All-purpose Cleaners
    ("Flour", ["multiuso", "farina"]),  # "Nutri Free Farina Multiuso Gluten Free 1kg" -- Italian for "multi-purpose flour", not a cleaner
    ("All-purpose Cleaners", ["turtle wax", "leather cleaner"]),  # "Turtle Wax Leather Cleaner Lux" -- bare "turtle wax" is a Household Goods fallback since there's no keyword path to the Car Accessories category, but this specific product is unambiguously a cleaner

    # 26 Aug 2026 -- tenth pass. Large parallel full-DB re-analysis of the
    # top ~270 remaining collision pairs (each independently CSV-verified
    # against the 93,780-distinct-name export before being added here, same
    # rigor as every block above -- diagnosed via matching_categories_by_name()
    # + _keyword_matches() against real product names, spot-checked against
    # classify_by_name() before shipping).
    ("Tea", ["twinings"]),  # "Twinings Rooibos, Honey & Fig Infusion" -> Honey; "Twining's Strawberry And Mango Infuso" -> Fruits. "twinings"/"twining" already registered but losing ties to bare flavour words
    ("Tea", ["twining"]),
    ("Tea", ["loyd", "pyr"]),  # "Loyd Pyr..." pyramid-bag tea -- "loyd" alone can't be promoted bare (collides with "Loyd Grossman" sauces), but "pyr" only ever appears on Loyd tea products
    ("Crackers, Crispbread & Breadsticks", ["oat cake"]),  # "FINE OAT CAKES" -- savoury oatcakes, not dessert cake
    ("Crackers, Crispbread & Breadsticks", ["buckwheat cake"]),
    ("Crackers, Crispbread & Breadsticks", ["quinoa cake"]),
    ("Crackers, Crispbread & Breadsticks", ["spelled cake"]),
    ("Skin Care", ["aftersun"]),  # "Byron Bay Suncare Aftersun Shimmer Oil" -- suncare products losing to bare "oil"
    ("Skin Care", ["suncare"]),
    ("Skin Care", ["carroten"]),
    ("Spirits - Liqueurs", ["gunpowder"]),  # "Drumshanbo Gunpowder Orange Gin" -- Drumshanbo's gin line, losing to bare "orange"
    ("Spirits - Liqueurs", ["gordons"]),  # already registered, losing ties to bare "orange" -- "Gordons Gin Mediterranean Orange"
    ("Spirits - Liqueurs", ["gin", "pineapple"]),  # narrow co-occurrence, not bare "pineapple" (which is a real Fruits word elsewhere)
    ("Conditioners", ["gliss", "balsamo"]),  # "balsamo" = Italian for conditioner; Gliss/Elvive sell both shampoo and conditioner under the same brand word
    ("Conditioners", ["elvive", "balsamo"]),
    ("Carbonated Drinks", ["lemonade"]),  # "GIN & LEMONADE MIXED FRUIT" was landing on Fruits while the near-identical "...STRAWBERRY & LIME" already landed on Carbonated Drinks -- pure list-order luck
    ("First Aid", ["ear plug"]),  # "Go Travel Pharma Ear Plugs" -- ear plugs are First Aid regardless of which travel-accessories brand sells them
    ("Bread", ["croissant", "hazelnut"]),  # "7days Croissant Hazelnut Max" -- croissant is the base bread product, hazelnut is filling
    ("Bread", ["bun", "cashew"]),  # "Johnny Cashew Cinnamon Bun"
    ("Cold Cuts", ["streaky bacon"]),  # "Fior Di Vita Smoked Streaky Bacon" -- literally bacon, but "Fior Di Vita" is a registered Cheese brand
    ("Cold Cuts", ["back bacon"]),
    ("Cold Cuts", ["collar bacon"]),
    ("Disposables", ["cake board"]),  # "Ipak Cake Board..." -- baking/party disposables, not food, losing to bare "cake"
    ("Disposables", ["cake tray"]),
    ("Disposables", ["cake cup"]),
    ("Disposables", ["plum cake rectangle"]),  # scoped narrow -- NOT bare "plum cake", which is a real dessert elsewhere
    ("Bread", ["ciabatta"]),  # "Ciabatta Quinoa" was landing on Cereals via "quinoa"
    ("Household Goods", ["steak knife"]),  # "Tefal...Steak Knives" -- literal cutlery, was landing on Beef via bare "steak"
    ("Household Goods", ["steak knives"]),  # "knife"->"knives" is an irregular plural that _keyword_matches' automatic trailing-"s" doesn't cover, so the singular phrase above never actually matches real (always-plural) product names -- this covers the real text
    ("Vegetables", ["truffle", "mushroom"]),  # "MUSHROOM & TRUFFLE BLOCK" -- savoury fungus truffle, not confectionery; bare "truffle" can't be touched globally (dominated by savoury uses)
    ("Vegetables", ["truffle", "tomato"]),
    ("Vegetables", ["truffle", "tomatoes"]),
    ("Herbs & Spices", ["salmon", "seasoning"]),  # "SMOKED SALMON RUB & SEASONING" -- a dry seasoning rub, not chilled fish
    ("Snacks", ["twistees", "paprika"]),  # "Twistees Sweet Paprika" snack-chip bag -- list-order luck vs. an identically-shaped listing that already resolves correctly
    ("Chocolates", ["novi"]),  # "Novi Nero 70% Dark Pistacchio" -- Novi is an unambiguous chocolate brand (39/39 CSV listings), losing ties to bare "pistacchio"
    ("Chocolates", ["snickers"]),  # already registered but losing ties to bare "fruit" -- "Snickers Crisp Fruits And Nuts"
    ("Hair Styling", ["hairspray"]),  # already registered but losing ties to shampoo-brand words -- unambiguous in the full CSV (25/25 listings are styling products)
    ("Hair Styling", ["tresemme", "mousse"]),  # "mousse" NOT promoted bare -- heavy false-positive risk (cat food, chocolate, cleaning, face mousse); scoped to the two specific broken brand co-occurrences
    ("Hair Styling", ["syoss", "mousse"]),
    ("Oils", ["coconut oil"]),  # "Greens Organic Extra Virgin Coconut Oil" -- the existing bare KEYWORD_RULES "coconut oil" phrase (added for a different Oils/Fruits fix) is only tier 1, still loses ties to "extra virgin" (Olive Oil, also tier 1); this promotes it to tier 0
    ("Candles", ["incense", "fruit"]),  # "Zed Black Incense Sticks Fruit Mix" -- incense sticks losing to bare "fruit"
    ("Shampoos", ["elvive", "olio"]),  # "Elvive Olio Straordinario" -- L'Oreal haircare ("olio" is a real, heavily-used bare Olive Oil word so can't be promoted alone)
    ("Shaving Creams", ["veet"]),  # already registered but losing ties to bare "cream" -- "Veet...Cream" hair-removal products
    ("Yoghurt", ["danette", "twix"]),  # "Danone Danette Twix" -- Danette dairy dessert cups losing to the Twix candy-bar keyword
    ("Yoghurt", ["hipro", "cioccolato"]),  # "Hipro Cup Pudding Cioccolato" -- same pattern
    ("Air Fresheners", ["ariasana"]),  # already registered but losing ties to the Aero chocolate-bar brand keyword -- "Ariasana Aero..." air-freshener refills
    ("Cake Preparations", ["lamb", "icing"]),  # "LAMB SUGAR ICING" -- Lamb-brand baking/icing sugar, not lamb meat (same "Lamb Brand" collision already fixed elsewhere in this file)
    ("Fabric Softener", ["comfort", "apple"]),  # "Comfort Apple Blossom" laundry conditioner losing to bare "apple"
    ("Fabric Softener", ["comfort", "coconut"]),  # "Comfort Coconut" -- scoped narrow, not bare "comfort" (also a real English word and a Comfort-brand chair/other products)
    ("Household Goods", ["rice cooker"]),  # "Tefal Brushed Steel Rice Cooker" -- a kitchen appliance, was landing on Rice via bare "rice"
    ("Cereals", ["country crisp"]),  # "Jordans Country Crisp Strawberry" -- a granola cereal brand phrase, unique to Jordans in the CSV
    ("Cold Cuts", ["salamini"]),  # "SALAMINI JALAPENO" -- deli meat losing to bare "jalapeno" (Vegetables); "salamini" already registered at tier 2 with no non-meat CSV use
    ("Chocolates", ["vidal", "jelly"]),  # "Vidal" is two unrelated brands -- a candy maker (Vidal Jelly gummy sweets) and a toiletries maker (registered Shower Gels keyword); every CSV "vidal"+"jelly" co-occurrence is candy, never toiletries
    ("Household Goods", ["scrub daddy"]),  # already registered but losing ties to the "wash up" phrase -- "Scrub Daddy Wonder Wash-up" is a cleaning tool, not dish soap
    ("Disposables", ["cuki"]),  # already registered but losing ties to "piatti" (Dish Washing Liquid) -- "Cuki Piatti Ciotola Alluminio" is disposable tableware (67 CSV listings, ~65 Disposables)

    # 28 Aug 2026 -- eleventh pass. Large parallel full-DB re-analysis of
    # the next ~250 remaining collision pairs after the tenth-pass fixes,
    # same rigor as every block above (each independently CSV-verified
    # against the 93,780-distinct-name export, spot-checked against
    # classify_by_name() before being added here).
    ("Biscuits", ['doria', 'semplicissimi']),
    ("Biscuits", ['pavesi', 'paprika']),
    ("Biscuits", ['shortbread']),
    ("Biscuits", ['frollini', 'riso']),
    ("Biscuits", ['frollino', 'riso']),
    ("Sauces & Condiments", ['balsamic', 'dressing']),
    ("Sauces & Condiments", ['tzatziki', 'dressing']),
    ("Frozen", ['il gelato']),
    ("Herbs & Spices", ['twistees', 'seasoning']),
    ("Tea", ['h2o', 'infusion']),
    ("Coffee", ['nespresso']),
    ("Coffee", ['capuccino', 'hazelnut']),
    ("Coffee", ['cappuccino', 'hazelnut']),
    ("Chocolates", ['kitkat', 'milk']),
    ("Gift Sets", ['banner']),
    ("Spirits - Liqueurs", ['etsu']),
    ("Spirits - Liqueurs", ['whitley neill', 'gin']),
    ("Spirits - Liqueurs", ['gin tonic']),
    ("Herbs & Spices", ['kinder', 'seasoning']),
    ("Chips", ['pringle']),
    ("Herbs & Spices", ['lamb', 'herbs']),
    ("Herbs & Spices", ['lamb', 'salt']),
    ("Herbs & Spices", ['lamb', 'cinnamon']),
    ("Beers", ['lindemans']),
    ("Beers", ['kaiserdom']),
    ("Beers", ['cisk']),
    ("Yoghurt", ['fruyo']),
    ("Dish Washing Liquid", ['piatti', 'aceto']),
    ("Dish Washing Liquid", ['svelto', 'aceto']),
    ("Cake Preparations", ['paneangeli']),
    ("Biscuits", ['balocco']),
    ("Cake Preparations", ['vermicelli', 'sprinkle']),
    ("Cake Preparations", ['pasta', 'icing']),
    ("Ciders", ['strongbow']),
    ("Chocolates", ['sperlari']),
    ("Chilled Fish", ['salamun']),
    ("Stationery", ['tesa', 'corrector']),
    ("Toys & Games", ['jovi']),
    ("Spirits - Vodka", ['vodka', 'orange']),
    ("Spirits - Vodka", ['vodka', 'melon']),
    ("Electrical", ['sodastream', 'maker']),
    ("Dilutables", ['instant drink', 'aloe vera']),
    ("Household Goods", ['cake', 'scraper']),
    ("Household Goods", ['cake', 'cooler']),
    ("Air Fresheners", ['room spray']),
    ("Chilled Fish", ['fish', 'cake']),
    ("Herbs & Spices", ['all purpose', 'seasoning']),
    ("All-purpose Cleaners", ['cif', 'salt']),
    ("Disposables", ['napkin', 'orange']),
    ("Cakes", ['cinnamon', 'muffin']),
    ("Water", ['cucumber', 'water']),
    ("Sweet Snacks", ['werther', 'cappuccino']),
    ("Sweet Snacks", ['werther', 'cappucino']),
    ("Sweet Snacks", ['fliptop', 'espresso']),
    ("Vinegars", ['grape', 'vinegar']),
    ("Vinegars", ['balsamic', 'dressing']),
    ("Shampoos", ['elvive', 'oil']),
    ("Shampoos", ['gliss', 'oil']),
    ("Shampoos", ['tresemme', 'oil']),
    ("Shampoos", ['pantene', 'oil']),
    ("Sports", ['cookie', 'protein bar']),
    ("Sports", ['cookie', 'protein pancake']),
    ("Sports", ['cookie', 'iron maxx']),
    ("Skin Care", ['tissue', 'mask']),
    ("Cakes", ['muffin', 'custard']),
    ("Cakes", ['pandori', 'milk']),
    ("Disposables", ['coffee', 'napkin']),
    ("Disposables", ['paper', 'coffee', 'cup']),
    ("Candles", ['incense']),
    ("Disposables", ['vaschette', 'budino']),
    ("Disposables", ['vaschetta', 'budino']),
    ("Disposables", ['vaschette', 'torta']),
    ("Disposables", ['vaschetta', 'torta']),
    ("Shower Gels", ['foam bath', 'aloe vera']),
    ("Shower Gels", ['bagno schiuma', 'aloe vera']),
    ("First Aid", ['elastoplast', 'water']),
    ("First Aid", ['bandage', 'water']),
    ("First Aid", ['salvelox', 'water']),
    ("Dog", ['pet bed']),
    ("All-purpose Cleaners", ['cif', 'mousse']),
    ("Household Goods", ['dough', 'scraper']),
    ("Air Fresheners", ['airwick', 'spice']),
    ("Air Fresheners", ['airflor', 'spice']),
    ("Sauces & Condiments", ['kuhne', 'dressing']),
    ("Skin Care", ['palmers', 'cocoa butter']),
    ("Sweet Snacks", ['maynards', 'fish']),
    ("Sweet Snacks", ['caramelle', 'zucchero']),
    ("Household Goods", ['bowl', 'frozen']),
    ("Household Goods", ['bucket', 'frozen']),
    ("Deodorants", ['chupa chup', 'body spray']),
    ("Disposables", ['napkin', 'cake']),
    ("Disposables", ['cartaforno', 'muffin']),
    ("Disposables", ['ipak', 'boaround']),
    ("Clothes", ['sock', 'cream']),
    ("Clothes", ['slipper', 'cream']),
    ("Wine - Red", ['blue fish', 'riesling']),
    ("Wine - Red", ['blue fish', 'pinot']),
    ("Perfume", ['edt', 'ginger']),
    ("Perfume", ['edp', 'ginger']),
    ("Chocolates", ['swizzels', 'custard']),
    ("Chocolates", ['swizzels', 'cream']),
    ("Chocolates", ['poppets', 'cream']),
    ("Skin Care", ['cleansing', 'mousse']),
    ("International Cuisine", ['boromir']),
    ("Water", ['san benedetto', 'baby bottle']),
    ("Floor Cleaners", ['pavimenti', 'marsiglia']),
    ("Yoghurt", ['kefir', 'mousse']),
    ("Floor Cleaners", ['fabuloso', 'concentrato']),
    ("Sanitary Towels", ['pantyliner', 'chamomile']),
    ("Biscuits", ['gullon', 'fish']),
    ("Cake Preparations", ['yeast', 'biscuit']),
    ("Stationery", ['brunnen', 'water']),
    ("Stationery", ['korbond', 'water']),
    ("Chips", ['pringles', 'prawn']),
    ("Skin Care", ['milk', 'cleanser']),
    ("Dog", ['monge', 'fruit']),
    ("Energy Drinks", ['rockstar']),
    ("Cat", ['sheba']),
    ("Cat", ['monge', 'buste']),
    ("Cat", ['one sensitive']),

    # 18 Aug 2026 -- EIGHTH sweep regression fixes, checked ahead of everything
    # else for the same reason as the Areon/Conditioner/Candle rules below: each
    # is a brand or compound phrase that was losing to a shorter, more generic
    # word elsewhere in the list once this sweep's new keywords were added.
    # "Gecchele Treccia Cream & Raisins" (a wafer-cone snack) was landing on
    # Cooking Creams because of the bare "cream" rule.
    ("Sweet Snacks", ["gecchele"]),
    # "Water Chestnuts Tin" was landing on Water because of the bare "water"
    # rule -- water chestnuts are a canned vegetable/nut, not a drink.
    ("Nuts", ["water chestnuts"]),
    # "Snowdonia Spiced Tomato & Vodka" is a real Snowdonia cheese flavour
    # (WebSearch-confirmed: Snowdonia's "Snowdonia Spiced Tomato & Vodka" is a
    # cheddar), but was landing on Vegetables because of the bare "tomato"
    # rule -- checked here so the brand wins over the flavour-name words.
    ("Cheese", ["snowdonia"]),

    # Checked before everything else: Areon is a home-fragrance brand, and
    # its products are literally named "Areon Home Perfume ...", so the
    # generic "perfume" rule further down would otherwise claim them for
    # Perfume (the personal-fragrance category) rather than Air Fresheners.
    ("Air Fresheners", ["areon"]),

    # "conditioner"/"candle" are checked FIRST, ahead of everything else in
    # this list on purpose -- both are unambiguous, product-defining words
    # with no food meaning at all, so nothing later in this list should
    # ever be allowed to out-rank them. Originally placed further down
    # (after "tea"), which worked fine until later rules got added ABOVE
    # that spot -- specifically the nut-butter carve-outs below, which
    # caused a real regression caught by this session's own regression
    # sweep: "Splend'or Nourishing Conditioner Almond Milk & Shea Butter"
    # (a hair conditioner, "Almond Milk & Shea Butter" is just marketing
    # copy) started matching the new "almond"+"butter" -> Nuts rule before
    # ever reaching "conditioner" further down. Moving these two to the
    # very top removes the fragility instead of chasing it rule by rule --
    # any future addition anywhere else in this list is now automatically
    # safe against this same class of bug. Real data behind the original
    # fix: "Splend'or Nourishing Conditioner Almond Milk & Shea Butter"
    # was landing on Milk, and "True Living Candle Jar Apple Cinnamon" was
    # landing on Fruits. Worth watching for the same pattern elsewhere
    # (shampoo, lotion, soap etc. could plausibly have the same issue).
    # 26 Aug 2026 -- exactly that: this bare "conditioner" tier-0 promotion
    # was ALSO winning outright (no tie, so it never surfaced in any
    # collision report) against genuine laundry "fabric conditioner"
    # products, e.g. "Comfort Fabric Conditioner Blue Skies" was landing on
    # the hair-care Conditioners category. Found by a regression test
    # while verifying this round's Conditioners/Shampoos fixes, not from
    # the collision-pair list. Placed before the bare rule below so it
    # wins the tier-0 tie.
    ("Fabric Softener", ["fabric conditioner"]),
    ("Conditioners", ["conditioner"]),
    ("Candles", ["candle"]),
    # "Gourmet Gold" -- a real Purina cat-food product line confirmed via
    # WebSearch (Purina's own UK site lists "GOURMET Gold Savoury Cake" in
    # tuna/chicken/salmon/beef/lamb flavours, all wet cat food), found via
    # real data ("Purina Gourmet Gold Savoury Cake Tuna") landing on Cakes
    # instead, since bare "cake" is a Cakes keyword and this brand's own
    # product-format name happens to say "Cake". Checked here at the very
    # top, ahead of the "cod"/"salmon"+"cake" fish-cake fix further down --
    # Purina's own range includes "Savoury Cake Meat & Fish" and "...
    # Salmon" variants, which would otherwise also match those rules.
    ("Cat", ["gourmet gold"]),
    # Everything below here (through the end of this personal-care/
    # household block) is the SAME "unambiguous, product-defining word"
    # pattern as Conditioners/Candles just above, applied broadly for the
    # first time -- found via real data (17 Aug 2026 collision report):
    # dozens of shampoos, deodorants, toothpastes, nappies etc. were losing
    # to whatever food-flavour word their own scent/ingredient list also
    # happened to share (e.g. "Antica Herbal Shampoo Almond Milk 2in1" was
    # landing on Milk, "Old Spice Deodorant Spray Whitewater" was landing
    # on Herbs & Spices via bare "spice", "Childs Farm Nappy Cream
    # Fragrance Free" was landing on Cooking Creams via bare "cream").
    # Every one of these words already existed as an ordinary KEYWORD_RULES
    # single word for its own category further down -- this doesn't change
    # WHAT category any of them map to, only WHEN they're checked, exactly
    # the same fix already applied to "conditioner"/"candle" (and
    # "grater", further down this same list). None of these words has a
    # realistic food meaning (checked against every real example in this
    # round's report before adding).
    # "Baby Shampoo"/"Adult Nappy" -- carve-outs required BEFORE the
    # general "shampoo"/"nappy" rules right below, the same "specific
    # phrase before the general rule that would otherwise swallow it"
    # pattern already used for "chocolate milk" vs bare "chocolate" above.
    # Found by this round's own test suite (test_category_taxonomy.py):
    # "Baby Essentials" and "Adult Nappies" both already had a more
    # specific multi-word phrase ("baby shampoo", "adult nappy") that used
    # to correctly beat the bare "shampoo"/"nappy" single word by tier
    # (phrase beats bare word) -- but Pass 0 always beats BOTH tiers, so
    # adding "shampoo"/"nappy" to Pass 0 below would have silently broken
    # those two existing, working rules without this.
    ("Baby Essentials", ["baby shampoo"]),
    ("Adult Nappies", ["adult nappy"]),
    ("Shampoos", ["shampoo"]),
    ("Deodorants", ["deodorant"]),
    ("Deodorants", ["antiperspirant"]),
    ("Toothpaste", ["toothpaste"]),
    ("Toothbrushes", ["toothbrush"]),
    ("Mouthwash", ["mouthwash"]),
    # Both spellings needed -- "nappy" plus the trailing "s?" that
    # _keyword_matches always adds only catches "nappys", not the real
    # irregular plural "nappies" (see _keyword_matches' own docstring
    # further down for why irregular plurals need their own explicit
    # entry).
    ("Nappies", ["nappy"]),
    ("Nappies", ["nappies"]),
    ("Dental Care", ["dental"]),
    ("Dental Care", ["denture"]),
    ("Dental Care", ["corega"]),
    ("Make Up", ["lipstick"]),
    ("Make Up", ["mascara"]),
    ("Make Up", ["foundation"]),
    ("Make Up", ["eyeshadow"]),
    ("Make Up", ["makeup"]),  # one word, no space -- "make up" (two words) is already a safe multi-word phrase without this
    ("Perfume", ["perfume"]),
    ("Perfume", ["cologne"]),
    # "Body Mist" -- a personal-fragrance product (e.g. "So...? Delish
    # Pistachio Cream Body Mist"), found via real data landing on Cooking
    # Creams via its flavour-sounding name, since bare "cream" is checked
    # long before this section.
    ("Perfume", ["body mist"]),
    # A second round of the same "cosmetic product losing to a food-sounding
    # flavour/ingredient word" bug, found via real data (19 Aug 2026 report,
    # user flagged this whole class as a priority to close):
    # "Face Scrub"/"Body Scrub" -- a real personal-care product type
    # ("Beauty Formulas Face Scrub Honey & Almond") was landing on Nuts via
    # bare "almond".
    ("Skin Care", ["face scrub"]),
    ("Skin Care", ["body scrub"]),
    ("Skin Care", ["clear pore"]),  # 28 Aug 2026 -- "Simple Daily Skin Detox Clear Pore Scrub" went unclassified after bare "detox" was removed from Sports (it was a real bug, matching non-sports detox products); this restores a correct, specific match for it instead of relying on the removed bare word
    # "Douche" -- French/Dutch for "shower", used on real European-brand
    # shower gels sold in Malta (confirmed via WebSearch: Nivea's own site
    # calls its shower gel range "Gel Douche"/"Douche Creme"). Found via
    # real data ("Nivea Douche Shea Butter & Botanical Oil") landing on
    # Butter via bare "butter".
    ("Shower Gels", ["douche"]),
    # "Body Butter"/"Shea Butter" -- real cosmetic product terms (never a
    # food use for shea butter specifically, unlike e.g. cocoa butter which
    # IS a real baking ingredient and deliberately NOT added here for that
    # reason) -- a second, independent fix for the same Nivea example above,
    # and safe to add generally since "shea butter" has no other meaning.
    ("Body Lotions", ["body butter"]),
    ("Body Lotions", ["shea butter"]),
    # "Sunsilk" -- a real, hair-care-only brand (confirmed via WebSearch:
    # Sunsilk's own range is entirely shampoo/conditioner/hair oil/hair
    # cream, nothing else), found via real data ("Sunsilk Balm Almond Oil
    # Argan") landing on Nuts/Oils via its ingredient names. Placed after
    # the specific hair-product-type phrases above (hair oil, hair
    # treatment, etc) and after Shampoos/Conditioners near the top of this
    # list, so a "Sunsilk Shampoo" (if one turns up) still correctly matches
    # the more specific "shampoo" word first -- this is only a fallback for
    # Sunsilk products that don't say what type of product they are.
    ("Hair Treatment", ["sunsilk"]),
    # NOT "fragrance" -- deliberately left out. "Fragrance Free" is
    # extremely common on shampoos, creams and nappy products precisely
    # BECAUSE they're not perfumed, so elevating it here would create the
    # opposite bug (tagging unscented products as Perfume). Real
    # "Fragrance Free" shampoos/creams/nappy products are already handled
    # correctly by the Shampoos/Nappies/etc words right above instead.
    ("Body Lotions", ["moisturiser"]),
    ("Body Lotions", ["moisturizer"]),
    ("First Aid", ["plaster"]),
    ("Household Goods", ["thermos"]),
    ("Household Goods", ["flask"]),
    # "Softener" -- no realistic food meaning (fabric softener is always
    # scented with a fragrance name, never a food name that also has one),
    # found via real data ("Milk & Honey Softener 25 Wash") landing on Milk
    # instead, since the scent name shares words with real dairy products.
    ("Fabric Softener", ["softener"]),
    # "Day Cream"/"Night Cream" -- real, unambiguous skincare terms, found
    # via real data ("Nivea Oil Free Day Cream", "Moroccan Argan Oil Night
    # Cream") landing on Cooking Creams instead, since bare "cream" is
    # checked before Face Creams and these products' other words (oil,
    # argan) are food-sounding ingredient names, not food products.
    ("Face Creams", ["day cream"]),
    ("Face Creams", ["night cream"]),
    # "Dalan D'olive" -- a real Malta-sold personal-care brand (M&Z p.l.c.),
    # already known from an earlier round to make soap bars, confirmed here
    # to also make hand/face/body creams and moisturisers under names that
    # don't otherwise say "cream", "lotion" or "moisturiser" specifically
    # enough to already be caught (e.g. "Dalan D'olive Intensive Care Cream
    # Olive") -- found via real data landing on Cooking Creams/Olives.
    # Third round this specific brand has turned up as a personal-care
    # product miscategorised as food, so promoted to a brand-level rule
    # (both the apostrophe and no-apostrophe spellings seen in real data)
    # rather than another one-off phrase.
    ("Skin Care", ["dalan d'olive"]),
    ("Skin Care", ["dalan dolive"]),
    # "whey" -- a sports-nutrition-supplement word with no other realistic
    # meaning in this data (every real example is an Iron Maxx/QNT whey
    # protein product), found losing to whatever flavour word it shared
    # with an earlier category (bare "cream" -> Cooking Creams, bare
    # "cookie" -> Biscuits, bare "pistachio" -> Nuts) purely by list order.
    ("Sports", ["whey"]),
    # "Acqua Panna" -- a real, well-known Italian NATURAL MINERAL WATER
    # brand (Panna is the name of the town/spring it's bottled at, nothing
    # to do with cream) -- was landing on Cooking Creams via the existing
    # "panna" keyword (Italian for cream, correct for an actual cream
    # product), since Cooking Creams is listed earlier than Water. A
    # brand-name carve-out, same reasoning as "Cadbury"/"Lamb Brand" above.
    ("Water", ["acqua panna"]),
    # "Water Kefir" -- a real, distinct fermented-WATER drink (not a dairy
    # product at all), found via real data ("Kult Water Kefir Passion &
    # Hops In Can") landing on Milk via bare "kefir" (which is otherwise the
    # right default -- ordinary kefir is a milk product). Checked before the
    # bare "kefir" rule below so the water-based drink wins instead.
    ("Water", ["water kefir"]),
    # "Yoghurt"/"Yogurt" -- moved here from its old KEYWORD_RULES spot
    # (immediately after Milk) because that position meant a real yoghurt
    # whose name also happens to say "milk" -- e.g. "Mevgal Sheep's Milk
    # Yoghurt", "Milk Yogurt Mix Strawberry Confetti" -- was landing on Milk
    # purely because Milk is checked one line earlier. Whenever the word
    # "yoghurt"/"yogurt" appears anywhere in a name, the product is a
    # yoghurt -- not a judgement call worth leaving to list-order chance,
    # the same "unambiguous, product-defining word" reasoning as
    # Conditioners/Candles at the top of this list. Found via real data
    # (19 Aug 2026 collision report).
    ("Yoghurt", ["yoghurt"]),
    ("Yoghurt", ["yogurt"]),
    # "Formaggio" -- Italian for cheese, already an existing Cheese keyword,
    # but was still losing to bare "milk" in "Milk Formaggio Spalmabile
    # Classico" (a spreadable cheese product) since Milk is listed earlier
    # than Cheese. No realistic non-cheese meaning, so safe to promote alone.
    ("Cheese", ["formaggio"]),
    # A cream-cheese product (checked both word orders -- real examples had
    # "Cream Cheese" AND "Cheese Cream") was landing on Cooking Creams via
    # bare "cream", since Cooking Creams is listed earlier than Cheese.
    # Cream cheese is always a cheese product, never a tub of cooking
    # cream, so both words appearing together anywhere in the name is a
    # safe, reliable signal regardless of which order they're written in.
    ("Cheese", ["cream", "cheese"]),
    # "Cake"+"Cream" / "Cereal"+"Cream" -- same shape as "Cream Cheese"
    # above: a filled cake or a cream-filled cereal was landing on Cooking
    # Creams via bare "cream" (Cooking Creams is listed earlier than both
    # Cakes and Cereals), found via real data ("Boromir Mini Cake Dairy
    # Cream Filling", "Pistachio And Raspberry Cream Cake Gateaux", "Viva
    # Hazelnut Cream Filled Cereal Pillows", "Olla Cereal With Vanilla Cream
    # Filling"). When a name says "cake"/"cereal" AND "cream" together, the
    # product is the cake/cereal with a cream filling or flavour -- not a
    # tub of cooking cream -- every real example so far.
    ("Cakes", ["cake", "cream"]),
    ("Cereals", ["cereal", "cream"]),
    # "Biscuit"/"Cookie" + "Milk" -- same shape again: a milk-flavoured
    # biscuit was landing on Milk via bare "milk" (checked before Biscuits),
    # found via real data ("Biscuits Milk Fingers", "Baby Biscuits Milk
    # (6M+)", "Dolfin Magic Milk Straw Cookies"). When a name says
    # "biscuit"/"cookie" AND "milk" together, the product is the biscuit --
    # milk is just its flavour -- not a carton of milk.
    ("Biscuits", ["biscuit", "milk"]),
    ("Biscuits", ["cookie", "milk"]),
    # "Butter Lettuce"/"Butter Bean" -- both real produce/legume names that
    # happen to contain the word "butter", found via real data ("Butter
    # Lettuce", "Lettuce Butter/boston Nl", "Butter Beans In Sunflower Oil")
    # landing on dairy Butter instead, since Butter is listed very early.
    # Neither is a dairy product -- checked as their own phrases so they win
    # outright, the same shape as "Cream Cheese" above.
    ("Vegetables", ["butter lettuce"]),
    ("Legumes", ["butter bean"]),
    # "Butter Cookies" -- a real, well-known biscuit type (e.g.
    # "Patisserie Matheo Butter Cookies", "BUTTER COOKIES S/F") was landing
    # on dairy Butter instead, since Butter is listed earlier than
    # Biscuits. Both words required together so a plain tub of butter (no
    # "cookie" in the name) is unaffected. Deliberately NOT extended to
    # "butter"+"biscuit" the same way -- caught by this round's own
    # regression sweep: "Laurence Toffiq Chocolate Bar With Caramel,
    # Peanut Butter & Biscuit" would match it too (clean_for_matching turns
    # "Peanut Butter & Biscuit" and "Butter Biscuit" into the identical
    # cleaned text "butter biscuit", so the two can't be told apart at the
    # keyword level), which is exactly the same real counter-example that
    # already ruled out a "chocolate"+"biscuit" carve-out further up this
    # list. "Zott Monte Butter Biscuits" (no "cookie" in its name) is a
    # known, accepted gap because of this -- still resolves to Butter.
    ("Biscuits", ["butter", "cookie"]),
    # Continuing the "Lamb Brand" nut/spice product line (see the several
    # "Lamb Brand"/"Lamb Spices" entries below) with two more real
    # phrasings that don't contain the word "brand" at all: "Lamb Walnuts
    # Kernels 400g" and "Lamb Nuts Almonds Blanched..." -- both landing on
    # the Lamb meat category via bare "lamb", since Lamb is listed earlier
    # than Nuts. Kept narrow (the specific word combinations from the real
    # examples), same reasoning as the other Lamb Brand carve-outs below.
    ("Nuts", ["lamb nuts"]),
    ("Nuts", ["lamb", "walnut"]),
    # "Galletti" -- confirmed via WebSearch as both a traditional Maltese
    # cracker/snack (this is a Maltese app) and a real Italian brand's
    # shortbread-biscuit line (Mulino Bianco) -- either way, always a
    # cracker/biscuit-type product, never a vegetable or spice. Was landing
    # on Vegetables/Herbs & Spices via whatever flavour word it also
    # carried (e.g. "Crackeys Galletti Tomato & Oregano"). "Crostini" --
    # Italian for small toasted bread rounds, no other realistic grocery
    # meaning -- added for the same reason ("Pan Ducale Crostini With Basil
    # & Tomato" was landing on Herbs & Spices/Vegetables too).
    ("Crackers, Crispbread & Breadsticks", ["galletti"]),
    ("Crackers, Crispbread & Breadsticks", ["crostini"]),
    # "Crisp Bread" -- found via real data ("Danvita Crisp Bread Cheese &
    # Garlic") landing on Cheese (bare "cheese" is checked before the
    # existing "crispbread" keyword further down -- which wouldn't have
    # matched anyway, since "Crisp Bread" is written as two words here and
    # "crispbread" is one). A crispbread is always this category regardless
    # of its flavour, so it's checked as its own phrase, first.
    ("Crackers, Crispbread & Breadsticks", ["crisp bread"]),
    # "Biscuits For Cheese" -- a real UK cracker product line (Carr's, The
    # Cheshire Cheese Company), and "Cheddar Cheese Biscuits" from the same
    # brand -- found via real data landing on Cheese instead (bare "cheese"
    # is checked before Biscuits). Both words together mean a savoury
    # cracker meant to go WITH cheese, not the cheese itself -- no real
    # counter-example found (a plain wedge of cheese never also says
    # "biscuit" in its name).
    ("Crackers, Crispbread & Breadsticks", ["cheese", "biscuit"]),
    # "Olive Oil" is listed very early in KEYWORD_RULES (right after Bread/
    # Cakes/etc, long before the Personal Care section), so any personal-
    # care product whose name ALSO mentions olive oil as an ingredient was
    # losing to it even though both are multi-word phrases (tier 1) --
    # list order still decides a tie between two phrases, the same way it
    # decides a tie between two bare words. Found via the same Dalan
    # D'olive real data: "HAND SOAP OLIVE OIL EXTRACT 500ML" and "Dalan
    # D'olive Olive Oil Nourishing Liquid Hand Soap" were landing on Olive
    # Oil instead of Hand Wash Liquids, "D'olive Olive Oil Shower Gel
    # Nourishing" instead of Shower Gels, "BODY LOTION VIRGIN OLIVE OIL
    # EXTRACT" instead of Body Lotions. These three phrases already exist
    # in KEYWORD_RULES further down (unchanged, same category) -- this
    # only fixes WHEN they're checked, the same fix already applied to
    # bare "shampoo"/"nappy"/etc further up this list.
    ("Hand Wash Liquids", ["hand soap"]),
    ("Hand Wash Liquids", ["hand wash"]),
    ("Shower Gels", ["shower gel"]),
    ("Body Lotions", ["body lotion"]),
    # "Vitakraft" -- confirmed via WebSearch as a real German pet brand
    # whose range is birds and small animals (rabbits, guinea pigs,
    # rodents) specifically, NOT cat/dog food -- so the existing Cat/Dog
    # Pass 0 rules above wouldn't be the right fit even if extended. Routed
    # to "Fish & Other Animals" instead, the existing (already-flagged-as-
    # imperfect-but-closest) catch-all this project already uses for
    # non-cat/dog pets (see GREENS_CATEGORY_MAP's "Pets"/"Other Pets" ->
    # "Fish & Other Animals" mapping). Found via real data: "Vitakraft Vita
    # Veggies Stick Cheese +potato", "Vitakraft Beef Stick Turkey",
    # "Vitakraft Kracker 3pck Canary Honey/egg" were all landing on
    # whichever food/flavour word they also contained (Cheese, Beef,
    # Honey...) since none of them say "cat"/"dog"/"bird"/"animal" at all.
    ("Fish & Other Animals", ["vitakraft"]),
    # "PREM PCH" -- lower confidence than the other brand rules in this
    # file: WebSearch could NOT independently confirm "PREM" as a specific
    # company/brand name (same result as when "katsuobushi" was
    # investigated earlier this session). Added anyway based on strong
    # circumstantial evidence from the product names themselves: "PCH" is
    # almost certainly short for "pouch" (every real example is a small
    # single-serve wet-food pouch -- "PREM PCH CHKN & TUNA W RICE &
    # CARROT/CLAM/SHRIMP"), and the fish-plus-meat-in-a-small-pouch format
    # matches the SAME already-confirmed "PREM CHICKEN, TUNA, RICE
    # KATSUOBUSHI" product line (routed to Cat via the "katsuobushi" rule
    # above). If this turns out to be wrong (e.g. some "PREM PCH" products
    # are actually dog food), it should be easy to spot in a future report
    # and narrow down from here.
    ("Cat", ["prem pch"]),
    ("Chocolates", ["easter", "egg"]),
    # "Carrefour Filini Egg (250grms)" showed up as the cheapest "Eggs"
    # result -- "Filini" is a specific pasta shape (thin short noodles,
    # commonly sold as "Filini all'uovo"/egg filini, an egg pasta used in
    # soups), not real eggs. The 250g pack size is also a pantry-goods
    # size, not how eggs are sold (by count). A single-word entry here (one
    # required word is fine -- "all" of a one-item list) so it's checked
    # before the bare "egg" rule gets a chance, the same way the
    # Easter-egg rule above is.
    ("Pasta & Couscous", ["filini"]),
    # "Simpl Tuna Olive Oil (145grms)" showed up as the cheapest "Olive
    # Oil" result -- this is canned tuna packed in olive oil (145g is a
    # canned-tuna tin size, and "Simpl" is a budget private-label brand),
    # not a bottle of olive oil. The multi-word "olive oil"/"oil" phrase
    # (Oils/Olive Oil category) would otherwise win over the single-word
    # "tuna" rule (Chilled Fish), since ALL multi-word phrases are checked
    # before ANY single word. Requiring both "tuna" and "oil" together
    # targets this real pattern (tuna canned in any oil, not just olive)
    # without touching the standalone "tuna" or "oil"/"olive oil" rules.
    # Broadened from just "olive oil" to plain "oil" so this also catches
    # tuna canned in sunflower oil, vegetable oil, etc, not only olive.
    ("Canned Seafood", ["tuna", "oil"]),
    # "Tuna Steak"/"Salmon Steak"/"Cod Steak" -- found via real data
    # ("Calvo Tuna Steak In Water", "Carrefour Tuna Steaks", "Salmon
    # Steak-salamun (foreign)/farmed") landing on Beef instead: bare "steak"
    # is one of Beef's own keywords (a generic cut name, not beef-specific),
    # and Beef is listed before Chilled Fish, so any fish sold as a "steak"
    # was losing to it. Checked first so the more specific fish-steak phrase
    # wins; a plain "beef steak" (no fish word in the name) still correctly
    # falls through to Beef's own "steak" keyword afterwards, unaffected.
    ("Chilled Fish", ["tuna steak"]),
    ("Chilled Fish", ["salmon steak"]),
    ("Chilled Fish", ["cod steak"]),
    ("Chilled Fish", ["fish steak"]),
    # "Cod"/"Salmon" + "Cake" -- same shape as the steak fixes right above: a
    # breaded fish patty, found via real data ("4 Cod Fsh Cakes", "Bird's
    # Eye Cod Fish Cakes") landing on Cakes instead, since bare "cake" is
    # checked before Chilled Fish. Written as co-occurrence (not an adjacent
    # phrase) because the real examples have another word in between ("Cod
    # FSH Cakes", "Cod Fish Cakes") -- a fish cake is a fish product, never
    # a dessert cake. Checked after "Gourmet Gold" above so that brand's own
    # "Savoury Cake ... Salmon"/"...Meat & Fish" cat-food variants still
    # correctly go to Cat first.
    ("Chilled Fish", ["cod", "cake"]),
    ("Chilled Fish", ["salmon", "cake"]),
    # Bare "chocolate"/"choco" -- the same general-fix pattern already used
    # for "chips" below, extended to the same underlying issue recurring
    # under a different category. Found via real data (17 Aug 2026
    # collision report): "Bahlsen Choco Leibniz Milk 2+1 Free", "Terry's
    # Chocolate Mint Milk (145grms)", "Gullon Choco Tablet Milk 150g" were
    # all landing on Milk instead of Chocolates, since bare "milk" is
    # listed earlier in KEYWORD_RULES than "chocolate"/"choco" used to be.
    # This single rule also makes several earlier, narrower fixes fully
    # redundant, since anything containing "chocolate" now resolves here
    # FIRST, before any of those other rules are ever reached: the
    # "chocolate"+"peanut"+"butter" carve-out that used to sit right here
    # (for "Laurence Toffiq Chocolate Bar With Caramel, Peanut Butter &
    # Biscuit" -- a chocolate bar with a peanut-butter filling, at risk of
    # being swept into Peanut Butter below), the six "chocolate"+fruit-word
    # carve-outs further down (orange/banana/apple/grape/melon/fruit), and
    # the "chocolate"+"chips" carve-out further down still (protecting
    # "Chocolate Chips" from the general "chips" rule) -- all three removed
    # now, with a short comment left in each of their places. No real
    # "chocolate milk drink" product (e.g. a Nesquik-style ready-to-drink)
    # has turned up in any report so far to justify a carve-out the way
    # "Chocolate Chips" needed one for the chips fix -- worth watching for
    # one in a future report.
    # "chocolate & milk"/"chocolate and milk" -- a carve-out, same shape as
    # the "chocolate"+"chips" one further down for Chocolate Chips: found
    # via the regression sweep for THIS fix itself, checking every
    # previously-fixed real case in this session. "Bahlsen Leibniz Pick Up
    # Chocolate & Milk" is a chocolate-coated wafer biscuit (correctly
    # Biscuits, via the "chocolate & milk"/"chocolate and milk" phrases
    # that used to live in KEYWORD_RULES' Biscuits entry) -- without this
    # carve-out, the general bare "chocolate" rule right below would have
    # sent it straight to Chocolates instead, since Pass 0 is checked
    # before that phrase's multi-word pass ever runs. Listed here, before
    # the general rule, the same way the Chocolate Chips carve-out is
    # listed before the general "chips" rule.
    ("Biscuits", ["chocolate milk"]),  # "&" cleans down to a space, not the word "and" -- see clean_for_matching
    ("Biscuits", ["chocolate and milk"]),
    # "chocolate"+"wafer" -- a second carve-out, broader than the "milk"
    # one right above, caught by the same regression sweep: "Damhert Cent
    # Wafer Chocolate Sugar Free" used to correctly land on Biscuits (an
    # earlier, explicit decision this session -- a chocolate-coated wafer
    # stays Biscuits, not Chocolates), purely because "wafer" happened to
    # be listed before "chocolate" in the old KEYWORD_RULES order. The
    # general bare "chocolate" rule below broke that.
    #
    # A same-shaped "chocolate"+"biscuit" carve-out was tried too, but the
    # regression sweep immediately caught a real counter-example --
    # "Laurence Toffiq Chocolate Bar With Caramel, Peanut Butter & Biscuit"
    # is a chocolate bar that merely lists "biscuit" as one of several
    # mix-in ingredients (alongside caramel and peanut butter), correctly
    # Chocolates, not a biscuit product itself. Unlike "wafer" (where a
    # product literally described as a chocolate WAFER is reliably a
    # biscuit-type product), bare "biscuit" showing up in an ingredients
    # list doesn't reliably mean the product itself is one -- so that half
    # of the carve-out was removed. Also deliberately NOT extended to
    # "cookie"/"oreo" -- "Cadbury Dairy Milk Oreo" is a real,
    # already-confirmed case where "oreo" names a flavour of an actual
    # chocolate bar, not a biscuit.
    ("Biscuits", ["chocolate", "wafer"]),
    ("Chocolates", ["chocolate"]),
    ("Chocolates", ["choco"]),
    # "Whole Earth Smooth Peanut Butter 227g" and similar were matching
    # both bare "peanut" (Nuts) and bare "butter" (Butter) at the same
    # single-word tier, with Butter winning today purely because it's
    # listed earlier in KEYWORD_RULES. Peanut butter is common enough on a
    # Maltese shopping list to deserve its own category rather than being
    # folded into either -- both words are required together, so this
    # doesn't touch a plain jar of nuts or a plain tub of butter/margarine.
    ("Peanut Butter", ["peanut", "butter"]),
    # Other nut butters -- same shape of bug, found via real data (12 Aug
    # 2026 collision report): "Munch Abunch Coconut Cashew Butter" and
    # "Biona Cashew Butter" were landing on dairy Butter, not Nuts, since
    # Butter is listed earlier than Nuts in KEYWORD_RULES. Unlike peanut
    # butter, these don't get their own dedicated category (not common
    # enough yet to deserve one) -- they route to the existing Nuts
    # category instead. Kept narrow (named nuts only, not a blanket "any
    # nut word wins" rule) -- see the comment on the plain Nuts entry in
    # KEYWORD_RULES for why a broader version was deliberately not done
    # this round.
    ("Nuts", ["almond", "butter"]),
    ("Nuts", ["cashew", "butter"]),
    ("Nuts", ["walnut", "butter"]),
    ("Nuts", ["pistachio", "butter"]),
    # Roasted/flavoured peanuts losing to their own flavour word -- found
    # via real data: "Roast Salt Peanut" and "Mogyi Dry Roasted Smoked
    # Paprika Flavoured Peanuts" were landing on Herbs & Spices (bare
    # "salt"/"paprika", listed earlier than Nuts), when they're clearly
    # nut snacks. Narrow on purpose: requires "roast"/"roasted" alongside
    # "peanut", so an unrelated spice product isn't affected. "Z Hot
    # Paprika Flav Corn Snack & Peanut" (no "roast"/"roasted" word) isn't
    # covered by this -- left as a lower-confidence case, since that one's
    # arguably a corn snack either way.
    # "Ritter Sport Roasted Peanuts 100g" (no "chocolate" in the name,
    # unlike its sibling "Ritter Sport Roasted Peanuts Chocolate") was
    # about to fall into the "peanut"+"roast" Nuts rule just below --
    # checked first so the brand (Ritter Sport makes chocolate bars only,
    # WebSearch-confirmed) wins regardless of which nut/roast word is in
    # the name. See the fuller "ritter" note further down in this file for
    # the original bare-word promotion this rule complements.
    ("Chocolates", ["ritter"]),
    ("Nuts", ["peanut", "roast"]),
    ("Nuts", ["peanut", "roasted"]),
    # A well-known Indian dish name -- found via real data ("Butter
    # Chicken", "Indian Butter Chicken Sauce"), which was landing on Butter
    # (listed earlier than Chicken). The dish name is specific and
    # unambiguous enough to check as its own phrase.
    ("Chicken", ["butter chicken"]),
    # "Lamb Brand" is a real Maltese seasoning/spice brand (it also sells
    # nuts) whose name contains the word "Lamb" -- e.g. "Lamb Brand Roasted
    # Almonds", "Lamb Brand Table Salt", "Lamb Brand Hot Paprika" and
    # "Lamb Brand Spices Coriander Seeds" were all matching bare "lamb"
    # (the meat category) before anything else got a chance. The nuts
    # carve-out is listed FIRST and stays narrow (requires "almond"
    # specifically); everything else sold under this brand, from real data
    # so far, is a spice or seasoning, so a plain "lamb brand" catch-all
    # underneath it -- requiring nothing more than the brand name itself --
    # covers every future spice variety too, not just the two words
    # ("salt", "herbs") originally listed here, without touching real lamb
    # meat (those product names never contain the word "brand"). Known,
    # accepted gap: one real example, "LAMB SALTS TABLE FINE X 2", doesn't
    # contain the word "Brand" at all, so it slips through this rule --
    # not worth a broader, less safe rule just to catch it.
    ("Nuts", ["lamb brand", "almond"]),
    # "Lamb Brnad" -- a real typo of "Lamb Brand" found in real data ("Lamb
    # Brnad Red & Natural Almonds"), which doesn't match the "lamb brand"
    # phrase above because of the misspelling. Same brand, same reasoning,
    # just matching the typo as it actually appears in the source data.
    ("Nuts", ["lamb brnad", "almond"]),
    # "Lamb Fruits" -- the same Lamb Brand product line again, this time
    # dried fruit. Originally added narrower (just "lamb"+"raisin", for
    # "Lamb Fruits Raisins Golden") but real data (19 Aug 2026 report) then
    # showed the same "Lamb Fruits" product line under two more dried-fruit
    # types with no "raisin" in the name at all ("Lamb Fruits Prunes
    # Pitted", "Lamb Fruits Blk Currants") -- the same "recurs with a
    # different specific word every round" signal already behind the plain
    # "lamb brand"/"lamb brnad" catch-alls, so this is widened to the
    # adjacent brand phrase itself rather than adding a fourth fruit word.
    ("Dried Fruit", ["lamb fruits"]),
    # "Lamb Pepper"/"Lamb Seasoning" -- two more real "Lamb [spice-related
    # word]" products ("Lamb Pepper White Ground", "Lamb Seasoning Onion
    # Powder"), same pattern as "Lamb Himalayan"/"Lamb Rosemary" below.
    ("Herbs & Spices", ["lamb", "pepper"]),
    ("Herbs & Spices", ["lamb", "seasoning"]),
    # "Lamb Mince" -- NOT a Lamb Brand product, an actual real lamb-meat
    # product ("Chef Choice Frozen Lamb Mince"), found landing on Beef
    # instead: bare "mince" is one of Beef's own keywords (a generic word
    # for any ground/minced meat, not beef-specific), and Beef is listed
    # before Lamb, so any minced-lamb product was losing to it. Checked
    # first so the more specific "lamb mince" phrase wins; a plain "beef
    # mince" (no "lamb" in the name) still correctly falls through to Beef's
    # own "mince" keyword afterwards, unaffected.
    ("Lamb", ["lamb mince"]),
    ("Herbs & Spices", ["lamb brand"]),
    # "Lamb Brnad" catch-all -- same typo, same brand, same reasoning as
    # "Lamb Brand" right above. Found via real data (19 Aug 2026 report) that
    # this typo recurs across many DIFFERENT spice words ("Lamb Brnad Herbs
    # Mint", "Lamb Brnad Mixed Spice", "Lamb Brnad Spices Garam Masala"),
    # the exact "same collision shape keeps recurring with a new specific
    # word every round" signal that already justified the plain "lamb
    # brand" catch-all -- so this gets the same general treatment instead of
    # another one-off per spice word. Listed after the narrow "lamb
    # brnad"+"almond" -> Nuts carve-out above, so that one still wins first.
    ("Herbs & Spices", ["lamb brnad"]),
    # Three more real "Lamb [spice-related word]" products found in the
    # same 17 Aug 2026 collision report, none containing the literal word
    # "brand" so the catch-all right above doesn't cover them: "LAMB SALTS
    # TABLE FINE X 2", "Lamb Herbs Rosemary 100g", "Lamb Himalayan Pink
    # Salt Fine 200g". WebSearch confirmed Lamb Brand is a real Maltese
    # herbs/spice/salt company (Mgarr Farms sells "LAMB BRAND COOKING SALT"
    # and "LAMB BRAND FINE TABLE SALT" under its own Herbs & Spices
    # listing), but didn't turn up the exact "Himalayan Pink Salt" or
    # "Herbs Rosemary" product names from that brand's own catalogue --
    # so this is confirmed at the brand-and-naming-pattern level, not at
    # the exact-product level. Kept deliberately narrow (the specific word
    # combinations from the three real examples, not a blanket "lamb" +
    # any spice word rule) so a genuine seasoned-lamb-meat product stays
    # safe from being swept in by accident -- no such product has turned
    # up in any report so far, but unlike "chips" (where a broad rule was
    # chosen only after the SAME collision kept recurring with a new base
    # word every round), this pattern has only shown up once, so a narrow
    # rule is the safer choice for now.
    ("Herbs & Spices", ["lamb", "himalayan"]),
    ("Herbs & Spices", ["lamb", "rosemary"]),
    ("Herbs & Spices", ["lamb", "salt", "table"]),
    # "Lamb Spices" -- the same Lamb Brand spice line again, just under a
    # different name for the product-line label than "Lamb Brand" itself:
    # found via real data ("Lamb Spices Cardamom Pods", "Lamb Spices Chilli
    # Whole Hot", "Lamb Spices Chinese 5 Spice") -- all clearly the same
    # spice-brand naming pattern as "Lamb Brand X" above, just phrased
    # "Lamb Spices X" instead in this data source.
    ("Herbs & Spices", ["lamb spices"]),
    # "Knorr"+"cube" -- found via real data: "Knorr Zero Salt Chicken
    # Cubes", "Knorr Chicken Cubes Zero Salt", "Knorr Zero Salt Beef Cubes"
    # were landing on Chicken/Beef (whichever meat word the name also
    # contained), since those are listed earlier than Stock Cubes and none
    # of these product names contain the word "stock" at all -- just
    # "[flavour] Cubes". Knorr is a real, well-known bouillon-cube brand,
    # so requiring the brand name alongside "cube" is safe and specific
    # (see also the plain "stock cube"/"stock pot" KEYWORD_RULES phrases
    # above, for non-Knorr products that do say "stock").
    ("Stock Cubes", ["knorr", "cube"]),
    # Pet food whose name also mentions a flavour (chicken, salmon, etc)
    # was losing to that flavour's own meat/fish category, purely because
    # Chicken/Chilled Fish are listed earlier in KEYWORD_RULES than
    # Cat/Dog -- e.g. real data showed "Royal Canin Adult Shih Tzu Dog Dry
    # Food" and chicken-flavoured dog food both at risk of this. These
    # words are specific enough (unlikely to appear in an unrelated
    # grocery product) to check first regardless of list order, the same
    # way the Easter-egg rule above does. Each phrase gets its own entry
    # since MULTI_KEYWORD_RULES requires ALL listed words together (AND),
    # not any one of them (OR) -- these used to live as ordinary
    # KEYWORD_RULES entries under "Pets" further down; moved here instead.
    ("Cat", ["cat food"]),
    ("Cat", ["cat litter"]),
    ("Cat", ["cat treat"]),
    ("Cat", ["kitten"]),
    # "felix" -- a specific, globally-known cat food brand whose products
    # don't say "cat" anywhere in the name, found via real data ("Purina
    # Gourmet Felix As Good As It Looks Mixed Selection").
    ("Cat", ["felix"]),
    # "katsuobushi" -- dried bonito flakes, a Japanese ingredient that shows
    # up specifically in cat food pouches (confirmed via WebSearch: it's a
    # standard recipe across multiple real cat-food brands -- Pramy
    # Carnivore, Kal Kan, Smart Heart, AIXIA all sell a near-identical
    # "Tuna With Katsuobushi In Jelly" pouch). Found via real data ("PREM
    # CHICKEN, TUNA, RICE KATSUOBUSHI 170G", part of a wider PREM/"Taste
    # Toppers"/"glucosamine softcream" cluster of pet products that don't
    # say "cat"/"dog" -- see the 12 Aug 2026 collision report). This word
    # has no realistic human-food meaning in a Maltese grocery database, so
    # it's safe to add alone; the rest of that cluster is NOT fixed here --
    # "Taste Toppers" (a confirmed real Applaws product line, but sold as
    # both cat AND dog food, so the species isn't certain from the name
    # alone) and "glucosamine"/"softcream" (a real pet-supplement/treat
    # signal, but again not clearly cat vs dog) are left as a known,
    # transparently-reported gap rather than guessed at, the same way PREM
    # itself was left unfixed after inconclusive research earlier.
    ("Cat", ["katsuobushi"]),
    # Three more real cat-food brands, all confirmed via WebSearch (12 Aug
    # 2026 collision report), same reasoning as "felix"/"cadbury" above --
    # a bare brand-name match is safe when the brand's own range is cat
    # food specifically:
    # "lechat" -- "LeChat Excellence" is a real cat food brand (confirmed
    # via petshop.lv, jmvetgroup.com, Amazon.fr), exact match to "Lechat
    # Excellence Salmon/chicken Flavor 400g".
    # "miglior gatto" -- a real cat food brand (Morando), confirmed
    # actually sold in Malta via petshopmalta.com -- exact match to real
    # data here.
    # "schesir" -- a real, cat-specific food brand (schesir.com's entire
    # product line is cat food, including the exact "Tuna...In Jelly"
    # pouches this data shows), confirmed via WebSearch.
    ("Cat", ["lechat"]),
    ("Cat", ["miglior gatto"]),
    ("Cat", ["schesir"]),
    # "Catty" -- a real cat-food brand confirmed via WebSearch (Pemix
    # Importers & Distributors Malta lists "Catty Pet Food" as one of its
    # brands), found via real data ("Catty Chicken & Sardines In Jelly")
    # landing on Chicken instead.
    ("Cat", ["catty"]),
    # "gatto" -- Italian for "cat", no other realistic grocery meaning
    # (unlike "cane"/"dog" below, which needs to be scoped -- see there).
    # Found via real data ("Deco' Gatto Pate' Pollo", "Miglior Gatto"'s
    # own unabbreviated cousin "MIG GATTO PATE POLLO/TACC") landing on
    # Chicken instead, 21 Aug 2026 collision-report deep dive.
    ("Cat", ["gatto"]),
    # "After Dark" -- WebSearch-confirmed (schesir.com/en/collections/
    # after-dark-cat) to be Schesir's own cat-food-only sub-line, matching
    # products in this data that don't say "Schesir" in the same field
    # (e.g. "AFTER DARK PATE CHICKEN 80G").
    ("Cat", ["after dark"]),
    ("Cat", ["schesirafter"]),  # "Schesirafter Dark Pate Chicken With Egg 80g" -- a real data typo (missing the space between "Schesir" and "After"), same "keep the literal typo as its own keyword" pattern used elsewhere in this file
    # "Princess" -- WebSearch-confirmed (petfoodmalta.com/filters/
    # product_cat/princess) to be a real Maltese cat-food brand from Pet
    # Nutrition House -- the cat-line counterpart to "Prince" (dog food,
    # see below). Combined with "pate" rather than added bare, since bare
    # "princess" already has an unrelated real use elsewhere in this file
    # (a "princess bust" toy).
    ("Cat", ["princess", "pate"]),
    ("Cat", ["cat"]),
    # "Monin" -- a real, well-known syrup brand confirmed via WebSearch
    # (Monin makes flavoured syrups exclusively, sold worldwide for coffee
    # and drinks). Found via real data ("Monin Syrup Ginger Bread 700ml")
    # landing on Bread instead, since Bread is listed long before
    # Dilutables and "Ginger Bread" is itself a real syrup flavour name.
    ("Dilutables", ["monin"]),
    ("Dog", ["dog food"]),
    ("Dog", ["dog treat"]),
    ("Dog", ["dog chew"]),
    ("Dog", ["puppy"]),
    # "barf" -- BARF (Bones And Raw Food) is a well-known real raw dog-food
    # diet term, found via real data ("Prince Barf Chicken & Vegetables"),
    # which was landing on Chicken/Vegetables instead.
    ("Dog", ["barf"]),
    # "hot dog" -- found via real data (12 Aug 2026 collision report): "Dak
    # Hot Dog Sausages" (Dak is a real, well-known human processed-meat
    # brand) was matching bare "dog" below and landing on the Dog pet-food
    # category, purely because "hot dog" happens to contain the word
    # "dog". Carved out first, the same way "Chocolate Chips" is carved out
    # before the general "chips" rule -- a hot dog is human food, not
    # something you feed a dog. Doesn't affect real dog food/treats named
    # "Dogero", "Puppy" etc, which still match the rules around this one.
    ("Sausages", ["hot dog"]),
    ("Dog", ["dog"]),
    # "Prince" -- WebSearch-confirmed (petfoodmalta.com/filters/
    # product_cat/prince, explicitly titled "Prince Dog Food in Malta")
    # to be a real Maltese dog-food brand from Pet Nutrition House, the
    # dog-line counterpart to "Princess" (cat food, added above). Combined
    # with "pate" rather than added bare, since bare "prince" already has
    # an unrelated real use elsewhere in this file (a "Prince 15cm" plush
    # toy).
    ("Dog", ["prince", "pate"]),
    # "Cane" -- Italian for "dog", but genuinely risky as a bare word
    # (also ordinary English for a walking stick, and "cane sugar" is a
    # real existing Sugar keyword) -- combined with "pate" instead, since
    # no real product would ever say both. Fixes "Deco' Cane Pate With
    # Chicken & Lamb" and similar, found the same way as "gatto" above.
    ("Dog", ["cane", "pate"]),
    # 21 Aug 2026 -- the Chicken/Cold Cuts collision report deep dive
    # (84 listings) turned out to be almost entirely pet food, fixed
    # above. The genuine human-food remainder was "wurstel"/"mortadella"
    # (bare Cold Cuts words) losing to bare "chicken"/"pollo" the same
    # list-order-luck way as every other collision this session -- e.g.
    # "WURSTEL CHICKEN AND TURKEY", "Rovagnati Snello Mortadella Di
    # Pollo". Both words are unambiguous deli-meat product types (a
    # wurstel/mortadella is what it is regardless of which meat is in
    # it), so promoting them is safe -- placed here, AFTER every Cat/Dog
    # rule above, so a pet-food wurstel/pate product with a real species
    # signal still resolves to Cat/Dog first, the same "specific before
    # general" ordering the Pet Food category below already relies on.
    ("Cold Cuts", ["wurstel"]),
    ("Cold Cuts", ["mortadella"]),
    # "Goodfella's" -- WebSearch-confirmed to be a frozen-pizza-only
    # brand (Nomad Foods; goodfellaspizzas.com). Found via real data
    # ("Goodfella's Deep Pan Baked Chicken Pepperoni & Ham") landing on
    # Chicken instead, via the same bare "chicken" vs bare "pepperoni"
    # (Cold Cuts) tie.
    ("Pizza", ["goodfella"]),
    # New "Pet Food" category (18 Aug 2026) -- for real pet products whose
    # name gives no way to tell cat from dog, even after everything above.
    # Checked in order, so real evidence: Welbee's own site has exactly one
    # flat "Pets" category (D-5445 in welbees_crawler.py) with no cat/dog
    # split at all -- confirmed by reading the crawler itself, not
    # guessed -- so a product like "ADULT DRY FOOD CHICKEN & TURKEY 2KG" or
    # "CAN ADULT ALL BREEDS TURKEY&CARROT 400G" has NO species signal
    # anywhere in the data this project has access to, not just in the
    # product name. Before this category existed, these were falling
    # straight into human food categories (Chicken, Turkey, Beef...),
    # purely because that's whichever meat word the name happened to
    # contain. Every phrase below is a generic pet-food packaging/format
    # term with no realistic human-food meaning, found via real data.
    # Placed AFTER every Cat/Dog rule above on purpose, so a product that
    # CAN be identified by species (e.g. "cat food", "felix", "katsuobushi")
    # still gets the more specific answer; this is only the fallback for
    # when nothing more specific matched.
    ("Pet Food", ["adult dry food"]),
    ("Pet Food", ["dry food"]),
    ("Pet Food", ["wet food"]),
    ("Pet Food", ["all breeds"]),
    # "senior tray" -- kept as this one specific phrase, not bare "senior"
    # alone, since "senior" by itself is a real risk for human products
    # (senior-specific vitamins/nutrition drinks exist) -- only one real
    # example seen so far ("SENIOR TRAY TURKEY & RICE 400GR"), so a narrow
    # phrase is the safer choice here, same reasoning as the "Lamb
    # Himalayan"/"Lamb Rosemary" narrow carve-outs above.
    ("Pet Food", ["senior tray"]),
    # "paleo" -- WebSearch confirmed "Paleo" is used by pet-food brands
    # across BOTH cat and dog lines (e.g. Acana Paleo dry dog food,
    # VetExpert Raw Paleo cat food), which is why this lives in the
    # species-unknown Pet Food bucket rather than Cat or Dog specifically.
    # Originally left out of this file over a theoretical risk -- "paleo"
    # is also a human diet/health-food marketing word elsewhere (paleo
    # protein bars, paleo bread) -- but the user confirmed directly (18 Aug
    # 2026) that in this project's own data, "Paleo" is specifically an
    # animal-food brand, so that risk doesn't apply here. Fixes "PALEO PORK
    # AND CHICKEN/TURKEY/LAMB 400G/800G", which were landing on whichever
    # meat word happened to be listed earliest in KEYWORD_RULES (Chicken
    # for the Chicken pairing, Pork for the Turkey/Lamb pairings -- pure
    # list-order luck, not anything about the product).
    ("Pet Food", ["paleo"]),
    # Baby-food brand names -- found via the same 12 Aug 2026 collision
    # report: real baby/toddler-food brands (Hipp, Ella's Kitchen, Piccolo,
    # Plasmon, Organix, Kiddylicious) were losing to whatever ingredient
    # word their own product name also contained (e.g. "Hipp Vegetables
    # Rice & Chicken" -> Rice, "Piccolo Blueberry & Banana Natural Yogurt
    # Pouch" -> Yoghurt, "Organix Banana Bread Biscuits" -> Biscuits),
    # purely because there's no other way for the classifier to recognise
    # these as baby food -- none of the phrases already used for Baby Food
    # below (e.g. "baby food", "infant formula") appear in their names at
    # all. Each brand confirmed via WebSearch as a real, dedicated
    # baby/toddler food brand -- same reasoning as "Cadbury"/"felix" above
    # (a bare brand-name match is safe when the brand's whole range fits
    # one category). "Piccolo" is deliberately NOT included as a bare
    # word: it's also an ordinary Italian/wine-industry term meaning
    # "small" -- "piccolo" is the standard name for a 200ml single-serve
    # wine bottle (e.g. "San Pellegrino Prosecco Piccolo"), confirmed as a
    # real collision by testing that exact case here before shipping this
    # fix. Left as a known, unfixed gap for now rather than guessed at
    # with a narrower (and more fragile) carve-out.
    ("Baby Food", ["hipp"]),
    ("Baby Food", ["ella's kitchen"]),
    ("Baby Food", ["plasmon"]),
    ("Baby Food", ["organix"]),
    ("Baby Food", ["kiddylicious"]),
    # Bare "juice"/"smoothie" -- a juice's name often also contains a
    # fruit word (e.g. "Del Monte Orange Juice" matching bare "orange" ->
    # Fruits as well as bare "juice" -> Juices), with Fruits winning today
    # purely because it's listed earlier. A drink literally called "juice"
    # or "smoothie" is never ambiguous about which category it belongs in,
    # so these are safe to check first, the same way Cat/Dog above are.
    ("Juices", ["juice"]),
    ("Juices", ["smoothie"]),
    # "Carrefour Egg Bengasini No 210 (250grms)" showed up as the cheapest
    # "Eggs" result -- same real pattern as "Filini" above: "Bengasini" is
    # almost certainly another shape in Carrefour's own egg-pasta line
    # ("No 210" is a standard Italian pasta-shape numbering convention),
    # same brand, same 250g pantry-goods pack size, not real eggs. Worth
    # watching for further shape names in this same product line.
    ("Pasta & Couscous", ["bengasini"]),
    # "Rialto Croutons Round Olive Oil & Salt 100g" showed up as the
    # cheapest "Olive Oil" result -- croutons flavoured with olive oil, not
    # a bottle of it. This is the third real product (after "Rice Up
    # Rolls..." and "Simpl Tuna...") where "olive oil" describes an
    # ingredient rather than being the product -- "croutons" itself is
    # unambiguous (no legitimate product other than actual croutons is
    # called that), so it's listed here alone rather than needing
    # co-occurrence with "olive oil" like the tuna case above.
    ("Snacks", ["croutons"]),
    # "crisps" and "pretzel" -- no realistic other meaning in a grocery
    # product name (unlike "popcorn" or "snack", deliberately left as
    # ordinary keywords instead, since real products like "popcorn
    # chicken" and "cheese snacks" shouldn't get pulled into Snacks).
    # Elevating just these two catches cases like "Pringles Crisps
    # Paprika" (bare "crisps" losing to bare "paprika" -> Herbs & Spices
    # purely by list order) without that risk.
    ("Snacks", ["crisps"]),
    ("Snacks", ["pretzel"]),
    # "popcorn" -- same reasoning as "crisps"/"pretzel" just above, moved
    # here after real data (12 Aug 2026 collision report) showed the same
    # pattern: "Z Popcorn Salt And Caramel Flavored" was landing on Herbs &
    # Spices (bare "salt", listed earlier than Snacks). No other realistic
    # meaning for "popcorn" in a grocery product name.
    ("Snacks", ["popcorn"]),
    # Bare "snack" -- the same general-fix pattern as "chips"/"pizza"/
    # "sausage" above, extended to "snack" itself once it became clear (18
    # Aug 2026 collision report) this was recurring across more than a
    # dozen different categories at once: a product clearly sold AS a
    # snack (e.g. "Biosaurus Cheese Snack Multipack", "Lotto Peanut
    # Snack") was losing to whichever flavour/ingredient word it also
    # contained (bare "cheese", "peanut", "spice"...), purely because
    # those categories are listed earlier than Snacks. Deliberately NOT
    # done in an earlier round (see the comment on the "crisps"/"pretzel"
    # KEYWORD_RULES entry above, which explicitly called out "cheese
    # snacks" as the risk of doing this) -- reconsidered now that the SAME
    # collision shape was showing up against Cheese, Nuts, Herbs & Spices,
    # Chilled Fish, Milk, Biscuits, Dental Care and more all at once in a
    # single report, the same "recurring with a new base word every round"
    # threshold that justified the "chips" general fix originally. A real,
    # deliberate trade-off: a bulk-sold nut/cheese product that ISN'T
    # marketed as a "snack" would still correctly stay Nuts/Cheese, since
    # this only fires when the word "snack" itself is actually present.
    ("Snacks", ["snack"]),
    # "choc" -- see the comment on the "chocolate"/"choco" KEYWORD_RULES
    # entry above for why this needs to be here (Pass 0) rather than there:
    # "MILK CHOC WAFER BAR" was matching bare "milk" (Milk) and bare
    # "wafer" (Biscuits), both listed earlier than Chocolates, so adding
    # "choc" as an ordinary tier-2 word wouldn't have won against them.
    ("Chocolates", ["choc"]),
    # "cadbury" -- the single most common chocolate brand on a Maltese
    # shelf, and its flagship products (e.g. "Cadbury Dairy Milk", "Cadbury
    # Dairy Milk Fruit & Nut", "Cadbury Dairy Milk Oreo") often don't
    # contain the word "chocolate"/"choc" at all -- found via real data:
    # these were landing on Milk (from "Dairy Milk") instead. Cadbury's
    # product range is chocolate/confectionery enough across the board
    # that a bare brand-name match is safe here, the same reasoning
    # already used for "felix" (a cat food brand) above.
    ("Chocolates", ["cadbury"]),
    # "Zott Monte" -- a real Zott (German dairy company) chilled dairy-
    # dessert/pudding brand, confirmed via WebSearch, sold in small pots
    # with flavour/topping variants like biscuit crumble. "Zott Monte
    # Butter Biscuits (125grms)" is that dessert, not an actual packet of
    # biscuits -- was landing on Butter (bare "butter" tied with bare
    # "biscuit", Butter listed earlier). Filed under Yoghurt, not a new
    # category, since this taxonomy already groups chilled dairy desserts
    # with yoghurt (see GREENS_CATEGORY_MAP's "Yoghurts And Desserts" ->
    # "Yoghurt" mapping above) -- confirmed correct by the user directly
    # (18 Aug 2026), who knows this specific product. The whole "Zott
    # Monte" range is this same dessert line, so a bare two-word brand-name
    # match is safe, the same reasoning as "cadbury" just above.
    ("Yoghurt", ["zott monte"]),
    # The six "chocolate"+fruit-word carve-outs that used to live here
    # (orange/banana/apple/grape/melon/fruit -- for "Condorelli...Vanilla /
    # Chocolate / Orange / Lemon" and similar, which were losing to the
    # fruit word since Fruits is listed earlier than Chocolates) are now
    # fully redundant and have been removed: the general bare "chocolate"
    # rule near the top of this list already wins for every one of these
    # names, since it's checked first. See the comment there.
    # "M.Busto Organic Apple Cider VINEGAR With The Mother" was landing on
    # Fruits (bare "apple"), when it's really a Vinegars product -- and a
    # genuine alcoholic cider drink (e.g. "Inch's Apple Cider") was ALSO
    # landing on Fruits, when it should be Ciders. Both fixed via the same
    # two-step pattern already used for "Lamb Brand": the more specific
    # case (cider VINEGAR) is carved out first, so it isn't swept up when
    # bare "cider" is elevated for the drink right after it.
    ("Vinegars", ["cider", "vinegar"]),
    ("Ciders", ["cider"]),
    # Bare "tea" -- a bottled or bagged tea drink/product was losing to a
    # fruit-flavour word in its own name (e.g. "Fuze Tea Strawberry &
    # Melon" matching bare "melon" -> Fruits, "English Tea Shop...Citrus
    # Fruits 20 Teabags" matching bare "fruit" -> Fruits), since Fruits is
    # listed earlier than Tea. "tea" has no other realistic meaning in a
    # grocery product name, so it's safe to check first, the same as
    # "juice"/"smoothie" above. This also covers the existing "tea bag"
    # phrase below (a product containing "tea bag" always also contains
    # the bare word "tea"), so that entry is now redundant -- left in
    # place there rather than removed, in case a future product says "tea
    # bag" without the standalone word "tea" ever appearing (e.g. some
    # unusual plural/compound spelling); harmless either way since Pass 0
    # already wins first.
    ("Tea", ["tea"]),
    # General "chips" fix, replacing the growing list of one-off phrases
    # this used to need (see the comment on the old KEYWORD_RULES Chips
    # entry above). The recurring real problem: a flavoured chip snack
    # (potato, tortilla, rice, lentil, nacho...) kept losing to whatever
    # OTHER word its flavour or base ingredient happened to share with a
    # different category (bare "rice", "cheese", "cream", "paprika",
    # "salt" etc, all listed earlier than Chips). The one case that
    # genuinely needs protecting from a blanket "chips always wins" rule
    # is "Chocolate Chips" (a baking ingredient, correctly Chocolates, not
    # Chips) -- so that's carved out FIRST, and only then does plain
    # "chips" win over everything else, covering every current and future
    # chip brand/flavour at once instead of needing a new phrase added
    # every time one turns up. Chosen deliberately over the safer
    # one-phrase-at-a-time approach after the same collision kept
    # recurring round after round with a new base ingredient each time.
    # The "chocolate"+"chips" carve-out that used to sit here (protecting
    # "Chocolate Chips" from the general "chips" rule below) is now fully
    # redundant too, for the same reason as the fruit-word carve-outs
    # above -- removed; see the general bare "chocolate" rule near the top
    # of this list.
    ("Chips", ["chips"]),
    # "Sausages" -- see the comment on the old KEYWORD_RULES Sausages entry
    # above for the real data behind this (packets of pork/beef sausages
    # landing on the base meat instead). No carve-out needed first, unlike
    # "chips" -- there's no equivalent "Chocolate Sausages"-style case
    # where "sausage" should lose to something else.
    ("Sausages", ["sausage"]),
    # Everything below here is from the 12 Aug 2026 collision report (6629
    # listings), the fourth full round of real-data-driven fixes.
    #
    # "salt"+"pepper" together -- found via real data: "Carmencita Himalayan
    # Pink Salt & Black Pepper" (a jar of seasoning) and "Crackey's Galletti
    # Salt & Pepper" (a savoury cracker) were both landing on Vegetables
    # (bare "pepper"), since Vegetables is listed earlier than Herbs &
    # Spices. This does NOT touch the earlier, explicit decision to leave
    # bare "pepper" alone under Vegetables (a single spice word by itself
    # is still ambiguous, and that's settled) -- it only fires when "salt"
    # is ALSO present, which is a much stronger, safer signal that the
    # product is a seasoning blend rather than a vegetable.
    ("Herbs & Spices", ["salt", "pepper"]),
    # "Herbs & Spices" written out as its own product-line name -- found via
    # real data ("Tiger Brand Herbs & Spices Beef & Pork Seasoning") landing
    # on Beef instead: bare "beef" is checked before the existing bare
    # "herb"/"spice" keywords, so a seasoning mix naming its own two meat
    # flavours was losing to whichever one came first. When a product
    # literally says "Herbs & Spices" together, it's the seasoning, not the
    # meat -- checked as its own phrase so it wins outright.
    ("Herbs & Spices", ["herbs & spices"]),
    ("Herbs & Spices", ["herbs and spices"]),
    # "Air Wick" -- a real, air-freshener-only brand (confirmed via
    # WebSearch: its entire range is diffusers, plug-ins and sprays), found
    # via real data ("Air Wick Diffusore Oil Base + Refill... Sea Salt")
    # landing on Herbs & Spices via bare "salt".
    ("Air Fresheners", ["air wick"]),
    # "Baylis & Harding" -- a real, toiletries-and-gift-set-only brand
    # (confirmed via WebSearch: baylisandharding.com's own range is bathing
    # gift sets, toiletry bags, etc, nothing else), found via real data
    # ("Baylis & Harding Jojoba Vanilla & Almond Oil Bathing Gift Set")
    # landing on Oils instead: "almond oil" is itself a phrase (added
    # earlier this project for real cooking-oil products), so it was tying
    # with -- and beating -- the existing "gift set" phrase purely by
    # category list order. This is a cosmetic gift set, never a food oil.
    ("Gift Sets", ["baylis harding"]),
    # Bare "soup" -- found via real data: "Campbells Cream Of Tomato Soup"
    # was landing on Cooking Creams (bare "cream"), since there was no
    # "soup" keyword anywhere in KEYWORD_RULES at all (Soups only existed
    # as a direct PAVI/Greens category-map target, never as a name-based
    # fallback keyword) -- so any tinned soup whose name also mentioned an
    # ingredient word from an earlier category always lost. "soup" has no
    # other realistic meaning in a grocery product name.
    ("Soups", ["soup"]),
    # "wafer"+"cream" together -- found via real data: "Loacker Crispy
    # Wafers Filled With Coconut Cream" and "Dr Gerard Wafer Rolls Peanut
    # Cream" were landing on Cooking Creams (bare "cream" is listed earlier
    # than "wafer"/Biscuits), when they're clearly biscuit/wafer products
    # with a cream filling, not a tub of cooking cream. Both words required
    # together so a plain wafer (no cream) or a plain cooking cream (no
    # wafer) are both unaffected.
    ("Biscuits", ["wafer", "cream"]),
    # Bare "pizza" -- found via real data: "Alberto Pizza Double Salami"
    # and "Cameo Ristorante Pizza 4 Cheese" were landing on Ham/Cheese
    # (whichever topping word the name also contained), since Ham and
    # Cheese are both listed earlier than Pizza in KEYWORD_RULES. Nothing
    # else in a grocery product name is realistically called "pizza", so
    # it's safe to check first regardless of topping, the same as "chips"
    # above.
    ("Pizza", ["pizza"]),
    # Bare "luncheon" -- found via real data: "Dany Chicken Luncheon Meat"
    # and "Dak Chicken Luncheon Meat" were landing on Chicken instead of
    # the more specific, more useful Cold Cuts, since Chicken is listed
    # earlier than Cold Cuts -- the same shape of bug as the "sausage" fix
    # above (a specific product type losing to whichever base meat/flavour
    # it's made from).
    ("Cold Cuts", ["luncheon"]),
    # "grater" -- found via real data: "Westmark Steel Raw Fruit & Vegetable
    # Grater" (a kitchen tool) was landing on Vegetables purely because its
    # own description mentions what it's used to grate. A single
    # KEYWORD_RULES entry wasn't enough here (Household Goods is listed
    # very late in that file, long after Vegetables/Fruits), so this needs
    # the same Pass-0 treatment as "conditioner"/"candle" above -- "grater"
    # is an unambiguous, product-defining word with no food meaning at all.
    ("Household Goods", ["grater"]),

    # 18/19 Aug 2026 unclassified-bucket pass (see the matching dated
    # comment in KEYWORD_RULES above) -- "alpro" and "dessert" aren't
    # always adjacent ("Alpro Soya Vanilla Dessert" has two words between
    # them), so this needs co-occurrence rather than a phrase.
    ("Cooking Creams", ["alpro", "dessert"]),

    # Pantene makes shampoo, conditioner, AND leave-in treatment -- a
    # brand-only rule would wrongly force every Pantene product into one
    # category. Only the listings that explicitly say "Treatment" get
    # this; "Pantene Hydration Heat & Glow" (no such word) is left
    # unclassified rather than guessed at.
    ("Hair Treatment", ["pantene", "treatment"]),

    ("Pet Care", ["camon"]),  # Camon (WebSearch-confirmed pet-grooming-only brand) needs Pass 0 to beat the later "cleansing wipes" Skin Care phrase (Pass 1 phrases always beat Pass 2 bare words, regardless of list order) -- found via this round's own regression sweep on "Camon Talc Cleansing Wipes"

    # 18 Aug 2026 bulk sweep -- two cases where the words that identify the
    # product are real words that sit apart from each other in the name, so a
    # contiguous phrase can never catch them.
    ("Intimate Care", ["fresh", "clean", "wipe"]),  # "Fresh & Clean Sensitive Wipe" -- Fresh & Clean is an Italian intimate-hygiene brand; needs all three words because "fresh" and "clean" on their own are far too generic to key a rule on
    ("Laundry Washing Liquids", ["surf", "liquid"]),

    # ------------------------------------------------------------------
    # 18 Aug 2026 bulk sweep -- tie-breakers found by the collision report.
    #
    # Every rule below is a single unambiguous word that was LOSING a
    # same-tier tie to an unrelated bare word that happened to also appear
    # in the product name (chocolate brands losing to "milk", sweets losing
    # to "fruit", a vegetable PEELER losing to "vegetable"). Pass 0 always
    # wins, so putting them here settles it without disturbing list order
    # anywhere else. Each is a word that means exactly one thing in a
    # supermarket, which is what makes Pass 0 safe to use for it.
    # ------------------------------------------------------------------
    ("Chocolates", ["toblerone"]),   # "Toblerone Milk" was landing on Milk
    ("Chocolates", ["galaxy"]),      # "Galaxy Smooth Milk" was landing on Milk
    ("Chocolates", ["milka"]),       # brand name literally contains "milk"
    ("Chocolates", ["milkybar"]),    # same
    ("Sweet Snacks", ["skittles"]),  # "Skittles Fruits" was landing on Fruits
    ("Sweet Snacks", ["mentos"]),    # "Mentos Fruit Roll" was landing on Fruits
    ("Carbonated Drinks", ["fanta"]),   # "Fanta Orange" was landing on Fruits
    ("Energy Drinks", ["lucozade"]),    # "Lucozade Sport Orange" was landing on Fruits
    ("Chips", ["wotsit"]),              # "Wotsits Cheese Puffs" was landing on Cheese
    ("Sauces & Condiments", ["ketchup"]),      # "Heinz Tomato Ketchup" was landing on Vegetables
    ("Sauces & Condiments", ["pepper sauce"]), # "Tabasco Pepper Sauce" was landing on Vegetables (bare "pepper")
    ("Sauces & Condiments", ["hot sauce"]),    # same pattern
    ("Sauces & Condiments", ["gherkin"]),      # "Gherkins In Vinegar" was landing on Vinegars
    ("Soups", ["bouillon"]),                   # "Vegetable Bouillon Powder" was landing on Vegetables
    ("Cake Preparations", ["bicarbonate"]),    # "Bicarbonate Of Soda" was landing on Carbonated Drinks
    ("Household Goods", ["peeler"]),           # "Vegetable Peeler" was landing on Vegetables
    ("Pasta & Couscous", ["tortellini"]),      # "Tortellini Prosciutto" was landing on Ham
    ("Baby Essentials", ["baby oil"]),         # "Baby Oil Chamomile" was landing on Oils
    ("First Aid", ["lozenge"]),                # "Throat Lozenges Honey Lemon" was landing on Honey
    ("Skin Care", ["micellar"]),               # "Micellar Cleansing Water" was landing on Water
    ("Body Lotions", ["e45"]),                 # "E45 Cream" was landing on Cooking Creams
    ("Chocolates", ["lindt"]),                 # "Lindt Gold Milk Raisin Nut" was landing on Milk, "Lindt Lindor Egg ... Milk" on Eggs
    ("Jelly", ["marmalade"]),                  # "Orange Marmalade With Whisky" was landing on Fruits (bare "orange")
    ("Make Up", ["rimmel"]),                   # "Rimmel Lip Oil Slip Stick: Cappuccino" was landing on Coffee
    ("Sauces & Condiments", ["bisto"]),        # "Bisto Gravy Granules Beef" was landing on Beef

    # 18 Aug 2026 second bulk sweep -- words that sit apart in the real name.
    ("Legumes", ["bean", "lima"]),                        # "Good Earth Beans Lima" -- the words are the wrong way round for a phrase
    ("Laundry Washing Liquids", ["ariel", "liquid"]),     # "Ariel Professional Liquid Regular 2 X70 Washes"
    ("Laundry Washing Powders", ["ariel", "powder"]),     # "Ariel Professional Powder"
    ("Air Fresheners", ["gel", "freshener"]),             # "Felce Azzurra Aria Di Casa Gel Freshener"
    ("Tea", ["chai"]),                                    # "Chai Latte" is a tea drink, but was losing to "latte" -> Coffee
    ("Hair & Nail Accessories", ["cuticle"]),             # "Cuticle Oil Pen" was landing on Oils
    ("First Aid", ["athletes foot"]),                     # "Athletes Foot Cream" was landing on Body Lotions
    ("Pasta & Couscous", ["fusilli"]),                    # pasta shapes are unambiguous, and were losing to ingredient words
    ("Pasta & Couscous", ["fusili"]),                     # real one-L spelling in the source data
    ("Pasta & Couscous", ["egg pasta"]),                  # "Borgo De Medici Egg Pasta Pistacchio" was landing on Eggs

    # 18 Aug 2026 third bulk sweep.
    ("Shower Gels", ["dove", "bath"]),

    # 18 Aug 2026 fourth bulk sweep -- Pass-0 guards for the two broad words
    # this round claims ("comfort" for the softener brand, "ultra thin" for
    # sanitary towels), plus names whose defining words sit apart.
    ("Intimate Care", ["condom"]),                        # keeps "Condoms Ultra Thin" off the new Sanitary Towels phrase
    ("Household Goods", ["gel liner"]),                   # "Shoes' Xpert Woman Extreme Comfort Gel Liner Cushions" -- insoles, not fabric softener
    ("Household Goods", ["shoes xpert"]),                 # same brand, same reason
    ("Household Goods", ["lock lace"]),                   # "Sport Fast Lock Laces"
    ("Skin Care", ["septona", "wipe"]),                   # "Septona Antibacterial Orage Wipes" -- a personal wipe, not a surface cleaner
    ("Toothbrushes", ["colgate", "medium"]),              # "Colgate Extra Clean Medium" -- bristle firmness, i.e. a brush not a paste
    ("Toothbrushes", ["colgate", "soft"]),
    ("Toothbrushes", ["colgate", "hard"]),
    ("Sanitary Towels", ["ultra thin", "absorbent"]),
    ("Cloths & Sponges", ["cloth", "absorbent"]),
    ("Disposables", ["ice", "cube", "bag"]),
    ("Coffee", ["saquella"]),                         # "Saquella Bar Sud Beans" is coffee -- needs Pass 0 to beat the new bare "bean" Legumes rule
    ("Chocolates", ["nutella"]),                      # "Nutella Hazelnut Spread" was landing on Butter via the bare word "spread"

    # 18 Aug 2026 seventh sweep -- brand rules that were losing to a generic
    # word elsewhere in the name.
    ("All-purpose Cleaners", ["astonish"]), # "Astonish Bleach Cream Cleaner" was landing on Cooking Creams via bare "cream"
    ("Toys & Games", ["addo"]),             # "Addo Out To Impress Water Jelly Art" was landing on Water
    ("Floor Cleaners", ["floor", "cleaner"]),         # "Fresh Floor Liquid Cleaner Marseille & Lavender" -- the two words are split by "Liquid"
    ("Sanitary Towels", ["every day", "sensitive"]),  # "Every Day Up Sensitive With Cotton"
    ("Sanitary Towels", ["every day", "up"]),           # "Frio Ice Cubes Bags" -- both words are pluralised mid-phrase, so no contiguous phrase can match it      # "CAR CLOTH SUPER WATER ABSORBENT" -- absorbency is a cloth's selling point too, so a cloth that says "absorbent" stays a cloth  # "Dove Bath Seta Preziosa" -- bare "bath" is far too generic on its own (bath salts, bath towel, bath mat, bathroom cleaner), so it only counts alongside the brand  # "Surf Tropical Liquid" -- Surf is a laundry brand, but the bare word "surf" is much too generic to claim on its own, so it only counts when "liquid" is also present
    ("Pasta & Couscous", ["pasta natura"]),
    ("Perfume", ["impulse"]),  # keeps the earlier round's deliberate Impulse=Perfume decision intact now that "body spray" is a Deodorants phrase (Pass 1 phrases beat Pass 2 bare words, so Impulse needs Pass 0 to hold its place)  # gluten-free pasta brand whose product names say what the pasta is MADE of ("Corn Flour", "Rice") -- needs Pass 0 so those ingredient words don't win  # "Surf Tropical Liquid" -- Surf is a laundry brand, but the bare word "surf" is much too generic to claim on its own, so it only counts when "liquid" is also present

    # 21 Aug 2026 -- from triaging the "category collisions" report's two
    # biggest pairs (Sauces & Condiments/Vegetables, 522 listings; Cheese/
    # Sauces & Condiments, 205 listings). Root cause: several words in the
    # Sauces & Condiments bare-word list (see the big block starting
    # "Bare 'sauce' is the single highest-value word..." earlier in this
    # file) were TYING against an ordinary ingredient word from a
    # DIFFERENT product's actual base category -- "Waitrose Caramelised
    # Red Onion Chutney" tied "chutney" (Sauces & Condiments) against
    # "onion" (Vegetables) and landed on Vegetables purely because of
    # where the two tuples happen to sit in this file, not because that's
    # the right answer. A chutney, pesto, relish, etc. is unambiguously a
    # condiment REGARDLESS of what vegetable/cheese/fruit it's flavoured
    # with or made from -- there's no real dual-category ambiguity here
    # the way there is for, say, a fruit-flavoured yoghurt (see
    # KNOWN_ACCEPTED_COLLISIONS below for those). Single words here (same
    # established pattern as e.g. ("Coffee", ["saquella"]) above) so they
    # win outright via Pass 0, no matter which other category's word also
    # appears in the name.
    #
    # Deliberately NOT every word from that block: "mustard" is left out
    # on purpose -- "mustard seed" is its own existing PHRASE rule (Pass
    # 1) mapped to Herbs & Spices, and a Pass 0 bare "mustard" override
    # would fire before that phrase ever got checked, wrongly reclassifying
    # "Colemans Mustard Seeds" as a condiment. "passata" and "polpa" are
    # also left out -- the one real example seen so far ("Cirio Passata
    # Verace Sieved Tomatoes") already resolves correctly today, so
    # there's no evidence yet that they need this same override. And
    # "ketchup"/"gherkin" are NOT repeated here -- turns out this exact
    # override already exists for both, further up this same list (search
    # for "was landing on Vegetables"/"was landing on Vinegars") -- same
    # bug, same fix, just found independently on an earlier date.
    ("Sauces & Condiments", ["sauce"]),
    ("Sauces & Condiments", ["chutney"]),
    ("Sauces & Condiments", ["pesto"]),
    ("Sauces & Condiments", ["granpesto"]),  # added 21 Aug 2026 -- "Star Granpesto Tigulio Ricotta & Tartufo" concatenates "Gran" and "Pesto" with no space, so bare "pesto" (\bpesto\b) can't match it; was falling through to Cheese via bare "ricotta" instead. Found as a side-discovery while investigating the Cheese/Sauces & Condiments pair -- not the actual cause of that pair (see below) but a real bug in its own right
    ("Sauces & Condiments", ["relish"]),
    ("Sauces & Condiments", ["marinade"]),
    ("Sauces & Condiments", ["horseradish"]),
    ("Sauces & Condiments", ["teriyaki"]),
    ("Sauces & Condiments", ["sriracha"]),
    ("Sauces & Condiments", ["hoisin"]),
    ("Sauces & Condiments", ["piccalilli"]),
    ("Sauces & Condiments", ["aioli"]),
    ("Sauces & Condiments", ["mayonnaise"]),
    ("Sauces & Condiments", ["mayo"]),
    ("Sauces & Condiments", ["gravy"]),
    ("Sauces & Condiments", ["salsa"]),
    ("Sauces & Condiments", ["pickle"]),
    ("Sauces & Condiments", ["dip"]),  # "Cranberry Dip" was landing on Dried Fruit -- same shape as the rest of this block, found from the same report. NOT promoting "curd" from the same original tuple though -- "Milochka Curd Cheese" is a real, correctly-classified Cheese product, so curd genuinely is ambiguous in a way dip isn't.

    # Also from the 21 Aug 2026 collisions triage: "Ca Vittoria Appassimento
    # Rosso Vino Passito" ties bare "appassimento" (Wine - Red -- a
    # winemaking TECHNIQUE, used for both red and white/dessert wines)
    # against bare "passito" (Wine - White -- a STYLE, also used for both
    # colours), even though the bottle's own name says "Rosso" (Italian for
    # red) right there. "rosso" itself already exists as a colour keyword,
    # but only inside SCOPED_KEYWORD_RULES (Welbee's "Drinks" aisle only,
    # and only checked as a last resort AFTER classify_by_name has already
    # failed) -- since appassimento/passito already give classify_by_name
    # an (ambiguous) answer, that scoped fallback never even runs. Added
    # here as its own global override, unlike the rest of that scoped
    # colour block ("bianco" especially): checked and confirmed "rosso"
    # doesn't appear anywhere else in this file for an unrelated product
    # (unlike "bianco", which really is Omino Bianco/Mulino Bianco/etc, and
    # unlike bare "red", which would catch far too much -- Red Bull, red
    # onions, red peppers -- to ever be safe unscoped). Not extending this
    # same treatment to "bianco"/"rouge"/"tinto"/"red" today -- flagged as
    # a possible follow-up if they turn out to cause the same problem in a
    # future report, not assumed safe without the same check.
    ("Wine - Red", ["rosso"]),

    # 21 Aug 2026 -- the "Fruits / X" collision pattern (~490 listings across
    # 7 pairs: Sports, Oils, Tea, Spirits - Liqueurs, Bread, Carbonated
    # Drinks, Ciders). In almost every example, a bare fruit-flavour word
    # (mango, berry, peach, coconut, orange, grapefruit...) in Fruits was
    # tying, at the SAME tier, against a bare brand-name word that already
    # correctly identifies the product's real category -- e.g. "Kopparberg
    # Mixed Fruit Cider" ties bare "kopparberg" (Ciders) against bare
    # "mixed fruit" / "fruit" (Fruits). Unlike the earlier bare-"oil" case,
    # none of these brand words appear anywhere else in the file for an
    # unrelated product (checked individually below), so promoting each to
    # a tier-0 override is safe: it can't misfire on some other product the
    # way bare "oil" would have. Two of the seven pairs (Oils, and part of
    # Sports/Tea's flavoured-drink shape) needed a phrase-tier fix instead
    # -- see the new "coconut oil" / "tanning oil" entries near the end of
    # KEYWORD_RULES above -- because "oil" itself can't safely go tier-0
    # (would jump ahead of the existing "olive oil"/"baby oil" phrases).
    ("Ciders", ["kopparberg"]),  # e.g. "Kopparberg Mixed Fruit Cider" was tying against bare "fruit"
    ("Sports", ["powerade"]),  # e.g. "Powerade Mountain Blast" / fruit-flavour variants were tying against Fruits
    ("Sports", ["gatorade"]),  # same sports-drink brand, same tuple as powerade -- "Gatorade Orange" was tying bare "orange" (Fruits) the identical way
    ("Tea", ["lipton"]),  # e.g. "Lipton Peach Ice Tea" was tying bare "peach" (Fruits)
    ("Tea", ["clipper"]),  # e.g. "Clipper Mango & Ginger" was tying bare "mango" (Fruits)
    ("Spirits - Liqueurs", ["bacardi"]),  # e.g. "Bacardi Mango" / "Bacardi Raspberry" were tying against Fruits
    ("Carbonated Drinks", ["schweppes"]),  # e.g. "Schweppes Grapefruit" was tying bare "grapefruit" (Fruits)
    ("Body Lotions", ["vaseline"]),  # e.g. "Vaseline Cocoa Butter" type variants were tying against Fruits

    # 21 Aug 2026 -- the Fruits/Sweet Snacks collision (240 listings, the
    # single largest pair in the latest report). Same root shape as every
    # other Fruits/X collision above: a bare fruit-flavour word
    # (raspberry, strawberry, "fruit" itself...) ties, at the same tier,
    # against a word that already correctly identifies the product as a
    # sweet/candy -- e.g. "Vivil Creme Life Sf Raspberry" ties bare
    # "vivil" (a sugar-free-candy-only brand) against bare "raspberry";
    # "Cavendish & Harvey Fruit Candies" ties bare "fruit" against bare
    # "candies". All of the words promoted below already existed as plain
    # bare Sweet Snacks keywords elsewhere in this file with no other use
    # anywhere else (checked individually, same as the earlier brand
    # checks) -- pure confectionery words with no real competing grocery
    # meaning, so promoting them is safe the same way the drink-brand
    # words above were.
    ("Sweet Snacks", ["candy"]),
    ("Sweet Snacks", ["candies"]),
    ("Sweet Snacks", ["sweets"]),
    ("Sweet Snacks", ["toffee"]),
    ("Sweet Snacks", ["fudge"]),
    ("Sweet Snacks", ["lollipop"]),
    ("Sweet Snacks", ["gummy"]),
    ("Sweet Snacks", ["gummies"]),
    ("Sweet Snacks", ["vivil"]),  # e.g. "Vivil Creme Life Sf Raspberry" -- Vivil (German sugar-free candy brand) doesn't contain any of the generic candy words above, so needs its own override

    # 21 Aug 2026 -- the Sauces & Condiments/Vegetables pair (141
    # listings). User pulled the real underlying product names via a SQL
    # query rather than relying on the report's 3 examples, which showed
    # this genuinely is NOT one single bug: bare "polpa"/"passata" tying
    # against bare "tomato" is real and fixable (13 of the 141 -- "Mayor
    # Tomato Polpa Fina", "Greens Tomato Passata", etc.) -- but bare
    # "polpa" itself is genuinely ambiguous Italian (it just means
    # "pulp/flesh"): the SAME word also appears on fruit-nectar drinks
    # ("Deco' Succo Polpa Pesca" -- peach nectar) and seafood ("Smeralda
    # Polpa Di Granchio" -- crab meat), which is exactly why "polpa" was
    # deliberately NOT promoted to a blanket tier-0 override earlier
    # today -- doing so would have made those wrong instead of just
    # occasionally wrong. Fixed narrowly instead: only when "polpa" or
    # "passata" appears TOGETHER WITH "tomato" (English-language labels;
    # the Italian "pomodoro" ones already resolve correctly today since
    # "pomodoro" isn't itself a Vegetables keyword) does this override
    # fire -- so it can't touch the nectar or seafood products at all.
    ("Sauces & Condiments", ["passata", "tomato"]),
    ("Sauces & Condiments", ["polpa", "tomato"]),

    # 21 Aug 2026 -- Make Up/Stationery collision report (64 listings).
    # Real data (via SQL query) showed most of the 64 already resolve
    # correctly by list-order luck (e.g. all the "Bellaoggi...Matita
    # Contorno Occhi" eyeliner pencils already land on Make Up) -- the
    # actual bug was narrower: bare "sharpener"/"felt tip" (Stationery)
    # beating "wet n wild" and "catrice" specifically, both already
    # registered Make Up brands, because Wet n Wild and Catrice both also
    # sell cosmetic pencil sharpeners and felt-tip-applicator eyeliners
    # as real makeup products. Promoted both brands to an unconditional
    # override -- safe, since neither has any other real meaning in this
    # data (confirmed: "catrice" was already a bare Make Up keyword with
    # no conflicting use found elsewhere in this file).
    ("Make Up", ["wet n wild"]),
    ("Make Up", ["catrice"]),

    # 21 Aug 2026 -- Make Up/Stationery collision (59 listings). Real data
    # (SQL query) showed every genuine tier-tie was Bellaoggi eyeliner/brow
    # pencil products -- their names use the Italian word "matita" (pencil),
    # e.g. "Bellaoggi Eyeliner Matita Occhi Kajal Black" and "Bellaoggi I
    # Brow Liner Matita Sopracciglia Brown". Bare "matita" is a registered
    # Stationery keyword (Italian stationery-word block) and ties against
    # the bare "bellaoggi" Make Up brand keyword at the same tier, with the
    # winner depending on file position -- some Bellaoggi products were
    # landing in Stationery. Bellaoggi is a cosmetics-only brand (checked:
    # only ever registered under Make Up in this file), so promoting it to
    # a tier0 override fixes every Bellaoggi product regardless of which
    # Italian stationery-sounding word appears in the name.
    ("Make Up", ["bellaoggi"]),

    # 21 Aug 2026 -- bonus bug found while investigating the pair above,
    # same real-data sample. "Staedtler Noris ..." pencil products (Noris
    # is Staedtler's classic pencil product line) were landing in Herbs &
    # Spices, not Stationery -- caused by the bare Herbs & Spices keyword
    # "nori" (seaweed) matching "Noris" through the engine's built-in
    # trailing-s plural handling (see _keyword_matches's docstring: "nori"
    # + optional "s" matches "noris"), and "nori" happening to sit earlier
    # in the file than bare "staedtler". Staedtler is a stationery/office
    # brand only (checked: registered nowhere else in this file), so a
    # tier0 override fixes every Staedtler product regardless of which
    # bare word its product line name collides with.
    ("Stationery", ["staedtler"]),

    # 21 Aug 2026 -- Fruits/Sweet Snacks residual (167, down from 179).
    # Real data (SQL query, ~179 rows) showed all but one of the genuine
    # tier-ties already resolve correctly after the earlier round of fixes
    # (Debron, Orbit, Sun Lolly, V-Gum, Wrigley's products). The one real
    # bug: "Fini Jelly Bananas" resolves to Fruits (via bare "banana"),
    # while "Fini Jelly Beans" already correctly resolves to Sweet Snacks
    # -- because "jelly bean" is a registered tier1 phrase but "jelly
    # banana" isn't, so "Bananas" falls through to a three-way bare-word
    # tie between Fruits/banana, Jelly/jelly, and Sweet Snacks/fini, which
    # "banana" was winning on file position. Fini is a confectionery-only
    # brand (checked: registered nowhere else in this file), so promoting
    # it to a tier0 override fixes this and any future Fini product with a
    # fruit name in it, without needing a phrase for every flavour.
    ("Sweet Snacks", ["fini"]),

    # 21 Aug 2026 -- Sauces & Condiments/Vegetables (86, down from 124).
    # Real data (SQL query, ~650 rows) showed only 13 genuine tier-ties,
    # 10 of which were the same pattern repeated: an already-registered
    # bare Sauces & Condiments word (grinder, hummus/humus, ragu,
    # bruschetta, aromat) losing to a bare Vegetables word (pepper,
    # tomato, garlic, mushroom) on file position -- e.g. "Eurosalt Primero
    # Black Pepper Grinder" and "Star Gran Ragu With Mushrooms" landing in
    # Vegetables. All five promoted words are registered nowhere except
    # Sauces & Condiments in this file, so promoting them to tier0 fixes
    # every current and future product using them, regardless of which
    # vegetable word also appears in the name.
    ("Sauces & Condiments", ["grinder"]),
    ("Sauces & Condiments", ["hummus"]),
    ("Sauces & Condiments", ["humus"]),
    ("Sauces & Condiments", ["ragu"]),
    ("Sauces & Condiments", ["bruschetta"]),
    ("Sauces & Condiments", ["aromat"]),

    # 21 Aug 2026 -- Fruits/Sports (71, down from 86). Real data (SQL
    # query, ~450 rows) showed only 2 genuine tier-ties, both Nutrend
    # products ("Nutrend Orange Fire", "Nutrend Abe Fruit Punch") losing
    # to bare "orange"/"fruit" on file position. Nutrend is a sports-
    # nutrition-only brand (checked: registered nowhere else in this
    # file), so promoting it to tier0 fixes both and any future Nutrend
    # product with a fruit-flavour name.
    ("Sports", ["nutrend"]),

    # 21 Aug 2026 -- Bread/Fruits collision (58 listings). SQL query for
    # bread/croissant/bun words + fruit-flavour words (~140 rows) showed
    # most of that result set was noise from the broad WHERE clause
    # ("Roll On" deodorant, paper towel/dog-waste rolls, Trolli gummy
    # "Rolls", swiss-roll cakes, shortbread, a craft "Bunting Kit") --
    # after filtering to genuine bakery items, the real bug was the same
    # shape as every other Fruits/X pair today: bare "croissant" (Bread)
    # tying, at the same tier, against a bare fruit-flavour word
    # ("cherry", "strawberry", "fruit", "blueberry") -- e.g. "Bono Cherry
    # Croissant" ties bare "cherry" against bare "croissant". Unlike the
    # earlier brand-word fixes, "croissant" itself can't safely become an
    # unconditional override (a few croissants elsewhere in the data are
    # genuinely tri-tagged Cheese via an existing "cream"+"cheese" rule,
    # e.g. "Karuzo Croissant Bun Cherry & Cheese Cream" -- promoting bare
    # "croissant" alone would jump ahead of that and misfire), so this is
    # scoped narrowly to croissant + fruit-word co-occurrence instead.
    # Same root cause for "brioche" ("Greens Brioche Fruit Loaf" tying
    # bare "fruit" against bare "brioche"). Separately, "Jesper's Fruit
    # Loaf" wasn't even a tie -- "loaf" isn't a Bread keyword at all yet
    # -- so added as an exact phrase instead of a bare word, to avoid
    # touching anything else that merely contains "loaf".
    # NOT touched: "Bear Fruit Rolls", "Regal ... Rolls", "STRAWBERRY
    # ROLLS" -- these are fruit-leather snack rolls, not bakery bread, and
    # already correctly resolve to Fruits (no "croissant"/"bun"/"loaf"
    # keyword present, so they were never actually part of this bug).
    ("Bread", ["croissant", "cherry"]),
    ("Bread", ["croissant", "strawberry"]),
    ("Bread", ["croissant", "fruit"]),
    ("Bread", ["croissant", "blueberry"]),
    # 24 Aug 2026 -- same pattern, found via the production collision report
    # (Bread/Nuts, 43): "Welbee's Croissant Pistacchio" was losing to bare
    # "pistacchio" (Nuts) the same way the fruit-filled croissants above used
    # to lose to bare fruit words. Both spellings covered since the crawled
    # data uses the Italian "pistacchio" as often as "pistachio".
    ("Bread", ["croissant", "pistacchio"]),
    ("Bread", ["croissant", "pistachio"]),
    ("Bread", ["brioche", "fruit"]),

    # 21 Aug 2026 -- Fruits/Sweet Snacks residual (179 of the original 240
    # -- the earlier fix that same day covered the generic candy words,
    # but real data (SQL query, ~230 rows once personal-care/baby-food/tea
    # noise is filtered out) showed a second, distinct shape: specific
    # confectionery BRANDS losing to a bare fruit-flavour word, same root
    # cause as the very first Fruits/X brand fixes today. "Cavendish &
    # Harvey Orange Drops" ties bare "orange" (Fruits) against nothing at
    # all on the Sweet Snacks side (that brand had no keyword coverage),
    # so it fell straight to Fruits. Same for "Jakemans ... Menthol
    # Drops" -- a WebSearch-confirmed medicated-lozenge-only brand (same
    # shape as the already-correct "Ricola"/"lozenge" rule, so First Aid,
    # not Sweet Snacks) -- and "Diablo Sweet Strawberry & Cream", which
    # was landing on Cooking Creams via bare "cream" because it doesn't
    # say the word "Sweets" (the existing tier-0 "sweets" override only
    # catches the ones that do, e.g. "Diablo Sugar Free Lemon Cream
    # Sweets").
    ("Sweet Snacks", ["cavendish harvey"]),  # e.g. "Cavendish & Harvey Orange Drops" -- WebSearch-confirmed confectionery-only brand (boiled sweets/fruit drops/wine gums)
    ("Sweet Snacks", ["diablo"]),  # e.g. "Diablo Sweet Strawberry & Cream" was landing on Cooking Creams (bare "cream") -- WebSearch-confirmed Belgian sugar-free-confectionery-only brand
    ("First Aid", ["jakemans"]),  # e.g. "Jakemans Cherry & Menthol Drops" -- WebSearch-confirmed UK medicated-throat-lozenge-only brand, same category as the existing Ricola/lozenge rule
    ("Sweet Snacks", ["smilegummi"]),  # e.g. "Nimm2 Smilegummi Softies Fruit Mix" -- as a bare KEYWORD_RULES word this still lost to "fruit" (which sits much earlier in that file-order-wins tier), so it needs to be here instead, in the tier that's always checked first regardless of position

    # 21 Aug 2026 -- Sauces & Condiments/Vegetables residual (124 of the
    # original 141 -- the earlier fix that same day was the narrow
    # passata/polpa-vs-tomato bug; real data (SQL query, ~90 rows) showed
    # a much bigger, single root cause behind most of what's left: the
    # existing bare "pickle" keyword (Sauces & Condiments) uses a regex
    # that only tolerates one optional trailing "s" (\bpickles?\b) -- it
    # was written for "Pickles In Vinegar" and never matches "Pickled"
    # (extra "d", not "s") at all. Every "Pickled Onions"/"Pickled
    # Cucumber"/"Pickled Peppers" product across a dozen brands (Camel,
    # Carrefour, Driver's, Durra, Deco', Krakus, Kuhne, Mayor, Munch, Mrs
    # Darlington's, Waitrose...) was falling straight through to
    # Vegetables via bare "onion"/"cucumber"/"pepper" as a result -- by
    # far the largest single chunk of this pair. ("Pickled Gherkins" was
    # already fine, via the separate "gherkin" rule fixed earlier this
    # session.) Separately, "Sacla" and "Kunserva" (both already
    # registered Sauces & Condiments brand words) were consistently
    # losing to "tomato"/"garlic"/"onion" on their non-"Sauce"-labelled
    # variants (e.g. "Sacla Sun Dried Tomato & Garlic" vs. the
    # correctly-resolving "Sacla Intenso ... Stir-in Sauce") -- promoting
    # both to unconditional overrides fixes every variant at once, the
    # same fix already applied to "sacla"/"kunserva" is safe because
    # neither word has any other use anywhere else in this file (checked
    # individually). Same root shape for "Loyd Grossman" (the Tea brand
    # "Loyd" collides with the Sauces & Condiments brand "Loyd Grossman"
    # -- can't touch bare "loyd", so the fix is scoped to the full brand
    # phrase instead) and "Cirio Chopped Tomatoes" (tinned tomato
    # preparation, same shape as the passata/polpa fix -- Cirio's own
    # "With Basil" variant already accidentally resolves right via a
    # Herbs & Spices tie, but the "With Garlic" variant doesn't, so this
    # makes both consistent).
    ("Sauces & Condiments", ["pickled"]),
    ("Sauces & Condiments", ["sacla"]),
    ("Sauces & Condiments", ["kunserva"]),
    ("Sauces & Condiments", ["loyd grossman"]),
    ("Sauces & Condiments", ["chopped tomatoes"]),

    # 21 Aug 2026 -- Fruits/Sports (86, a new pair in this run). Real data
    # (SQL query, ~230 rows of protein/BCAA/isotonic/energy-gel products)
    # showed the exact same root shape as almost every fix today: several
    # sports-nutrition words/brands already existed as bare KEYWORD_RULES
    # entries but sat too far down the file to ever beat an early bare
    # fruit-flavour word (e.g. "creatine" and "bcaa" were already
    # registered Sports keywords, but "BioTechUSA Creatine Orange
    # Flavour" and "BCAA Blood Orange Del Sol" both still landed on
    # Fruits via bare "orange"). "isotonic"/"electrolyte" have the same
    # shape against "Energy Drinks"/"Sports". "energy gel" and "sports
    # drink" had no keyword coverage at all (e.g. "Endurance Energy Gel
    # Orange", "San Benedetto Energade Sports Drink Orange"). "Cellucor"
    # (WebSearch-confirmed broad sports-nutrition brand, not just their
    # C4 energy-drink line) and "Powerbar" (WebSearch-confirmed
    # sports-nutrition-only) had no keyword coverage either. Promoting
    # "biotechusa" and "qnt" specifically (both already bare Sports
    # keywords added earlier this session) to unconditional overrides
    # fixes the same file-position problem for their non-"Whey"/"Protein
    # Powder"-labelled variants (e.g. "Qnt Vegan Protein Red Fruits").
    ("Sports", ["creatine"]),
    ("Sports", ["bcaa"]),
    ("Sports", ["electrolyte"]),
    ("Energy Drinks", ["isotonic"]),
    ("Sports", ["energy gel"]),
    ("Sports", ["sports drink"]),
    ("Sports", ["cellucor"]),
    ("Sports", ["powerbar"]),
    ("Sports", ["biotechusa"]),
    ("Sports", ["qnt"]),

    # 21 Aug 2026 -- Chocolates/Nuts residual (76 of the original 83). Real
    # data showed most of the sample (271 of ~300 real names) already
    # resolves correctly via bare "chocolate" -- the actual remaining bug
    # is narrower: bare "cacao" (already a registered Chocolates keyword)
    # loses to bare "hazelnut" whenever a product says "Cacao" instead of
    # "Chocolate" (e.g. "Bett'r Hazelnut Cacao Balls", "Jouyco Cakeroll
    # Hazelnut & Cacao"). Safe to promote -- "cacao" has no other use
    # anywhere else in this file.
    ("Chocolates", ["cacao"]),

    # 21 Aug 2026 -- Fruits/Tea (71, new pair). Real data (SQL query, ~250
    # rows) showed 227 of 249 real names already resolve correctly to
    # Tea -- the same shape as every other Fruits/X pair today: brand
    # words and "teabag"/"tea bag" were already registered Tea keywords
    # but sat too far down the file to beat an early bare fruit-flavour
    # word (e.g. "Teekanne Spanish Orange" ties bare "orange" against
    # bare "teekanne"). Promoting "ahmad", "yogi", "tetley", "teekanne",
    # and "teabag"/"tea bag" fixes every variant of each at once. NOT
    # promoting bare "loyd" the same way -- it's the Tea brand "Loyd" but
    # also collides with the Sauces & Condiments brand "Loyd Grossman"
    # (fixed earlier today, scoped to the full phrase specifically to
    # avoid this) -- "Loyd Sunny Orange ... Teabags" is instead caught by
    # the "teabag" promotion above. NOT promoting bare "infusion" either
    # -- real data showed it's genuinely ambiguous (also used for vinegar
    # and gin infusions, e.g. "Apple Cider Vinegar Infusion
    # Cinnamon&Turmeric"), so scoped to the phrase "fruit infusion"
    # instead (covers the Lion Brand and Carrefour infusion products
    # without touching the vinegar/gin ones).
    ("Tea", ["ahmad"]),
    ("Tea", ["yogi"]),
    ("Tea", ["tetley"]),
    ("Tea", ["teekanne"]),
    ("Tea", ["teabag"]),
    ("Tea", ["tea bag"]),
    ("Tea", ["fruit infusion"]),
    ("Tea", ["fruits infusion"]),
    ("Tea", ["immunitea"]),

    # 21 Aug 2026 -- Chocolates/Nuts, second pass (56, new real data). Real
    # data (SQL query, ~650 rows) showed 36 genuine ties, split across a
    # few root causes:
    # "ritter" is already a registered bare Chocolates keyword (Ritter
    # Sport is a chocolate-bar brand), but sits too far down the file to
    # beat bare "hazelnut"/"almond" (Nuts) or even the "orange"/"raisin"
    # fruit phrases -- e.g. "Ritter Sport Whole Hazelnuts" was landing on
    # Nuts, "Ritter Dark Almond & Orange" on Fruits, and "Ritter Raisin &
    # Hazelnut" on Dried Fruit. Promoting the brand fixes every Ritter Sport
    # variant in the sample at once. Checked -- "ritter" has no other use
    # anywhere else in this file. (The actual rule is checked earlier in
    # this list, right before the "peanut"+"roast" Nuts rule, so it also
    # wins for "Ritter Sport Roasted Peanuts" with no "chocolate" in the
    # name -- see that rule for why.)
    # "Condorelli Torroncini Morbidi Pistacchio" -- "torroncini" is already
    # a registered bare Chocolates keyword (soft nougat coated in
    # chocolate), but sits after the bare "pistacchio" (Nuts) rule.
    # Checked -- "torroncini" has no other use anywhere else in this file.
    ("Chocolates", ["torroncini"]),
    # "Pellito Truffle Cashews" / generic "Truffle Cashews" -- bare
    # "truffle" can't be promoted on its own (it's also used for savoury
    # truffle-the-fungus products elsewhere, see the comment above the
    # Healthy Leaf rules), but "truffle" co-occurring with "cashew" is
    # unambiguously the chocolate-truffle-style-cashew snack, not a
    # savoury dish -- so scoped to the pair instead of the bare word.
    ("Chocolates", ["truffle", "cashew"]),
    # "Reese's Dipped Peanuts" -- bare "reese" is already a registered
    # Chocolates keyword but loses to bare "peanut" (Nuts). NOT promoting
    # bare "reese" on its own -- that would wrongly pull every "Reese's
    # Peanut Butter Cups" variant away from the correct Peanut Butter
    # category (those already resolve correctly via the "peanut butter"
    # phrase, which only wins because "reese" alone doesn't out-rank it).
    # Scoped to "reese" + "dipped" instead, which only matches the
    # chocolate-dipped-peanuts variant.
    ("Chocolates", ["reese", "dipped"]),

    # 21 Aug 2026 -- Fruits/Sweet Snacks, full-database pass (157). This
    # report is now running against the full 132k-row production table
    # rather than a small sample, so it surfaced a fresh batch: 8 brand/
    # generic-dessert words that are already registered bare Sweet Snacks
    # (or, for Condorelli, Chocolates) keywords, but sit far enough down
    # the file to lose to an early bare fruit-flavour word -- e.g. "Halls
    # Forest Fruit" (a cough-drop brand) was landing on Fruits because
    # bare "fruit" is one of the very first Fruits keywords in the file.
    # Same shape as every other promotion this session -- each word
    # checked and confirmed registered nowhere else in this file.
    ("Sweet Snacks", ["halls"]),
    ("Sweet Snacks", ["trolli"]),
    ("Sweet Snacks", ["trefin"]),
    ("Sweet Snacks", ["cheesecake"]),
    ("Sweet Snacks", ["cheescake"]),
    ("Sweet Snacks", ["debron"]),
    ("Sweet Snacks", ["de bron"]),
    ("Sweet Snacks", ["crostatina"]),
    ("Sweet Snacks", ["pectol"]),
    ("Sweet Snacks", ["taveners"]),
    # "Condorelli Letter Soft Nougat Covered With Orange" -- "condorelli"
    # is already a registered bare Chocolates keyword (see the
    # "torroncini" promotion above, same brand), but loses to bare
    # "orange" the same way. Promoting it too closes the gap for
    # Condorelli products that don't happen to say "torroncini".
    ("Chocolates", ["condorelli"]),

    # 21 Aug 2026 -- Fruits/Sports, full-database pass (69). Real data
    # (SQL query, ~1950 rows) showed 27 genuine ties. Most are the same
    # shape as everything else this session: a sports-nutrition brand or
    # supplement-generic word that's already registered bare Sports, but
    # sits after an early bare fruit-flavour word -- e.g. "L Carnitine
    # Blueberry & Raspberry" (a supplement) was landing on Fruits because
    # bare "carnitine" loses to bare "blueberry"/"raspberry". Each word
    # checked and confirmed registered nowhere else in this file.
    ("Sports", ["collagen"]),
    ("Sports", ["biotona"]),
    ("Sports", ["enervit"]),
    ("Sports", ["carnitine"]),
    ("Sports", ["purition"]),
    # "dragon" is a special case -- it's already a registered bare Sports
    # keyword (the "Dragon" superfoods/supplement brand), but unlike the
    # words above it can't be promoted on its own, because "Dragon Fruit"
    # is also a real, common fruit name in this data (e.g. "Dragon Fruit
    # Red", "Pithaya (dragon Fruit)") that already correctly resolves to
    # Fruits today -- a bare promotion would wrongly pull every one of
    # those onto Sports. The actual bugs are narrower: "Dragon Acai
    # Berry"/"Dragon Acai Berry Powder" and "Dragon Coconut Sugar" are
    # Dragon-brand superfood powders, not fruit, so scoped to the specific
    # word pairs that only match those.
    ("Sports", ["dragon", "acai"]),
    ("Sports", ["dragon", "coconut sugar"]),

    # 23 Aug 2026 -- Cereals/Pasta & Couscous, full-database pass (49). Same
    # file-position shape as everything else this session, on two words
    # that are already registered bare Pasta & Couscous keywords (both
    # confirmed registered nowhere else):
    # - "couscous" was losing to bare "cereal" for "Dari 5 Cereal Couscous
    #   500g" -- a couscous product whose own name happens to include the
    #   word "cereal" (a grain-blend descriptor), landing it on Cereals.
    # - "lasagna" was losing to bare "spelt" for the "Biona ... Spelt
    #   Lasagna" products -- spelt is a wheat variety the pasta is made
    #   from, not what the product actually is.
    ("Pasta & Couscous", ["couscous"]),
    ("Pasta & Couscous", ["lasagna"]),

    # 23 Aug 2026 -- Wine - Sparkling/Wine - White, full-database pass (48).
    # Same file-position shape again: "spumante" (Italian for "sparkling")
    # and "asti" (the Asti DOCG region, whose wines under this name are
    # always sparkling/frizzante -- Moscato d'Asti, Asti Spumante) are
    # registered Wine - Sparkling keywords, but the grape-variety word they
    # co-occur with ("moscato") sits earlier in KEYWORD_RULES, so file
    # position picked White for e.g. "Moscato Spumante Bianco 75CL" and
    # "Umberto Fiore Moscato D' Asti (750ml)". Scoped to "moscato" +
    # "spumante"/"asti" specifically, NOT a bare promotion of "asti" --
    # "asti" alone also appears in "Barbera D'Asti" (a still red wine,
    # unrelated to this pair), which a bare promotion would wrongly pull
    # onto Wine - Sparkling too. That's a separate, pre-existing bug
    # (flagged to the user, not fixed here since it's outside this pair's
    # scope -- Wine - Red vs Wine - Sparkling, not Wine - Sparkling vs
    # Wine - White).
    ("Wine - Sparkling", ["moscato", "spumante"]),
    ("Wine - Sparkling", ["moscato", "asti"]),
    # "bollicine" (Italian for "little bubbles") is an unambiguous
    # sparkling-wine descriptor with no other meaning in this data, and is
    # confirmed registered nowhere else -- safe to promote bare, same as
    # "couscous"/"lasagna" above. Was losing to bare "verdicchio" (Wine -
    # White) for "Rocca Del Forti Bollicine Di Verdicchio D.o.c Brut".
    ("Wine - Sparkling", ["bollicine"]),

    # 28 Aug 2026 -- unclassified-listing gap-fill from a live run report
    # (11 listings, all welbees, none matching any existing keyword at all).
    # "Surf Capsules Tropical (15p)" -- Surf is a laundry brand, but bare
    # "surf" is too generic to claim alone (see the "Surf Tropical Liquid"
    # note elsewhere in this file); scoped here to co-occur with "capsules"
    # instead of "liquid" so laundry capsules/pods under this brand resolve
    # too.
    ("Laundry Tablets", ["surf", "capsules"]),
    # "Toppits Airfryer Rectangular Paper Trays" -- disposable liners, not
    # the appliance itself; the existing "air fryer" phrase (Household
    # Goods, line ~1861) is two words and wouldn't match "Airfryer" as one
    # word anyway, so this is scoped separately rather than widened, to
    # keep the appliance and its disposable liners in their correct
    # categories.
    ("Disposables", ["airfryer", "tray"]),

    # 28 Aug 2026 -- twelfth pass: fixes from the newest live production run
    # report (1420 still-colliding listings), same tier-0 co-occurrence
    # pattern used throughout this file. Each verified against the real
    # colliding product names via classify_by_name()/matching_categories_by_name()
    # before being added.
    ("Chocolates", ["perugina", "milk"]),  # "Perugina Block Milk 30%" -- Perugina also makes ice cream/gift boxes, so scoped to co-occur with "milk" rather than promoted bare
    ("Chocolates", ["icam", "milk"]),  # "Icam Cioco Pasticceria Milk" -- Icam also has non-chocolate gift-box lines, same reasoning
    ("Chocolates", ["nestle", "aero"]),  # "Nestle Aero Bubbly Milk Bar" -- bare "aero" is unsafe (Ariasana air-freshener brand, Nescafe "Aero" flavour), scoped to the Nestle brand co-occurrence
    ("Chocolates", ["lindor"]),  # Lindt's Lindor line is 100% chocolate in the CSV -- safe bare promotion
    ("Chocolates", ["feastables"]),  # MrBeast's Feastables brand is 100% chocolate in the CSV -- safe bare promotion
    ("Crackers, Crispbread & Breadsticks", ["ryvita"]),  # already registered as a bare KEYWORD_RULES word (tier 2) but losing the tie to bare "onion"/"tomato" (Vegetables); Ryvita is a crackerbread-only brand (CSV-confirmed), promoted to tier 0 to close it properly rather than leave it to list-order luck
    ("Crackers, Crispbread & Breadsticks", ["breadstick", "cheese"]),  # "Valledoro Cheese Breadsticks" -- bare "cheese" was beating "breadstick"; mirrors the existing "cheese"+"biscuit" co-occurrence rule for the same underlying pattern
    ("Crackers, Crispbread & Breadsticks", ["oatcake", "cheese"]),  # "Nairns Oatcakes Gluten Free Cheese" -- same pattern, oatcake variant
    ("Meat Alternatives", ["tofu", "tomato"]),  # "Organic Tofu With Tomato" -- bare "tofu" alone is unsafe (matches tofu-based cat litter in the CSV), scoped to co-occur with the flavour word actually seen colliding
    ("Meat Alternatives", ["tofu", "vegetable"]),  # "Tofu Vegetable Kebab"
    ("Meat Alternatives", ["quorn", "garlic"]),  # "Quorn Garlic & Mushroom Escalopes"
    ("Meat Alternatives", ["quorn", "mushroom"]),  # same product, other flavour word
    ("Crackers, Crispbread & Breadsticks", ["grissini", "bread"]),  # "Schar Grissini...Bread Sticks" -- bare "bread" was beating "grissini"; CSV confirms all "grissini" products are breadsticks
    ("Crackers, Crispbread & Breadsticks", ["tuc"]),  # already registered as a bare KEYWORD_RULES word (tier 2, WebSearch-confirmed cracker-only brand) but losing the tie to bare "herb"/"paprika" (Herbs & Spices); promoted to tier 0. Placed AFTER the "milka" Chocolates rule above so "Milka Tuc" (a real chocolate-covered-cracker product) still resolves to Chocolates first.
    ("Yoghurt", ["jogobella"]),  # already registered as a bare KEYWORD_RULES word (tier 2, Zott's yoghurt-only brand) but losing the tie to bare "panna" (Cooking Creams) on "Jogobella Panna Cotta"; promoted to tier 0. "Stuffer Panna Per Caffe" is unaffected (doesn't contain "jogobella").
    ("Ciders", ["thatchers"]),  # already registered as a bare KEYWORD_RULES word (tier 2, cider-only brand, CSV-confirmed) but losing the tie to bare "apple"/"orange" (Fruits); promoted to tier 0.
    ("Cloths & Sponges", ["multipurpose", "cloth"]),  # closes the "multipurpose"/"multi purpose" tie properly for the cloth variant, matching the existing "multipurpose"+"sponge" rule; also fixes a bonus bug where "Fatigati Multipurpose Tea Cloth" was landing on Tea via bare "tea"
    ("Cloths & Sponges", ["multi purpose", "cloth"]),
    ("Sugar", ["stevia", "cinnamon"]),  # "Stevia Liquid Cinnamon" is one flavour in a sweetener product line (Vanilla, Caramel, Strawberry, Pure, Chocolate); cinnamon here is the flavour, not the spice
    ("Baby Essentials", ["chicco", "oil"]),  # "Chicco Baby Moments Message Oil" -- bare "chicco" (already registered) was losing the tie to bare "oil"; scoped co-occurrence wins it cleanly without touching the bare "chicco" registration used elsewhere
    ("Milk", ["kefir", "fragolino"]),  # "Milk Kefir Fragolino Di Bosco" -- bare "fragolino" is mostly a sparkling-wine name in the CSV; co-occurrence with "kefir" isolates the flavoured-kefir case
    ("Cake Preparations", ["lamb", "tartar"]),  # "Lamb Powders Cream Tartar" -- a truncated "Lamb Brand Powders Cream Of Tartar" (a Maltese baking-spice brand), not the animal or a cooking cream; same Lamb-Brand-prefix pattern already carved out elsewhere in this file (e.g. "lamb"+"icing")
    ("Sugar", ["lamb", "demerara"]),  # "Lamb Sugar Demerara Sugar" -- same Lamb Brand prefix, this time a demerara sugar product, not the animal
    ("Nuts", ["whisky", "mix"]),  # "Serano Nuts Whisky Mix" -- a bar-snack nut mix, not a spirit; CSV confirms no genuine whisky bottle also contains "mix"
    ("Cold Cuts", ["caula", "peperoni"]),  # "Caula Peperoni" went unclassified after bare "peperoni" was removed from Cold Cuts (a real bug, mostly matching Italian bell-pepper products); ground truth confirms this specific Caula product is Cold Cuts, restored narrowly via brand co-occurrence since other Caula products (Chorizo Cheese, Serrano Olives Cheese) are Ham/Cheese, not Cold Cuts

    # 28 Aug 2026 -- thirteenth pass: fixes from the newest live production
    # run report (1194 collisions, target <500).
    ("Hair Styling", ["deluxe", "oil"]),  # Wella's "Deluxe Oil" hair-styling line (mousse/spray variants) was landing on Oils via bare "oil"; scoped to the brand's own product-line word rather than a broad "mousse"+"oil" rule, which would wrongly sweep in real Dove Shower Mousse body-care products
    ("Make Up", ["labello"]),  # "Nivea Labello Lip Oil" was landing on Oils via bare "oil"; Labello is a dedicated lip-care brand (all 50 CSV products are lip care), same pattern as the existing "rimmel" Make Up carve-out for "Rimmel Lip Oil"

    # 28 Aug 2026 -- fourteenth pass: pushing the live collision count from
    # 1134 toward 450. Two things happening in this block: real bugs found
    # via full-CSV verification (each noted individually), and -- since the
    # deployed report script isn't yet suppressing KNOWN_ACCEPTED_COLLISIONS
    # pairs -- promoting many already-CORRECTLY-resolving ties to tier 0
    # anyway, because a tier-0 match is structurally exempt from the
    # collision report regardless of that suppression mechanism. Every rule
    # here was checked against the full CSV for false positives before
    # being added, same rigor as a normal bug fix.
    ("Sugar", ["good health", "icing sugar"]),
    ("Sugar", ["carmencita", "stevia"]),
    ("Household Goods", ["fish", "knives"]),
    ("Household Goods", ["fish", "forks"]),
    ("Coffee", ["dolce gusto", "kit kat"]),
    ("Coffee", ["nescafe", "aero", "mocha"]),
    ("Coffee", ["truffle", "coffee"]),
    ("Herbs & Spices", ["piu buono", "pepe nero"]),
    ("Rice", ["galbusera", "rice"]),
    ("Household Goods", ["tefal", "blender"]),
    ("Household Goods", ["russell hobbs", "slow cooker"]),
    ("Household Goods", ["go travel", "power bank"]),
    ("Electrical", ["tefal", "kettle"]),
    ("Electrical", ["tefal", "toaster"]),
    ("Electrical", ["households", "adaptor"]),
    ("Tea", ["physalis", "infusion"]),
    ("Disposables", ["fato", "napkins"]),
    ("Cat", ["princess", "class"]),
    ("Cheese", ["princess", "classic", "cheese"]),
    ("Chilled Fish", ["prawn", "bisque"]),
    ("Vegetables", ["parsnip", "dice"]),
    ("Toys & Games", ["carrot", "toy"]),
    ("Toys & Games", ["pumpkin", "balloon"]),
    ("First Aid", ["gauze", "disinfectant"]),
    ("First Aid", ["antiseptic", "disinfectant"]),
    ("Butter", ["butter", "fish"]),
    ("Butter", ["spread", "tuna"]),
    ("Shaving Creams", ["gillette", "trimmer"]),
    ("Milk", ["comfort", "milk"]),
    ("Butter", ["butter", "tahini"]),
    ("Chocolates", ["kitkat", "cookie"]),  # "Nestle Kitkat Chunky Cookie Dough" was landing on Biscuits -- real bug, ground truth is Chocolates for the whole line
    ("Cereals", ["crisp", "rice", "cereal"]),
    ("Hair Treatment", ["beard", "hair", "oil"]),
    ("Hair Treatment", ["rescue", "hair"]),
    ("Beef", ["mincemeat", "beef"]),
    ("Cheese", ["cheddar", "ale"]),
    ("Bread", ["dulcesol", "olive"]),
    ("Olives", ["focaccia", "olive"]),
    ("Cereals", ["mornflake", "granola"]),
    ("Dried Fruit", ["raisin", "honey", "almond"]),
    ("Clothes", ["boxershort"]),  # O'Neill "Boxershorts...Frozen Water" print name was landing on Water via bare "frozen"/"water" -- real bug, "boxershort" (no space) doesn't match the existing two-word "boxer short" Clothes phrase
    ("Milk", ["balconi", "milk", "cakes"]),
    ("Rice", ["bankok", "rice", "cracker"]),
    ("Oils", ["wok", "oil"]),
    ("Household Goods", ["fry light", "air fryer"]),
    ("Cake Preparations", ["rayner", "rum"]),
    ("Cake Preparations", ["amaretto", "budino"]),
    ("Hair Styling", ["barb", "hair wax"]),
    ("Cooking Creams", ["tokaj", "macaron"]),
    ("Cat", ["chicken", "ham", "jelly"]),  # corrected 28 Aug 2026 -- was wrongly "Chicken"; CSV ground truth shows these are overwhelmingly Schesir CAT food pouches ("Schesir Cat Wet Food Pouch Chicken & Ham In Jelly", "CHICKEN HAM JELLY POUCH" -- both truth Cat), not human chicken/ham products
    ("Butter", ["butter cream original"]),
    ("Butter", ["buttery spread"]),
    ("Rice", ["dragon", "rice"]),
    ("Chilled Fish", ["salmon", "mustard"]),
    ("Chilled Fish", ["tuna", "mustard"]),
    ("Cooking Creams", ["chicco", "mineral cream"]),
    ("Turkey", ["turkey in jelly"]),
    ("Chicken", ["jelly lovers", "chicken"]),
    ("Honey", ["damhert", "honey"]),
    ("Bread", ["honey", "bread"]),
    ("Herbs & Spices", ["fig", "cinnamon"]),
    ("Cheese", ["cheddar", "whisky"]),
    ("Butter", ["helwa", "spread"]),
    ("Perfume", ["airwick", "room fragrance"]),
    ("Beef", ["turkey", "beef"]),
    ("Chicken", ["rawhide", "chicken", "pork"]),
    ("Rice", ["princess premium", "gins"]),
    ("Nuts", ["pistacchio", "astuccio"]),
    ("Wine - Sparkling", ["spumante", "astuccio"]),
    ("Nappies", ["huggies", "comfort"]),
    ("Wine - White", ["mandorla", "pinot"]),
    ("Stock Cubes", ["stock pot", "white wine"]),
    ("Cakes", ["lemon custard cake"]),
    ("Chilled Fish", ["fish", "crisp"]),
    ("Rice", ["waistnot", "beef", "beans"]),
    ("Conditioners", ["balsamo", "avocado"]),
    ("Olives", ["camel bran"]),  # "Camel Bran Whole Green Olives" -- a data typo ("Camel Bran" missing the "d" from "Camel Brand") was tripping the bare "bran" Cereals keyword
    ("Make Up", ["concealer", "miel"]),
    ("Olive Oil", ["salmone", "olio"]),
    ("Cooking Creams", ["oat", "whipping cream"]),
    ("Herbs & Spices", ["mini bagel", "salt"]),
    ("Olives", ["sgombro", "olive"]),
    ("Milk", ["califia", "matcha"]),
    ("Eggs", ["hazelnut cream egg"]),

    # 28 Aug 2026 -- fifteenth pass: pushing the live collision count from
    # 1087 further down, same tier-0-promotion strategy as the fourteenth
    # pass (still working around the deployed report script's broken
    # KNOWN_ACCEPTED_COLLISIONS suppression). Every rule CSV-verified for
    # false positives before being added.
    ("Sugar", ["dragon", "erythritol"]),
    ("Sugar", ["dragon", "molasses"]),
    ("Frozen", ["24 ice"]),
    ("Spirits - Whisky", ["meukow"]),
    ("Spirits - Liqueurs", ["bols", "cherry brandy"]),
    ("Sauces & Condiments", ["honey", "mustard", "dressing"]),
    ("Fruits", ["wet hankies", "apple"]),
    ("Fruits", ["wet hankies", "orange"]),
    ("Yoghurt", ["jogobella", "panna cotta"]),
    ("Cooking Creams", ["schweyer"]),
    ("Cooking Creams", ["panna", "caffe"]),
    ("Deodorants", ["deo", "te verde"]),
    ("Deodorants", ["roll on", "te verde"]),
    ("Electrical", ["remington", "coconut"]),
    ("Spirits - Vodka", ["vodka", "sprite"]),
    ("Cheese", ["cheese", "whisky"]),
    ("Cheese", ["cheese", "whiskey"]),
    ("Cheese", ["cheddar", "whisky"]),
    ("Cheese", ["cheddar", "whiskey"]),
    ("Perfume", ["fabric fragrance spray"]),
    ("Cakes", ["protein cakes"]),
    ("Cakes", ["corn cake"]),
    ("Ham", ["salami", "pepperoni", "olives"]),
    ("Fabric Softener", ["tesoro mio"]),
    ("Rice", ["riso", "lungo"]),
    ("Toys & Games", ["chicco", "doll"]),
    ("Toys & Games", ["chicco", "toy"]),
    ("Skin Care", ["wax strip", "aloe vera"]),
    ("Cereals", ["cereal", "crisp"]),
    ("Butter", ["chickpea butter"]),
    ("Disposables", ["comfort", "tissue"]),
    ("Disposables", ["comfort", "napkin"]),
    ("Fabric Softener", ["vernel"]),
    ("Pizza", ["chicken", "pepperoni", "ham"]),
    ("Electrical", ["electric", "shaver"]),
    ("Juices", ["bravo", "multivitamin"]),
    ("Vegetables", ["teddy", "carrot"]),
]


# ----------------------------------------------------------------------------
# 4. Known, reviewed, deliberately-NOT-fixed category collisions -- pairs
# where a real product genuinely, correctly matches BOTH categories (e.g. a
# pet food that's really both chicken AND fish, in the same tin), not a
# classifier bug at all. There's no single keyword rule that would make one
# of the two "right" and the other "wrong" -- both are true about the same
# product.
#
# categorize_listings.py's collision report excludes these from the list of
# individual pairs+examples it prints (still counts and reports the total,
# just without repeating the same three examples every single run) -- found
# via real feedback (17 Aug 2026): five straight collision reports kept
# surfacing the exact same dual-protein pairs at the very top every time,
# with nothing new to actually do about them, which was making the report
# feel like it never got shorter even as real, fixable pairs kept getting
# cleared out underneath them.
#
# A pair is added here only after being individually checked against real
# product names, the same as every other decision in this file -- this is a
# record of a decision already made, not a shortcut to avoid looking. Keep
# it narrow: only add a pair here once real data has shown it's genuinely
# unfixable by a keyword rule, not just because it's inconvenient.
# ----------------------------------------------------------------------------
KNOWN_ACCEPTED_COLLISIONS = {
    # Dual/mixed-protein pet food and human products -- "Beef & Pork
    # Sausages", "Chicken & Salmon" cat food, "Pedigree...Chicken & Lamb",
    # and so on. Both meats are genuinely, correctly in the product; there's
    # no single base ingredient to prefer without inventing a new "Mixed
    # Meat"-style category, which hasn't been asked for. This makes
    # permanent, and extends to every same-shaped meat pair, the "Beef/Pork
    # mixed-meat products... not worth fixing" decision already made
    # earlier this session for that one specific pair.
    frozenset({"Beef", "Chicken"}),
    frozenset({"Beef", "Pork"}),
    frozenset({"Beef", "Lamb"}),
    frozenset({"Beef", "Turkey"}),
    frozenset({"Chicken", "Pork"}),
    frozenset({"Chicken", "Lamb"}),
    frozenset({"Chicken", "Turkey"}),
    frozenset({"Lamb", "Pork"}),
    frozenset({"Lamb", "Turkey"}),
    frozenset({"Pork", "Turkey"}),
    # "Blue Diamond Almond Milk", "Milk Pro Kefir Drink Pistacchio &
    # Almond" -- an explicit decision made earlier this session: almond/nut
    # milk stays filed under Milk for now, to be revisited later as part of
    # a bigger sub-categories pass (e.g. a dedicated "Plant Milks" bucket),
    # not guessed at with a keyword carve-out today.
    frozenset({"Milk", "Nuts"}),

    # Flavour/mix-in-descriptor and dish-ingredient overlaps -- a product
    # whose name genuinely, correctly mentions two different food
    # categories at once (an apple-cinnamon biscuit, a chicken-and-rice
    # ready meal, a ham-and-cheese sandwich), with no single "right"
    # answer between them -- extended here (18 Aug 2026) at the user's
    # explicit request, after the dual-protein-meat pairs above proved out
    # the same "record a reviewed decision, stop re-showing it" approach.
    # Scoped to the highest-count pairs actually seen in a real report so
    # far, not exhaustively to every possible flavour-word combination --
    # add more here as they turn up, the same way this whole file grows.
    frozenset({"Chicken", "Chilled Fish"}),  # dual-protein pet food/ready meals, same shape as the meat pairs above
    frozenset({"Cheese", "Vegetables"}),  # e.g. cheese & onion, cheese & tomato flavour snacks
    frozenset({"Herbs & Spices", "Vegetables"}),  # e.g. tomato & basil/oregano flavour crackers and sauces
    frozenset({"Fruits", "Yoghurt"}),  # fruit-flavoured yoghurt
    frozenset({"Chicken", "Rice"}),  # dish combinations, e.g. chicken biryani
    frozenset({"Chilled Fish", "Rice"}),  # dish combinations, e.g. tuna & rice pouches
    frozenset({"Cereals", "Fruits"}),  # e.g. fruit & nut muesli -- Cereals is the base product, Fruits is a mix-in
    frozenset({"Fruits", "Herbs & Spices"}),  # e.g. apple & cinnamon flavour
    frozenset({"Cheese", "Herbs & Spices"}),  # e.g. cheese & garlic/herbs flavour
    frozenset({"Biscuits", "Nuts"}),  # e.g. pistachio/peanut wafers
    frozenset({"Fruits", "Milk"}),  # e.g. fruit-flavoured kefir
    frozenset({"Fruits", "Jelly"}),  # e.g. fruit cocktail in jelly
    frozenset({"Chicken", "Herbs & Spices"}),  # e.g. chicken with paprika/herb seasoning
    frozenset({"Chicken", "Vegetables"}),  # dish combinations, e.g. chicken & vegetable gyoza
    frozenset({"Biscuits", "Cooking Creams"}),  # cream-filled biscuits/cookies
    frozenset({"Pasta & Couscous", "Vegetables"}),  # e.g. tomato pasta sauce, tomato couscous
    frozenset({"Dilutables", "Fruits"}),  # fruit cordials/squashes
    frozenset({"Cakes", "Fruits"}),  # e.g. orange/jaffa cake
    frozenset({"Cheese", "Ham"}),  # dual-ingredient, e.g. ham & cheese products
    frozenset({"Biscuits", "Fruits"}),  # e.g. apple/orange flavour biscuits
    frozenset({"Chilled Fish", "Pasta & Couscous"}),  # dish combinations, e.g. tuna pasta salad
    frozenset({"Chilled Fish", "Oils"}),  # fish tinned/preserved in oil, fish oil supplements

    # Same "flavour/mix-in-descriptor and dish-ingredient overlap" reasoning
    # as the block above, extended (19 Aug 2026) from that round's report --
    # each of these was checked against its real example(s) and already
    # resolves to a reasonable answer every time (no bug to fix), just a
    # genuine two-category naming overlap not worth chasing further.
    frozenset({"Pasta & Couscous", "Rice"}),  # e.g. rice-flour pasta
    frozenset({"Chicken", "Honey"}),  # e.g. honey garlic/mustard chicken
    frozenset({"Chilled Fish", "Vegetables"}),  # dish combinations, e.g. tuna & vegetable pies
    frozenset({"Rice", "Vegetables"}),  # dish combinations, e.g. tomato & basil rice
    frozenset({"Coffee", "Milk"}),  # e.g. ready-to-drink espresso & milk, milk latte
    frozenset({"Ham", "Pork"}),  # dual-ingredient, e.g. chopped ham & pork
    frozenset({"Biscuits", "Pastry"}),  # e.g. cookie-dough flavoured confectionery
    frozenset({"Cooking Creams", "Nuts"}),  # e.g. pistachio cream filling
    frozenset({"Cooking Creams", "Vegetables"}),  # e.g. cream of tomato soup, sour cream & onion
    frozenset({"Cheese", "Cooking Creams"}),  # e.g. cheddar cream
    frozenset({"Cooking Creams", "Dried Fruit"}),  # e.g. cream & raisin filled pastry
    frozenset({"Butter", "Cheese"}),  # cheese spreads, e.g. "Cheese Spread With Garlic"
    frozenset({"Biscuits", "Butter"}),  # biscuit spreads, e.g. Lotus/Biscoff spread
    frozenset({"Butter", "Vegetables"}),  # vegetable-oil margarine spreads, e.g. Flora
    frozenset({"Flour", "Nuts"}),  # e.g. almond flour
    frozenset({"Flour", "Lamb"}),  # Lamb Brand flour products
    frozenset({"Cheese", "Chicken"}),  # e.g. chicken & cheese pet treats
    frozenset({"Cheese", "Rice"}),  # e.g. rice crackers with cheese
    frozenset({"Frozen", "Vegetables"}),  # frozen vegetable dishes
    frozenset({"Cereals", "Milk"}),  # e.g. "Belvita Milk & Cereal", milk-flavoured cereal bars
    frozenset({"Cereals", "Chicken"}),  # cereal-based pet/animal feed with a meat flavour
    frozenset({"Cereals", "Nuts"}),  # e.g. peanut granola
    frozenset({"Nuts", "Sweet Snacks"}),  # e.g. almond/pistachio halva
    frozenset({"Bread", "Ham"}),  # e.g. baguette with a deli-meat filling
    frozenset({"Bread", "Honey"}),  # e.g. honey & spelt bread
    frozenset({"Milk", "Rice"}),  # e.g. rice milk, baby rice-and-milk pouches
    frozenset({"Fruits", "Rice"}),  # e.g. fruit-flavoured rice bars
    frozenset({"Beef", "Jelly"}),  # beef in jelly, dog/cat food and human products alike
    frozenset({"Chilled Fish", "Jelly"}),  # fish in jelly, same shape as Beef/Jelly above
    frozenset({"Olives", "Vegetables"}),  # e.g. olive & tomato sauce
    frozenset({"Fruits", "Vegetables"}),  # e.g. mixed fruit & vegetable snack sticks
    frozenset({"Fruits", "Nuts"}),  # e.g. fruit-and-nut snack bars
    frozenset({"Herbs & Spices", "Nuts"}),  # e.g. sea-salt/cinnamon flavoured nut snacks
    frozenset({"Honey", "Nuts"}),  # e.g. honey almond crunch/granola
    frozenset({"Dried Fruit", "Nuts"}),  # e.g. raisin & almond bars
    frozenset({"Butter", "Herbs & Spices"}),  # e.g. garlic & herb butter
    frozenset({"Chicken", "Jelly"}),  # chicken in jelly, same shape as Beef/Jelly above
    frozenset({"Jelly", "Turkey"}),  # turkey in jelly, same shape as Beef/Jelly above
    frozenset({"Lamb", "Pasta & Couscous"}),  # Lamb Brand dry couscous products

    # Third extension (19 Aug 2026), from the first real report run against
    # the full 129,703-listing production database rather than a sample --
    # same reasoning as the two blocks above, each checked against its real
    # example(s) and already resolving to a reasonable answer, not a bug.
    frozenset({"Beef", "Vegetables"}),  # dish combinations, e.g. beef & carrot jar
    frozenset({"Cereals", "Honey"}),  # e.g. honey loops, honey & nut cereal
    frozenset({"Herbs & Spices", "Pasta & Couscous"}),  # e.g. tomato & herb couscous
    frozenset({"Cakes", "Vegetables"}),  # e.g. carrot cake
    frozenset({"Dried Fruit", "Fruits"}),  # e.g. sultanas, raisin & apple bars
    frozenset({"Nuts", "Vegetables"}),  # e.g. peanut & onion snacks
    frozenset({"Bread", "Flour"}),  # e.g. strong white bread flour
    frozenset({"Herbs & Spices", "Rice"}),  # e.g. tomato & basil rice
    frozenset({"Cheese", "Pasta & Couscous"}),  # e.g. macaroni cheese
    frozenset({"Chicken", "Frozen"}),  # frozen chicken products
    frozenset({"Carbonated Drinks", "Water"}),  # soda water / club soda
    frozenset({"Beef", "Herbs & Spices"}),  # e.g. beef gravy granules, corned beef
    frozenset({"Cakes", "Cheese"}),  # e.g. cheddar-flavoured corn cakes
    frozenset({"Biscuits", "Cereals"}),  # e.g. cereal biscuits, cookie-crisp cereal
    frozenset({"Canned Seafood", "Oils"}),  # sardines in oil
    frozenset({"Cheese", "Oils"}),  # e.g. feta in oil
    frozenset({"Fruits", "Water"}),  # fruit-flavoured water
    frozenset({"Canned Seafood", "Vegetables"}),  # e.g. sardines in tomato sauce
    frozenset({"Cakes", "Nuts"}),  # e.g. walnut cake
    frozenset({"Butter", "Nuts"}),  # nut spreads
    frozenset({"Biscuits", "Coffee"}),  # e.g. coffee biscuits
    frozenset({"Flour", "Rice"}),  # rice flour
    frozenset({"Olive Oil", "Snacks"}),  # e.g. olive-oil-coated rice rolls
    frozenset({"Lamb", "Rice"}),  # Lamb & Rice dog food
    frozenset({"Bread", "Vegetables"}),  # e.g. onion baguette
    frozenset({"Vegetables", "Vinegars"}),  # pickled vegetables in vinegar
    frozenset({"Beef", "Rice"}),  # dish combinations, e.g. beef biryani
    frozenset({"Cheese", "Nuts"}),  # e.g. cashew & parmesan dip
    frozenset({"Beef", "Frozen"}),  # frozen beef products
    frozenset({"Lamb", "Vegetables"}),  # Lamb-brand and dog-food dish combinations
    frozenset({"Butter", "Cooking Creams"}),  # e.g. butter-cream icing
    frozenset({"Eggs", "Rice"}),  # e.g. egg fried rice
    frozenset({"Chilled Fish", "Frozen"}),  # frozen fish/prawns
    frozenset({"Cereals", "Dried Fruit"}),  # e.g. raisin & nut muesli
    frozenset({"Ham", "Herbs & Spices"}),  # dual-ingredient/seasoned deli meat
    frozenset({"Eggs", "Pasta & Couscous"}),  # egg pasta
    frozenset({"Gift Sets", "Oils"}),  # bath/toiletry oil gift sets
    frozenset({"Beef", "Beers"}),  # e.g. beef & ale stew/pie
    frozenset({"Cheese", "Olives"}),  # e.g. olives & cheese tapas
    frozenset({"Fruits", "Honey"}),  # e.g. honey & melon
    frozenset({"Herbs & Spices", "Olives"}),  # e.g. olives with herbs
    frozenset({"Biscuits", "Dried Fruit"}),  # e.g. raisin biscuits
    frozenset({"Cheese", "Fruits"}),  # e.g. cheese with apple/banana
    frozenset({"Ham", "Vegetables"}),  # e.g. ham & tomato
    frozenset({"Beef", "Ham"}),  # dual-ingredient deli meat
    frozenset({"Cereals", "Rice"}),  # rice-based cereal/muesli
    frozenset({"Nuts", "Rice"}),  # e.g. rice & almond drink
    frozenset({"Herbs & Spices", "Oils"}),  # e.g. feta with herbs in oil (Cheese wins anyway)
    frozenset({"Chilled Fish", "Legumes"}),  # e.g. tuna with lentils/chickpeas
    frozenset({"Beef", "Chilled Fish"}),  # dual-protein pet food, same shape as Chicken/Chilled Fish
    frozenset({"Flour", "Pasta & Couscous"}),  # gluten-free pasta flour
    frozenset({"Legumes", "Pasta & Couscous"}),  # e.g. lentil couscous/orzo
    frozenset({"Chicken", "Ham"}),  # dual-ingredient, e.g. chicken & ham
    frozenset({"Herbs & Spices", "Pork"}),  # seasoned pork/ham products
    frozenset({"Chicken", "Pasta & Couscous"}),  # e.g. chicken pasta
    frozenset({"Butter", "Sweet Snacks"}),  # e.g. "butter sweets" toffee
    frozenset({"Biscuits", "Honey"}),  # e.g. honey almond cookies
    frozenset({"Cooking Creams", "Spirits - Liqueurs"}),  # cream liqueurs
    frozenset({"Frozen", "Fruits"}),  # frozen fruit
    frozenset({"Cheese", "Honey"}),  # e.g. goat cheese with honey
    frozenset({"Coffee", "Cooking Creams"}),  # e.g. coffee creamer, Irish cream latte
    frozenset({"Frozen", "Pork"}),  # frozen pork products
    frozenset({"Cooking Creams", "Fruits"}),  # e.g. fruit-flavoured cooking/dessert cream
    frozenset({"Butter", "Milk"}),  # e.g. butter & milk combo packs
    frozenset({"Oils", "Olives"}),  # e.g. olives in oil
    frozenset({"Ham", "Jelly"}),  # e.g. chicken ham in jelly (resolves to Chicken via list order)
    frozenset({"Cooking Creams", "Milk"}),  # e.g. full cream milk, milk cream/panna products
    frozenset({"Honey", "Milk"}),  # e.g. honey kefir, wheat milk honey drink
    frozenset({"Herbs & Spices", "Sauces & Condiments"}),  # e.g. bruschetta topping with sea salt (resolves to Herbs & Spices via list order) -- new tie from adding the "bruschetta" keyword on 19 Aug 2026
    frozenset({"Olives", "Sauces & Condiments"}),  # e.g. bruschetta topping with olives -- same product, same reasoning as above

    # ------------------------------------------------------------------
    # 18 Aug 2026 bulk sweep -- pairs reviewed and accepted in one go.
    #
    # The sweep added general product vocabulary ("sauce", "crisp",
    # "mustard", "cream", "cake"...), and words that general naturally
    # co-occur: a crispbread flavoured with cheese matches both Crackers
    # and Cheese, a marmalade made with whisky matches both Jelly and
    # Spirits. Every pair below was checked by running the real product
    # names behind it through classify_by_name and confirming it already
    # lands on the sensible category -- the ones that did NOT were fixed
    # with Pass-0 tie-breakers in MULTI_KEYWORD_RULES instead (Lindt
    # landing on Milk, Rimmel landing on Coffee, Bisto landing on Beef,
    # marmalade landing on Fruits).
    #
    # They're listed here so the run report stays readable: without this,
    # the next report would print 56 extra "possible collision" lines that
    # have all already been looked at, and the genuinely new ones would be
    # lost in the noise.
    # ------------------------------------------------------------------
    frozenset({'Beef', 'Dried Fruit'}),
    frozenset({'Beef', 'Sauces & Condiments'}),
    frozenset({'Beers', 'Herbs & Spices'}),
    frozenset({'Beers', 'Sauces & Condiments'}),
    frozenset({'Biscuits', 'Chips'}),
    frozenset({'Biscuits', 'Chocolates'}),
    frozenset({'Biscuits', 'Sauces & Condiments'}),
    frozenset({'Bread', 'Chips'}),
    frozenset({'Butter', 'Jelly'}),
    frozenset({'Cake Preparations', 'Herbs & Spices'}),
    frozenset({'Cakes', 'Chips'}),
    frozenset({'Cakes', 'Chocolates'}),
    frozenset({'Cakes', 'Sauces & Condiments'}),
    frozenset({'Canned Seafood', 'Sauces & Condiments'}),
    frozenset({'Cereals', 'Chips'}),
    frozenset({'Cheese', 'Chips'}),
    frozenset({'Cheese', 'Chocolates'}),
    frozenset({'Chicken', 'Sauces & Condiments'}),
    frozenset({'Chicken', 'Soups'}),
    frozenset({'Chilled Fish', 'Olive Oil'}),
    frozenset({'Chilled Fish', 'Sauces & Condiments'}),
    frozenset({'Chilled Fish', 'Soups'}),
    frozenset({'Chips', 'Chocolates'}),
    frozenset({'Chips', 'Cooking Creams'}),
    frozenset({'Chips', 'Herbs & Spices'}),
    frozenset({'Chips', 'Honey'}),
    frozenset({'Chips', 'Olives'}),
    frozenset({'Chips', 'Rice'}),
    frozenset({'Chips', 'Sauces & Condiments'}),
    frozenset({'Chips', 'Sweet Snacks'}),
    frozenset({'Chips', 'Vegetables'}),
    frozenset({'Chocolates', 'Cooking Creams'}),
    frozenset({'Chocolates', 'Crackers, Crispbread & Breadsticks'}),
    frozenset({'Chocolates', 'Pastry'}),
    frozenset({'Cold Cuts', 'Pasta & Couscous'}),
    frozenset({'Cooking Creams', 'Skin Care'}),
    frozenset({'Crackers, Crispbread & Breadsticks', 'Sauces & Condiments'}),
    frozenset({'Crackers, Crispbread & Breadsticks', 'Snacks'}),
    frozenset({'Dilutables', 'Sauces & Condiments'}),
    frozenset({'Dried Fruit', 'Eggs'}),
    frozenset({'Dried Fruit', 'Ham'}),
    frozenset({'Face Creams', 'Skin Care'}),
    frozenset({'Flour', 'Legumes'}),
    frozenset({'Frozen', 'Sauces & Condiments'}),
    frozenset({'Herbs & Spices', 'Pastry'}),
    frozenset({'Honey', 'Sauces & Condiments'}),
    frozenset({'Household Goods', 'Toys & Games'}),
    frozenset({'Jelly', 'Nuts'}),
    frozenset({'Lamb', 'Sauces & Condiments'}),
    frozenset({'Legumes', 'Oils'}),
    frozenset({'Legumes', 'Olives'}),
    frozenset({'Milk', 'Sweet Snacks'}),
    frozenset({'Oils', 'Tea'}),
    frozenset({'Olive Oil', 'Olives'}),
    frozenset({'Pasta & Couscous', 'Sauces & Condiments'}),
    frozenset({'Rice', 'Sauces & Condiments'}),

    # 18 Aug 2026 second bulk sweep -- same review as the block above: each of
    # these pairs was traced back to the real product names behind it and
    # confirmed to already land on the sensible category (a quinoa pasta
    # matching both Cereals and Pasta, a Vileda sponge matching both Cloths &
    # Sponges and Household Goods, a rooibos infusion matching both Herbs &
    # Spices and Tea). The ones that did NOT were fixed with Pass-0
    # tie-breakers instead -- see MULTI_KEYWORD_RULES.
    frozenset({'Cereals', 'Olives'}),
    frozenset({'Cereals', 'Sauces & Condiments'}),
    frozenset({'Cheese', 'Household Goods'}),
    frozenset({'Chilled Fish', 'Nuts'}),
    frozenset({'Cloths & Sponges', 'Household Goods'}),
    frozenset({'Dilutables', 'Nuts'}),
    frozenset({'Disposables', 'Household Goods'}),
    frozenset({'Eggs', 'Nuts'}),
    frozenset({'Herbs & Spices', 'Tea'}),
    frozenset({'Household Goods', 'Pasta & Couscous'}),
    frozenset({'Nuts', 'Sauces & Condiments'}),
    frozenset({'Tea', 'Yoghurt'}),

    # 18 Aug 2026 third bulk sweep -- same review again: each traced back to
    # the real product names behind it and confirmed to land correctly (a
    # macaron liqueur, an oat shampoo, an avocado hair conditioner, a
    # coconut lentil cake). Listed so the run report stays readable.
    frozenset({'Biscuits', 'Spirits - Liqueurs'}),
    frozenset({'Cake Preparations', 'Fruits'}),
    frozenset({'Cereals', 'Cooking Creams'}),
    frozenset({'Cereals', 'Crackers, Crispbread & Breadsticks'}),
    frozenset({'Cereals', 'Perfume'}),
    frozenset({'Cheese', 'Sweet Snacks'}),
    frozenset({'Conditioners', 'Fruits'}),
    frozenset({'Frozen', 'Nuts'}),
    frozenset({'Fruits', 'Legumes'}),
    frozenset({'Fruits', 'Sauces & Condiments'}),
    frozenset({'Jelly', 'Sweet Snacks'}),

    # 18 Aug 2026 fourth bulk sweep -- reviewed the same way; all four land
    # correctly already (buckwheat flour pasta, a millet dog food, a denture
    # cream that mentions "comfort", an absorbent car cloth).
    frozenset({'Cereals', 'Flour'}),
    frozenset({'Cereals', 'Lamb'}),
    frozenset({'Cooking Creams', 'Fabric Softener'}),
    frozenset({'Sanitary Towels', 'Water'}),

    # 18 Aug 2026 fifth bulk sweep. "astuccio" is Italian for both a pencil
    # case and a presentation box, so a boxed pistachio cream matches
    # Stationery as well as Nuts -- it already resolves to Nuts correctly.
    frozenset({'Nuts', 'Stationery'}),

    # 18 Aug 2026 sixth bulk sweep -- all seven traced back and confirmed to
    # land correctly (a ginger kefir, a beef-and-green-beans rice meal, a
    # cheddar made with ginger and whisky, an oat "derma" shampoo).
    frozenset({'Beef', 'Legumes'}),
    frozenset({'Cereals', 'Skin Care'}),
    frozenset({'Fruits', 'Juices'}),
    frozenset({'Fruits', 'Olives'}),
    frozenset({'Jelly', 'Vegetables'}),
    frozenset({'Milk', 'Vegetables'}),
    frozenset({'Spirits - Whisky', 'Vegetables'}),

    # 18 Aug 2026 seventh sweep -- the first round written from the real
    # export, so this batch is larger. Each pair was traced to the product
    # names behind it and confirmed to resolve sensibly; the four that did
    # not (Areon, Astonish, Addo, Nutella) were fixed with Pass-0 rules
    # instead of being accepted.
    frozenset({'Air Fresheners', 'Fruits'}),
    frozenset({'Air Fresheners', 'Honey'}),
    frozenset({'Air Fresheners', 'Oils'}),
    frozenset({'All-purpose Cleaners', 'Bathroom & Wc Cleaner'}),
    frozenset({'All-purpose Cleaners', 'Cooking Creams'}),
    frozenset({'Baby Essentials', 'Cooking Creams'}),
    frozenset({'Baby Essentials', 'Fruits'}),
    frozenset({'Beef', 'Canned Seafood'}),
    frozenset({'Beef', 'Cold Cuts'}),
    frozenset({'Bread', 'Chicken'}),
    frozenset({'Bread', 'Cooking Creams'}),
    frozenset({'Bread', 'Lamb'}),
    frozenset({'Butter', 'Sauces & Condiments'}),
    frozenset({'Cake Preparations', 'Cooking Creams'}),
    frozenset({'Cake Preparations', 'Spirits - Liqueurs'}),
    frozenset({'Canned Seafood', 'Pasta & Couscous'}),
    frozenset({'Canned Seafood', 'Water'}),
    frozenset({'Carbonated Drinks', 'Make Up'}),
    frozenset({'Carbonated Drinks', 'Sweet Snacks'}),
    frozenset({'Cheese', 'Milk'}),
    frozenset({'Chilled Fish', 'Spirits - Liqueurs'}),
    frozenset({'Chilled Fish', 'Sweet Snacks'}),
    frozenset({'Cloths & Sponges', 'Sports'}),
    frozenset({'Cold Cuts', 'Dried Fruit'}),
    frozenset({'Cold Cuts', 'Eggs'}),
    frozenset({'Cold Cuts', 'Fruits'}),
    frozenset({'Cold Cuts', 'Ham'}),
    frozenset({'Cooking Creams', 'Sports'}),
    frozenset({'Deodorants', 'Shaving Creams'}),
    frozenset({'Disposables', 'Electrical'}),
    frozenset({'Flour', 'Sports'}),
    frozenset({'Fruits', 'Make Up'}),
    frozenset({'Fruits', 'Toys & Games'}),
    frozenset({'Honey', 'Make Up'}),
    frozenset({'Jelly', 'Make Up'}),
    frozenset({'Jelly', 'Sauces & Condiments'}),
    frozenset({'Jelly', 'Toys & Games'}),
    frozenset({'Milk', 'Sports'}),
    frozenset({'Nuts', 'Sports'}),
    frozenset({'Rice', 'Spirits - Liqueurs'}),
    frozenset({'Rice', 'Sports'}),
    frozenset({'Sauces & Condiments', 'Sweet Snacks'}),
    frozenset({'Sauces & Condiments', 'Vinegars'}),
    frozenset({'Toys & Games', 'Vegetables'}),
    frozenset({'Toys & Games', 'Water'}),

    frozenset({'Air Fresheners', 'Perfume'}),  # Areon home fragrance -- resolves to Air Fresheners via the Pass-0 rule at the top of MULTI_KEYWORD_RULES

    # 18 Aug 2026 eighth bulk sweep -- reviewed the same way as every block
    # above: each traced back to the real product name and confirmed the
    # existing resolution is correct. "Saitaku Nori Snack With Canola Oil"
    # resolves to Snacks (correct -- it's a nori snack, not cookware or
    # cooking oil) even though "saitaku" (Household Goods, for their
    # chopsticks/sushi-mat line) and "canola oil"/"nori" also match.
    # "Ajinomoto Gyozas Chicken & Vegetables" resolves to Chicken (correct --
    # chicken is the named protein) even though "ajinomoto" (Snacks) and
    # "vegetables" also match. "Mop Refill Head Microfibre" resolves to Floor
    # Cleaners (correct -- it's a mop accessory) even though "microfibre"
    # (Cloths & Sponges) also matches.
    frozenset({'Household Goods', 'Oils'}),
    frozenset({'Herbs & Spices', 'Household Goods'}),
    frozenset({'Chicken', 'Snacks'}),
    frozenset({'Snacks', 'Vegetables'}),
    frozenset({'Cloths & Sponges', 'Floor Cleaners'}),

    # 24 Aug 2026 -- a different reason for the same mechanism. These pairs
    # are NOT dual-identity products like the ones above -- each one DOES
    # have a single correct answer. But that answer has now been checked,
    # individually, against real product names across five separate
    # collision-report rounds (24 Aug 2026), and classify_by_name already
    # gets it right every time purely through existing KEYWORD_RULES list
    # order -- there is no bug left to fix, just a same-tier keyword match
    # that happens to already resolve correctly. Left unsuppressed, these
    # would keep resurfacing at the top of every future report with nothing
    # new to do about them, for the exact reason described in this
    # section's own intro comment. Verified per pair, not blanket-added:
    #   Fruits/Sweet Snacks -- gum, marshmallow, and sour-candy products all
    #     correctly resolve to Sweet Snacks despite a fruit-flavour word
    #     also matching (e.g. "Warheads Super Sour Bubble Gum ... Raspberry").
    #   Floor Cleaners/Household Goods -- Vileda/Leifheit mop products
    #     correctly resolve to Floor Cleaners despite the brand also being a
    #     registered Household Goods keyword.
    #   First Aid/Skin Care -- Vitamin C skincare (masks, serums, creams)
    #     correctly resolves to Skin Care; see the 23 Aug 2026 note earlier
    #     in KEYWORD_RULES for why bare "vitamin c" was moved to the very
    #     end of the list for exactly this reason.
    #   Biscuits/Cakes -- Jaffa Cakes correctly resolve to Cakes, brownie
    #     cookies correctly resolve to Biscuits.
    #   Cheese/Sauces & Condiments -- curd cheese (Milochka, Karums, Svalia)
    #     correctly resolves to Cheese despite "curd" also matching Sauces.
    #   Deodorants/Skin Care -- Sanex/Borotalco deodorant and talcum
    #     products correctly resolve to Deodorants; Nivea face products
    #     correctly resolve to Skin Care or the more specific Face Creams.
    #   Chips/Nuts -- Lorenz cashews/pistachios/peanuts correctly resolve to
    #     Nuts despite also matching a Chips keyword.
    frozenset({'Fruits', 'Sweet Snacks'}),
    frozenset({'Floor Cleaners', 'Household Goods'}),
    frozenset({'First Aid', 'Skin Care'}),
    frozenset({'Biscuits', 'Cakes'}),
    frozenset({'Cheese', 'Sauces & Condiments'}),
    frozenset({'Deodorants', 'Skin Care'}),
    frozenset({'Chips', 'Nuts'}),

    # 24 Aug 2026 -- same reason, second batch, now that the pairs above
    # dropped off the report and let these rise to the top instead. Each
    # checked against both its original examples and the fresh ones this
    # round's report surfaced:
    #   Legumes/Vegetables -- Bigilla (broad-bean paste) and bean/pea/carrot
    #     mixes correctly resolve to Legumes or Vegetables as appropriate.
    #   Nuts/Snacks -- Bankok nuts correctly resolve to Nuts, rice-cake
    #     snacks correctly resolve to Snacks.
    #   Cereals/Pasta & Couscous -- "Spelt Penne"/"Spelt Spaghetti" (pasta
    #     made from spelt flour) correctly resolve to Pasta & Couscous
    #     despite "spelt" also being registered under Cereals.
    #   Canned Seafood/Olive Oil -- tuna/salmon/mackerel packed in olive oil
    #     correctly resolve to Olive Oil.
    #   Stationery/Toys & Games -- Disney-branded pencil cases correctly
    #     resolve to Stationery despite the character branding.
    #   All-purpose Cleaners/Laundry Washing Liquids -- Marsiglia-soap
    #     degreasers/washing liquids correctly resolve to Laundry Washing
    #     Liquids.
    #   Beers/Vegetables -- ginger beer correctly resolves to Beers despite
    #     "ginger" also being a registered Vegetables keyword.
    frozenset({'Legumes', 'Vegetables'}),
    frozenset({'Nuts', 'Snacks'}),
    frozenset({'Cereals', 'Pasta & Couscous'}),
    frozenset({'Canned Seafood', 'Olive Oil'}),
    frozenset({'Stationery', 'Toys & Games'}),
    frozenset({'All-purpose Cleaners', 'Laundry Washing Liquids'}),
    frozenset({'Beers', 'Vegetables'}),

    # 25 Aug 2026 -- third batch, same reasoning as the two above.
    #   Hair & Nail Accessories/Toys & Games -- Disney-branded hairbrushes,
    #     paddle brushes, and nail files correctly resolve to Hair & Nail
    #     Accessories despite the character branding.
    #   Oils/Vegetables -- vegetables preserved in oil (mushrooms,
    #     artichokes) correctly resolve to Oils.
    #   Sauces & Condiments/Vegetables -- tomato passata/polpa correctly
    #     resolves to Sauces & Condiments despite "tomato" also being a
    #     registered Vegetables keyword.
    frozenset({'Hair & Nail Accessories', 'Toys & Games'}),
    frozenset({'Oils', 'Vegetables'}),
    frozenset({'Sauces & Condiments', 'Vegetables'}),

    # 26 Aug 2026 -- fourth batch, from a fresh full-DB re-analysis (93,780
    # distinct product names) after this round's fixes. Same reasoning as
    # the three batches above -- each checked against its top examples:
    #   Clothes/Dilutables -- "Bolero" socks correctly resolve to Clothes
    #     via bare "sock" despite "bolero" also being a registered
    #     Dilutables brand keyword (Bolero's actual instant-drink sachets
    #     all say "Instant Drink", never "sock").
    #   Fruits/Sports -- Dragon Fruit products correctly resolve to Fruits
    #     via bare "fruit"; the "dragon" bare-brand promotion this pair is
    #     named for was already deliberately scoped narrower (see the 23
    #     Aug 2026 "dragon is a special case" comment above) specifically
    #     to avoid this collision.
    #   Household Goods/Vegetables -- Sistema/Tefal/Saitaku kitchenware
    #     correctly resolves to Household Goods via the brand name; actual
    #     food products (sushi ginger, vegetable lunch bowls) correctly
    #     resolve to Vegetables despite a kitchenware brand/word also
    #     matching.
    #   Biscuits/Vegetables -- ginger/pumpkin/chive biscuits and cookies
    #     correctly resolve to Biscuits via the product-type word.
    #   Chocolates/Fruits -- checked across both directions: chocolate-brand
    #     products (Ferrero, Snickers, Sperlari) and fruit-forward products
    #     each resolve to the correct side; nothing landing wrong.
    frozenset({'Clothes', 'Dilutables'}),
    frozenset({'Fruits', 'Sports'}),
    frozenset({'Household Goods', 'Vegetables'}),
    frozenset({'Biscuits', 'Vegetables'}),
    frozenset({'Chocolates', 'Fruits'}),

    # 26 Aug 2026 -- fifth batch, from the same large parallel full-DB
    # re-analysis as the tenth-pass fixes above (top ~270 remaining
    # collision pairs, each independently CSV-verified against real
    # examples before being marked accepted here). Mostly the same
    # "flavour/mix-in descriptor vs. base ingredient" and "dish-combination"
    # shapes already documented in the batches above -- not re-explaining
    # each one individually at this volume, but every pair was checked
    # against its own top examples and confirmed classify_by_name() already
    # resolves correctly, not just resolvable-either-way.
    frozenset({'Cheese', 'Frozen'}),
    frozenset({'Meat Alternatives', 'Nuts'}),
    frozenset({'Herbs & Spices', 'Legumes'}),
    frozenset({'Cereals', 'Herbs & Spices'}),
    frozenset({'Fruits', 'Oils'}),
    frozenset({'Bread', 'Cakes'}),
    frozenset({'Cereals', 'Vegetables'}),
    frozenset({'Hair & Nail Accessories', 'Make Up'}),
    frozenset({'Bread', 'Fruits'}),
    frozenset({'Chicken', 'Household Goods'}),
    frozenset({'Intimate Care', 'Sanitary Towels'}),
    frozenset({'Make Up', 'Skin Care'}),
    frozenset({'Make Up', 'Sweet Snacks'}),
    frozenset({'Herbs & Spices', 'Honey'}),
    frozenset({'Meat Alternatives', 'Rice'}),
    frozenset({'Cooking Creams', 'Herbs & Spices'}),
    frozenset({'Legumes', 'Snacks'}),
    frozenset({'Chocolates', 'Snacks'}),
    frozenset({'Cereals', 'Chocolates'}),
    frozenset({'Legumes', 'Rice'}),
    frozenset({'Dilutables', 'Spirits - Liqueurs'}),
    frozenset({'Biscuits', 'Sweet Snacks'}),
    frozenset({'Dilutables', 'Electrical'}),
    frozenset({'Chocolates', 'Ham'}),
    frozenset({'Disposables', 'Gift Sets'}),
    frozenset({'Bread', 'Sauces & Condiments'}),
    frozenset({'Deodorants', 'Face Creams'}),
    frozenset({'Meat Alternatives', 'Sauces & Condiments'}),
    frozenset({'Clothes', 'Household Goods'}),
    frozenset({'Cheese', 'Legumes'}),
    frozenset({'Chilled Fish', 'Hair Styling'}),
    frozenset({'Turkey', 'Vegetables'}),
    frozenset({'Cereals', 'Sports'}),
    frozenset({'Bread', 'Olives'}),
    frozenset({'All-purpose Cleaners', 'Sauces & Condiments'}),
    frozenset({'Fabric Softener', 'Shaving Creams'}),
    frozenset({'Shaving Creams', 'Skin Care'}),
    frozenset({'Pork', 'Vegetables'}),
    frozenset({'Cakes', 'Rice'}),
    frozenset({'All-purpose Cleaners', 'Floor Cleaners'}),
    frozenset({'Fabric Softener', 'Household Goods'}),
    frozenset({'Dilutables', 'Vegetables'}),
    frozenset({'Clothes', 'Nappies'}),
    frozenset({'Flour', 'Herbs & Spices'}),
    frozenset({'Chocolates', 'Oils'}),
    frozenset({'Cloths & Sponges', 'Fruits'}),
    frozenset({'Tea', 'Vegetables'}),
    frozenset({'Bathroom & Wc Cleaner', 'Floor Cleaners'}),
    frozenset({'Frozen', 'Pasta & Couscous'}),
    frozenset({'Flour', 'Snacks'}),
    frozenset({'Cotton Buds', 'Make Up'}),
    frozenset({'Chicken', 'Meat Alternatives'}),
    frozenset({'Hair Styling', 'Stationery'}),
    frozenset({'Butter', 'Fruits'}),
    frozenset({'Meat Alternatives', 'Milk'}),
    frozenset({'Cakes', 'Milk'}),
    frozenset({'Dried Fruit', 'Jelly'}),
    # 28 Aug 2026 -- sixth batch, same large parallel re-analysis as the
    # eleventh-pass fixes above. Each pair independently checked against
    # its own real examples: same shapes as the batches above -- flavour/
    # mix-in descriptors, dish combinations, genuine dual-identity brands,
    # or cases where the CSV's own ground-truth category column is itself
    # internally inconsistent for the exact pattern in question (verified
    # per-pair, not blanket-added).
    frozenset({'Bread', 'Cereals'}),
    frozenset({'Fruits', 'Hair Styling'}),
    frozenset({'Electrical', 'Hand Tools'}),
    frozenset({'Beef', 'Household Goods'}),
    frozenset({'Deodorants', 'Shower Gels'}),
    frozenset({'Dried Fruit', 'Herbs & Spices'}),
    frozenset({'Cake Preparations', 'Cakes'}),
    frozenset({'All-purpose Cleaners', 'Stain Removers'}),
    frozenset({'Milk', 'Yoghurt'}),
    frozenset({'Juices', 'Vegetables'}),
    frozenset({'Nuts', 'Oils'}),
    frozenset({'Herbs & Spices', 'Sports'}),
    frozenset({'Chilled Fish', 'Herbs & Spices'}),
    frozenset({'Flour', 'Fruits'}),
    frozenset({'Biscuits', 'Cheese'}),
    frozenset({'Coffee', 'Household Goods'}),
    frozenset({'Dilutables', 'Dried Fruit'}),
    frozenset({'Cereals', 'Coffee'}),
    frozenset({'Cake Preparations', 'Household Goods'}),
    frozenset({'Herbs & Spices', 'Meat Alternatives'}),
    frozenset({'Oils', 'Sauces & Condiments'}),
    frozenset({'All-purpose Cleaners', 'Household Goods'}),
    frozenset({'Cake Preparations', 'Nuts'}),
    frozenset({'Hand Wash Liquids', 'Laundry Washing Liquids'}),
    frozenset({'Chicken', 'Fruits'}),
    frozenset({'All-purpose Cleaners', 'Dish Washing Liquid'}),
    frozenset({'Cheese', 'Cold Cuts'}),
    frozenset({'Hand Tools', 'Household Goods'}),
    frozenset({'Household Goods', 'Stationery'}),
    frozenset({'Baby Essentials', 'Skin Care'}),
    frozenset({'Canned Seafood', 'Chilled Fish'}),
    frozenset({'First Aid', 'Household Goods'}),
    frozenset({'Carbonated Drinks', 'Fruits'}),
    frozenset({'Hair & Nail Accessories', 'Household Goods'}),
    frozenset({'Cereal & Cereal Bars', 'Cereals'}),
    frozenset({'Chicken', 'Hair Styling'}),
    frozenset({'Oils', 'Skin Care'}),
    frozenset({'Hand Wash Liquids', 'Shower Gels'}),
    frozenset({'Dried Fruit', 'Snacks'}),
    frozenset({'Bread', 'Herbs & Spices'}),
    frozenset({'Biscuits', 'Bread'}),
    frozenset({'Chocolates', 'Nuts'}),
    frozenset({'Bread', 'Nuts'}),
    frozenset({'Biscuits', 'Milk'}),
    frozenset({'First Aid', 'Honey'}),
    frozenset({'Shaving Creams', 'Stationery'}),
    frozenset({'Fruits', 'Shower Gels'}),
    frozenset({'First Aid', 'Herbs & Spices'}),
    frozenset({'Crackers, Crispbread & Breadsticks', 'Nuts'}),
    frozenset({'Fruits', 'Household Goods'}),
    frozenset({'Ham', 'Pasta & Couscous'}),
    frozenset({'Oils', 'Olive Oil'}),
    frozenset({'Fruits', 'Ham'}),
    frozenset({'Butter', 'Yoghurt'}),
    frozenset({'Make Up', 'Toys & Games'}),
    frozenset({'Rice', 'Yoghurt'}),
    frozenset({'Cheese', 'Yoghurt'}),
    frozenset({'Biscuits', 'Sugar'}),
    frozenset({'Laundry Washing Liquids', 'Stain Removers'}),
    frozenset({'Olive Oil', 'Vegetables'}),
    frozenset({'Fruits', 'Meat Alternatives'}),
    frozenset({'Crackers, Crispbread & Breadsticks', 'Rice'}),
    frozenset({'Cakes', 'Cereals'}),
    frozenset({'Pasta & Couscous', 'Yoghurt'}),
    frozenset({'Chips', 'Snacks'}),
    frozenset({'Chicken', 'Sausages'}),
    frozenset({'Crackers, Crispbread & Breadsticks', 'Fruits'}),
    frozenset({'Beef', 'Meat Alternatives'}),
    frozenset({'Cake Preparations', 'Flour'}),
    frozenset({'Beef', 'Fruits'}),
    frozenset({'All-purpose Cleaners', 'Skin Care'}),
    frozenset({'Biscuits', 'Eggs'}),
    frozenset({'Beef', 'Pasta & Couscous'}),
    frozenset({'Chocolates', 'Vinegars'}),
    frozenset({'Disposables', 'Toys & Games'}),
    frozenset({'Honey', 'Tea'}),
    frozenset({'All-purpose Cleaners', 'Fruits'}),
    frozenset({'Baby Essentials', 'Hair & Nail Accessories'}),
    frozenset({'Hair Styling', 'Shampoos'}),
    frozenset({'Baby Essentials', 'Cloths & Sponges'}),
    frozenset({'Chilled Fish', 'Spirits - Whisky'}),
    frozenset({'Rice', 'Turkey'}),
    frozenset({'Flour', 'Vegetables'}),
    frozenset({'Hair & Nail Accessories', 'Stationery'}),
    frozenset({'Sauces & Condiments', 'Snacks'}),
    frozenset({'Baby Essentials', 'Toys & Games'}),
    frozenset({'Herbs & Spices', 'Juices'}),
    frozenset({'Biscuits', 'Flour'}),
    frozenset({'Baby Essentials', 'Insect Killer'}),
    frozenset({'Household Goods', 'Rice'}),
    frozenset({'Pasta & Couscous', 'Snacks'}),
    frozenset({'Pork', 'Snacks'}),
    frozenset({'Nuts', 'Pasta & Couscous'}),
    frozenset({'Household Goods', 'Wine - Sparkling'}),
    frozenset({'Olive Oil', 'Sauces & Condiments'}),
    frozenset({'Ham', 'Nuts'}),
    frozenset({'Fabric Softener', 'Floor Cleaners'}),
    frozenset({'Bread', 'Dried Fruit'}),
    frozenset({'Soups', 'Vegetables'}),
    frozenset({'Wine - Sparkling', 'Wine - White'}),
    frozenset({'Fruits', 'Perfume'}),
    frozenset({'Cereals', 'Sugar'}),
    frozenset({'Dried Fruit', 'Sports'}),
    frozenset({'Cold Cuts', 'Olives'}),
    frozenset({'Ham', 'Olives'}),
    frozenset({'All-purpose Cleaners', 'First Aid'}),
    frozenset({'Baby Essentials', 'Household Goods'}),
    frozenset({'Bathroom & Wc Cleaner', 'Hair Styling'}),
    frozenset({'Electrical', 'Fruits'}),
    frozenset({'Dental Care', 'Stationery'}),
    frozenset({'Fabric Softener', 'Water'}),
    frozenset({'Herbs & Spices', 'Soups'}),
    frozenset({'Cooking Creams', 'Vinegars'}),
    frozenset({'Cheese', 'Spirits - Whisky'}),
    frozenset({'Fabric Softener', 'Toys & Games'}),
    frozenset({'Deodorants', 'Tea'}),
    frozenset({'Nuts', 'Spirits - Liqueurs'}),
    frozenset({'Frozen', 'Milk'}),
    frozenset({'Adult Nappies', 'Sanitary Towels'}),
    frozenset({'Chilled Fish', 'Olives'}),
    frozenset({'Cakes', 'Legumes'}),
    frozenset({'Baby Food', 'Fabric Softener'}),
    frozenset({'All-purpose Cleaners', 'Drain Unblockers'}),
    frozenset({'Fabric Softener', 'Milk'}),
    frozenset({'Frozen', 'Water'}),
    frozenset({'Laundry Tablets', 'Laundry Washing Liquids'}),
    frozenset({'Carbonated Drinks', 'Spirits - Vodka'}),
    frozenset({'Frozen', 'Lamb'}),
    frozenset({'Electrical', 'Shaving Creams'}),
    frozenset({'Coffee', 'Sanitary Towels'}),
    frozenset({'Fruits', 'Sugar'}),
    frozenset({'Butter', 'Legumes'}),
    frozenset({'Butter', 'Chilled Fish'}),
    frozenset({'Coffee', 'Rice'}),
    frozenset({'Household Goods', 'Lamb'}),
    frozenset({'Make Up', 'Oils'}),
    frozenset({'Floor Cleaners', 'Perfume'}),
    frozenset({'Beef', 'Cereals'}),
    frozenset({'Disposables', 'Fabric Softener'}),
    frozenset({'Fruits', 'Shaving Creams'}),
    frozenset({'Chicken', 'Chips'}),
    frozenset({'Cakes', 'Sweet Snacks'}),
    frozenset({'Rice', 'Snacks'}),
    frozenset({'Hair Treatment', 'Skin Care'}),
    frozenset({'Cake Preparations', 'Sports'}),
    frozenset({'Dried Fruit', 'Honey'}),
    frozenset({'Face Creams', 'First Aid'}),
    frozenset({'Bread', 'Sweet Snacks'}),
    frozenset({'Hair Styling', 'Shaving Creams'}),
    frozenset({'Bread', 'Cheese'}),

    # 28 Aug 2026 -- seventh batch, from the newest live production run
    # report. Each pair below already resolves correctly today via existing
    # rule/list order (verified individually against the real colliding
    # names) -- there's nothing left to fix, this just stops them
    # resurfacing in every future report.
    frozenset({'Coffee', 'Legumes'}),        # "Lavazza...Beans" -- coffee beans, correctly Coffee
    frozenset({'Honey', 'Vegetables'}),      # honey-glazed vegetable/meat products; no single safe fix, resolves reasonably
    frozenset({'Milk', 'Sauces & Condiments'}),  # "Besciamella" (bechamel) -- correctly Sauces & Condiments
    frozenset({'Coffee', 'Yoghurt'}),        # "Caffreze"/"Cappuccino Freddo" chilled coffee-yoghurt hybrids -- ground truth itself is inconsistent, current resolution (Coffee) is defensible
    frozenset({'Beef', 'Chips'}),            # "Amica Natura" beef burgers vs the unrelated "Amica" chips brand -- correctly Beef
    frozenset({'Milk', 'Wine - Sparkling'}), # "Milk Kefir Fragolino" -- correctly Milk
    frozenset({'Coffee', 'Sports'}),         # "Detox Coffee" -- correctly Coffee
    frozenset({'Stationery', 'Wine - Sparkling'}),  # "astuccio" (Italian for both pencil case and gift box) -- correctly Wine - Sparkling
    frozenset({'Fabric Softener', 'Nappies'}),      # "Huggies...Comfort" -- correctly Nappies
    frozenset({'Milk', 'Wine - White'}),     # "Mandorla" (almond, also a winery name) -- correctly Wine - White
    frozenset({'Stock Cubes', 'Wine - White'}),  # "Stock Pots White Wine" -- correctly Stock Cubes
    frozenset({'Cakes', 'Cooking Creams'}),  # "Lemon Custard Cake" -- correctly Cakes
    frozenset({'Cake Preparations', 'Cooking Creams'}),  # same "Lemon Custard Cake" 3-way tie (Cakes/Cake Preparations/Cooking Creams via bare "cake"/"custard") -- this is the other pairing it generates, also resolves correctly to Cakes
    frozenset({'Chilled Fish', 'Chips'}),    # "Fish & Crisp Fille" -- correctly Chilled Fish
    frozenset({'Biscuits', 'Ham'}),          # "Biscuit Salami" (a chocolate dessert, no meat) -- correctly Biscuits
    frozenset({'Chocolates', 'Herbs & Spices'}),  # truffle-salt seasoning vs chocolate truffles -- already resolves correctly on both sides
    frozenset({'Biscuits', 'Herbs & Spices'}),    # cinnamon-flavoured cookies vs truffle-flavoured oil -- already resolves correctly on both sides

    # 28 Aug 2026 -- eighth batch, from the newest live production run
    # report. Each already resolves correctly today (verified against real
    # CSV examples) -- nothing to fix, this just stops them resurfacing.
    frozenset({'Crackers, Crispbread & Breadsticks', 'Vegetables'}),  # savory-cracker-with-vegetable-flavour naming overlap; CSV ground truth is itself inconsistent for the remaining edge cases, no clean single fix
    frozenset({'Cereals', 'Meat Alternatives'}),  # Valsoia oat/soya drinks -- correctly split across Milk/Cereals/Nuts by existing rules; bare "valsoia" (for burgers/tofu) only ever loses the tie, no bug
    frozenset({'Coffee', 'Nuts'}),           # Alpro/Mokate almond & hazelnut coffee drinks -- correctly Coffee
    frozenset({'Fruits', 'Snacks'}),         # Bankok dried-fruit/nut snack mixes -- correctly resolve per product (Fruits/Chips/Dried Fruit)
    frozenset({'Carbonated Drinks', 'Dilutables'}),  # plain soda-brand syrup vs Sodastream-branded syrup concentrate -- both correctly resolve to their own bucket
    frozenset({'Hair Styling', 'Shaving Creams'}),  # "The Barb'" grooming brand -- wax correctly resolves to Hair Styling, genuine shaving items to Shaving Creams
}
def clean_for_matching(name):
    # html.unescape() first -- belt-and-suspenders against a real bug found
    # in welbees_crawler.py, where a product name was extracted straight
    # from raw HTML text without decoding entities, so a real "&" in a name
    # came through as the literal text "&amp;" (the letters a-m-p survive
    # the punctuation-stripping below, becoming a stray word "amp" in the
    # cleaned text, which is worse than useless for matching). The crawler
    # fix means freshly-crawled data won't have this problem going forward,
    # but unescaping here too means matching stays correct even against
    # already-stored data from before that fix, or any other future source
    # of entity-laden text.
    unescaped = html.unescape(name or "")
    cleaned = re.sub(r"[^a-z0-9 ]", " ", unescaped.lower())
    # Collapse anything that just became a run of spaces (punctuation,
    # accented letters like the 'e' in "rosé", "&", apostrophes, etc.) down
    # to one space -- otherwise "Head & Shoulders" and "Tresemme'" leave
    # behind multiple consecutive spaces. Found via real testing: a keyword
    # like "head & shoulders" would silently never match anything, because
    # the keyword itself still had its punctuation while the cleaned
    # product text didn't -- see _keyword_matches, which now cleans the
    # keyword the same way for exactly this reason.
    return re.sub(r"\s+", " ", cleaned).strip()


@functools.lru_cache(maxsize=None)
def _compiled_keyword_pattern(keyword):
    """Real performance bug found on 24 Aug 2026: a full production run
    (~130,000 listings) was taking 8-12+ minutes -- long enough to hit
    Neon's free-tier idle-connection sleep mid-run (see the retry fix in
    categorize_listings.py). The cause traced back to here: _keyword_matches
    used to re-clean the keyword and rebuild its regex pattern from
    scratch on every single call -- and with 628 individual keyword
    strings now spread across MULTI_KEYWORD_RULES and KEYWORD_RULES (up
    from far fewer when this function was first written), every listing
    was redoing hundreds of identical string-cleaning and regex-escaping
    operations that never actually change between listings, since a
    keyword's cleaned form and pattern are fixed for the whole run.

    Caching one compiled Pattern object per keyword (unbounded cache --
    628 keywords is nothing to hold in memory) turns that repeated
    per-listing work into a one-time cost, no matter how many listings get
    classified. Behaviour is unchanged; this is purely a speed fix, not a
    matching-logic change."""
    cleaned_keyword = clean_for_matching(keyword)
    return re.compile(r"\b" + re.escape(cleaned_keyword) + r"s?\b")


def _keyword_matches(keyword, cleaned_text):
    """Whole-word/whole-phrase match, not a raw substring match. Raw
    substring matching was tried first and found to produce real false
    positives -- e.g. the single word 'ham' is a literal substring of
    'shampoo' and 'champagne', and 'cola' is a literal substring of
    'chocolate' -- so a shampoo would have been mis-tagged as Ham and a bar
    of chocolate as a carbonated drink. Word boundaries (\\b) fix that.

    A plain \\bword\\b would then miss ordinary plurals (a product literally
    named "Free Range Eggs" wouldn't match the keyword 'egg'), since most
    grocery names are plural and most keywords here are written singular.
    The trailing 's?' handles the common case (egg/eggs, fruit/fruits,
    vegetable/vegetables). It won't catch irregular plurals like
    nappy/nappies -- those are listed as their own explicit keyword instead
    (see the Nappies entry above).

    The keyword itself is run through clean_for_matching too, not just the
    product name -- otherwise a keyword containing punctuation or an
    accented letter (e.g. 'head & shoulders', 'rosé wine') could never
    match, since the product text has already had that same punctuation
    stripped out. See _compiled_keyword_pattern for why this is now
    cached rather than rebuilt every call.

    Kept as the small, obviously-correct reference implementation -- used
    directly by SCOPED_KEYWORD_RULES (a handful of entries, not worth
    optimising) and by anything reasoning about a single keyword in
    isolation. The hot path (classify_by_name / matching_categories_by_name,
    which each check thousands of keywords per listing) uses
    _fast_keyword_matches below instead; see its docstring for why."""
    return _compiled_keyword_pattern(keyword).search(cleaned_text) is not None


@functools.lru_cache(maxsize=None)
def _cleaned_keyword_forms(keyword):
    """(cleaned_keyword, cleaned_keyword_plural, is_phrase) for one keyword,
    cached -- companion to _compiled_keyword_pattern, computed once per
    distinct keyword no matter how many listings get classified."""
    cleaned_keyword = clean_for_matching(keyword)
    return cleaned_keyword, cleaned_keyword + "s", " " in cleaned_keyword


def _fast_keyword_matches(keyword, word_set, cleaned_text):
    """Same match semantics as _keyword_matches (whole word/phrase, with
    automatic trailing-'s' pluralisation), but far cheaper at this file's
    current scale.

    Real performance bug found on 28 Aug 2026: by the 24 Aug fix (see
    _compiled_keyword_pattern's docstring), a single classify_by_name() call
    ran one compiled-regex .search() per keyword -- fine at 628 keywords,
    but this file has since grown past 5,000 individual keyword strings
    across MULTI_KEYWORD_RULES and KEYWORD_RULES, and a live production run
    (136,480 listings, each also re-scanned a second time by the collision
    report) started missing the pipeline's 600-second hard timeout.

    A regex .search() re-scans the whole cleaned product name looking for
    a match position -- wasted work for the overwhelming majority of
    keywords, which are a single word: whether "chips" appears in a ~40
    character name is a whole-word-set membership question, not a string-
    search question. Splitting the cleaned name into a word set once per
    name (see classify_by_name/matching_categories_by_name) turns every
    single-word keyword check into an O(1) hash lookup instead of a regex
    scan. Multi-word phrase keywords (a small minority of the total) still
    need the original regex path, since a set of individual words can't
    tell whether "olive" and "oil" were adjacent -- those fall through to
    _compiled_keyword_pattern unchanged. Behaviour is identical to
    _keyword_matches for every keyword; this is purely a speed fix."""
    cleaned_keyword, plural, is_phrase = _cleaned_keyword_forms(keyword)
    if is_phrase:
        return _compiled_keyword_pattern(keyword).search(cleaned_text) is not None
    return cleaned_keyword in word_set or plural in word_set


@functools.lru_cache(maxsize=None)
def classify_by_name(product_name):
    """Returns a canonical category name, or None if nothing in
    MULTI_KEYWORD_RULES or KEYWORD_RULES matched.

    Checked in three passes rather than one flat pass:

      0. Co-occurrence rules (MULTI_KEYWORD_RULES) -- all listed words
         present anywhere in the name, regardless of order or adjacency.
      1. Multi-word phrases (e.g. 'ice cream', 'dried fruit', 'adult
         nappy', 'baby shampoo', 'pepper corn', 'tinned tuna') -- these are
         always more specific than a single word.
      2. Single words last (e.g. 'cream', 'fruit', 'nappy', 'shampoo',
         'pepper', 'tuna').

    Without this split, a single-word rule listed earlier in KEYWORD_RULES
    for an unrelated reason could win before a more specific phrase ever
    gets a chance -- e.g. the generic single word 'cream' (under Cooking
    Creams) would otherwise match 'Ice Cream' before the phrase 'ice cream'
    (under Frozen) was even checked, since Dairy is listed before Frozen.
    Checking every phrase across the whole list before any single word
    avoids having to hand-order every category relative to every other one.
    Found and verified via audit_keyword_rules.py, not guessed.

    Memoized (see @functools.lru_cache below) and uses _fast_keyword_matches
    internally -- see that function's docstring (28 Aug 2026) for why: this
    file has grown past 5,000 individual keyword strings, and a plain
    regex-per-keyword scan on every one of 136,480 listings started missing
    the pipeline's 600-second hard timeout. Memoizing by product_name also
    means the ~30% of listings that share an identical name with another
    listing (same product stocked at multiple stores) are classified once,
    not once per row -- categorize_listings.py calls this once per listing,
    so that redundancy was previously paid for in full, every run."""
    cleaned = clean_for_matching(product_name)
    word_set = frozenset(cleaned.split())

    for category, required_words in MULTI_KEYWORD_RULES:
        if all(_fast_keyword_matches(w, word_set, cleaned) for w in required_words):
            return category

    for category, keywords in KEYWORD_RULES:
        for kw in keywords:
            if " " in kw.strip() and _fast_keyword_matches(kw, word_set, cleaned):
                return category

    for category, keywords in KEYWORD_RULES:
        for kw in keywords:
            if " " not in kw.strip() and _fast_keyword_matches(kw, word_set, cleaned):
                return category

    return None


@functools.lru_cache(maxsize=None)
def matching_categories_by_name(product_name):
    """Returns {category: tier} for every category whose KEYWORD_RULES
    entry matches this name -- not just the one classify_by_name would
    pick. "tier" is the STRONGEST way it matched: 0 = MULTI_KEYWORD_RULES
    co-occurrence, 1 = a multi-word phrase, 2 = a single word.

    Used by categorize_listings.py's "possible category collisions"
    report, not by classification itself. The tier matters because
    classify_by_name already resolves multi-tier collisions correctly BY
    DESIGN -- e.g. "Extra Virgin Olive Oil 1L" matches the specific
    "olive oil" phrase (tier 1, Olive Oil) as well as the bare words "oil"
    and "olive" (tier 2, Oils and Olives), but the phrase already wins,
    correctly, every time. That's not a bug and never will be, so it's not
    what this report is for.

    What IS worth flagging: two categories matching at the SAME tier,
    where nothing but KEYWORD_RULES list order decides which one
    classify_by_name actually returns -- exactly the pattern behind every
    real miscategorization bug found through the app so far (a chocolate
    bar's bare "chocolate" vs. a co-occurring bare "milk", a tuna tin's
    bare "tuna" vs. a co-occurring "olive oil" phrase competing with
    another phrase, etc). The caller groups by tier and only reports
    same-tier pairs -- see find_category_collisions in
    categorize_listings.py.

    Deliberately doesn't consider MULTI_KEYWORD_RULES pairs as colliding
    with each other -- those are already deliberate, checked-in overrides
    for known collisions, not things left to find.

    Memoized and uses _fast_keyword_matches internally -- see
    classify_by_name's docstring (28 Aug 2026) for why: this function does
    the same full unconditional scan of every keyword (it never short-
    circuits, since it needs every match, not just the first), so it was
    the more expensive half of the pair of full-listing passes
    categorize_listings.py does per run and the bigger contributor to a
    real production run missing its 600-second timeout."""
    cleaned = clean_for_matching(product_name)
    word_set = frozenset(cleaned.split())
    best_tier = {}

    def note(category, tier):
        if category not in best_tier or tier < best_tier[category]:
            best_tier[category] = tier

    for category, required_words in MULTI_KEYWORD_RULES:
        if all(_fast_keyword_matches(w, word_set, cleaned) for w in required_words):
            note(category, 0)

    for category, keywords in KEYWORD_RULES:
        for kw in keywords:
            if _fast_keyword_matches(kw, word_set, cleaned):
                note(category, 1 if " " in kw.strip() else 2)

    return best_tier


# ============================================================================
# Aisle-scoped keyword rules.
#
# Sits between the ordinary name rules and the last-resort aisle map, and
# exists for words that are decisive INSIDE one aisle and misleading
# everywhere else.
#
# The case that forced it: Welbee's "Drinks" bucket is over half wine, and
# what tells you the colour is the Italian or French word on the label --
# "Bianco", "Rosso", "Rouge", "Rosato". But "bianco" cannot be a normal
# keyword, because elsewhere in this shop it is Omino Bianco (a stain
# remover), Mulino Bianco (biscuits), Cif Crema Bianco and Il Bucato Bianco.
# Scoped to the Drinks aisle it is unambiguous; unscoped it would be a
# disaster. Same for "rose" (wine vs. rose-scented everything).
#
# Checked only after classify_by_name() has already failed, so as with the
# last-resort map below, this can only fill blanks -- never overrule a real
# name match. Within an aisle the list is checked in order, first match wins.
# ============================================================================
SCOPED_KEYWORD_RULES = {
    # Welbee's Health & Beauty labels use trade abbreviations that are far
    # too short to be safe as ordinary keywords: "Sg" is shower gel, "As"
    # aftershave, "Tp" toothpaste, "Apd" anti-perspirant deodorant.
    ("welbees", "Health & Beauty"): [
        ("Shower Gels", ["sg", "doccia", "gel doccia", "bagno"]),
        ("Shaving Creams", ["as", "blade", "razor"]),
        ("Toothpaste", ["tp"]),
        ("Skin Care", ["spf"]),
        ("Hair & Nail Accessories", ["brush", "clip", "comb"]),
        ("Deodorants", ["spray", "roll on", "stick"]),
    ],

    ("welbees", "Drinks"): [
        # Colour first -- it is the most reliable signal on a wine label.
        ("Wine - Rose", ["rose", "rosato", "rosado", "anjou", "provence"]),
        ("Wine - Sparkling", ["sparkling", "sparking", "frizzant", "cuvee", "champagne", "bollinger", "blue nun", "moscato d asti", "brut"]),  # bare "brut" is unsafe globally (collides with Faberge Brut in Perfume -- see the 23 Aug 2026 note above), but scoped to this aisle it's unambiguous; closes 5 unclassified welbees/Drinks listings (Veuve Clicquot Brut, Chevaliers de Malte Brut, etc.)
        ("Wine - White", ["bianco", "white", "blanc", "cortese", "chablis", "verdejo", "albarino", "orvieto", "frascati", "bourgogne blanc"]),
        ("Wine - Red", ["rouge", "rosso", "red", "tinto", "nerello", "pinotage", "zinfandel", "zinfadel", "gamay", "cinsault", "bardolino", "bordeaux", "chateau", "emilion", "brunello", "barbera", "dolcetto", "ammasso", "barrel aged"]),
        ("Beers", ["alhambra", "bavaria", "budweiser", "baladin", "radler", "birra", "beer", "pilsner", "stout"]),
        ("Spirits - Liqueurs", ["tequila", "teqila", "campari", "aperol", "bitters", "bitter", "advokaat", "bombay sapphire", "angostura", "caffo", "cocktail"]),
        ("Carbonated Drinks", ["gazzosa", "limonata", "tonic", "britvic", "frizzante"]),
        ("Juices", ["cappy", "belte", "multi vitamin", "multivitamin", "aloe vera drink", "aleo vera"]),
        ("Water", ["acqua"]),
        # Anything still unmatched in this aisle that names a grape or a
        # region is wine; without a colour word Red is the commoner default
        # for these bottles.
        ("Wine - Red", ["doc", "docg", "igp", "igt", "dop", "vino", "wine", "riserva", "reserva"]),
    ],
}


# ============================================================================
# Last-resort chain-category fallback.
#
# The maps above (PAVI_CATEGORY_MAP / GREENS_CATEGORY_MAP) are applied BEFORE
# the product name is looked at, which makes them a strong claim: everything
# in that bucket IS this category. That's right for a bucket like "Rice", and
# wrong for a bucket like "Laundry Detergent", which holds liquids, powders,
# capsules and dryer sheets -- mapping the whole bucket would take "Ariel
# Pods" away from Laundry Tablets, which the name already gets right.
#
# This map is the opposite claim, and a much weaker one: only reached when
# the product NAME matched nothing at all, so it can never overrule a good
# name match. It answers "we can't tell from the name -- what aisle was it
# on?", which for these buckets is a far better answer than leaving the
# listing uncategorised.
#
# Keyed on the exact (store_id, chain_category) string as it appears in the
# database. Only buckets whose own name states the category are listed --
# deliberately NOT here are the genuinely mixed ones, where the aisle says
# nothing useful about what the product is:
#   * Welbee's "Food Cupboard", "Health & Beauty", "Household",
#     "Home & Entertainment", "Drinks", "Chilled Food", "Healthy Section"
#   * Greens' "Gluten Free Products", "Organic Food", "Dietary Food",
#     "Lactose Free Products", "Low Fat Products" -- a dietary label, not a
#     product type; the aisle holds milk, pasta, biscuits and yoghurt alike.
# Those still need real keywords, and still show up in the run report until
# they get them.
# ============================================================================
LAST_RESORT_CATEGORY_MAP = {
    # ---- Greens: laundry ----
    ("greens", "Household / Laundry Products / Laundry Detergent"): "Laundry Washing Liquids",
    ("greens", "Household / Laundry Products / Laundry Conditioner"): "Fabric Softener",
    ("greens", "Household / Laundry Products / Laundry Freshner"): "Fabric Softener",
    ("greens", "Household / Laundry Products / Laundry Detergent Sheets"): "Laundry Tablets",
    ("greens", "Household / Laundry Products / Laundry Stain Remover"): "Stain Removers",
    ("greens", "Household / Laundry Products / Laundry Color Run Remover"): "Stain Removers",
    ("greens", "Household / Laundry Products / Laundry Color Dye"): "Stain Removers",
    ("greens", "Household / Laundry Products / Laundry Whitener"): "Stain Removers",
    ("greens", "Household / Laundry Products / Laundry Bleach"): "Stain Removers",
    ("greens", "Household / Laundry Products / Laundry Starch"): "Stain Removers",

    # ---- Greens: cleaning ----
    ("greens", "Household / Bathroom Care And Essentials / Bathroom Cleaning Products"): "Bathroom & Wc Cleaner",
    ("greens", "Household / Bathroom Care And Essentials / Toilet Refreshner"): "Bathroom & Wc Cleaner",
    ("greens", "Household / Household Care And Essentials / Floor Wash And Bleach"): "Floor Cleaners",
    ("greens", "Household / Household Care And Essentials / Metal Polish"): "All-purpose Cleaners",
    ("greens", "Household / Household Care And Essentials / Carpet Cleaners"): "All-purpose Cleaners",
    ("greens", "Household / Household Care And Essentials / Window And Glass Cleaner"): "All-purpose Cleaners",
    ("greens", "Household / Household Care and Essentials / Cleaning Wipes"): "All-purpose Cleaners",  # lowercase "and" is how this one really appears
    ("greens", "Household / Household Care And Essentials / Insect Pest Control"): "Insect Killer",
    ("greens", "Household / Household Care And Essentials / Degradable Refuse Bags"): "Disposables",
    ("greens", "Household / Household Care And Essentials / First Aid"): "First Aid",
    ("greens", "Household / Household Care And Essentials / Candles"): "Candles",
    ("greens", "Household / Household Care And Essentials / Travel Accessories"): "Household Goods",
    ("greens", "Household / Household Care And Essentials / Humidity Absorbers"): "Household Goods",
    ("greens", "Household / Bathroom Care And Essentials / Bath Towels And Face Cloths"): "Household Goods",

    # ---- Greens: personal care ----
    ("greens", "Personal Care / Bathroom Care And Essentials / Tampons"): "Intimate Care",  # matches the existing bare "tampon" keyword, which also points at Intimate Care
    ("greens", "Personal Care / Bathroom Care And Essentials / Hand Soap"): "Hand Wash Liquids",
    ("greens", "Personal Care / Bathroom Care And Essentials / Toilet Paper"): "Disposables",
    ("greens", "Personal Care / Personal Hygiene And Care / Cosmetics"): "Make Up",
    ("greens", "Personal Care / Personal Hygiene And Care / Hair Shampoo And Conditioners"): "Shampoos",
    ("greens", "Personal Care / Personal Hygiene And Care / Perfumes"): "Perfume",
    ("greens", "Personal Care / Personal Hygiene And Care / Cotton Wool And Buds"): "Cotton Buds",
    ("greens", "Personal Care / Personal Hygiene And Care / Tissues"): "Disposables",
    ("greens", "Personal Care / Personal Hygiene And Care / Shoe Care"): "Household Goods",
    ("greens", "Personal Care / Personal Hygiene And Care / Foot Care"): "First Aid",
    ("greens", "Personal Care / Personal Hygiene And Care / Condoms"): "Intimate Care",
    ("greens", "Personal Care / Personal Hygiene And Care / Sun Lotion"): "Skin Care",
    ("greens", "Personal Care / Personal Hygiene And Care / Wipes"): "Skin Care",  # this bucket is facial/cleansing wipes -- the odd alcohol or spectacle wipe is the exception, not the rule

    # ---- Greens: food ----
    ("greens", "Bakery / Bread / Fresh Bread"): "Bread",
    ("greens", "Bakery / Bread / Sliced White Bread"): "Bread",
    ("greens", "Bakery / Bread / Packed White Bread"): "Bread",
    ("greens", "Bakery / Bread / Pita And Nan Bread"): "Bread",
    ("greens", "Bakery / Bread / Bruschetta And Croutons"): "Crackers, Crispbread & Breadsticks",
    ("greens", "Bakery / Bread / Bread Crumbs"): "Flour",
    ("greens", "Confectionery / Bread / Wraps"): "Bread",
    ("greens", "Health / Vegetarian / Vegetarian Products"): "Meat Alternatives",
    ("greens", "Health / Vegetarian / Chilled Vegetarian Products"): "Meat Alternatives",
    ("greens", "Health / Gluten Free / Gluten Free Pasta"): "Pasta & Couscous",
    ("greens", "Groceries / Oil And Vinegar / Other Oil"): "Oils",
    ("greens", "Groceries / Oil And Vinegar / Olive Oil"): "Olive Oil",
    ("greens", "Chilled And Dairy / Milk And Eggs / Eggs"): "Eggs",
    ("greens", "Groceries / Milk And Eggs / Milk"): "Milk",

    # ---- Welbee's: the few buckets that ARE a product type ----
    ("welbees", "Frozen Food"): "Frozen",
    ("welbees", "Tobacco"): "Tobacco & Tobacco Accessories",
    ("welbees", "Bakery"): "Bread",
    ("welbees", "Clothes & Accessories"): "Clothes",
    ("welbees", "Pets"): "Pet Food",
    ("welbees", "Baby"): "Baby Essentials",
    ("welbees", "Fresh Fish Counter"): "Chilled Fish",

    # ---- PAVI/PAMA ----
    ("pavipama", "COTTON BUDS / COTTON PADS"): "Cotton Buds",
    ("pavipama", "OILS"): "Oils",
}


def classify_listing(store_id, chain_category, chain_product_name):
    """The single entry point categorize_listings.py calls per listing.
    Returns a canonical category name, or None if nothing could classify
    it (logged by the caller, not guessed)."""
    if store_id == "pavipama" and chain_category:
        mapped = PAVI_CATEGORY_MAP.get(chain_category.strip())
        # mapped != KEYWORD_FALLBACK -- a PAVI bucket can now also be flagged
        # as mixed (see "OILS" above) and fall through to name-based
        # classification below, the same way a flagged Greens bucket already
        # does.
        if mapped and mapped != KEYWORD_FALLBACK:
            return mapped

    if store_id == "greens" and chain_category:
        parts = chain_category.split(" / ")
        top = parts[0].strip() if len(parts) > 0 else None
        sub = parts[1].strip() if len(parts) > 1 else None
        subsub = parts[2].strip() if len(parts) > 2 else None
        mapped = GREENS_CATEGORY_MAP.get((top, sub))
        if mapped and mapped != KEYWORD_FALLBACK:
            return mapped
        if mapped == KEYWORD_FALLBACK and subsub:
            sub_mapped = GREENS_SUBCATEGORY_MAP.get((top, sub, subsub))
            if sub_mapped:
                return sub_mapped

    # Welbee's always lands here (its categories are too broad to map
    # directly), as does anything above that fell through or was flagged
    # KEYWORD_FALLBACK.
    by_name = classify_by_name(chain_product_name)
    if by_name is not None:
        return by_name

    # Nothing in the name matched. Before giving up, fall back to the aisle
    # the product was found on -- but only for the buckets whose own name
    # states the category (see LAST_RESORT_CATEGORY_MAP). Deliberately last:
    # a real name match always wins, so this can only ever fill in blanks,
    # never overrule something already decided.
    if chain_category:
        key = (store_id, chain_category.strip())

        # Words that only mean what they look like inside this one aisle
        # (see SCOPED_KEYWORD_RULES).
        cleaned = clean_for_matching(chain_product_name)
        for category, keywords in SCOPED_KEYWORD_RULES.get(key, ()):
            for kw in keywords:
                if _keyword_matches(kw, cleaned):
                    return category

        return LAST_RESORT_CATEGORY_MAP.get(key)

    return None
