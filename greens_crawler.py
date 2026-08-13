"""
Xirja crawler -- Greens Supermarket.

What this does, in plain terms:
  For every outlet we support (Swieqi, Mriehel, Gozo) and every product
  category on greens.com.mt, this asks Greens' own product-list address for
  that category's products, and saves what it gets back into our database:
  one row per product per outlet ("listing"), and one dated price row per
  product per crawl ("price_observation" -- never overwritten, so we can see
  price history and notice if a crawl silently stops finding real prices).

  It's read-only. It never logs in, never adds anything to a cart, and never
  changes anything on greens.com.mt -- it only asks for public product pages,
  the same way your browser does when you look at the site.

Before you rely on this:
  This was built from one real, hand-captured example of Greens' product
  address (see "Scraper Spike Findings.md"), not from a live test run from
  inside the environment that wrote it -- that environment has no general
  internet access, so this genuinely could not be tested end-to-end before
  landing in your hands. The very first thing to do is run it once (see
  SETUP.md) and check the crawl_run table afterwards. If item_count comes
  back as 0 or very low across the board, something about the request shape
  needs adjusting -- see the NOTE near CART_PLACEHOLDER below for the most
  likely culprit.

How to run it:
  See SETUP.md. In short: set the DATABASE_URL environment variable to your
  Neon connection string, then run `python greens_crawler.py`.
"""

import os
import sys
import time
import json
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

STORE_ID = "greens"
BASE_URL = "https://www.greens.com.mt/apiservices/retail/sync/productlist"

# Identify ourselves honestly, per the README's legal-footing guidance.
# Replace the contact address if you'd rather a different one shows up in
# Greens' server logs.
USER_AGENT = (
    "XirjaCrawler/0.1 (+https://github.com/; "
    "contact: ranier.chircop@gmail.com; polite, low-volume, once-daily crawl)"
)

# Robots.txt for greens.com.mt specifies a 5-second crawl delay. We sleep at
# least that long between every request, no exceptions.
REQUEST_DELAY_SECONDS = 5

# Each outlet's id here MUST match the outlet.id rows inserted by seed.sql.
OUTLETS = [
    {"outlet_id": "greens_swieqi", "source_code": "SM"},
    {"outlet_id": "greens_mriehel", "source_code": "MR"},
    {"outlet_id": "greens_gozo", "source_code": "GZ"},
]

# NOTE on the "Cart" parameter:
# The real request we captured from a live browser session included a
# Cart=<uuid> value tied to that browser's shopping-cart session. We're
# deliberately omitting it below -- most retail platforms treat a missing
# cart id as "no cart yet" rather than an error, but we do not know that for
# certain for Greens specifically. If a test run comes back with item_count
# near 0 for every category, this is the first thing to investigate: try
# adding a random placeholder UUID as the Cart value and see if that changes
# anything.
CART_PLACEHOLDER = None  # e.g. "00000000-0000-0000-0000-000000000000"

