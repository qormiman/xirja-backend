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
    "CANNED FRUIT": "Canned Fruit", "SPIRITS - LIQUERS": "Spirits - Liquers",
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
    ("Yoghurt", ["yoghurt", "yogurt"]),
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
    ("Biscuits", ["biscuit", "cookie", "oreo", "petit beurre", "petite beurre", "wafer milk", "milk wafer", "wafer", "cookies and cream", "cookies & cream"]),  # "oreo" and "petit(e) beurre" -- specific, well-known biscuit brand/type names, found via real data
    ("Cakes", ["cake"]),
    ("Cereals", ["cereal", "cornflakes", "muesli", "granola"]),
    ("Cereal & Cereal Bars", ["cereal bar"]),
    ("Crackers, Crispbread & Breadsticks", ["crispbread", "oatcake"]),
    ("Pasta & Couscous", ["pasta", "spaghetti", "penne", "macaroni", "couscous", "lasagne"]),
    ("Rice", ["rice", "risotto"]),
    ("Flour", ["flour"]),
    ("Cake Preparations", ["yeast"]),  # baking ingredient, found via real data ("Doves Farm Yeast Quick Gluten Free")
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
    ("Cold Cuts", ["mortadella", "luncheon", "cold cut"]),
    ("Frozen Fish", ["frozen fish", "haddock"]),
    ("Chilled Fish", ["fish", "salmon", "tuna", "cod", "prawn", "shrimp"]),
    ("Canned Seafood", ["tinned tuna", "canned tuna", "sardine", "anchov"]),

    # Fruit & veg
    ("Vegetables", ["vegetable", "tomato", "potato", "onion", "carrot", "lettuce", "cucumber", "pepper"]),
    ("Fruits", ["fruit", "apple", "banana", "orange", "grape", "melon"]),
    ("Dried Fruit", ["dried fruit", "raisin", "sultana", "prune"]),
    ("Frozen Vegetables", ["frozen vegetable", "frozen peas", "frozen corn"]),
    ("Herbs & Spices", ["spice", "herb", "pepper corn", "cinnamon", "paprika", "oregano", "basil", "salt"]),
    ("Legumes", ["lentil"]),  # distinct from the broader "Legumes & Nuts" bucket below -- found via real data ("Pensa Bio Lentils")

    # Drinks
    ("Water", ["water"]),
    # Bare "juice"/"smoothie" moved to MULTI_KEYWORD_RULES (Pass 0, below)
    # -- see the comment there for why (a juice's name often also contains
    # a fruit word, e.g. "Del Monte Orange Juice", and Fruits used to win
    # by list order).
    ("Carbonated Drinks", ["cola", "soda", "fizzy", "carbonated"]),
    ("Beers", ["beer", "lager", "ale"]),
    ("Ciders", ["cider"]),
    ("Wine - Red", ["red wine", "red blend"]),
    ("Wine - White", ["white wine", "white blend"]),
    ("Wine - Rose", ["rose wine", "rosé wine"]),
    ("Wine - Sparkling", ["sparkling wine", "prosecco", "champagne", "cava"]),
    ("Spirits - Whisky", ["whisky", "whiskey"]),
    ("Spirits - Vodka", ["vodka"]),
    ("Spirits - Liquers", ["liqueur", "liquer"]),
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
    # so the two real spellings clean down to two different strings.
    ("Snacks", ["popcorn", "snack", "rice up rolls", "rice cake", "potato straws",
                "salt and vinegar", "salt vinegar"]),
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
    ("Nuts", ["peanut", "almond", "cashew", "walnut", "pistachio"]),
    ("Honey", ["honey"]),
    ("Jelly", ["jelly", "jello"]),
    # "olive oil" is checked in the multi-word pass, so it wins over the
    # bare "olive" rule right below it for any product whose name says both
    # -- e.g. "Extra Virgin Olive Oil 1L" lands on Olive Oil, not Olives.
    ("Olive Oil", ["olive oil"]),
    ("Olives", ["olive"]),  # found via real data: "Fragata Sliced Olives" was falling through unclassified
    # Bare "oil"/"vinegar" -- needed now that both PAVI's "OILS" bucket and
    # Greens' "Oil And Vinegar" bucket split by name instead of mapping
    # directly (see the "Olive Oil" fix). Checked in the single-word pass,
    # AFTER "olive oil" above (so a real olive oil still lands on Olive Oil)
    # and after the existing "hair oil"/"facial oil"/"dry oil" phrases
    # elsewhere in this list (those are multi-word, always checked first).
    ("Oils", ["oil"]),
    ("Vinegars", ["vinegar"]),

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
    ("Disposables", ["bin bag", "cling film", "foil", "kitchen roll", "paper towel", "paper plate", "napkin", "plastic cup"]),
    # Generic catch-all last, after the specific liquid/powder/tablet/softener
    # keywords above -- found via real data: "Surf Liquid Coconut 24 Washes"
    # and "General Laundry Wash Universal" don't contain the exact phrase
    # "laundry liquid", just the word "laundry" or "wash(es)" on its own.
    ("Laundry Washing Liquids", ["wash booster", "laundry wash"]),
    ("Household Goods", ["storage container", "lunch box", "thermos", "flask", "wooden spoon"]),
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
    ("Shower Gels", ["shower gel", "body wash", "bath foam", "bubble bath"]),
    ("Hair & Nail Accessories", ["comb"]),
    ("Toothpaste", ["toothpaste"]),
    ("Toothbrushes", ["toothbrush"]),
    ("Mouthwash", ["mouthwash"]),
    ("Deodorants", ["deodorant", "antiperspirant", "deo spray", "deo roll on", "deo stick"]),
    ("Body Lotions", ["body lotion", "hand lotion", "moisturiser", "moisturizer"]),
    ("Face Creams", ["face cream", "facial cream"]),
    ("Skin Care", ["face wash", "facial wash", "cleansing gel", "facial cleanser", "facial oil", "dry oil"]),
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
    ("Pizza", ["pizza"]),
    # "dough" placed AFTER "pizza" (both single words, checked in list
    # order) so a "Pizza Dough" product still lands on Pizza, not Pastry --
    # found via real data ("Buitoni Rectangular Dough").
    ("Pastry", ["dough"]),

    # Tobacco / misc
    ("Tobacco & Tobacco Accessories", ["cigarette", "tobacco", "rolling paper"]),

    # Sports nutrition/supplements -- no dedicated canonical category exists
    # yet (PAVI's own data only has a generic "SPORTS" bucket, no
    # supplements-specific one), so this is an imperfect catch-all, same
    # kind of approximation as a few Greens mappings above. Revisit if this
    # turns out to be a large enough group to deserve its own category.
    ("Sports", ["whey", "protein powder", "creatine", "bcaa", "pre workout"]),
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
    ("Herbs & Spices", ["lamb brand"]),
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
    ("Cat", ["cat"]),
    ("Dog", ["dog food"]),
    ("Dog", ["dog treat"]),
    ("Dog", ["dog chew"]),
    ("Dog", ["puppy"]),
    ("Dog", ["dog"]),
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
    # A hair conditioner or a scented candle naming a food-sounding
    # ingredient (e.g. "Almond Milk & Shea Butter" as a marketing
    # description, or "Apple Cinnamon" as a scent) was losing to the food
    # word and landing in a food category entirely -- found via real data:
    # "Splend'or Nourishing Conditioner Almond Milk & Shea Butter" landed
    # on Milk, and "True Living Candle Jar Apple Cinnamon" landed on
    # Fruits. Both "conditioner" and "candle" are unambiguous,
    # product-defining words -- there's no food product called either one
    # -- so they're safe to check first regardless of what ingredient-style
    # words also appear in the name. Worth watching for the same pattern
    # elsewhere (shampoo, lotion, soap etc. could plausibly have the same
    # issue) if it shows up in a future collision report.
    ("Conditioners", ["conditioner"]),
    ("Candles", ["candle"]),
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
]


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
    stripped out."""
    cleaned_keyword = clean_for_matching(keyword)
    pattern = r"\b" + re.escape(cleaned_keyword) + r"s?\b"
    return re.search(pattern, cleaned_text) is not None


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
    Found and verified via audit_keyword_rules.py, not guessed."""
    cleaned = clean_for_matching(product_name)

    for category, required_words in MULTI_KEYWORD_RULES:
        if all(_keyword_matches(w, cleaned) for w in required_words):
            return category

    for category, keywords in KEYWORD_RULES:
        for kw in keywords:
            if " " in kw.strip() and _keyword_matches(kw, cleaned):
                return category

    for category, keywords in KEYWORD_RULES:
        for kw in keywords:
            if " " not in kw.strip() and _keyword_matches(kw, cleaned):
                return category

    return None


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
    for known collisions, not things left to find."""
    cleaned = clean_for_matching(product_name)
    best_tier = {}

    def note(category, tier):
        if category not in best_tier or tier < best_tier[category]:
            best_tier[category] = tier

    for category, required_words in MULTI_KEYWORD_RULES:
        if all(_keyword_matches(w, cleaned) for w in required_words):
            note(category, 0)

    for category, keywords in KEYWORD_RULES:
        for kw in keywords:
            if _keyword_matches(kw, cleaned):
                note(category, 1 if " " in kw.strip() else 2)

    return best_tier


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
    return classify_by_name(chain_product_name)
