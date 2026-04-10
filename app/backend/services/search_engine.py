"""
Smart search & filter engine.

Given a target LAB + filter constraints, this module:
1. Filters eligible pigments from the library
2. Finds existing recipes closest to the target LAB in the requested polymer
3. Suggests cross-polymer adaptations if an exact polymer match isn't available
4. Suggests new pigment combinations using K-M model if no close match exists
"""
import json
import math
from typing import List, Optional, Dict, Tuple

from models.database import (
    db, Product, ProductSpec, ProductRawMaterialMap,
    RawMaterial, AlphaCode, LabResult
)
from services.color_engine import delta_e_cie2000, Pigment, predict_mixture_lab, hex_to_lab
from services.ml_engine import get_ml_suggestions, get_ml_status


# Compliance hierarchy (what each level covers)
COMPLIANCE_LEVELS = {
    "NON-R": 0,
    "ROHS1": 1,
    "ROHS2": 2,
    "REACH": 3,
}

# Polymer prefix mapping from alpha_code
POLYMER_PREFIX = {
    "PE": "E",
    "PP": "C",
    "ABS": "S",
    "SAN": "S",
    "OTHER": "O",
}


def _safe_json_list(val: str) -> List[str]:
    if not val:
        return []
    try:
        return json.loads(val.replace("'", '"'))
    except Exception:
        return []


def _compliance_ok(pigment_compliance: str, required_compliance: str) -> bool:
    """Return True if pigment compliance satisfies the required level."""
    if not required_compliance or required_compliance == "NON-R":
        return True
    p = COMPLIANCE_LEVELS.get(pigment_compliance or "NON-R", 0)
    r = COMPLIANCE_LEVELS.get(required_compliance, 0)
    return p >= r


def get_eligible_pigments(
    compliance: Optional[str] = None,
    excluded_ids: Optional[List[str]] = None,
    light_fastness: Optional[float] = None,
    weather_fastness: Optional[float] = None,
    heat_stability: Optional[float] = None,
) -> List[RawMaterial]:
    """Return pigments (type=PG) that have LAB data and pass all filter criteria.

    Pigments with no fastness/heat data on record are included (no data ≠ failing —
    e.g. carbon blacks and TiO2 have no fastness data but are always valid).
    """
    q = RawMaterial.query.filter(
        RawMaterial.type == "PG",
        RawMaterial.full_tone_L.isnot(None),
    )
    results = q.all()
    out = []
    for rm in results:
        if excluded_ids and rm.rawmaterialid in excluded_ids:
            continue
        if compliance and not _compliance_ok(rm.compliance, compliance):
            continue
        if light_fastness and rm.light_fastness_tone is not None:
            if rm.light_fastness_tone < light_fastness:
                continue
        if weather_fastness and rm.weather_fastness_tone is not None:
            if rm.weather_fastness_tone < weather_fastness:
                continue
        if heat_stability and rm.heat_resistance is not None:
            if rm.heat_resistance < heat_stability:
                continue
        out.append(rm)
    return out


def _recipe_min_properties(product: Product) -> Dict:
    """Return the minimum light_fastness, weather_fastness, and heat_resistance
    across all PG pigments in the product's recipe.
    Used as fallback when product_spec fields are empty (the common case).
    """
    lf_vals, wf_vals, hr_vals = [], [], []
    for item in product.recipe_items:
        rm = item.raw_material
        if rm is None or rm.type != "PG":
            continue
        if rm.light_fastness_tone is not None:
            lf_vals.append(rm.light_fastness_tone)
        if rm.weather_fastness_tone is not None:
            wf_vals.append(rm.weather_fastness_tone)
        if rm.heat_resistance is not None:
            hr_vals.append(rm.heat_resistance)
    return {
        "light_fastness": min(lf_vals) if lf_vals else None,
        "weather_fastness": min(wf_vals) if wf_vals else None,
        "heat_resistance": min(hr_vals) if hr_vals else None,
    }