# The full category / subcategory tree, captured from greens.com.mt's own
# navigation menu. Each pair is (cat, typ) exactly as the site's URLs use
# them. This is deliberately the complete list rather than a sample, since a
# missed category is a missed set of products with no visible symptom.
CATEGORIES = [
    ("Baby", "BabyCareAndAccessories"), ("Baby", "BabyFood"), ("Baby", "MumToBe"),
    ("Bakery", "BakedGoods"), ("Bakery", "BiscuitsAndCrackers"), ("Bakery", "Bread"),
    ("Bakery", "CerealsAndCerealBars"), ("Bakery", "Confectionery"),
    ("Bakery", "FrozenGoods"), ("Bakery", "OtherConfectionery"),
    ("Bakery", "PastaRiceAndCouscous"), ("Bakery", "ReadyToEat"),
    ("Bakery", "SeasonalGoods"),
    ("Beverages", "BeerAndCiders"), ("Beverages", "Ciders"),
    ("Beverages", "EnergyDrinks"), ("Beverages", "IceTea"),
    ("Beverages", "JuicesAndSmoothies"), ("Beverages", "MixersAndSquashes"),
    ("Beverages", "SoftDrinks"), ("Beverages", "Water"),
    ("Butcher", "Bacon"), ("Butcher", "Beef"), ("Butcher", "Chicken"),
    ("Butcher", "Duck"), ("Butcher", "Lamb"), ("Butcher", "OtherButcherItems"),
    ("Butcher", "Pork"), ("Butcher", "Rabbit"), ("Butcher", "Sausages"),
    ("Butcher", "Turkey"),
    ("CheeseCounter", "Salads"),
    ("ChilledAndDairy", "ButterDipsAndSpreadables"), ("ChilledAndDairy", "ChilledBeverages"),
    ("ChilledAndDairy", "ChilledFoods"), ("ChilledAndDairy", "FreshCream"),
    ("ChilledAndDairy", "MilkAndEggs"), ("ChilledAndDairy", "MortadellaAndLuncheonMeat"),
    ("ChilledAndDairy", "OtherChilled"), ("ChilledAndDairy", "YoghurtsAndDesserts"),
    ("CondimentsAndSeasoning", "HerbsSpicesAndCubes"), ("CondimentsAndSeasoning", "SpicesAndHerbs"),
    ("Confectionery", "BiscuitsAndCrackers"), ("Confectionery", "Bread"),
    ("Confectionery", "ChocolatesAndSweets"), ("Confectionery", "Confectionery"),
    ("Confectionery", "CrispsPopcornAndOtherSnacks"), ("Confectionery", "Dips"),
    ("Confectionery", "PastaRiceAndCouscous"), ("Confectionery", "PastriesAndPrepackedCakes"),
    ("Cosmetics", "BeautyTools"), ("Cosmetics", "Brows"), ("Cosmetics", "Complection"),
    ("Cosmetics", "Eyes"), ("Cosmetics", "Lips"), ("Cosmetics", "Nails"),
    ("Cosmetics", "Perfume"), ("Cosmetics", "SkinCare"),
    ("Delicatessen", "AntipastoFood"), ("Delicatessen", "Cheeses"),
    ("Delicatessen", "FreshPasta"), ("Delicatessen", "HamAndSalami"),
    ("Delicatessen", "MortadellaAndLuncheonMeat"), ("Delicatessen", "Seasonal"),
    ("Fish", "FreshFish"), ("Fish", "FrozenFish"),
    ("FlowersAndPlants", "Flowers"), ("FlowersAndPlants", "Plants"),
    ("FrozenFoods", "ChipsAndOtherPotatoProducts"), ("FrozenFoods", "DisposableGoods"),
    ("FrozenFoods", "FrozenFruitAndVegetables"), ("FrozenFoods", "FrozenMeat"),
    ("FrozenFoods", "FrozenPizzasAndPastries"), ("FrozenFoods", "IceCreamAndDesserts"),
    ("FrozenFoods", "OtherFrozenFood"),
    ("FruitsAndVegetables", "BabyFruitAndVegetables"), ("FruitsAndVegetables", "BeansPeasAndSprouts"),
    ("FruitsAndVegetables", "DriedFruit"), ("FruitsAndVegetables", "Fruit"),
    ("FruitsAndVegetables", "FruitAndVegetable(freshlyCut)"), ("FruitsAndVegetables", "HerbsAndSpices"),
    ("FruitsAndVegetables", "HerbsSpicesAndCubes"), ("FruitsAndVegetables", "Organic"),
    ("FruitsAndVegetables", "Pre-packed"), ("FruitsAndVegetables", "ReadyToEat"),
    ("FruitsAndVegetables", "Salads"), ("FruitsAndVegetables", "Vegetables"),
    ("Groceries", "BakedGoods"), ("Groceries", "BakingNeeds"),
    ("Groceries", "ButterDipsAndSpreadables"), ("Groceries", "CakeMix"),
    ("Groceries", "CoffeeTeaAndHotChocolate"), ("Groceries", "DisposableGoods"),
    ("Groceries", "DriedFruitLegumeeAndNuts"), ("Groceries", "DriedFruitLegumeesAndNuts"),
    ("Groceries", "Flour"), ("Groceries", "HerbsSpicesAndCubes"),
    ("Groceries", "HotBeverages"), ("Groceries", "InternationalCuisine"),
    ("Groceries", "JamsHoneyAndPeanutButter"), ("Groceries", "Jelly"),
    ("Groceries", "MilkAndEggs"), ("Groceries", "MiscellaneousSnacks"),
    ("Groceries", "OilAndVinegar"), ("Groceries", "PastaRiceAndCouscous"),
    ("Groceries", "SaucesAndCondiments"), ("Groceries", "SeasonalAndFestiveFood"),
    ("Groceries", "Soups"), ("Groceries", "SugarAndSweetners"),
    ("Groceries", "SweetCreamAndPanna"), ("Groceries", "TinnedGoods"),
    ("Health", "DairyFree"), ("Health", "Diet"), ("Health", "GlutenFree"),
    ("Health", "LactoseFree"), ("Health", "LowFat"), ("Health", "OrganicAndBio"),
    ("Health", "Protein"), ("Health", "ProteinBars"),
    ("Health", "SugarFreeAndNoAddedSugar"), ("Health", "Vegetarian"),
    ("HomeGarden", "FurnitureCare"), ("HomeGarden", "GardenAndAccessories"),
    ("HomeGarden", "HouseholdGoods"), ("HomeGarden", "Ironmongery"),
    ("HomeGarden", "PicnicAndBbqEssentials"),
    ("Household", "BabyCareAndAccessories"), ("Household", "BathroomCareAndEssentials"),
    ("Household", "Batteries"), ("Household", "CarProducts"),
    ("Household", "DisposableGoods"), ("Household", "Footwear"),
    ("Household", "Garments"), ("Household", "Health"),
    ("Household", "HouseholdCareAndEssentials"), ("Household", "KitchenCareAndAccessories"),
    ("Household", "LaundryProducts"), ("Household", "PartyItems"),
    ("Household", "SeasonalItems"), ("Household", "Sports"),
    ("Household", "Stationery"), ("Household", "StationeryGoods"),
    ("Household", "Toys"), ("Household", "Vouchers"),
    ("New", "New"),
    ("Organic", "DietaryFood"),
    ("PersonalCare", "BathroomCareAndEssentials"), ("PersonalCare", "Cosmetics"),
    ("PersonalCare", "GiftSets"), ("PersonalCare", "MensSection"),
    ("PersonalCare", "PersonalHygieneAndCare"), ("PersonalCare", "WomensSection"),
    ("Pets", "CatSection"), ("Pets", "DogSection"), ("Pets", "OtherPets"),
    ("Pets", "PetAccessoriesAndHygiene"), ("Pets", "PetTreats"),
    ("WineCellar", "PortAndSherryWine"), ("WineCellar", "Spirits"),
    ("WineCellar", "Wines"), ("WineCellar", "WinesAndChampagne"),
]

