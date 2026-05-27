"""
Surya Masterbatch — Full System Debug Script
============================================
Runs end-to-end checks on:
  1. CSV files — existence, columns, duplicates, reference integrity
  2. Database   — row counts, FK orphans, LAB coverage, recipe totals
  3. Color math — LAB↔XYZ roundtrip, K-M formulas, CIEDE2000, mixture prediction
  4. ML model   — feature engineering, corpus, training, predictions

Usage (from workspace root, with .venv active):
    python debug_system.py
    python debug_system.py --section csv     # only CSV checks
    python debug_system.py --section db      # only DB checks
    python debug_system.py --section color   # only color math
    python debug_system.py --section ml      # only ML checks
"""

import os
import sys
import csv
import math
import time
import argparse
from typing import List, Tuple, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
BACKEND   = os.path.join(WORKSPACE, "app", "backend")
sys.path.insert(0, BACKEND)

# ---------------------------------------------------------------------------
# Tiny reporting helpers
# ---------------------------------------------------------------------------
_pass  = 0
_fail  = 0
_warn  = 0

def PASS(msg: str):
    global _pass; _pass += 1
    print(f"  [PASS] {msg}")

def FAIL(msg: str):
    global _fail; _fail += 1
    print(f"  [FAIL] {msg}")

def WARN(msg: str):
    global _warn; _warn += 1
    print(f"  [WARN] {msg}")

def INFO(msg: str):
    print(f"  [INFO] {msg}")