def _product_matches_filters(
    product: Product,
    polymer: str,
    application: Optional[str],
    sub_application: Optional[str],
    compliance: Optional[str],
    light_fastness: Optional[float],
    weather_fastness: Optional[float],
    heat_stability: Optional[float],
) -> bool:
    """Check whether a product's alpha codes include at least one matching all filters."""
    codes = _safe_json_list(product.alphacode)
    if not codes:
        return False

    polymer_prefix = POLYMER_PREFIX.get(polymer.upper(), polymer[0].upper())
    matched_code = False
    for code in codes:
        ac = AlphaCode.query.get(code)
        if ac is None:
            continue
        if ac.polymer.upper() != polymer.upper():
            continue
        if application and ac.application.upper() not in (application.upper(), "N.A."):
            if application.upper() != "N.A.":
                continue
        if sub_application and sub_application.upper() != "N.A.":
            if ac.sub_application.upper() not in (sub_application.upper(), "N.A."):
                continue
        if compliance and compliance != "NON-R":
            req = COMPLIANCE_LEVELS.get(compliance, 0)
            prod_comp = COMPLIANCE_LEVELS.get(ac.compliance, 0)
            if prod_comp < req:
                continue
        matched_code = True
        break

    if not matched_code:
        return False

    # Check spec filters — prefer product spec, fall back to recipe pigment minimums.
    # product_spec data is mostly empty in the current dataset, so the fallback
    # to _recipe_min_properties() is the active code path for almost all searches.
    spec = product.spec
    spec_lf = spec.light_fastness if spec else None
    spec_wf = spec.weather_fastness if spec else None
    spec_hs = spec.heat_stability if spec else None

    if (light_fastness or weather_fastness or heat_stability) and (
        spec_lf is None or spec_wf is None or spec_hs is None
    ):
        rp = _recipe_min_properties(product)
        if spec_lf is None:
            spec_lf = rp["light_fastness"]
        if spec_wf is None:
            spec_wf = rp["weather_fastness"]
        if spec_hs is None:
            spec_hs = rp["heat_resistance"]

    if light_fastness and spec_lf is not None and spec_lf < light_fastness:
        return False
    if weather_fastness and spec_wf is not None and spec_wf < weather_fastness:
        return False
    if heat_stability and spec_hs is not None and spec_hs < heat_stability:
        return False

    return True


def _lab_to_color_keywords(L: float, a: float, b: float) -> List[str]:
    """Convert LAB values to likely color name keywords for product name search."""
    if L < 25:
        return ["BLACK"]
    if L > 85 and abs(a) < 12 and abs(b) < 12:
        return ["WHITE"]
    chroma = math.sqrt(a ** 2 + b ** 2)
    if chroma < 10:
        return ["GREY", "GRAY"]

    keywords: List[str] = []
    if a < -15:
        keywords.append("GREEN")
    if a > 20:
        if b > 15:
            keywords.append("ORANGE")
        keywords.append("RED")
    if b > 20 and abs(a) < 25:
        if "ORANGE" not in keywords:
            keywords.append("YELLOW")
    if b < -15 and a < 5:
        keywords.append("BLUE")
    if a > 5 and b < -10:
        keywords.extend(["VIOLET", "BLUE"])
    if not keywords:
        if abs(a) > abs(b):
            keywords = ["RED"] if a > 0 else ["GREEN"]
        else:
            keywords = ["YELLOW"] if b > 0 else ["BLUE"]
    return list(dict.fromkeys(keywords))  # deduplicate while preserving order


def _product_in_polymer(prod: Product, polymer: str) -> bool:
    """Return True if any of the product's alpha codes is in the given polymer."""
    codes = _safe_json_list(prod.alphacode)
    for code in codes:
        ac = AlphaCode.query.filter_by(alpha_code=code).first()
        if ac and ac.polymer.upper() == polymer.upper():
            return True
    return False