PAGE_SIZE = 48  # matches the value confirmed working in the spike capture

# Sizes that make a per-kg / per-litre price meaningful to compute.
WEIGHT_UNITS = {"Kilogram": "kg", "Litre": "l"}


# ----------------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------------

def fetch_page(cat, typ, loc, page):
    """Ask Greens for one page of one category, at one outlet. Returns the
    parsed JSON response, or raises an exception on failure."""
    params = {
        "Agent": "GREENS",
        "Loc": loc,
        "Eid": "N/A",
        "SearchCriteria": "",
        "page": page,
        "NumberOfRecords": PAGE_SIZE,
        "SortType": "Position",
        "SortDirection": "Asc",
        "Category": cat,
        "Category2": "",
        "Category3": "",
        "Type": typ,
        "Cid": "00000000-0000-0000-0000-000000000000",
        "SubType": "",
        "Brand": "",
        "ProductListType": "products",
        "Mobdev": "False",
        "Detailed": "True",
    }
    if CART_PLACEHOLDER:
        params["Cart"] = CART_PLACEHOLDER

    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------

def parse_products(payload):
    """Turn one page's raw response into a list of plain dicts ready to store."""
    out = []
    for item in payload.get("ProductList", []):
        d = item.get("ProductDetails", {})
        code = d.get("PART_NUMBER")
        name = d.get("PART_DESCRIPTION")
        if not code or not name:
            continue  # skip anything malformed rather than guess

        price = d.get("SALES_PRICE")
        rrp = d.get("SALES_PRICE_RRP")
        size_value = d.get("SIZE_VALUE")
        size_uom = d.get("SIZE_UOM")

        price_per_unit = None
        price_per_unit_measure = None
        if size_value and size_uom in WEIGHT_UNITS and price is not None:
            try:
                if float(size_value) > 0:
                    price_per_unit = round(float(price) / float(size_value), 4)
                    price_per_unit_measure = WEIGHT_UNITS[size_uom]
            except (TypeError, ValueError, ZeroDivisionError):
                pass

        category = " / ".join(
            filter(None, [d.get("GROUP_1"), d.get("GROUP_2"), d.get("GROUP_3")])
        ) or None

        out.append({
            "chain_product_code": str(code),
            "chain_product_name": name,
            "chain_category": category,
            "url": f"https://www.greens.com.mt/productdetails?pid={code}",
            "price": price,
            "regular_price": rrp if rrp and rrp != price else None,
            "price_per_unit": price_per_unit,
            "price_per_unit_measure": price_per_unit_measure,
        })
    return out


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------

