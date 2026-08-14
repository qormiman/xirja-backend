"""
Xirja -- cross-chain product matcher.

What this does, in plain terms:
  The three crawlers each save their own chain's products completely
  separately -- Greens' "Coca Cola 2L", PAVI PAMA's "Coca-Cola 2 Litre", and
  Welbee's "Coca Cola (2l)" all end up as three unrelated rows in the
  `listing` table, with no idea they're the same real-world product. This
  script is what connects them: it finds listings (from the same chain's
  other branches, and across different chains) that represent the same real
  product, and links them together via the shared `product` table so the
  app can eventually show "this product costs X at Greens, Y at PAVI PAMA,
  Z at Welbee's" side by side.

  It's read-only towards the outside world -- it never touches any of the
  three sites, it only reads and updates your own database.

Two very different kinds of matching happen here, because they have very
different levels of certainty:

  1. Same chain, different branch (e.g. Greens Swieqi vs Greens Mriehel vs
     Greens Gozo). These share the exact same chain_product_code, because
     it's genuinely the same catalogue entry at a different location -- so
     this is a certain, automatic match. No fuzzy comparison involved.

  2. Across chains (Greens vs PAVI PAMA vs Welbee's). There's no shared ID
     to lean on here -- barcodes were considered and ruled out, since only
     PAVI PAMA ever captures one, and even then there's nothing on the
     Greens/Welbee's side to compare it against. So this instead:
       a. Pulls a pack size out of each product's own name (e.g. "2L",
          "500ml", "6x330ml"), converts it to a common unit (litres for
          volume, kilograms for weight), and REQUIRES two products to have
          the same size before they can ever be considered a match -- a
          500ml and a 2L bottle of the same drink are always different
          products here, no matter how similar the names look.
       b. With sizes agreeing (or unknown on one/both sides), compares
          what's left of the name after removing the size text, using
          Python's own built-in text-similarity tool (difflib) -- nothing
          fancier than that; it's a well-understood, dependency-free
          approach and good enough for "is this obviously the same
          product" once size has already ruled out the false positives
          that matter most.

  Confidence policy (decided deliberately, not left to a fixed cutoff):
    - Very close name match AND confirmed matching size -> 'high',
      linked automatically, used right away.
    - Good-but-not-exact name match (with matching size), OR a very close
      name match where size couldn't be read off one side -> 'medium',
      linked but flagged so a person can check it -- see "Reviewing
      matches" in SETUP.md for the exact query.
    - Anything weaker isn't linked at all. The listing is simply left
      unmatched (product_id stays NULL) and gets reconsidered automatically
      the next time this script runs, once there's more data to compare
      against.

  This is safe to run as often as you like. It only ever looks at listings
  that don't have a product_id yet -- it never revisits or undoes a match
  from a previous run, and it never touches a product you've manually
  confirmed (match_confidence = 'manual'), even if a new, weaker listing
  later attaches to it.

Known limitations, worth knowing about before trusting the output blindly:
  - Size extraction is a best-effort pattern match on the product name text
    (looking for things like "500ml" or "6 x 330g"), not a real understanding
    of the product -- an unusual size format could be missed, in which case
    that product is only matchable by name (capped at 'medium').
  - `product.brand` is left empty for every product created here -- reliably
    picking a brand out of free-text names (vs. reliably NOT picking a
    generic word) wasn't attempted in this first version.
  - Like every crawler in this project, this hasn't been run against your
    real, full database yet at the time it was written -- run it and look at
    the summary it prints, and especially at the 'medium' rows it flags, to
    see how well it's actually doing before trusting it fully.

How to run it:
  See SETUP.md's "Matching products across chains" section. In short: set
  DATABASE_URL, then run `python product_matcher.py`. No browser, no network
  access to any of the three sites -- this only talks to your database.
"""

import os
import re
import sys
import difflib
import threading
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