def _fallback_recipe_search(
    target: Tuple[float, float, float],
    polymer: str,
    application: Optional[str],
    sub_application: Optional[str],
    compliance: Optional[str],
    light_fastness: Optional[float],
    weather_fastness: Optional[float],
    heat_stability: Optional[float],
    eligible_rms: List[RawMaterial],
    top_n: int = 10,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Fallback search when LabResult table has no data.

    Strategy:
    1. Rank eligible pigments by full-tone LAB delta-E to target.
    2. Collect candidate products that use the top-N closest pigments.
    3. For each candidate product predict its LAB via K-M using only the
       pigment components of its recipe.
    4. Rank by predicted delta-E and split into same-polymer / cross-polymer.
    """
    # ---- rank pigments closest to target -----------------------------------
    pigment_scores: List[Tuple[float, RawMaterial]] = []
    for rm in eligible_rms:
        if rm.full_tone_L is None:
            continue
        de = delta_e_cie2000(
            target,
            (rm.full_tone_L,
             rm.full_tone_a if rm.full_tone_a is not None else 0.0,
             rm.full_tone_b if rm.full_tone_b is not None else 0.0),
        )
        pigment_scores.append((de, rm))
    pigment_scores.sort(key=lambda x: x[0])

    # Keep top-20 closest pigments to bound the candidate product set
    top_pigments = [rm for _, rm in pigment_scores[:20]]
    top_pigment_ids = {rm.rawmaterialid for rm in top_pigments}

    # Build a quick lookup: rawmaterialid -> RawMaterial (for K-M objects)
    rm_lookup: Dict[str, RawMaterial] = {rm.rawmaterialid: rm for rm in eligible_rms}

    def _rm_to_pigment(rm: RawMaterial) -> Optional[Pigment]:
        if rm.full_tone_L is None or rm.tint_tone_L is None:
            return None
        return Pigment(
            name=rm.rawmaterialname,
            full_L=rm.full_tone_L,
            full_a=rm.full_tone_a if rm.full_tone_a is not None else 0.0,
            full_b=rm.full_tone_b if rm.full_tone_b is not None else 0.0,
            tint_L=rm.tint_tone_L,
            tint_a=rm.tint_tone_a if rm.tint_tone_a is not None else 0.0,
            tint_b=rm.tint_tone_b if rm.tint_tone_b is not None else 0.0,
        )

    # ---- collect candidate product IDs from recipe map --------------------
    candidate_product_ids: set = set()
    for rm_id in top_pigment_ids:
        rows = ProductRawMaterialMap.query.filter_by(rawmaterialid=rm_id).all()
        for row in rows:
            candidate_product_ids.add(row.productid)
        if len(candidate_product_ids) >= 500:   # hard cap to keep response fast
            break

    # ---- predict LAB for each candidate -----------------------------------
    exact_matches: List[Dict] = []
    cross_polymer_list: List[Dict] = []

    for prod_id in candidate_product_ids:
        prod = Product.query.filter_by(id=prod_id).first()
        if prod is None:
            continue

        recipe_items = ProductRawMaterialMap.query.filter_by(productid=prod_id).all()
        if not recipe_items:
            continue

        total_kg = sum(i.qtyinkg for i in recipe_items if i.qtyinkg)
        if not total_kg:
            continue

        # Build K-M mixture from pigment-only components of the recipe
        mixture: List[Tuple[Pigment, float]] = []
        for item in recipe_items:
            rm = rm_lookup.get(item.rawmaterialid)
            if rm is None:
                continue                     # non-pigment component — skip for K-M
            pig = _rm_to_pigment(rm)
            if pig is None:
                continue
            conc = (item.qtyinkg or 0.0) / total_kg
            if conc > 0:
                mixture.append((pig, conc))

        if not mixture:
            continue

        try:
            pred_lab = predict_mixture_lab(mixture)
            de = delta_e_cie2000(target, pred_lab)
        except Exception:
            continue

        is_target_polymer = _product_in_polymer(prod, polymer)

        result = {
            "product": prod.to_dict(),
            "predicted_lab": {
                "L": round(pred_lab[0], 2),
                "a": round(pred_lab[1], 2),
                "b": round(pred_lab[2], 2),
            },
            "delta_e": round(de, 3),
            "polymer": polymer.upper(),
            "in_polymer": is_target_polymer,
            "recipe": [r.to_dict() for r in prod.recipe_items],
            "source": "recipe_prediction",
        }

        if is_target_polymer:
            passes = _product_matches_filters(
                prod, polymer, application, sub_application,
                compliance, light_fastness, weather_fastness, heat_stability,
            )
            if passes and de < 30:   # only include if K-M prediction is reasonably close
                exact_matches.append(result)
        else:
            if de < 8:
                result["native_polymer"] = "unknown"
                result["target_polymer"] = polymer.upper()
                result["note"] = (
                    f"Predicted ΔE={round(de, 2)} via K-M model. "
                    f"Not confirmed in {polymer.upper()} — adjust loading ±10–20%."
                )
                cross_polymer_list.append(result)

    exact_matches.sort(key=lambda x: x["delta_e"])
    cross_polymer_list.sort(key=lambda x: x["delta_e"])

    # ------------------------------------------------
    # If K-M found nothing (pigment IDs unmatched),
    # fall back to color-name-based product search.
    # ------------------------------------------------
    if not exact_matches and not cross_polymer_list:
        exact_matches, cross_polymer_list = _color_name_product_search(
            target=target,
            polymer=polymer,
            application=application,
            sub_application=sub_application,
            compliance=compliance,
            light_fastness=light_fastness,
            weather_fastness=weather_fastness,
            heat_stability=heat_stability,
            top_n=top_n,
        )

    return exact_matches, cross_polymer_list


def _color_name_product_search(
    target: Tuple[float, float, float],
    polymer: str,
    application: Optional[str],
    sub_application: Optional[str],
    compliance: Optional[str],
    light_fastness: Optional[float],
    weather_fastness: Optional[float],
    heat_stability: Optional[float],
    top_n: int = 10,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Fallback: find products whose names contain color keywords derived from
    the target LAB, then filter by polymer and other constraints.
    Products are returned with a note that their LAB is unconfirmed.
    """
    target_L, target_a, target_b = target
    keywords = _lab_to_color_keywords(target_L, target_a, target_b)

    # Query products whose name matches any keyword
    from sqlalchemy import or_
    name_filters = [Product.name.ilike(f"%{kw}%") for kw in keywords]
    candidates = Product.query.filter(or_(*name_filters)).all()

    same_polymer: List[Dict] = []
    other_polymer: List[Dict] = []
    seen_ids: set = set()

    for prod in candidates:
        if prod.id in seen_ids:
            continue
        seen_ids.add(prod.id)

        is_target_polymer = _product_in_polymer(prod, polymer)

        result = {
            "product": prod.to_dict(),
            "delta_e": None,        # No LAB data to compute ΔE
            "polymer": polymer.upper(),
            "in_polymer": is_target_polymer,
            "recipe": [r.to_dict() for r in prod.recipe_items],
            "source": "color_name_match",
            "note": (
                f"Matched by color name ({', '.join(keywords)}). "
                "No spectrophotometer data on record — verify ΔE after measurement."
            ),
        }

        if is_target_polymer:
            passes = _product_matches_filters(
                prod, polymer, application, sub_application,
                compliance, light_fastness, weather_fastness, heat_stability,
            )
            if passes:
                same_polymer.append(result)
        else:
            other_polymer.append(result)

    # Sort by product name (no delta_e available)
    same_polymer.sort(key=lambda x: x["product"].get("name", ""))
    other_polymer.sort(key=lambda x: x["product"].get("name", ""))
    return same_polymer[:top_n], other_polymer[:top_n]


def search_recipes(
    target_L: float,
    target_a: float,
    target_b: float,
    polymer: str,
    application: Optional[str] = None,
    sub_application: Optional[str] = None,
    compliance: Optional[str] = None,
    light_fastness: Optional[float] = None,
    weather_fastness: Optional[float] = None,
    heat_stability: Optional[float] = None,
    ral_pantone: Optional[str] = None,
    top_n: int = 10,
) -> Dict:
    """
    Main search function.
    Returns a dict with:
      - exact_matches: products in the requested polymer sorted by ΔE
      - cross_polymer_suggestions: products in other polymers that are close
      - pigment_suggestions: KM-based pigment combination suggestions
      - eligible_pigments: list of eligible pigments for manual mixing
    """
    target = (target_L, target_a, target_b)

    # Apply project default: heat stability minimum 200°C (standard PE processing)
    effective_heat = heat_stability if heat_stability is not None else 200.0

    # -----------------------------------------------------------------------
    # RAL/Pantone reference resolution
    # -----------------------------------------------------------------------
    from models.database import RalPantoneShade
    reference_color = None
    if ral_pantone:
        shade = RalPantoneShade.query.filter(
            RalPantoneShade.shade_code.ilike(ral_pantone.strip())
        ).first()
        if shade:
            lab = hex_to_lab(shade.hex_code) if shade.hex_code else None
            reference_color = {
                "shade_code": shade.shade_code,
                "color_name": shade.color_name,
                "hex_code": shade.hex_code,
                "lab": {"L": round(lab[0], 2), "a": round(lab[1], 2), "b": round(lab[2], 2)} if lab else None,
            }

    # -----------------------------------------------------------------------
    # Step 1: Fetch all products that have spectrophotometer LAB results
    # -----------------------------------------------------------------------
    lab_results = LabResult.query.all()
    product_lab_map: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
    for lr in lab_results:
        if lr.product_id not in product_lab_map:
            product_lab_map[lr.product_id] = {}
        product_lab_map[lr.product_id][lr.polymer] = (lr.L, lr.a, lr.b)

    # -----------------------------------------------------------------------
    # Step 2: Score products that have measured LAB data
    # -----------------------------------------------------------------------
    exact_matches = []
    cross_polymer = []

    if product_lab_map:
        all_products = Product.query.all()
        for prod in all_products:
            prod_labs = product_lab_map.get(prod.id, {})

            if polymer.upper() in prod_labs:
                lab = prod_labs[polymer.upper()]
                de = delta_e_cie2000(target, lab)
                passes = _product_matches_filters(
                    prod, polymer, application, sub_application,
                    compliance, light_fastness, weather_fastness, heat_stability,
                )
                if passes or de < 5:
                    exact_matches.append({
                        "product": prod.to_dict(),
                        "measured_lab": {"L": lab[0], "a": lab[1], "b": lab[2]},
                        "delta_e": round(de, 3),
                        "polymer": polymer.upper(),
                        "in_polymer": True,
                        "recipe": [r.to_dict() for r in prod.recipe_items],
                        "source": "measured",
                    })
            else:
                for poly, lab in prod_labs.items():
                    de = delta_e_cie2000(target, lab)
                    if de < 8:
                        cross_polymer.append({
                            "product": prod.to_dict(),
                            "measured_lab": {"L": lab[0], "a": lab[1], "b": lab[2]},
                            "delta_e": round(de, 3),
                            "native_polymer": poly,
                            "target_polymer": polymer.upper(),
                            "in_polymer": False,
                            "recipe": [r.to_dict() for r in prod.recipe_items],
                            "source": "measured",
                            "note": (
                                f"This recipe achieves ΔE={round(de,2)} in {poly}. "
                                f"Adjust pigment loading by ±10–20% for {polymer.upper()} base."
                            ),
                        })

        exact_matches.sort(key=lambda x: x["delta_e"])
        cross_polymer.sort(key=lambda x: x["delta_e"])

    # -----------------------------------------------------------------------
    # Step 3: If no measured data, fall back to K-M recipe prediction
    # -----------------------------------------------------------------------
    eligible = get_eligible_pigments(
        compliance=compliance,
        light_fastness=light_fastness,
        weather_fastness=weather_fastness,
        heat_stability=effective_heat,
    )

    if not exact_matches and not cross_polymer:
        exact_matches, cross_polymer = _fallback_recipe_search(
            target=target,
            polymer=polymer,
            application=application,
            sub_application=sub_application,
            compliance=compliance,
            light_fastness=light_fastness,
            weather_fastness=weather_fastness,
            heat_stability=effective_heat,
            eligible_rms=eligible,
            top_n=top_n,
        )

    # -----------------------------------------------------------------------
    # Step 4: K-M pigment combination suggestions
    # -----------------------------------------------------------------------
    pigment_suggestions = _suggest_pigment_combinations(
        target, compliance,
        light_fastness=light_fastness,
        weather_fastness=weather_fastness,
        heat_stability=effective_heat,
        top_n=5,
    )

    # -----------------------------------------------------------------------
    # Step 5: ML recipe suggestions (trained models)
    # -----------------------------------------------------------------------
    ml_suggestions = get_ml_suggestions(target_L, target_a, target_b, polymer, top_n=3)
    ml_status = get_ml_status()

    return {
        "target_lab": {"L": target_L, "a": target_a, "b": target_b},
        "polymer": polymer.upper(),
        "reference_color": reference_color,
        "exact_matches": exact_matches[:top_n],
        "cross_polymer_suggestions": cross_polymer[:top_n],
        "pigment_suggestions": pigment_suggestions,
        "eligible_pigments": [rm.to_dict() for rm in eligible],
        "ml_suggestions": ml_suggestions,
        "ml_status": ml_status,
        "total_exact": len(exact_matches),
        "total_cross": len(cross_polymer),
    }


def _suggest_pigment_combinations(
    target: Tuple[float, float, float],
    compliance: Optional[str],
    light_fastness: Optional[float] = None,
    weather_fastness: Optional[float] = None,
    heat_stability: Optional[float] = None,
    top_n: int = 5,
) -> List[Dict]:
    """
    Suggest single-, two-, and three-pigment combinations that minimise ΔE to
    the target using the Kubelka-Munk model.

    Strategy:
      1. Pre-filter eligible pigments to the top-15 closest to the target
         (scored by min of full-tone ΔE and tint-tone ΔE).
      2. Single-pigment: sweep loading concentrations for every candidate.
      3. Two-pigment: exhaustive search over ALL C(15,2)=105 pairs with a 2-D
         grid search over concentrations for each pair.
      4. Three-pigment: extend the best two-pigment combos by trialling every
         remaining candidate as a trim pigment; only kept when ΔE improves ≥15%.
      5. Return all results sorted by ΔE (up to top_n × 3 entries so the UI
         has a rich list to display).  Each pigment entry includes kg_per_100kg
         for direct use on the production floor.
    """
    target_L, target_a, target_b = target
    target_chroma = math.sqrt(target_a ** 2 + target_b ** 2)
    is_achromatic = target_chroma < 10

    eligible_rms = get_eligible_pigments(
        compliance=compliance,
        light_fastness=light_fastness,
        weather_fastness=weather_fastness,
        heat_stability=heat_stability,
    )

    # Build Pigment objects — require both full-tone AND tint-tone data for K-M
    pig_pool: List[Tuple["RawMaterial", Pigment]] = []
    for rm in eligible_rms:
        if rm.full_tone_L is not None and rm.tint_tone_L is not None:
            pig_pool.append((rm, Pigment(
                name=rm.rawmaterialname,
                full_L=rm.full_tone_L,
                full_a=rm.full_tone_a if rm.full_tone_a is not None else 0.0,
                full_b=rm.full_tone_b if rm.full_tone_b is not None else 0.0,
                tint_L=rm.tint_tone_L,
                tint_a=rm.tint_tone_a if rm.tint_tone_a is not None else 0.0,
                tint_b=rm.tint_tone_b if rm.tint_tone_b is not None else 0.0,
            )))

    if not pig_pool:
        return []

    # ---------------------------------------------------------------------------
    # Concentration grids
    # Achromatic (grey/black/white) needs sub-percent ranges for carbon/TiO2.
    # Chromatic colours use higher loadings (0.5–30%).
    # ---------------------------------------------------------------------------
    if is_achromatic:
        conc_main = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20]
        conc_mod  = [0.001, 0.005, 0.01, 0.02, 0.05, 0.10]
        conc_trim = [0.001, 0.005, 0.01, 0.02, 0.05]
    else:
        conc_main = [0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.30]
        conc_mod  = [0.002, 0.005, 0.01, 0.02, 0.05, 0.10]
        conc_trim = [0.001, 0.005, 0.01, 0.02, 0.05]

    # ---------------------------------------------------------------------------
    # Pre-filter: keep top-15 pigments closest to target.
    # Score = min(full-tone ΔE, tint-tone ΔE) so that both strongly coloured
    # pigments (close at full tone) and tint-tone pigments (good as modifiers)
    # are considered.
    # ---------------------------------------------------------------------------
    def _pig_score(rm: "RawMaterial") -> float:
        de_full = delta_e_cie2000(
            target,
            (rm.full_tone_L,
             rm.full_tone_a if rm.full_tone_a is not None else 0.0,
             rm.full_tone_b if rm.full_tone_b is not None else 0.0),
        )
        de_tint = delta_e_cie2000(
            target,
            (rm.tint_tone_L,
             rm.tint_tone_a if rm.tint_tone_a is not None else 0.0,
             rm.tint_tone_b if rm.tint_tone_b is not None else 0.0),
        )
        return min(de_full, de_tint)

    pig_pool.sort(key=lambda x: _pig_score(x[0]))
    candidates = pig_pool[:15]

    # ---------------------------------------------------------------------------
    # Helper builders
    # ---------------------------------------------------------------------------
    def _pig_entry(pig: Pigment, conc: float) -> Dict:
        return {
            "name": pig.name,
            "concentration": round(conc, 4),
            "kg_per_100kg": round(conc * 100, 2),
        }

    def _make_result(entries: List[Dict], pred: Tuple, de: float, rtype: str) -> Dict:
        return {
            "type": rtype,
            "pigments": entries,
            "predicted_lab": {
                "L": round(pred[0], 2),
                "a": round(pred[1], 2),
                "b": round(pred[2], 2),
            },
            "delta_e": round(de, 3),
        }

    # ---------------------------------------------------------------------------
    # 1. Single-pigment suggestions
    # ---------------------------------------------------------------------------
    single_results: List[Dict] = []
    for rm, pig in candidates:
        best_de, best_c, best_pred = float("inf"), conc_main[0], None
        for c in conc_main:
            try:
                pred = predict_mixture_lab([(pig, c)])
                de = delta_e_cie2000(target, pred)
                if de < best_de:
                    best_de, best_c, best_pred = de, c, pred
            except Exception:
                continue
        if best_pred:
            single_results.append(_make_result([_pig_entry(pig, best_c)], best_pred, best_de, "single"))

    single_results.sort(key=lambda x: x["delta_e"])

    # ---------------------------------------------------------------------------
    # 2. Two-pigment suggestions — ALL C(N,2) pairs from top-15 candidates
    # ---------------------------------------------------------------------------
    two_pig_results: List[Dict] = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            _, pig1 = candidates[i]
            _, pig2 = candidates[j]
            best_de, best_c1, best_c2, best_pred = float("inf"), conc_main[0], conc_mod[0], None
            for c1 in conc_main:
                for c2 in conc_mod:
                    try:
                        pred = predict_mixture_lab([(pig1, c1), (pig2, c2)])
                        de = delta_e_cie2000(target, pred)
                        if de < best_de:
                            best_de, best_c1, best_c2, best_pred = de, c1, c2, pred
                    except Exception:
                        continue
            if best_pred:
                two_pig_results.append(_make_result(
                    [_pig_entry(pig1, best_c1), _pig_entry(pig2, best_c2)],
                    best_pred, best_de, "combination",
                ))

    two_pig_results.sort(key=lambda x: x["delta_e"])

    # ---------------------------------------------------------------------------
    # 3. Three-pigment suggestions
    # Extend the best two-pigment combos with a trim/modifier pigment.
    # Only kept when the third pigment gives ≥15% ΔE improvement over the pair.
    # ---------------------------------------------------------------------------
    three_pig_results: List[Dict] = []
    pig_by_name: Dict[str, Pigment] = {pig.name: pig for _, pig in candidates}

    for combo in two_pig_results[:5]:
        p1_entry = combo["pigments"][0]
        p2_entry = combo["pigments"][1]
        c1 = p1_entry["concentration"]
        c2 = p2_entry["concentration"]
        pig1 = pig_by_name.get(p1_entry["name"])
        pig2 = pig_by_name.get(p2_entry["name"])
        if pig1 is None or pig2 is None:
            continue
        names_in = {p1_entry["name"], p2_entry["name"]}
        base_de = combo["delta_e"]

        for _, pig3 in candidates:
            if pig3.name in names_in:
                continue
            best_de3, best_c3, best_pred3 = float("inf"), conc_trim[0], None
            for c3 in conc_trim:
                try:
                    pred = predict_mixture_lab([(pig1, c1), (pig2, c2), (pig3, c3)])
                    de = delta_e_cie2000(target, pred)
                    if de < best_de3:
                        best_de3, best_c3, best_pred3 = de, c3, pred
                except Exception:
                    continue
            # Only add if the third pigment yields ≥15% improvement in ΔE
            if best_pred3 and best_de3 < base_de * 0.85:
                three_pig_results.append(_make_result(
                    [
                        _pig_entry(pig1, c1),
                        _pig_entry(pig2, c2),
                        _pig_entry(pig3, best_c3),
                    ],
                    best_pred3, best_de3, "combination",
                ))

    three_pig_results.sort(key=lambda x: x["delta_e"])

    # ---------------------------------------------------------------------------
    # Merge: return top singles + best two-pig + best three-pig, all sorted by ΔE
    # Cap at top_n × 3 so the UI has a rich but bounded list.
    # ---------------------------------------------------------------------------
    all_results = (
        single_results[:3]
        + two_pig_results[:top_n]
        + three_pig_results[:top_n]
    )
    all_results.sort(key=lambda x: x["delta_e"])
    return all_results[: top_n * 3]


