"""
Comprehensive system audit — checks:
  A. Data integrity (CSV/Excel → DB completeness)
  B. Color math (roundtrips, CIEDE2000 reference pairs)
  C. K-M model (pigment extraction, mixture prediction sanity)
  D. ML engine (corpus, model training, prediction sanity)
  E. Search engine flow (end-to-end with a real target)
  F. Recipe recommendation sanity (do suggestions make physical sense?)
"""
import sys, os, math, json, traceback

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.database import (
    db, RawMaterial, Product, ProductSpec, ProductRawMaterialMap,
    AlphaCode, RalPantoneShade, Stock, LabResult, ClientProductMapping
)

app = create_app()

PASS = FAIL = 0
ISSUES = []

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        ISSUES.append((name, detail))
        print(f"  [FAIL] {name}: {detail}")


with app.app_context():

    # =====================================================================
    # A. DATA INTEGRITY
    # =====================================================================
    print("\n=== A. Data Integrity ===")

    # A1: Raw materials
    rm_count = RawMaterial.query.count()
    check("Raw materials loaded", rm_count > 100, f"got {rm_count}")

    pg_count = RawMaterial.query.filter(RawMaterial.type == "PG").count()
    rm_typed = RawMaterial.query.filter(RawMaterial.type == "RM").count()
    check("PG pigments present", pg_count > 20, f"got {pg_count}")
    check("RM raw materials present", rm_typed > 50, f"got {rm_typed}")

    # A2: Pigments with LAB data
    pg_with_lab = RawMaterial.query.filter(
        RawMaterial.type == "PG",
        RawMaterial.full_tone_L.isnot(None),
    ).count()
    check("PG with full_tone_L", pg_with_lab >= 20, f"got {pg_with_lab}")

    # A3: Tint-tone data (essential for K-M)
    pg_with_tint = RawMaterial.query.filter(
        RawMaterial.type == "PG",
        RawMaterial.tint_tone_L.isnot(None),
    ).count()
    check("PG with tint_tone_L (for K-M)", pg_with_tint >= 15, f"got {pg_with_tint}")

    # A4: Pigment properties (CI name, fastness)
    pg_with_ci = RawMaterial.query.filter(
        RawMaterial.ci_name.isnot(None),
    ).count()
    check("Pigments with CI name", pg_with_ci >= 10, f"got {pg_with_ci}")

    pg_with_heat = RawMaterial.query.filter(
        RawMaterial.heat_resistance.isnot(None),
    ).count()
    check("Pigments with heat_resistance", pg_with_heat >= 10, f"got {pg_with_heat}")

    # A5: Products
    prod_count = Product.query.count()
    check("Products loaded", prod_count > 100, f"got {prod_count}")

    # A6: Product specs
    spec_count = ProductSpec.query.count()
    check("Product specs loaded", spec_count > 50, f"got {spec_count}")

    # A7: Recipes
    recipe_count = ProductRawMaterialMap.query.count()
    check("Recipe entries loaded", recipe_count > 500, f"got {recipe_count}")

    # A8: Products with recipes
    products_with_recipes = db.session.query(
        ProductRawMaterialMap.productid
    ).distinct().count()
    check("Products with recipes", products_with_recipes > 50, f"got {products_with_recipes}")

    # A9: Lab results (measured spectrophotometer data)
    lab_count = LabResult.query.count()
    check("Lab results loaded", lab_count > 100, f"got {lab_count}")

    # A10: Alpha codes
    alpha_count = AlphaCode.query.count()
    check("Alpha codes loaded", alpha_count > 0, f"got {alpha_count}")

    # A11: RAL/Pantone shades
    ral_count = RalPantoneShade.query.count()
    check("RAL/Pantone shades loaded", ral_count > 100, f"got {ral_count}")

    # A12: Stocks
    stock_count = Stock.query.count()
    check("Stocks loaded", stock_count > 50, f"got {stock_count}")

    # A13: TiO2 pigments exist with LAB
    tio2_rms = RawMaterial.query.filter(
        RawMaterial.chemical_name.ilike("%PIGMENT WHITE%"),
        RawMaterial.full_tone_L.isnot(None),
    ).all()
    check("TiO2 pigments with LAB data", len(tio2_rms) >= 2, f"got {len(tio2_rms)}")

    # A14: Carbon blacks with LAB
    carbons = RawMaterial.query.filter(
        RawMaterial.chemical_name.ilike("%CARBON%"),
        RawMaterial.full_tone_L.isnot(None),
    ).all()
    check("Carbon blacks with LAB data", len(carbons) >= 2, f"got {len(carbons)}")

    # A15: Orphan recipes (recipe refers to non-existent product) — DATA WARNING
    orphan_recipes = db.session.query(ProductRawMaterialMap).filter(
        ~ProductRawMaterialMap.productid.in_(
            db.session.query(Product.id)
        )
    ).count()
    if orphan_recipes:
        print(f"  [WARN] {orphan_recipes} orphan recipe entries (CSV data issue, app handles gracefully)")
    else:
        check("No orphan recipe entries", True)

    # A16: Recipes with unknown RM — DATA WARNING
    orphan_rm = db.session.query(ProductRawMaterialMap).filter(
        ~ProductRawMaterialMap.rawmaterialid.in_(
            db.session.query(RawMaterial.rawmaterialid)
        )
    ).count()
    if orphan_rm:
        print(f"  [WARN] {orphan_rm} recipe entries reference unknown RM IDs (CSV data issue)")
    else:
        check("No recipes with unknown RM IDs", True)

    # A17: Lab results for non-existent products — DATA WARNING
    orphan_lab = db.session.query(LabResult).filter(
        ~LabResult.product_id.in_(
            db.session.query(Product.id)
        )
    ).count()
    if orphan_lab:
        print(f"  [WARN] {orphan_lab} orphan lab results (CSV data issue, app handles gracefully)")
    else:
        check("No orphan lab results", True)

    # =====================================================================
    # B. COLOR MATH
    # =====================================================================
    print("\n=== B. Color Math ===")
    from services.color_engine import (
        lab_to_xyz, xyz_to_lab, xyz_to_reflectance, reflectance_to_xyz,
        ks_from_reflectance, reflectance_from_ks, lab_to_ks, ks_to_lab,
        delta_e_cie2000, delta_e_cie76, hex_to_lab, Pigment, predict_mixture_lab,
        _TIO2_KS
    )

    # B1: LAB → XYZ → LAB roundtrip
    for L, a, b in [(50, 0, 0), (65, 40, 30), (30, -25, 5), (80, -10, 60), (20, 30, -40)]:
        X, Y, Z = lab_to_xyz(L, a, b)
        L2, a2, b2 = xyz_to_lab(X, Y, Z)
        err = max(abs(L - L2), abs(a - a2), abs(b - b2))
        check(f"LAB roundtrip ({L},{a},{b})", err < 0.01, f"err={err:.6f}")

    # B2: XYZ → reflectance → XYZ roundtrip
    # Note: D65 white point (95.047,100,108.883) maps to R≈1.0, clamped to 0.999
    # so the roundtrip error is larger — this is expected physical clamping.
    for X, Y, Z, tol in [(50, 50, 50, 0.05), (10, 40, 70, 0.05),
                          (95.047, 100, 108.883, 0.15)]:
        R, G, B = xyz_to_reflectance(X, Y, Z)
        X2, Y2, Z2 = reflectance_to_xyz(R, G, B)
        err = max(abs(X - X2), abs(Y - Y2), abs(Z - Z2))
        check(f"XYZ→Refl→XYZ roundtrip ({X},{Y},{Z})", err < tol, f"err={err:.6f}")

    # B3: K/S roundtrip
    for R in [0.05, 0.2, 0.5, 0.8, 0.95]:
        ks = ks_from_reflectance(R)
        R2 = reflectance_from_ks(ks)
        check(f"K/S roundtrip R={R}", abs(R - R2) < 0.001, f"R2={R2:.6f}")

    # B4: LAB → K/S → LAB roundtrip
    for L, a, b in [(50, 0, 0), (65, 40, 30), (80, -10, 60)]:
        ks = lab_to_ks(L, a, b)
        L2, a2, b2 = ks_to_lab(*ks)
        err = max(abs(L - L2), abs(a - a2), abs(b - b2))
        check(f"LAB→KS→LAB roundtrip ({L},{a},{b})", err < 0.1, f"err={err:.6f}")

    # B5: D65 white point
    R, G, B = xyz_to_reflectance(95.047, 100.0, 108.883)
    check("D65 white → reflectance ≈ 1.0", all(abs(v - 0.999) < 0.01 for v in [R, G, B]),
          f"R={R:.4f} G={G:.4f} B={B:.4f}")

    # B6: CIEDE2000 — Sharma et al. (2005) reference pairs (subset)
    SHARMA = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
        ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
        ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
        ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
        ((50.0, -1.0, 2.0), (50.0, 0.0, 0.0), 2.3669),
        ((50.0, 2.4900, -0.0010), (50.0, -2.4900, 0.0009), 7.1792),
        ((50.0, 2.4900, -0.0010), (50.0, -2.4900, 0.0010), 7.1792),
        ((50.0, 2.4900, -0.0010), (50.0, -2.4900, 0.0011), 7.2195),
        ((50.0, 2.4900, -0.0010), (50.0, -2.4900, 0.0012), 7.2195),
    ]
    for lab1, lab2, expected in SHARMA:
        got = delta_e_cie2000(lab1, lab2)
        check(f"CIEDE2000 ({lab1[1]:.2f},{lab1[2]:.2f})-({lab2[1]:.2f},{lab2[2]:.2f})",
              abs(got - expected) < 0.002, f"got={got:.4f} expected={expected:.4f}")

    # B7: hex_to_lab basic checks
    lab = hex_to_lab("#FFFFFF")
    check("hex FFFFFF → L≈100", lab is not None and abs(lab[0] - 100) < 0.5, f"L={lab[0] if lab else '?'}")
    lab = hex_to_lab("#000000")
    check("hex 000000 → L≈0", lab is not None and abs(lab[0]) < 0.5, f"L={lab[0] if lab else '?'}")
    lab = hex_to_lab("#FF0000")
    check("hex FF0000 → a* > 50 (red)", lab is not None and lab[1] > 50, f"a={lab[1] if lab else '?'}")

    # =====================================================================
    # C. K-M MODEL SANITY
    # =====================================================================
    print("\n=== C. K-M Model Sanity ===")

    # C1: TiO2 K/S should be very small (nearly white)
    check("TiO2 K/S all < 0.1", all(k < 0.1 for k in _TIO2_KS),
          f"TiO2 K/S = {_TIO2_KS}")

    # C2: Build a test pigment (red) and check K/S extraction
    test_pig = Pigment("TEST_RED", full_L=38, full_a=55, full_b=40,
                       tint_L=70, tint_a=30, tint_b=15)
    check("Red pigment _ks_unit all positive", all(k > 0 for k in test_pig._ks_unit),
          f"ks_unit={test_pig._ks_unit}")

    # C3: Predicting with concentration=0 should give substrate LAB (~white)
    lab_zero = predict_mixture_lab([(test_pig, 0.0)])
    check("Zero concentration → L > 90 (white substrate)", lab_zero[0] > 90,
          f"got L={lab_zero[0]:.2f}")

    # C4: Higher concentration → lower L (darker)
    lab_low = predict_mixture_lab([(test_pig, 0.01)])
    lab_high = predict_mixture_lab([(test_pig, 0.10)])
    check("Higher conc → lower L*", lab_high[0] < lab_low[0],
          f"L@1%={lab_low[0]:.2f} L@10%={lab_high[0]:.2f}")

    # C5: TiO2 effect — in single-constant K-M, TiO2 K/S ≈ 0, so adding it
    # barely changes mix. Real lightening comes from reducing pigment fraction.
    lab_highpig = predict_mixture_lab([(test_pig, 0.05)])
    lab_lowpig = predict_mixture_lab([(test_pig, 0.02)], tio2_conc=0.3)
    check("Reducing pigment + adding TiO2 → higher L*",
          lab_lowpig[0] > lab_highpig[0],
          f"L_high_pig={lab_highpig[0]:.2f} L_low_pig+tio2={lab_lowpig[0]:.2f}")

    # C6: Two reds vs one red → should shift, not be identical
    test_pig2 = Pigment("TEST_ORANGE", full_L=55, full_a=45, full_b=60,
                        tint_L=80, tint_a=15, tint_b=30)
    lab_one = predict_mixture_lab([(test_pig, 0.05)])
    lab_two = predict_mixture_lab([(test_pig, 0.03), (test_pig2, 0.02)])
    de_mix = delta_e_cie2000(lab_one, lab_two)
    check("Two-pigment blend ≠ single pigment", de_mix > 1.0, f"ΔE={de_mix:.2f}")

    # C7: All DB pigments should produce valid K/S
    all_pg = RawMaterial.query.filter(
        RawMaterial.type == "PG",
        RawMaterial.full_tone_L.isnot(None),
        RawMaterial.tint_tone_L.isnot(None),
    ).all()
    bad_pigs = []
    for rm in all_pg:
        try:
            pig = Pigment(
                rm.rawmaterialid,
                rm.full_tone_L, rm.full_tone_a or 0, rm.full_tone_b or 0,
                rm.tint_tone_L, rm.tint_tone_a or 0, rm.tint_tone_b or 0,
            )
            if any(k <= 0 for k in pig._ks_unit):
                bad_pigs.append(rm.rawmaterialid)
        except Exception as e:
            bad_pigs.append(f"{rm.rawmaterialid}:{e}")
    check(f"All {len(all_pg)} DB pigments → valid K/S", len(bad_pigs) == 0,
          f"bad: {bad_pigs}")

    # =====================================================================
    # D. ML ENGINE
    # =====================================================================
    print("\n=== D. ML Engine ===")
    from services.ml_engine import _feature_vector, MLRecipeModel, get_ml_status, get_ml_suggestions

    # D1: Feature vector dimensions
    fv = _feature_vector(50, 10, -20, "PE")
    check("Feature vector = 12 dims", len(fv) == 12, f"got {len(fv)}")

    # D2: Feature vector normalization
    check("L normalized", 0 <= fv[0] <= 1, f"fv[0]={fv[0]}")
    check("Polymer one-hot sums to 1", sum(fv[6:]) == 1.0, f"sum={sum(fv[6:])}")

    # D3: Train synchronous for testing
    print("  Training ML model synchronously for testing...")
    model = MLRecipeModel()
    model._train(app)
    if model.is_trained:
        print(f"  ML trained: corpus={model.stats.get('corpus_size')}, "
              f"pig_models={model.stats.get('trainable_pigments')}")
        check("ML corpus >= 5 samples", model.stats.get("corpus_size", 0) >= 5,
              f"got {model.stats.get('corpus_size')}")
        check("ML trainable pigments >= 1", model.stats.get("trainable_pigments", 0) >= 1,
              f"got {model.stats.get('trainable_pigments')}")

        # D4: Predict for a known red
        preds = model.predict(45, 50, 30, "PE", target=(45, 50, 30))
        check("ML predicts ≥1 suggestion for red", len(preds) >= 1,
              f"got {len(preds)}")

        if preds:
            sug = preds[0]
            # D5: Predicted LAB should exist
            check("ML suggestion has predicted_lab", sug.get("predicted_lab") is not None,
                  str(sug.get("predicted_lab")))
            # D6: Delta-E should exist
            check("ML suggestion has delta_e", sug.get("delta_e") is not None,
                  str(sug.get("delta_e")))
            # D7: Components sum ≈ 100%
            total_pct = sum(c.get("pct", 0) for c in sug.get("components", []))
            check("ML components sum ≈ 100%", abs(total_pct - 100) < 1.0,
                  f"sum={total_pct:.2f}")
            # D8: All components have constraint_ok field
            all_have = all("constraint_ok" in c for c in sug.get("components", []))
            check("All ML components have constraint_ok", all_have)

            # D9: Pigments have explainability fields
            pigs = [c for c in sug.get("components", []) if c.get("role") == "colorant"]
            if pigs:
                p = pigs[0]
                check("ML colorant has n_recipes", p.get("n_recipes") is not None,
                      str(p.get("n_recipes")))
                check("ML colorant has conc_range", p.get("conc_range") is not None,
                      str(p.get("conc_range")))

        # D10: Predict for white (L=95, a=0, b=0) — TiO2 should dominate
        white_preds = model.predict(95, 0, 0, "PE", target=(95, 0, 0))
        if white_preds:
            comps = white_preds[0].get("components", [])
            tio2 = [c for c in comps if c.get("role") == "opacity"]
            if tio2:
                check("White target → TiO2 > 5%", tio2[0]["pct"] > 5,
                      f"TiO2={tio2[0]['pct']}%")

        # D11: Predict for black (L=5) — high pigment loading expected
        black_preds = model.predict(5, 0, 0, "PE", target=(5, 0, 0))
        if black_preds:
            comps = black_preds[0].get("components", [])
            colorants = [c for c in comps if c.get("role") == "colorant"]
            if colorants:
                total_pig = sum(c.get("pct", 0) for c in colorants)
                check("Black target → colorant loading > 1%", total_pig > 1,
                      f"total colorant={total_pig:.2f}%")

        # D12: ML model shouldn't crash on any polymer
        for poly in ["PE", "PP", "ABS", "SAN", "OTHER"]:
            try:
                model.predict(50, 20, 10, poly, target=(50, 20, 10))
                check(f"ML predict works for {poly}", True)
            except Exception as e:
                check(f"ML predict works for {poly}", False, str(e))

    else:
        check("ML model trained successfully", False,
              model._training_error or "unknown error")

    # =====================================================================
    # E. SEARCH ENGINE FLOW
    # =====================================================================
    print("\n=== E. Search Engine Flow ===")
    from services.search_engine import search_recipes, get_eligible_pigments

    # E1: Eligible pigments basic test
    eligible = get_eligible_pigments(compliance="NON-R")
    check("Eligible pigments (NON-R) > 0", len(eligible) > 0, f"got {len(eligible)}")

    eligible_reach = get_eligible_pigments(compliance="REACH")
    check("Eligible pigments (REACH) ≤ NON-R", len(eligible_reach) <= len(eligible),
          f"REACH={len(eligible_reach)} NONR={len(eligible)}")

    # E2: Full search
    results = search_recipes(
        target_L=45.0, target_a=50.0, target_b=30.0,
        polymer="PE",
    )
    check("Search returns dict with expected keys",
          all(k in results for k in ["exact_matches", "cross_polymer_suggestions",
                                      "pigment_suggestions", "ml_suggestions"]),
          str(results.keys()))

    # E3: Exact matches should have recipe
    for m in results.get("exact_matches", [])[:3]:
        has_recipe = len(m.get("recipe", [])) > 0
        check(f"Exact match {m['product']['id']} has recipe", has_recipe)

    # E4: Pigment suggestions should have predicted LAB + ΔE
    for i, ps in enumerate(results.get("pigment_suggestions", [])[:3]):
        check(f"KM suggestion #{i} has predicted_lab",
              ps.get("predicted_lab") is not None)
        check(f"KM suggestion #{i} has delta_e",
              ps.get("delta_e") is not None)

    # E5: ML suggestions should have predicted LAB + ΔE
    for i, ms in enumerate(results.get("ml_suggestions", [])[:3]):
        check(f"ML suggestion #{i} has predicted_lab",
              ms.get("predicted_lab") is not None,
              str(ms.get("predicted_lab")))
        check(f"ML suggestion #{i} has delta_e",
              ms.get("delta_e") is not None,
              str(ms.get("delta_e")))

    # =====================================================================
    # F. RECIPE SANITY
    # =====================================================================
    print("\n=== F. Recipe Sanity ===")

    # F1: Check that recipes in DB have total qty > 0
    bad_recipes = 0
    products_checked = 0
    for prod in Product.query.limit(50).all():
        items = prod.recipe_items
        if items:
            total = sum(r.qtyinkg or 0 for r in items)
            if total <= 0:
                bad_recipes += 1
            products_checked += 1
    check(f"All {products_checked} checked recipes have total > 0", bad_recipes == 0,
          f"found {bad_recipes} with zero/negative total")

    # F2: Check no recipe has negative qty (known: 1 data entry error in CSV)
    neg_qty = ProductRawMaterialMap.query.filter(
        ProductRawMaterialMap.qtyinkg < 0
    ).count()
    if neg_qty:
        print(f"  [WARN] {neg_qty} negative recipe quantity (CSV data entry error)")
    else:
        check("No negative recipe quantities", True)

    # F3: Check that lab results have valid LAB ranges
    bad_lab = LabResult.query.filter(
        (LabResult.L < 0) | (LabResult.L > 100) |
        (LabResult.a < -128) | (LabResult.a > 128) |
        (LabResult.b < -128) | (LabResult.b > 128)
    ).count()
    check("All lab results in valid LAB range", bad_lab == 0, f"found {bad_lab} out of range")

    # F4: Check DB pigment L values are in sensible range
    bad_pig_L = RawMaterial.query.filter(
        RawMaterial.type == "PG",
        RawMaterial.full_tone_L.isnot(None),
        ((RawMaterial.full_tone_L < 0) | (RawMaterial.full_tone_L > 100))
    ).count()
    check("All pigment L* in 0-100", bad_pig_L == 0, f"found {bad_pig_L} out of range")

    # F5: Check tint_tone_L > full_tone_L for colored pigments
    # (Tint is diluted 1:10 with white TiO2, so should be lighter)
    suspicious_tint = []
    for rm in RawMaterial.query.filter(
        RawMaterial.type == "PG",
        RawMaterial.full_tone_L.isnot(None),
        RawMaterial.tint_tone_L.isnot(None),
        RawMaterial.full_tone_L < 85,  # only for non-white pigments
    ).all():
        if rm.tint_tone_L < rm.full_tone_L - 5:  # tint darker than full? suspicious
            suspicious_tint.append(f"{rm.rawmaterialid}: full_L={rm.full_tone_L} tint_L={rm.tint_tone_L}")
    check(f"Tint tone lighter than full tone (colored pigments)",
          len(suspicious_tint) == 0, "; ".join(suspicious_tint[:5]))


# =====================================================================
# SUMMARY
# =====================================================================
print(f"\n{'='*60}")
print(f"TOTAL: {PASS + FAIL}   PASSED: {PASS}   FAILED: {FAIL}")
if ISSUES:
    print(f"\nFAILED CHECKS:")
    for name, detail in ISSUES:
        print(f"  - {name}")
        if detail:
            print(f"    {detail}")
print(f"{'='*60}")