# How close two (size-stripped) product names need to be, on a 0-1 scale from
# Python's difflib, to count as each tier. These are a reasoned starting
# point, not something confirmed against real output yet -- see "Known
# limitations" above. Easy to adjust here if real results show them too
# loose or too strict.
NAME_HIGH_THRESHOLD = 0.90
NAME_MEDIUM_THRESHOLD = 0.75

# How close two normalised sizes need to be (in litres for volume, kilograms
# for weight) to count as "the same size" -- a small tolerance to absorb
# rounding, not meant to blur genuinely different sizes.
SIZE_TOLERANCE = 0.01

DB_WRITE_HARD_TIMEOUT_SECONDS = 600

CONFIDENCE_RANK = {"unmatched": 0, "low": 1, "medium": 2, "high": 3, "manual": 4}

# ----------------------------------------------------------------------------
# Text and size normalisation
# ----------------------------------------------------------------------------

# We don't actually know which of the three sites spells units out in full
# ("2 Litre") versus abbreviated ("2L") in every case -- rather than guess
# one style, both are recognised and mapped down to the same short form.
UNIT_ALIASES = {
    "ml": "ml", "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "milliliters": "ml",
    "cl": "cl", "centilitre": "cl", "centilitres": "cl", "centiliter": "cl", "centiliters": "cl",
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg",
}
_UNIT_PATTERN = "|".join(sorted(UNIT_ALIASES, key=len, reverse=True))

# Multipack sizes, e.g. "6x330ml" or "4 x 250 grams" -- checked before the
# plain pattern below, since a plain match would otherwise only catch the
# "330ml" part and miss that this is 6 of them (1.98l total, not 0.33l).
MULTIPACK_SIZE_RE = re.compile(
    rf'(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)\s*({_UNIT_PATTERN})\b'
)
SIMPLE_SIZE_RE = re.compile(rf'(\d+(?:[.,]\d+)?)\s*({_UNIT_PATTERN})\b')


