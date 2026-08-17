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
import re


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
    "OILS": "Oils", "WAFERS": "Wafers", "RICE": "Rice", "WOMEN CARE": "Women Care",
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
# KEYWORD_FALLBACK marks a bucket that mixes too many different kinds of
# product to assign one category -- these fall through to name-based
# classification instead (see classify_by_name below).
# ----------------------------------------------------------------------------

KEYWORD_FALLBACK = "__KEYWORD_FALLBACK__"

GREENS_CATEGORY_MAP = {
    ("Baby", "Baby Food"): "Baby Food",
    ("Baby", "Baby Care And Accessories"): "Baby Essentials",
    ("Baby", "Mum To Be"): "Mum To Be",

    ("Bakery", "Biscuits And Crackers"): "Biscuits",
    ("Bakery", "Cereals And Cereal Bars"): "Cereal & Cereal Bars",
    ("Bakery", "Bread"): "Bread",
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
    ("Confectionery", "Bread"): "Bread",
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
    ("Groceries", "Oil And Vinegar"): "Oils",
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
    ("Cheese", ["cheese", "mozzarella", "cheddar", "feta", "halloumi", "parmigiano", "parmesan", "formaggio"]),
    ("Butter", ["butter", "margarine", "spread"]),
    ("Cooking Creams", ["cream", "panna"]),

    # Bakery & carbs
    ("Bread", ["bread", "baguette", "ftira", "hobz", "panini"]),  # "panini" found via real data: an Italian bread roll, not the toasted sandwich in this context
    # "wafer milk"/"milk wafer" and "chocolate & milk"/"chocolate and milk"
    # are specific real phrasings (checked in the multi-word pass) for the
    # same underlying pattern: a chocolate/biscuit snack that mentions
    # "milk" as an ingredient, not an actual carton of milk. Found via real
    # API testing -- first "Storck Knoppers Wafer Milk", then (after that
    # fix) "Bahlsen Leibniz Pick Up Chocolate & Milk" turned up as the next
    # wrong result. Worth watching for further variants of this same
    # pattern as more real data gets tested.
    ("Biscuits", ["biscuit", "cookie", "oreo", "petit beurre", "petite beurre", "wafer milk", "milk wafer", "wafer", "chocolate & milk", "chocolate and milk"]),  # "oreo" and "petit(e) beurre" -- specific, well-known biscuit brand/type names, found via real data
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
    ("Sausages", ["sausage"]),
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
    ("Juices", ["juice", "smoothie"]),
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
    # "milk chocolate" is listed explicitly (and checked in the multi-word
    # pass) so that brand names like "Cadbury Dairy Milk Chocolate Bar"
    # land on Chocolates, not Milk -- found via real testing, see
    # test_category_taxonomy.py. "milk choclate" (one c) is the same fix
    # for a real misspelling seen live ("Rice Up Milk Choclate Rice Bar").
    ("Chocolates", ["chocolate", "choco", "milk chocolate", "milk choclate"]),
    ("Snacks", ["crisps", "popcorn", "pretzel", "snack"]),
    ("Chips", ["chips"]),
    ("Nuts", ["peanut", "almond", "cashew", "walnut", "pistachio"]),
    ("Honey", ["honey"]),
    ("Jelly", ["jelly", "jello"]),
    ("Olives", ["olive"]),  # found via real data: "Fragata Sliced Olives" was falling through unclassified

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

    # Pets
    # "felix" -- a specific, globally-known cat food brand whose products
    # don't say "cat" anywhere in the name, found via real data ("Purina
    # Gourmet Felix As Good As It Looks Mixed Selection").
    ("Cat", ["cat food", "cat litter", "cat treat", "kitten", "felix"]),
    ("Dog", ["dog food", "dog treat", "dog chew", "puppy"]),
    # bare "dog"/"cat" last -- found via real data: "Royal Canin Adult Shih
    # Tzu Dog Dry Food" doesn't contain any of the specific phrases above,
    # just the word "Dog" on its own.
    ("Dog", ["dog"]),
    ("Cat", ["cat"]),

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


def clean_for_matching(name):
    cleaned = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
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
    KEYWORD_RULES matched.

    Checked in two passes rather than one flat pass:

      1. Multi-word phrases first (e.g. 'ice cream', 'dried fruit', 'adult
         nappy', 'baby shampoo', 'pepper corn', 'tinned tuna') -- these are
         always more specific than a single word.
      2. Single words second (e.g. 'cream', 'fruit', 'nappy', 'shampoo',
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

    for category, keywords in KEYWORD_RULES:
        for kw in keywords:
            if " " in kw.strip() and _keyword_matches(kw, cleaned):
                return category

    for category, keywords in KEYWORD_RULES:
        for kw in keywords:
            if " " not in kw.strip() and _keyword_matches(kw, cleaned):
                return category

    return None


def classify_listing(store_id, chain_category, chain_product_name):
    """The single entry point categorize_listings.py calls per listing.
    Returns a canonical category name, or None if nothing could classify
    it (logged by the caller, not guessed)."""
    if store_id == "pavipama" and chain_category:
        mapped = PAVI_CATEGORY_MAP.get(chain_category.strip())
        if mapped:
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
