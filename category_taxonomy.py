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
    # Bare "oil"/"vinegar" -- needed now that both PAVI's "OILS" bucket and
    # Greens' "Oil And Vinegar" bucket split by name instead of mapping
    # directly (see the "Olive Oil" fix). Checked in the single-word pass,
    # AFTER "olive oil" above (so a real olive oil still lands on Olive Oil)
    # and after the existing "hair oil"/"facial oil"/"dry oil" phrases
    # elsewhere in this list (those are multi-word, always checked first).
    ("Oils", ["oil"]),
    # "rice vinegar" -- was landing on Rice instead (both bare "rice" and
    # bare "vinegar" are single-word/tier-2, with Rice listed earlier),
    # found via real data ("Blue Dragon Rice Vinegar", "Yutaka Rice
    # Vinegar"). Listed as its own phrase so it wins over bare "rice"
    # outright, the same way "olive oil" already wins over bare "olive"/
    # "oil".
    ("Vinegars", ["rice vinegar", "vinegar"]),

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
    ("Conditioners", ["conditioner"]),
    ("Candles", ["candle"]),
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
    # A cream-cheese product (checked both word orders -- real examples had
    # "Cream Cheese" AND "Cheese Cream") was landing on Cooking Creams via
    # bare "cream", since Cooking Creams is listed earlier than Cheese.
    # Cream cheese is always a cheese product, never a tub of cooking
    # cream, so both words appearing together anywhere in the name is a
    # safe, reliable signal regardless of which order they're written in.
    ("Cheese", ["cream", "cheese"]),
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
    ("Cat", ["cat"]),
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