def SECTION(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def approx_equal(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol


# ============================================================
# 1.  CSV FILE CHECKS
# ============================================================

def check_csv():
    SECTION("1. CSV File Integrity")

    expected_files = {
        "raw_material.csv":         ["rawmaterialid", "rawmaterialname", "type", "compliance"],
        "products.csv":             ["id", "name"],
        "product_spec.csv":         ["id", "product_id"],
        "productrawmaterialmap.csv":["productid", "rawmaterialid", "qtyinkg"],
        "pigment_properties.csv":   ["pigment_name", "ci_name", "chemistry"],
        "lab_results.csv":          ["product_id", "polymer", "L", "a", "b"],
        "stocks.csv":               ["rawmaterialid"],
        "alphacode.csv":            ["alpha_code", "product_code"],
        "ral_pantone_shade.csv":    ["shade_code", "color_name"],
    }

    csv_data = {}

    for fname, req_cols in expected_files.items():
        fpath = os.path.join(WORKSPACE, fname)
        if not os.path.exists(fpath):
            FAIL(f"{fname} — file NOT FOUND")
            csv_data[fname] = []
            continue

        with open(fpath, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        csv_data[fname] = rows

        if not rows:
            WARN(f"{fname} — file exists but has 0 data rows")
            continue

        # Check required columns
        missing_cols = [c for c in req_cols if c not in rows[0]]
        if missing_cols:
            FAIL(f"{fname} — missing columns: {missing_cols}")
        else:
            PASS(f"{fname} — {len(rows)} rows, required columns present")

    # ------- raw_material.csv checks -------
    rms = csv_data.get("raw_material.csv", [])
    if rms:
        ids = [r["rawmaterialid"].strip() for r in rms]
        dupes = [x for x in ids if ids.count(x) > 1]
        if dupes:
            FAIL(f"raw_material.csv — duplicate rawmaterialids: {set(dupes)}")
        else:
            PASS("raw_material.csv — no duplicate rawmaterialids")

        no_type = [r["rawmaterialid"] for r in rms if not r.get("type", "").strip()]
        if no_type:
            WARN(f"raw_material.csv — {len(no_type)} records with blank 'type': {no_type[:5]}")
        else:
            PASS("raw_material.csv — all records have 'type'")

        valid_types = {"PG", "RM", "PRM"}
        bad_type = [r["rawmaterialid"] for r in rms if r.get("type","").strip() not in valid_types and r.get("type","").strip()]
        if bad_type:
            WARN(f"raw_material.csv — unexpected type values: {set(r['type'] for r in rms if r['rawmaterialid'] in bad_type)}")

        pg_count = sum(1 for r in rms if r.get("type","").strip() == "PG")
        INFO(f"raw_material.csv — PG (pigment) type: {pg_count}, RM: {sum(1 for r in rms if r.get('type','').strip()=='RM')}, PRM: {sum(1 for r in rms if r.get('type','').strip()=='PRM')}")

        no_price = [r["rawmaterialid"] for r in rms if not r.get("current_price","").strip()]
        if len(no_price) > 20:
            WARN(f"raw_material.csv — {len(no_price)} records have no current_price")
        else:
            PASS(f"raw_material.csv — {len(rms)-len(no_price)}/{len(rms)} records have current_price")

    # ------- products.csv checks -------
    prods = csv_data.get("products.csv", [])
    if prods:
        prod_ids = [r["id"].strip() for r in prods]
        dupes = [x for x in prod_ids if prod_ids.count(x) > 1]
        if dupes:
            FAIL(f"products.csv — duplicate product ids: {set(dupes)}")
        else:
            PASS(f"products.csv — {len(prods)} products, no duplicates")

        no_name = [r["id"] for r in prods if not r.get("name","").strip()]
        if no_name:
            WARN(f"products.csv — {len(no_name)} products with no name: {no_name[:5]}")

    # ------- productrawmaterialmap.csv checks -------
    prm = csv_data.get("productrawmaterialmap.csv", [])
    if prm and rms and prods:
        rm_id_set   = {r["rawmaterialid"].strip() for r in rms}
        prod_id_set = {r["id"].strip() for r in prods}

        orphan_rm   = [r for r in prm if r["rawmaterialid"].strip() not in rm_id_set]
        orphan_prod = [r for r in prm if r["productid"].strip() not in prod_id_set]

        if orphan_rm:
            FAIL(f"productrawmaterialmap.csv — {len(orphan_rm)} recipe rows reference unknown RM IDs: "
                 f"{list(set(r['rawmaterialid'] for r in orphan_rm))[:8]}")
        else:
            PASS("productrawmaterialmap.csv — all rawmaterialids exist in raw_material.csv")

        if orphan_prod:
            FAIL(f"productrawmaterialmap.csv — {len(orphan_prod)} recipe rows reference unknown product IDs: "
                 f"{list(set(r['productid'] for r in orphan_prod))[:8]}")
        else:
            PASS("productrawmaterialmap.csv — all productids exist in products.csv")

        # Check for zero/negative quantities
        bad_qty = [r for r in prm if r.get("qtyinkg","").strip() and float(r["qtyinkg"].strip()) <= 0]
        if bad_qty:
            WARN(f"productrawmaterialmap.csv — {len(bad_qty)} recipe rows with qty ≤ 0")
        else:
            PASS("productrawmaterialmap.csv — all quantities > 0")

        # Check per-product recipe totals
        from collections import defaultdict
        prod_totals = defaultdict(float)
        for r in prm:
            try:
                prod_totals[r["productid"].strip()] += float(r["qtyinkg"].strip() or 0)
            except ValueError:
                pass

        zero_total = [pid for pid, tot in prod_totals.items() if tot < 0.01]
        if zero_total:
            WARN(f"productrawmaterialmap.csv — {len(zero_total)} products with recipe total < 0.01 kg: {zero_total[:5]}")
        else:
            PASS(f"productrawmaterialmap.csv — all {len(prod_totals)} products have recipe total > 0")

    # ------- lab_results.csv checks -------
    lab = csv_data.get("lab_results.csv", [])
    if lab and prods:
        prod_id_set = {r["id"].strip() for r in prods}
        orphan = [r for r in lab if str(r.get("product_id","")).strip() not in prod_id_set
                  and str(r.get("product_id","")).strip()]
        if orphan:
            WARN(f"lab_results.csv — {len(orphan)} rows reference unknown product IDs: "
                 f"{list(set(r['product_id'] for r in orphan))[:5]}")
        else:
            PASS(f"lab_results.csv — {len(lab)} rows, all product IDs valid")

        # Check LAB ranges
        bad_L = [r for r in lab if r.get("L","").strip() and not (0 <= float(r["L"]) <= 100)]
        bad_a = [r for r in lab if r.get("a","").strip() and not (-128 <= float(r["a"]) <= 128)]
        bad_b = [r for r in lab if r.get("b","").strip() and not (-128 <= float(r["b"]) <= 128)]
        if bad_L: FAIL(f"lab_results.csv — {len(bad_L)} rows with L* out of range [0,100]")
        else:     PASS("lab_results.csv — all L* values in [0, 100]")
        if bad_a: WARN(f"lab_results.csv — {len(bad_a)} rows with a* out of range [-128,128]")
        if bad_b: WARN(f"lab_results.csv — {len(bad_b)} rows with b* out of range [-128,128]")

    # ------- pigment_properties.csv cross-check -------
    pp   = csv_data.get("pigment_properties.csv", [])
    if pp and rms:
        rm_id_set = {r["rawmaterialid"].strip() for r in rms}
        PROPS_ID_MAP = {
            "YELLOW 114": "RM507",   "YELLOW 132K": "RM517",
            "YELLOW 2909": "RM515",  "YELLOW 2939 K": "RM512",
            "YELLOW 2925K": "RM510", "ORANGE 2917": "RM705",
            "ORANGE 212": "RM702",   "RED 5016": "RM307",
            "RED 570": "RM302",      "RED 2967K": "RM312",
            "RED 2985": "RM383",     "RED 635": "RM309",
            "RED 2991K": "RM310",    "BLUE 2789": "RM605",
            "GREEN 2730K": "RM401",  "YELLOW 162K": "RM503",
            "YELLOW 137K": "RM508",  "ORANGE 203K": "RM701",
            "RED 507K": "RM304",     "RED 2957K": "RM313",
            "RED 2963K": "RM311",    "RED 565": "RM300",
            "RED 587": "RM308",      "BLUE 2633K": "RM600",
        }
        unlinked = []
        for row in pp:
            pname = row["pigment_name"].strip()
            if pname in PROPS_ID_MAP:
                if PROPS_ID_MAP[pname] not in rm_id_set:
                    unlinked.append(f"{pname} → {PROPS_ID_MAP[pname]} (RM missing)")
            else:
                unlinked.append(f"{pname} (no PROPS_ID_MAP entry)")

        if unlinked:
            WARN(f"pigment_properties.csv — {len(unlinked)}/{len(pp)} entries won't link to any RM:")
            for u in unlinked:
                INFO(f"    {u}")
        else:
            PASS("pigment_properties.csv — all entries link to an RM")

    stocks = csv_data.get("stocks.csv", [])
    if stocks and rms:
        rm_id_set = {r["rawmaterialid"].strip() for r in rms}
        orphan_stocks = [s for s in stocks if s.get("rawmaterialid","").strip() not in rm_id_set]
        if orphan_stocks:
            WARN(f"stocks.csv — {len(orphan_stocks)}/{len(stocks)} stock rows use RM IDs not in "
                 f"raw_material.csv (stocks may use a different ID scheme). "
                 f"Samples: {list(set(s['rawmaterialid'] for s in orphan_stocks))[:5]}")
        else:
            PASS(f"stocks.csv — {len(stocks)} stock rows, all RM IDs valid")

    # ------- alphacode.csv checks -------
    ac = csv_data.get("alphacode.csv", [])
    if ac:
        # product_code in alphacode.csv is a range pattern (e.g. '10XXX'), not a direct FK
        PASS(f"alphacode.csv — {len(ac)} rows loaded (product_code is a pattern, not a direct FK)")


# ============================================================
# 2.  DATABASE CHECKS
# ============================================================

def check_db():
    SECTION("2. Database Integrity")

    db_path = os.path.join(WORKSPACE, "surya.db")
    if not os.path.exists(db_path):
        FAIL(f"surya.db not found at {db_path} — run import_data.py first")
        return

    PASS(f"surya.db found ({os.path.getsize(db_path) // 1024} KB)")

    try:
        from app import create_app
        from models.database import (
            db, RawMaterial, Product, ProductSpec,
            ProductRawMaterialMap, AlphaCode, RalPantoneShade,
            Stock, LabResult, ClientProductMapping
        )

        app = create_app()
        with app.app_context():
            _check_db_inner(
                RawMaterial, Product, ProductSpec,
                ProductRawMaterialMap, AlphaCode, RalPantoneShade,
                Stock, LabResult, ClientProductMapping
            )
    except Exception as exc:
        FAIL(f"Could not load Flask app for DB checks: {exc}")


def _check_db_inner(RawMaterial, Product, ProductSpec,
                    ProductRawMaterialMap, AlphaCode, RalPantoneShade,
                    Stock, LabResult, ClientProductMapping):

    # --- Row counts ---
    counts = {
        "RawMaterial":           RawMaterial.query.count(),
        "Product":               Product.query.count(),
        "ProductSpec":           ProductSpec.query.count(),
        "ProductRawMaterialMap": ProductRawMaterialMap.query.count(),
        "Stock":                 Stock.query.count(),
        "LabResult":             LabResult.query.count(),
        "AlphaCode":             AlphaCode.query.count(),
        "RalPantoneShade":       RalPantoneShade.query.count(),
    }
    for tbl, cnt in counts.items():
        if cnt == 0:
            WARN(f"DB table {tbl} is EMPTY")
        else:
            INFO(f"DB {tbl}: {cnt} rows")

    # --- Cross-check DB vs CSV row counts ---
    csv_counts = {}
    for fname, col in [
        ("raw_material.csv", "rawmaterialid"),
        ("products.csv", "id"),
        ("productrawmaterialmap.csv", "productid"),
        ("lab_results.csv", "productid"),
        ("stocks.csv", "rawmaterialid"),
    ]:
        fpath = os.path.join(WORKSPACE, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                csv_counts[fname] = sum(1 for _ in csv.DictReader(f))

    csv_db_map = [
        ("raw_material.csv",         counts["RawMaterial"]),
        ("products.csv",             counts["Product"]),
        ("productrawmaterialmap.csv",counts["ProductRawMaterialMap"]),
        ("lab_results.csv",          counts["LabResult"]),
        ("stocks.csv",               counts["Stock"]),
    ]
    for fname, db_cnt in csv_db_map:
        csv_cnt = csv_counts.get(fname)
        if csv_cnt is None:
            continue
        # DB may have more rows than CSV (Lab stubs, extra data)
        if abs(db_cnt - csv_cnt) <= 5:
            PASS(f"Row count match: {fname} CSV={csv_cnt} DB={db_cnt}")
        elif db_cnt > csv_cnt:
            INFO(f"Row count: {fname} CSV={csv_cnt} DB={db_cnt} (DB has extra rows — likely stubs/imports)")
        else:
            FAIL(f"Row count MISMATCH: {fname} CSV={csv_cnt} DB={db_cnt} — re-run import_data.py")

    # --- Foreign key orphans ---
    all_rm_ids  = {rm.rawmaterialid for rm in RawMaterial.query.all()}
    all_prod_ids= {p.id for p in Product.query.all()}

    orphan_recipe = ProductRawMaterialMap.query.filter(
        ~ProductRawMaterialMap.rawmaterialid.in_(list(all_rm_ids))
    ).count()
    if orphan_recipe:
        FAIL(f"DB: {orphan_recipe} recipe rows reference non-existent rawmaterialid")
    else:
        PASS("DB: all recipe rows have valid rawmaterialid FK")

    orphan_lab = LabResult.query.filter(
        ~LabResult.product_id.in_(list(all_prod_ids))
    ).count()
    if orphan_lab:
        FAIL(f"DB: {orphan_lab} LabResult rows reference non-existent product_id")
    else:
        PASS("DB: all LabResult rows have valid product_id FK")

    orphan_spec = ProductSpec.query.filter(
        ~ProductSpec.product_id.in_(list(all_prod_ids))
    ).count()
    if orphan_spec:
        WARN(f"DB: {orphan_spec} ProductSpec rows reference non-existent product_id")
    else:
        PASS("DB: all ProductSpec rows have valid product_id FK")

    # --- LAB data coverage ---
    pg_rms = RawMaterial.query.filter_by(type="PG").all()
    pg_with_lab   = [rm for rm in pg_rms if rm.full_tone_L is not None]
    pg_with_tint  = [rm for rm in pg_rms if rm.tint_tone_L is not None]
    pg_stubs      = [rm for rm in pg_rms if rm.rawmaterialid.startswith("LAB_")]

    INFO(f"DB: PG pigments total={len(pg_rms)}, with full-tone LAB={len(pg_with_lab)}, "
         f"with tint-tone LAB={len(pg_with_tint)}, LAB stubs={len(pg_stubs)}")

    if len(pg_with_lab) == 0:
        FAIL("DB: No PG pigments have LAB data — K-M predictions will fail entirely")
    elif len(pg_with_lab) < 10:
        WARN(f"DB: Only {len(pg_with_lab)} PG pigments have LAB data — limited K-M coverage")
    else:
        PASS(f"DB: {len(pg_with_lab)} PG pigments have full-tone LAB data")

    # Check for implausible LAB values
    bad_lab = []
    for rm in pg_with_lab:
        if not (0 <= (rm.full_tone_L or 0) <= 100):
            bad_lab.append(f"{rm.rawmaterialid}: L={rm.full_tone_L}")
        if not (-128 <= (rm.full_tone_a or 0) <= 128):
            bad_lab.append(f"{rm.rawmaterialid}: a={rm.full_tone_a}")
        if not (-128 <= (rm.full_tone_b or 0) <= 128):
            bad_lab.append(f"{rm.rawmaterialid}: b={rm.full_tone_b}")
        if rm.tint_tone_L and not (0 <= rm.tint_tone_L <= 100):
            bad_lab.append(f"{rm.rawmaterialid}: tint_L={rm.tint_tone_L}")
    if bad_lab:
        FAIL(f"DB: {len(bad_lab)} LAB values out of valid range:")
        for b in bad_lab[:10]:
            INFO(f"    {b}")
    else:
        PASS("DB: all LAB values within valid ranges")

    # Check tint tone is lighter than full tone (should be — it's diluted with TiO2)
    tint_darker = []
    for rm in pg_rms:
        if rm.full_tone_L is not None and rm.tint_tone_L is not None:
            if rm.tint_tone_L < rm.full_tone_L - 5:
                tint_darker.append(f"{rm.rawmaterialid}: full_L={rm.full_tone_L:.1f} tint_L={rm.tint_tone_L:.1f}")
    if tint_darker:
        WARN(f"DB: {len(tint_darker)} pigments where tint_L is significantly DARKER than full_L (unexpected):")
        for t in tint_darker[:8]:
            INFO(f"    {t}")
    else:
        PASS("DB: tint tone is lighter than full tone for all pigments (as expected)")

    # --- Recipes with zero or near-zero total kg ---
    from sqlalchemy import func
    recipe_totals = (
        ProductRawMaterialMap.query
        .with_entities(
            ProductRawMaterialMap.productid,
            func.sum(ProductRawMaterialMap.qtyinkg).label("total")
        )
        .group_by(ProductRawMaterialMap.productid)
        .all()
    )
    zero_recipes = [(pid, tot) for pid, tot in recipe_totals if (tot or 0) < 0.01]
    if zero_recipes:
        WARN(f"DB: {len(zero_recipes)} products have recipe total < 0.01 kg: {[pid for pid, _ in zero_recipes[:5]]}")
    else:
        PASS(f"DB: {len(recipe_totals)} products have recipe total > 0")

    # --- Products with no recipe ---
    products_with_recipe = {pid for pid, _ in recipe_totals}
    all_products = all_prod_ids
    no_recipe = all_products - products_with_recipe
    if no_recipe:
        INFO(f"DB: {len(no_recipe)} products have NO recipe (may be raw material master items)")
    else:
        PASS("DB: all products have at least one recipe row")

    # --- LabResult LAB ranges ---
    bad_lr = []
    for lr in LabResult.query.all():
        if not (0 <= (lr.L or 0) <= 100):
            bad_lr.append(f"id={lr.id} product={lr.product_id} L={lr.L}")
        if not (-128 <= (lr.a or 0) <= 128):
            bad_lr.append(f"id={lr.id} product={lr.product_id} a={lr.a}")
        if not (-128 <= (lr.b or 0) <= 128):
            bad_lr.append(f"id={lr.id} product={lr.product_id} b={lr.b}")
    if bad_lr:
        FAIL(f"DB: {len(bad_lr)} LabResult rows with out-of-range LAB:")
        for b in bad_lr[:5]:
            INFO(f"    {b}")
    else:
        PASS("DB: all LabResult L/a/b values in valid range")

    # --- Polymer values in LabResult ---
    known_polymers = {"PE", "PP", "ABS", "SAN", "PVC", "OTHER"}
    bad_poly = LabResult.query.filter(~LabResult.polymer.in_(list(known_polymers))).all()
    if bad_poly:
        unusual = set(lr.polymer for lr in bad_poly)
        WARN(f"DB: {len(bad_poly)} LabResult rows with unexpected polymer values: {unusual}")
    else:
        PASS("DB: all LabResult polymer values are recognised")

    # --- TiO2 detection preview ---
    from services.ml_engine import TIO2_CHEM_KEYWORDS
    tio2_rms = [rm for rm in RawMaterial.query.all()
                if any(kw in (rm.chemical_name or "").upper() for kw in TIO2_CHEM_KEYWORDS)
                   or "TT " in (rm.rawmaterialname or "").upper()]
    if tio2_rms:
        PASS(f"DB: {len(tio2_rms)} raw materials identified as TiO2/white: "
             f"{[rm.rawmaterialid for rm in tio2_rms[:6]]}")
    else:
        FAIL("DB: No TiO2 materials identified — TiO2 fraction model cannot train")

    # --- CI name / chemistry coverage ---
    pg_with_ci = [rm for rm in pg_rms if rm.ci_name]
    INFO(f"DB: {len(pg_with_ci)}/{len(pg_rms)} PG pigments have CI name")
    pg_with_chem = [rm for rm in pg_rms if rm.chemistry]
    INFO(f"DB: {len(pg_with_chem)}/{len(pg_rms)} PG pigments have chemistry")


# ============================================================
# 3.  COLOR ENGINE MATH
# ============================================================

def check_color():
    SECTION("3. Color Engine Math")

    try:
        from services.color_engine import (
            lab_to_xyz, xyz_to_lab, xyz_to_reflectance, reflectance_to_xyz,
            ks_from_reflectance, reflectance_from_ks,
            lab_to_ks, ks_to_lab,
            predict_mixture_lab, delta_e_cie2000, delta_e_cie76, hex_to_lab,
            Pigment, _TIO2_KS
        )
    except ImportError as e:
        FAIL(f"Cannot import color_engine: {e}")
        return

    # --- LAB → XYZ → LAB roundtrip ---
    test_labs = [
        (50.0,  0.0,   0.0,   "neutral gray"),
        (30.0, 60.0,  20.0,   "saturated red"),
        (90.0, -10.0, 80.0,   "bright yellow"),
        (20.0, 30.0, -60.0,   "dark blue-purple"),
        (100.0, 0.0,   0.0,   "paper white"),
        (0.0,   0.0,   0.0,   "absolute black"),
    ]
    all_ok = True
    for L, a, b, label in test_labs:
        X, Y, Z = lab_to_xyz(L, a, b)
        Lr, ar, br = xyz_to_lab(X, Y, Z)
        if not (approx_equal(L, Lr, 0.05) and approx_equal(a, ar, 0.05) and approx_equal(b, br, 0.05)):
            FAIL(f"LAB→XYZ→LAB roundtrip failed for {label}: ({L},{a},{b}) → ({Lr:.3f},{ar:.3f},{br:.3f})")
            all_ok = False
    if all_ok:
        PASS("LAB→XYZ→LAB roundtrip: all 6 test cases within 0.05 tolerance")

    # --- K/S ↔ Reflectance roundtrip ---
    ks_ok = True
    for R_in in [0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99]:
        ks = ks_from_reflectance(R_in)
        R_out = reflectance_from_ks(ks)
        if not approx_equal(R_in, R_out, 0.001):
            FAIL(f"K/S roundtrip failed: R={R_in} → K/S={ks:.4f} → R={R_out:.4f}")
            ks_ok = False
    if ks_ok:
        PASS("K/S ↔ Reflectance roundtrip: 7 test values within 0.001 tolerance")

    # --- K/S formula checks ---
    # At R=1 (perfect white), K/S should be 0
    ks_white = ks_from_reflectance(0.999)
    if ks_white < 0.001:
        PASS(f"K/S at near-white (R=0.999) ≈ 0: {ks_white:.6f}")
    else:
        FAIL(f"K/S at near-white should be ~0, got {ks_white:.4f}")

    # At R=0.5, K/S = (0.5)^2 / (2*0.5) = 0.25
    ks_half = ks_from_reflectance(0.5)
    if approx_equal(ks_half, 0.25, 0.001):
        PASS(f"K/S at R=0.5: expected 0.25, got {ks_half:.4f}")
    else:
        FAIL(f"K/S at R=0.5: expected 0.25, got {ks_half:.4f}")

    # --- TiO2 K/S module constant ---
    if _TIO2_KS is not None and len(_TIO2_KS) == 3:
        if all(k >= 0 for k in _TIO2_KS):
            PASS(f"TiO2 K/S constant is non-negative: {tuple(round(k,4) for k in _TIO2_KS)}")
        else:
            FAIL(f"TiO2 K/S constant has negative values: {_TIO2_KS}")
    else:
        FAIL("TiO2 K/S constant not defined or wrong shape")

    # --- LAB → K/S → LAB roundtrip ---
    ks_lab_ok = True
    for L, a, b, label in test_labs[1:4]:  # skip extreme white/black
        ks_r, ks_g, ks_b = lab_to_ks(L, a, b)
        Lr, ar, br = ks_to_lab(ks_r, ks_g, ks_b)
        if not (approx_equal(L, Lr, 1.0) and approx_equal(a, ar, 2.0) and approx_equal(b, br, 2.0)):
            WARN(f"LAB→K/S→LAB roundtrip has drift for {label}: "
                 f"({L},{a},{b}) → ({Lr:.2f},{ar:.2f},{br:.2f}) "
                 f"ΔL={abs(L-Lr):.2f} Δa={abs(a-ar):.2f} Δb={abs(b-br):.2f}")
            ks_lab_ok = False
    if ks_lab_ok:
        PASS("LAB→K/S→LAB roundtrip: within tolerance for typical colors")

    # --- predict_mixture_lab: pure TiO2 → near white ---
    try:
        # TiO2 pure: tint is ~L=99, a=0, b=1.5  (same as the module constant)
        tio2_pig = Pigment("TIO2", full_L=99.0, full_a=0.0, full_b=1.5,
                                    tint_L=99.0, tint_a=0.0, tint_b=1.5)
        Lm, am, bm = predict_mixture_lab([(tio2_pig, 0.9)], tio2_conc=0.0)
        if Lm > 80:
            PASS(f"predict_mixture_lab with TiO2-like pigment → L={Lm:.1f} (near white, expected)")
        else:
            WARN(f"predict_mixture_lab with TiO2-like pigment → L={Lm:.1f} (expected >80)")
    except Exception as e:
        FAIL(f"predict_mixture_lab (TiO2 test) raised exception: {e}")

    # --- predict_mixture_lab: blue pigment → should shift b* strongly negative ---
    try:
        blue_pig = Pigment("TESTBLUE", full_L=30.0, full_a=-5.0, full_b=-50.0,
                                        tint_L=70.0, tint_a=-3.0, tint_b=-30.0)
        Lm, am, bm = predict_mixture_lab([(blue_pig, 0.05)], tio2_conc=0.3)
        if bm < 0:
            PASS(f"predict_mixture_lab blue+TiO2 → b*={bm:.1f} (negative, correct for blue)")
        else:
            WARN(f"predict_mixture_lab blue+TiO2 → b*={bm:.1f} (expected negative)")
    except Exception as e:
        FAIL(f"predict_mixture_lab (blue test) raised exception: {e}")

    # --- predict_mixture_lab: yellow pigment → b* positive ---
    try:
        yel_pig = Pigment("TESTYEL", full_L=80.0, full_a=5.0, full_b=80.0,
                                      tint_L=92.0, tint_a=2.0, tint_b=40.0)
        Lm, am, bm = predict_mixture_lab([(yel_pig, 0.03)], tio2_conc=0.25)
        if bm > 0:
            PASS(f"predict_mixture_lab yellow+TiO2 → b*={bm:.1f} (positive, correct for yellow)")
        else:
            WARN(f"predict_mixture_lab yellow+TiO2 → b*={bm:.1f} (expected positive)")
    except Exception as e:
        FAIL(f"predict_mixture_lab (yellow test) raised exception: {e}")

    # --- CIEDE2000 ---
    # Same color → ΔE = 0
    dE_same = delta_e_cie2000((50.0, 30.0, -20.0), (50.0, 30.0, -20.0))
    if approx_equal(dE_same, 0.0, 0.001):
        PASS(f"CIEDE2000: same color → ΔE={dE_same:.4f} (expected 0)")
    else:
        FAIL(f"CIEDE2000: same color → ΔE={dE_same:.4f} (should be 0)")

    # Known reference pair from Sharma 2005 Table 1 pair 1:
    # Lab1=(50.0, 2.6772, -79.7751) Lab2=(50.0, 0.0, -82.7485) → ΔE≈2.0425
    dE_ref = delta_e_cie2000((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485))
    if approx_equal(dE_ref, 2.0425, 0.01):
        PASS(f"CIEDE2000 Sharma (2005) test pair: ΔE={dE_ref:.4f} (expected ≈2.0425)")
    else:
        FAIL(f"CIEDE2000 Sharma (2005) test pair: ΔE={dE_ref:.4f} (expected ≈2.0425)")

    # Sharma pair 2: Lab1=(50,3.1571,-77.2803) Lab2=(50,0,-82.7485) → ΔE≈2.8615
    dE_ref2 = delta_e_cie2000((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485))
    if approx_equal(dE_ref2, 2.8615, 0.01):
        PASS(f"CIEDE2000 Sharma (2005) pair 2: ΔE={dE_ref2:.4f} (expected ≈2.8615)")
    else:
        FAIL(f"CIEDE2000 Sharma (2005) pair 2: ΔE={dE_ref2:.4f} (expected ≈2.8615)")

    # ΔE76 vs ΔE2000: 2000 should be ≤ 76 in most cases for small differences
    dE76 = delta_e_cie76((60.0, 10.0, 10.0), (62.0, 11.0, 9.0))
    dE00 = delta_e_cie2000((60.0, 10.0, 10.0), (62.0, 11.0, 9.0))
    INFO(f"ΔE76={dE76:.3f} vs ΔE2000={dE00:.3f} for a small color shift (both should be small)")

    # --- hex_to_lab ---
    # #FF0000 (sRGB red) → known approximate LAB: L≈53, a≈80, b≈67
    lab_red = hex_to_lab("#FF0000")
    if lab_red:
        L, a, b = lab_red
        if 40 < L < 60 and 60 < a < 100 and 40 < b < 80:
            PASS(f"hex_to_lab('#FF0000') → L={L:.1f} a={a:.1f} b={b:.1f} (correct range for sRGB red)")
        else:
            FAIL(f"hex_to_lab('#FF0000') → L={L:.1f} a={a:.1f} b={b:.1f} (out of expected range)")
    else:
        FAIL("hex_to_lab('#FF0000') returned None")

    # White → L≈100
    lab_white = hex_to_lab("#FFFFFF")
    if lab_white and approx_equal(lab_white[0], 100.0, 1.0):
        PASS(f"hex_to_lab('#FFFFFF') → L={lab_white[0]:.1f} (near 100, correct)")
    else:
        FAIL(f"hex_to_lab('#FFFFFF') failed or L not near 100: {lab_white}")

    # Black → L≈0
    lab_black = hex_to_lab("#000000")
    if lab_black and approx_equal(lab_black[0], 0.0, 1.0):
        PASS(f"hex_to_lab('#000000') → L={lab_black[0]:.1f} (near 0, correct)")
    else:
        FAIL(f"hex_to_lab('#000000') failed or L not near 0: {lab_black}")


# ============================================================
# 4.  ML MODEL CHECKS
# ============================================================

def check_ml():
    SECTION("4. ML Model — Feature Engineering & Training")

    # --- 4a. Feature vector structure ---
    try:
        from services.ml_engine import _feature_vector, _poly_onehot, POLYMERS, MIN_SAMPLES
    except ImportError as e:
        FAIL(f"Cannot import ml_engine: {e}")
        return

    fv = _feature_vector(50.0, 0.0, 0.0, "PP")
    if len(fv) == 12:
        PASS(f"Feature vector is 12-dimensional (correct)")
    else:
        FAIL(f"Feature vector is {len(fv)}-dimensional (expected 12)")

    # Normalisation checks
    L_feat = fv[0]
    if approx_equal(L_feat, 0.5, 0.001):
        PASS(f"Feature[0] (L*/100): L=50 → {L_feat:.3f} (expected 0.5)")
    else:
        FAIL(f"Feature[0] (L*/100): L=50 → {L_feat:.3f} (expected 0.5)")

    # a* = 0 → feature[1] = 0
    if approx_equal(fv[1], 0.0, 0.001):
        PASS(f"Feature[1] (a*/128): a=0 → {fv[1]:.3f} (expected 0)")
    else:
        FAIL(f"Feature[1] (a*/128): a=0 → {fv[1]:.3f} (expected 0)")

    # Chroma check: a=0, b=0 → C=0 → feature[3]=0
    fv_achrom = _feature_vector(50.0, 0.0, 0.0, "PE")
    if approx_equal(fv_achrom[3], 0.0, 0.001):
        PASS(f"Feature[3] (C*/181): achromatic → {fv_achrom[3]:.3f} (expected 0)")
    else:
        FAIL(f"Feature[3] (C*/181): achromatic → {fv_achrom[3]:.3f} (expected 0)")

    # --- Polymer one-hot ---
    for poly in POLYMERS:
        oh = _poly_onehot(poly)
        if len(oh) == len(POLYMERS):
            PASS(f"One-hot {poly}: length={len(oh)}, sum={sum(oh)} (expected 1)")
        else:
            FAIL(f"One-hot {poly}: wrong length {len(oh)}")
        if sum(oh) != 1:
            FAIL(f"One-hot {poly}: sum={sum(oh)} should be 1")

    oh_unknown = _poly_onehot("UNKNOWN")
    if sum(oh_unknown) == 0:
        PASS("One-hot for unknown polymer is all-zeros (correct)")
    else:
        FAIL(f"One-hot for unknown polymer has sum={sum(oh_unknown)} (should be 0)")

    # --- Hue encoding (sin/cos) ---
    # b=0, a=1 → hue=0 → sin=0, cos=1
    fv_hue = _feature_vector(50.0, 64.0, 0.0, "PE")  # a>0, b=0 → hue=0
    if approx_equal(fv_hue[4], 0.0, 0.01):
        PASS(f"Feature[4] (sin hue): a=64, b=0 → sin≈0: {fv_hue[4]:.3f}")
    else:
        FAIL(f"Feature[4] (sin hue): a=64, b=0 → should be sin(0)=0, got {fv_hue[4]:.3f}")
    if approx_equal(fv_hue[5], 1.0, 0.01):
        PASS(f"Feature[5] (cos hue): a=64, b=0 → cos≈1: {fv_hue[5]:.3f}")
    else:
        FAIL(f"Feature[5] (cos hue): a=64, b=0 → should be cos(0)=1, got {fv_hue[5]:.3f}")

    # a=0, b=64 → hue=90° → sin=1, cos≈0
    fv_hue90 = _feature_vector(50.0, 0.0, 64.0, "PE")
    if approx_equal(fv_hue90[4], 1.0, 0.01):
        PASS(f"Feature[4] (sin hue): a=0, b=64 → sin≈1: {fv_hue90[4]:.3f}")
    else:
        FAIL(f"Feature[4] (sin hue): a=0, b=64 → should be 1, got {fv_hue90[4]:.3f}")

    # --- MIN_SAMPLES ---
    INFO(f"ML: MIN_SAMPLES = {MIN_SAMPLES} (minimum recipe appearances per pigment to train)")

    # --- 4b. Train model and inspect ---
    SECTION("4b. ML Model Training & Prediction")

    db_path = os.path.join(WORKSPACE, "surya.db")
    if not os.path.exists(db_path):
        WARN("surya.db not found — skipping model training checks")
        return

    try:
        from app import create_app
        from services.ml_engine import MLRecipeModel, get_ml_status, TIO2_CHEM_KEYWORDS
    except ImportError as e:
        FAIL(f"Cannot import app/ml_engine: {e}")
        return

    try:
        app = create_app()
        with app.app_context():
            _check_ml_inner(MLRecipeModel, app)
    except Exception as exc:
        FAIL(f"Could not start Flask app for ML checks: {exc}")
        import traceback; traceback.print_exc()


def _check_ml_inner(MLRecipeModel, app):
    model = MLRecipeModel()

    INFO("Training ML model synchronously (this may take 10–60 seconds)…")
    t0 = time.time()
    with app.app_context():
        model._train(app)
    elapsed = time.time() - t0
    INFO(f"Training took {elapsed:.1f}s")

    if not model.is_trained:
        err = model._training_error or "unknown"
        FAIL(f"ML model did NOT train successfully: {err}")
        return
    PASS("ML model trained successfully")

    # --- Corpus stats ---
    cs = model.stats.get("corpus_size", 0)
    tp = model.stats.get("trainable_pigments", 0)
    INFO(f"ML corpus_size = {cs}")
    INFO(f"ML trainable_pigments = {tp}")

    if cs < 5:
        FAIL(f"Corpus too small: {cs} samples (need ≥ 5). Add more products with recipes.")
    elif cs < 50:
        WARN(f"Corpus is small ({cs} samples) — ML predictions may be unreliable")
    else:
        PASS(f"Corpus size {cs} is adequate")

    if tp == 0:
        FAIL("No trainable pigments — no per-pigment model was trained")
    elif tp < 5:
        WARN(f"Only {tp} pigments trained — very limited prediction capability")
    else:
        PASS(f"{tp} pigments have trained classifiers/regressors")

    clf_count = len(model._pig_clf)
    reg_count = len(model._pig_reg)
    INFO(f"ML: {clf_count} RandomForest classifiers, {reg_count} GradientBoosting regressors")

    if clf_count != reg_count:
        WARN(f"Classifier count ({clf_count}) ≠ regressor count ({reg_count}) — "
             "some pigments have no concentration predictor")

    if model._tio2_reg:
        PASS("TiO2 fraction GradientBoosting model trained")
    else:
        WARN("TiO2 fraction model NOT trained (need ≥ 5 samples with TiO2 in recipe)")

    # --- TiO2 RM set ---
    if model._tio2_rm_ids:
        PASS(f"TiO2 raw material IDs detected: {list(model._tio2_rm_ids)[:8]}")
    else:
        FAIL("No TiO2 raw materials detected by ML engine")

    # --- Predictions ---
    test_cases = [
        (50.0,  0.0,   0.0,  "PP", "achromatic mid-gray"),
        (90.0, -5.0,  85.0,  "PE", "bright yellow"),
        (30.0, 55.0,  25.0,  "ABS","saturated red"),
        (40.0, -10.0,-30.0,  "PP", "blue-green"),
    ]

    for L, a, b, poly, label in test_cases:
        try:
            results = model.predict(L, a, b, poly)
            if not results:
                WARN(f"Predict({label}): returned empty list (model may lack data for this colour)")
                continue
            r0 = results[0]
            # Check structure
            has_pigments = "pigment_system" in r0 or "colorants" in r0
            if not has_pigments:
                WARN(f"Predict({label}): result missing 'pigment_system' key. Keys: {list(r0.keys())}")
            # Check delta_e if present
            de = r0.get("predicted_delta_e")
            if de is not None:
                if de < 0:
                    FAIL(f"Predict({label}): predicted_delta_e={de:.2f} is negative (impossible)")
                elif de > 30:
                    WARN(f"Predict({label}): predicted_delta_e={de:.2f} is very high (>30) — poor suggestion quality")
                else:
                    PASS(f"Predict({label}): {len(results)} suggestion(s), ΔE={de:.2f}")
            else:
                PASS(f"Predict({label}): {len(results)} suggestion(s) returned")
        except Exception as e:
            FAIL(f"Predict({label}): exception → {e}")

    # --- Concentration sanity ---
    try:
        preds = model.predict(50.0, 0.0, 0.0, "PP")
        for i, pred in enumerate(preds):
            ps = pred.get("pigment_system", [])
            for item in ps:
                pct = item.get("percentage", 0)
                if pct < 0:
                    FAIL(f"Prediction {i+1}: pigment {item.get('name')} has negative percentage {pct}%")
                elif pct > 50:
                    WARN(f"Prediction {i+1}: pigment {item.get('name')} has very high percentage {pct}%")
            total_pct = sum(item.get("percentage", 0) for item in ps)
            tio2_pct = pred.get("tio2_percentage", 0)
            grand = total_pct + tio2_pct
            if grand > 0:
                INFO(f"Prediction {i+1}: colorants={total_pct:.2f}% + TiO2={tio2_pct:.2f}% = {grand:.2f}%")
    except Exception as e:
        WARN(f"Concentration sanity check: {e}")

    # --- Pigment metadata completeness ---
    meta_no_lab = [pid for pid, m in model._pig_meta.items() if m.get("full_tone_L") is None]
    meta_total  = len(model._pig_meta)
    if meta_no_lab:
        WARN(f"ML meta: {len(meta_no_lab)}/{meta_total} trained pigments have NO LAB data "
             "(K-M ΔE prediction will not work for these). IDs: "
             + str(meta_no_lab[:8]))
    else:
        PASS(f"ML meta: all {meta_total} trained pigments have LAB data")

    # --- Polymer coverage per pigment ---
    mono_poly = {pid: m for pid, m in model._pig_meta.items()
                 if len(m.get("polymer_counts", {})) == 1}
    if mono_poly:
        WARN(f"ML: {len(mono_poly)}/{meta_total} pigments trained on only 1 polymer type "
             f"— predictions for other polymers will extrapolate blindly")
    else:
        PASS(f"ML: all pigments trained on ≥2 polymer types")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Surya Masterbatch system debug")
    parser.add_argument("--section", choices=["csv", "db", "color", "ml", "all"],
                        default="all", help="Which section to run")
    args = parser.parse_args()
    s = args.section

    print("\nSurya Masterbatch — Full System Debug")
    print("=" * 60)

    if s in ("csv", "all"):  check_csv()
    if s in ("db",  "all"):  check_db()
    if s in ("color","all"): check_color()
    if s in ("ml",  "all"):  check_ml()

    SECTION("Summary")
    total = _pass + _fail + _warn
    print(f"  PASS: {_pass}   FAIL: {_fail}   WARN: {_warn}   TOTAL: {total}")
    if _fail == 0:
        print("\n  All checks passed (with warnings noted above).")
    else:
        print(f"\n  {_fail} check(s) FAILED — review above for details.")
    print()


if __name__ == "__main__":
    main()