def clean_lower(name):
    """Lowercases and strips punctuation, but keeps digits, letters, and the
    '.'/',' inside numbers (like "2.5") intact, so size extraction below
    still works on the result."""
    s = (name or "").lower()
    s = re.sub(r'[^a-z0-9.,\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _to_base_unit(value, unit):
    """Converts a raw (value, unit) pair into a common base unit -- litres
    for anything volume-like, kilograms for anything weight-like -- so a
    "2l" from one chain and a "2000ml" (or "2 Litres") from another compare
    as equal."""
    unit = UNIT_ALIASES.get(unit.lower())
    if unit == "ml":
        return "volume", round(value / 1000, 4)
    if unit == "cl":
        return "volume", round(value / 100, 4)
    if unit == "l":
        return "volume", round(value, 4)
    if unit == "g":
        return "weight", round(value / 1000, 4)
    if unit == "kg":
        return "weight", round(value, 4)
    return None


def extract_size(cleaned_name):
    """Looks for a pack size in an already-cleaned (clean_lower'd) product
    name. Returns (family, value, (start, end)) for the LAST size-looking
    match found (sizes are usually near the end of a product name, and this
    avoids accidentally grabbing an earlier number that isn't a size), or
    None if nothing size-shaped was found."""
    multipack_matches = list(MULTIPACK_SIZE_RE.finditer(cleaned_name))
    if multipack_matches:
        m = multipack_matches[-1]
        count = float(m.group(1).replace(",", "."))
        per_item = float(m.group(2).replace(",", "."))
        base = _to_base_unit(count * per_item, m.group(3))
        if base:
            return base[0], base[1], m.span()

    simple_matches = list(SIMPLE_SIZE_RE.finditer(cleaned_name))
    if simple_matches:
        m = simple_matches[-1]
        value = float(m.group(1).replace(",", "."))
        base = _to_base_unit(value, m.group(2))
        if base:
            return base[0], base[1], m.span()

    return None


def name_core(cleaned_name, size_span):
    """Removes the matched size text (if any) from a cleaned name, so text
    similarity is judged on the rest of the name (mostly brand + product
    words) rather than being thrown off by "2l" vs "2 l" vs "2000ml"."""
    if size_span is None:
        return cleaned_name
    start, end = size_span
    core = cleaned_name[:start] + " " + cleaned_name[end:]
    core = re.sub(r"\s+", " ", core).strip()
    return core if core else cleaned_name  # don't leave an empty string


def name_similarity(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def classify_match(name_sim, size_known, size_matches):
    """Turns a name-similarity score and what we know about sizes into a
    confidence tier, or None if it's not a match at all. See the module
    docstring's "Confidence policy" section for the reasoning."""
    if size_known and not size_matches:
        return None  # different confirmed sizes -- never a match, full stop
    if name_sim >= NAME_HIGH_THRESHOLD:
        return "high" if size_known else "medium"
    if name_sim >= NAME_MEDIUM_THRESHOLD:
        return "medium"
    return None


# ----------------------------------------------------------------------------
# A genuine, independent wall-clock ceiling, reusable for anything that
# might hang -- same helper as every crawler in this project.
# ----------------------------------------------------------------------------

def run_with_timeout(fn, timeout_seconds, *args, **kwargs):
    result = {}

    def target():
        try:
            result["value"] = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, re-raised below
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(f"{getattr(fn, '__name__', 'operation')} did not finish within {timeout_seconds}s")
    if "error" in result:
        raise result["error"]
    return result.get("value")


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------

def get_connection():
    database_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(
        database_url,
        connect_timeout=30,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    # Same fix as every other script in this project -- see greens_crawler.py
    # for the full story of why this can't be passed as a connection option
    # against Neon's pooled endpoint.
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = 30000")
    conn.commit()
    return conn


def fetch_unmatched_listings(cur):
    cur.execute(
        """
        SELECT listing.id, outlet.store_id, listing.chain_product_code,
               listing.chain_product_name, listing.chain_category
        FROM listing
        JOIN outlet ON outlet.id = listing.outlet_id
        WHERE listing.product_id IS NULL
        """
    )
    return cur.fetchall()


def fetch_linked_listings(cur):
    """Every listing that already has a product -- used two ways: (a) to
    trivially reattach a same-store/same-code listing that's newly appeared
    (e.g. Mriehel finally crawling a code Swieqi already established), and
    (b) to know which stores are already represented on each product, so we
    don't attach a second listing from a store that's already there."""
    cur.execute(
        """
        SELECT listing.id, outlet.store_id, listing.chain_product_code, listing.product_id
        FROM listing
        JOIN outlet ON outlet.id = listing.outlet_id
        WHERE listing.product_id IS NOT NULL
        """
    )
    return cur.fetchall()


def fetch_products(cur):
    cur.execute("SELECT id, canonical_name, match_confidence FROM product")
    return cur.fetchall()


# ----------------------------------------------------------------------------
# Matching
# ----------------------------------------------------------------------------

def build_candidates(unmatched, already_linked_index):
    """Groups not-yet-matched listings by (store_id, chain_product_code) --
    each group is one "candidate product" from that chain. Anything whose
    (store_id, code) already exists on an already-linked listing is instead
    handed back separately for a trivial, certain reattachment (no fuzzy
    matching needed -- same store, same code, same product, by definition).
    """
    groups = {}
    trivial_reattach = []  # [(listing_id, existing_product_id), ...]

    for row in unmatched:
        key = (row["store_id"], row["chain_product_code"])
        if key in already_linked_index:
            trivial_reattach.append((row["id"], already_linked_index[key]))
            continue
        groups.setdefault(key, []).append(row)

    candidates = []
    for (store_id, code), rows in groups.items():
        # Longest name is usually the most descriptive -- arbitrary but
        # harmless tie-break when a code somehow has slightly different
        # name text across branches.
        best_row = max(rows, key=lambda r: len(r["chain_product_name"] or ""))
        cleaned = clean_lower(best_row["chain_product_name"])
        size = extract_size(cleaned)
        candidates.append({
            "listing_ids": [r["id"] for r in rows],
            "store_id": store_id,
            "raw_name": best_row["chain_product_name"],
            "category": best_row["chain_category"],
            "cleaned": cleaned,
            "core": name_core(cleaned, size[2] if size else None),
            "family": size[0] if size else None,
            "value": size[1] if size else None,
        })
    return candidates, trivial_reattach


def build_product_targets(products):
    targets = []
    for p in products:
        cleaned = clean_lower(p["canonical_name"])
        size = extract_size(cleaned)
        targets.append({
            "id": p["id"],
            "confidence": p["match_confidence"],
            "core": name_core(cleaned, size[2] if size else None),
            "family": size[0] if size else None,
            "value": size[1] if size else None,
        })
    return targets


def sizes_match(a, b):
    """Returns (size_known, size_matches). size_known is True only when BOTH
    sides have a readable size -- if either side doesn't, we can't confirm
    OR rule out a match on size alone, so size_known is False and the
    decision falls entirely to name similarity (capped at 'medium', per
    classify_match)."""
    if a["family"] is None or b["family"] is None:
        return False, False
    if a["family"] != b["family"]:
        return True, False
    return True, abs(a["value"] - b["value"]) <= SIZE_TOLERANCE


def _size_block_key(item):
    """Blocks on size AND the leading word of the name together, not size
    alone. Size alone isn't fine-grained enough for real grocery data --
    common sizes like "500ml", "1kg", or "2L" are shared by huge numbers of
    otherwise-unrelated products (every soft drink, not just one brand), so
    a size-only bucket can still hold thousands of items that were never
    going to match by name anyway. Combining with the first word (which is
    almost always the brand) cuts each bucket down to roughly "how many
    same-sized products does this one brand have", which in practice is a
    handful, not thousands -- confirmed by testing against a synthetic
    60,000-product stress case before this was ever run for real; blocking
    on size alone was still far too slow at that scale, and this fixed it.

    The 2-decimal rounding (vs. the 4 decimals sizes are stored at) is
    purely a performance grouping, not the actual match decision --
    sizes_match() still does the precise, tolerance-based comparison for
    anything that ends up being compared."""
    if item["family"] is None:
        return None
    return (item["family"], round(item["value"], 2), _first_word(item["core"]))


def _first_word(core):
    return core.split(" ", 1)[0] if core else ""


def _score(a, b):
    size_known, size_ok = sizes_match(a, b)
    sim = name_similarity(a["core"], b["core"])
    tier = classify_match(sim, size_known, size_ok)
    return sim, tier


def find_best_pairs(candidates, product_targets, existing_product_stores):
    """Scores viable (candidate, target) pairs -- against existing products
    AND against other candidates -- and returns them sorted best first,
    ready for greedy assignment.

    A first version of this compared every candidate against every other
    candidate and every product -- simple, but it doesn't scale: run for
    real against ~60,000 real candidates (Greens + PAVI PAMA alone), it
    meant on the order of a BILLION comparisons and the job never finished
    in any reasonable time. Since a match requires matching sizes anyway
    (see sizes_match/classify_match), there's no need to compare two things
    with different sizes in the first place -- so this only ever compares
    within groups that could plausibly match:

      Pass A: candidates/products with a KNOWN size are only compared
      against others sharing that same (rounded) size -- this is where
      almost all real matches live, and turns "everything times everything"
      into "everything times the handful of other things the same size."

      Pass B: anything where at least one side's size couldn't be read is
      compared within groups sharing the first word of the (size-stripped)
      name instead, since it can't be blocked by size. Pairs where BOTH
      sides have a known size are skipped here -- Pass A already covers
      those, and skipping avoids scoring the same pair twice."""
    pairs = []

    def add_pair(ci, right):
        cand = candidates[ci]
        if right[0] == "product":
            target = product_targets[right[2]]
            if cand["store_id"] in existing_product_stores.get(target["id"], set()):
                return
            sim, tier = _score(cand, target)
            if tier:
                pairs.append((sim, tier, ("candidate", ci), ("product", target["id"])))
        else:
            cj = right[2]
            if cj <= ci or candidates[cj]["store_id"] == cand["store_id"]:
                return  # unordered pair counted once; never merge two codes from one chain
            sim, tier = _score(cand, candidates[cj])
            if tier:
                pairs.append((sim, tier, ("candidate", ci), ("candidate", cj)))

    # ---- Pass A: blocked by known size. ----
    cand_size_buckets = {}
    for ci, cand in enumerate(candidates):
        key = _size_block_key(cand)
        if key is not None:
            cand_size_buckets.setdefault(key, []).append(ci)

    product_size_buckets = {}
    for pi, target in enumerate(product_targets):
        key = _size_block_key(target)
        if key is not None:
            product_size_buckets.setdefault(key, []).append(pi)

    largest_bucket = 0
    for key, cand_idxs in cand_size_buckets.items():
        largest_bucket = max(largest_bucket, len(cand_idxs))
        for pi in product_size_buckets.get(key, []):
            for ci in cand_idxs:
                add_pair(ci, ("product", None, pi))
        for a in range(len(cand_idxs)):
            for b in range(a + 1, len(cand_idxs)):
                add_pair(cand_idxs[a], ("candidate", None, cand_idxs[b]))
    if largest_bucket:
        print(f"    (largest same-size group while matching: {largest_bucket} candidates)")

    # ---- Pass B: blocked by first word, only pairs with at least one
    # unknown size (known-vs-known already handled by Pass A above). ----
    word_buckets = {}
    for ci, cand in enumerate(candidates):
        word_buckets.setdefault(_first_word(cand["core"]), ([], []))[0].append(ci)
    for pi, target in enumerate(product_targets):
        word_buckets.setdefault(_first_word(target["core"]), ([], []))[1].append(pi)

    for word, (cand_idxs, product_idxs) in word_buckets.items():
        for ci in cand_idxs:
            cand = candidates[ci]
            for pi in product_idxs:
                target = product_targets[pi]
                if cand["family"] is not None and target["family"] is not None:
                    continue  # both known -- Pass A already covered this
                add_pair(ci, ("product", None, pi))
        for a in range(len(cand_idxs)):
            ci = cand_idxs[a]
            cand = candidates[ci]
            for b in range(a + 1, len(cand_idxs)):
                cj = cand_idxs[b]
                if cand["family"] is not None and candidates[cj]["family"] is not None:
                    continue  # both known -- Pass A already covered this
                add_pair(ci, ("candidate", None, cj))

    pairs.sort(key=lambda p: p[0], reverse=True)
    return pairs


def assign_matches(candidates, product_targets, existing_product_stores, pairs):
    """Walks the sorted pairs best-first and greedily assigns each candidate
    to the best still-available match. A candidate that gets attached to
    another (not-yet-a-product) candidate becomes the seed of a brand new
    temporary group, which can then go on to accept further candidates later
    in the same pass (e.g. a third chain's matching listing) -- so one run
    can link all three chains' listings together in one go, not just two at
    a time.

    Each pair's two sides are handled symmetrically -- whichever side (or
    neither, or both) already belongs to a group is checked explicitly,
    rather than assuming the first-listed side is always the "known" one.
    An earlier version of this only checked the first side, which meant a
    same-scoring pair arriving right after a group had just formed could be
    silently dropped instead of joining that group -- caught by testing
    against a synthetic 3-chain scenario before this was ever run for real."""
    assigned = {}          # candidate index -> ("existing", product_id) | ("new", temp_id)
    new_products = []      # list of dicts describing products to create
    store_sets = {pid: set(stores) for pid, stores in existing_product_stores.items()}
    existing_confidence = {t["id"]: t["confidence"] for t in product_targets}

    def group_stores(ref):
        kind, key = ref
        return store_sets.setdefault(key if kind == "existing" else ("temp", key), set())

    def group_confidence(ref):
        kind, key = ref
        return existing_confidence[key] if kind == "existing" else new_products[key]["confidence"]

    def set_group_confidence(ref, tier):
        kind, key = ref
        current = group_confidence(ref)
        if current == "manual":
            return  # never let an automatic match touch a human-confirmed product
        new_conf = tier if CONFIDENCE_RANK[tier] < CONFIDENCE_RANK[current] else current
        if kind == "existing":
            existing_confidence[key] = new_conf
        else:
            new_products[key]["confidence"] = new_conf

    def try_attach(cand_idx, ref, tier):
        stores = group_stores(ref)
        if candidates[cand_idx]["store_id"] in stores:
            return False  # that chain's already represented in this group
        set_group_confidence(ref, tier)
        stores.add(candidates[cand_idx]["store_id"])
        assigned[cand_idx] = ref
        if ref[0] == "new":
            new_products[ref[1]]["listing_candidate_idxs"].append(cand_idx)
        return True

    for sim, tier, left, right in pairs:
        assert left[0] == "candidate"
        ci = left[1]

        if right[0] == "product":
            if ci in assigned:
                continue
            try_attach(ci, ("existing", right[1]), tier)
            continue

        # right is another candidate.
        cj = right[1]
        ci_ref = assigned.get(ci)
        cj_ref = assigned.get(cj)

        if ci_ref and cj_ref:
            continue  # both sides already settled elsewhere -- nothing to do
        if ci_ref and not cj_ref:
            try_attach(cj, ci_ref, tier)
            continue
        if cj_ref and not ci_ref:
            try_attach(ci, cj_ref, tier)
            continue

        # Neither side is assigned yet -- form a brand new group, unless
        # they're from the same chain (never merge two different codes from
        # one chain into a single product here).
        if candidates[ci]["store_id"] == candidates[cj]["store_id"]:
            continue
        temp_id = len(new_products)
        # Prefer the longer/more descriptive raw name for the product's own
        # display name -- same tie-break idea as build_candidates.
        a, b = candidates[ci], candidates[cj]
        canonical = a["raw_name"] if len(a["raw_name"] or "") >= len(b["raw_name"] or "") else b["raw_name"]
        size_family = a["family"] or b["family"]
        size_value = a["value"] if a["family"] else b["value"]
        new_products.append({
            "canonical_name": canonical,
            "category": a["category"] or b["category"],
            "size_family": size_family,
            "size_value": size_value,
            "confidence": tier,
            "listing_candidate_idxs": [ci, cj],
        })
        ref = ("new", temp_id)
        assigned[ci] = ref
        assigned[cj] = ref
        group_stores(ref).update({candidates[ci]["store_id"], candidates[cj]["store_id"]})

    return assigned, new_products, existing_confidence


# ----------------------------------------------------------------------------
# Writing results
# ----------------------------------------------------------------------------

def apply_results(cur, candidates, trivial_reattach, assigned, new_products, existing_confidence_updates):
    reattached = 0
    for listing_id, product_id in trivial_reattach:
        cur.execute("UPDATE listing SET product_id = %s WHERE id = %s", (product_id, listing_id))
        reattached += 1

    # Create the new products first, so we know their real ids.
    temp_to_real_id = {}
    for temp_id, product in enumerate(new_products):
        if not any(assigned.get(idx) == ("new", temp_id) for idx in product["listing_candidate_idxs"]):
            continue  # nothing ended up assigned to this temp product after all (shouldn't normally happen)
        size_unit = {"volume": "l", "weight": "kg"}.get(product["size_family"])
        cur.execute(
            """
            INSERT INTO product (canonical_name, size_value, size_unit, category, match_confidence)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (product["canonical_name"], product["size_value"], size_unit,
             product["category"], product["confidence"]),
        )
        # cur is a RealDictCursor (used throughout this script so the SELECT
        # queries can be read by column name) -- fetchone() here returns a
        # dict-like row keyed by "id", not a plain positional tuple, so it
        # has to be ["id"], not [0]. Missing that was the actual bug on the
        # last real run (KeyError: 0) -- everything before this line had
        # already run correctly against your real data.
        temp_to_real_id[temp_id] = cur.fetchone()["id"]

    new_product_count = len(temp_to_real_id)

    linked = 0
    for ci, ref in assigned.items():
        kind, key = ref
        product_id = key if kind == "existing" else temp_to_real_id.get(key)
        if product_id is None:
            continue
        for listing_id in candidates[ci]["listing_ids"]:
            cur.execute("UPDATE listing SET product_id = %s WHERE id = %s", (product_id, listing_id))
            linked += 1

    for product_id, new_confidence in existing_confidence_updates.items():
        cur.execute("UPDATE product SET match_confidence = %s WHERE id = %s", (new_confidence, product_id))

    return reattached, new_product_count, linked


# ----------------------------------------------------------------------------
# The matching run itself
# ----------------------------------------------------------------------------

def run_matcher(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    unmatched = fetch_unmatched_listings(cur)
    linked_rows = fetch_linked_listings(cur)
    products = fetch_products(cur)

    already_linked_index = {(r["store_id"], r["chain_product_code"]): r["product_id"] for r in linked_rows}
    existing_product_stores = {}
    for r in linked_rows:
        existing_product_stores.setdefault(r["product_id"], set()).add(r["store_id"])

    print(f"  {len(unmatched)} unmatched listing(s), {len(linked_rows)} already-linked listing(s), "
          f"{len(products)} existing product(s)")

    candidates, trivial_reattach = build_candidates(unmatched, already_linked_index)
    print(f"  {len(trivial_reattach)} listing(s) can be trivially reattached (same store, same code, "
          f"already-known product)")
    print(f"  {len(candidates)} distinct candidate product(s) to try to match, from this run's unmatched listings")

    product_targets = build_product_targets(products)

    pairs = find_best_pairs(candidates, product_targets, existing_product_stores)
    print(f"  {len(pairs)} viable candidate pair(s) found above the matching threshold")

    assigned, new_products, existing_confidence = assign_matches(
        candidates, product_targets, existing_product_stores, pairs
    )

    # Figure out which EXISTING products actually changed confidence, so we
    # only write the ones that changed.
    original_confidence = {t["id"]: t["confidence"] for t in product_targets}
    existing_confidence_updates = {
        pid: new_conf for pid, new_conf in existing_confidence.items()
        if new_conf != original_confidence.get(pid)
    }

    def write_and_commit():
        result = apply_results(cur, candidates, trivial_reattach, assigned, new_products, existing_confidence_updates)
        conn.commit()
        return result

    reattached, new_product_count, linked = run_with_timeout(write_and_commit, DB_WRITE_HARD_TIMEOUT_SECONDS)

    still_unmatched = len(candidates) - len({ci for ci in assigned})
    print(f"  Done: {reattached} trivially reattached, {new_product_count} new product(s) created, "
          f"{linked} listing(s) linked in total, {len(existing_confidence_updates)} existing product(s) "
          f"had their confidence adjusted, {still_unmatched} candidate(s) still unmatched (left for next run)")

    return {
        "reattached": reattached,
        "new_products": new_product_count,
        "linked": linked,
        "still_unmatched": still_unmatched,
    }


def main():
    conn = get_connection()
    try:
        started = datetime.now(timezone.utc)
        print(f"=== Product matching run started {started.isoformat()} ===")
        run_matcher(conn)
        print("=== Done ===")
    except Exception as exc:  # noqa: BLE001 -- surface any failure plainly, then exit non-zero
        conn.rollback()
        print(f"ERROR during matching: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