def get_product_cost_estimate(product_id: str) -> Optional[Dict]:
    """Estimate batch cost from recipe + current raw material prices."""
    items = ProductRawMaterialMap.query.filter_by(productid=product_id).all()
    if not items:
        return None
    total_qty = sum(i.qtyinkg for i in items if i.qtyinkg)
    total_cost = 0.0
    breakdown = []
    for item in items:
        rm = item.raw_material
        if rm and rm.current_price and item.qtyinkg:
            cost = rm.current_price * item.qtyinkg
            total_cost += cost
            breakdown.append({
                "rawmaterialid": item.rawmaterialid,
                "name": rm.rawmaterialname,
                "qty_kg": item.qtyinkg,
                "price_per_kg": rm.current_price,
                "cost": round(cost, 2),
            })
        else:
            breakdown.append({
                "rawmaterialid": item.rawmaterialid,
                "name": rm.rawmaterialname if rm else item.rawmaterialid,
                "qty_kg": item.qtyinkg,
                "price_per_kg": None,
                "cost": None,
            })

    return {
        "product_id": product_id,
        "total_batch_qty_kg": total_qty,
        "total_cost": round(total_cost, 2),
        "cost_per_kg": round(total_cost / total_qty, 2) if total_qty else None,
        "breakdown": breakdown,
    }