def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(database_url)


def upsert_listing(cur, outlet_id, product):
    cur.execute(
        """
        INSERT INTO listing (outlet_id, chain_product_code, chain_product_name, chain_category, url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (outlet_id, chain_product_code)
        DO UPDATE SET chain_product_name = EXCLUDED.chain_product_name,
                      chain_category = EXCLUDED.chain_category,
                      url = EXCLUDED.url
        RETURNING id
        """,
        (outlet_id, product["chain_product_code"], product["chain_product_name"],
         product["chain_category"], product["url"]),
    )
    return cur.fetchone()[0]


def insert_price_observation(cur, listing_id, product):
    cur.execute(
        """
        INSERT INTO price_observation
            (listing_id, price, regular_price, price_per_unit, price_per_unit_measure, source)
        VALUES (%s, %s, %s, %s, %s, 'site')
        """,
        (listing_id, product["price"], product["regular_price"],
         product["price_per_unit"], product["price_per_unit_measure"]),
    )


# ----------------------------------------------------------------------------
# Crawl one outlet
# ----------------------------------------------------------------------------

def crawl_outlet(conn, outlet_id, source_code):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO crawl_run (store_id, outlet_id, status) VALUES (%s, %s, 'running') RETURNING id",
        (STORE_ID, outlet_id),
    )
    run_id = cur.fetchone()[0]
    conn.commit()

    item_count = 0
    error_message = None

    try:
        for cat, typ in CATEGORIES:
            page = 1
            while True:
                payload = fetch_page(cat, typ, source_code, page)
                products = parse_products(payload)

                for product in products:
                    listing_id = upsert_listing(cur, outlet_id, product)
                    if product["price"] is not None:
                        insert_price_observation(cur, listing_id, product)
                        item_count += 1
                conn.commit()

                print(f"  {outlet_id} / {cat}/{typ} page {page}: {len(products)} products")

                page_end = payload.get("pageEnd", True)
                if page_end or not products:
                    break
                page += 1
                time.sleep(REQUEST_DELAY_SECONDS)

            time.sleep(REQUEST_DELAY_SECONDS)

        status = "success"

    except Exception as exc:  # noqa: BLE001 -- we want to log ANY failure and move on
        status = "failed"
        error_message = f"{type(exc).__name__}: {exc}"
        print(f"  ERROR crawling {outlet_id}: {error_message}", file=sys.stderr)

    cur.execute(
        "UPDATE crawl_run SET finished_at = %s, status = %s, item_count = %s, error_message = %s WHERE id = %s",
        (datetime.now(timezone.utc), status, item_count, error_message, run_id),
    )
    conn.commit()
    cur.close()

    print(f"Finished {outlet_id}: status={status}, item_count={item_count}")
    return status == "success"


# ----------------------------------------------------------------------------

def main():
    conn = get_connection()
    all_ok = True
    for outlet in OUTLETS:
        print(f"\n=== Crawling {outlet['outlet_id']} ===")
        ok = crawl_outlet(conn, outlet["outlet_id"], outlet["source_code"])
        all_ok = all_ok and ok
    conn.close()

    if not all_ok:
        sys.exit(1)  # non-zero exit so GitHub Actions marks the run as failed


if __name__ == "__main__":
    main()
