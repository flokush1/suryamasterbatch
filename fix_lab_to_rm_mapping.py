"""
fix_lab_to_rm_mapping.py
========================
Transfers LAB data from synthetic LAB_xxx RawMaterial entries (created from
Lab_Values_Color.xlsx) to the real RMxxx entries that share recognisable
product-number tokens in their names.

Then deletes the synthetic entries so the K-M recipe prediction can use the
correct IDs.

Run once:
    python fix_lab_to_rm_mapping.py
"""
import re
import sys
sys.path.insert(0, 'c:/Users/kushp/Downloads/SuryaMasterBatch/app/backend')

from app import create_app

app = create_app()

# ── Manual overrides ─────────────────────────────────────────────────────────
# Maps LAB pigment name → exact RawMaterial ID to update.
# Extend this list for names that can't be matched by number extraction alone.
MANUAL_MAP = {
    "GREEN 2730K":   "RM401",   # PG7-SD GR2727/2730
    "VOILET 2945K":  "RM801",   # PV23- SD VL 2945
    "VOILET 2946K":  None,      # no clear match — skip
    "BLUE 2749":     "RM602",   # PB15:1-SD BU 2749
    "BLUE 2789":     "RM605",   # PB15:3-SD BU 2789
    "BLUE 2778K":    None,      # not in recipes — skip
    "BLUE 2764":     None,      # not in recipes — skip
    "ORANGE 212":    "RM702",   # PO34-SD OR 212
    "ORANGE 2917":   "RM705",   # PO64-SD OR 2917
    "RED 507K":      "RM304",   # PR53:1-SD RD 507
    "RED 570":       "RM302",   # PR48:3-SD RD 570
    "RED 635":       "RM309",   # PR57:1-SD RD 635
    "RED2963K":      "RM311",   # PR170-SD RD 2963
    "RED 2967K":     "RM312",   # PR170-SD RD 2967
    "RED 5016":      "RM307",   # PR53:1-SD RD 5016
    "RED 2991K":     "RM310",   # PR122-SD RD 2991
    "RED 554":       None,
    "RED 564":       None,
    "RED 2985":      "RM383",   # RED 2985 — direct name match
    "YELLOW 2909":   "RM515",   # PY180- SD YL 2909
    "YELLOW 3033K":  "RM992",   # SOLVENT YELLOW 3033 K
    "YELLOW 114":    "RM1010",  # DMB YEL 114
    "YELLOW 3031K":  None,
    "YELLOW 2908":   None,
    "YELLOW 165":    None,
    "YELLOW 129":    None,
    "YELLOW 2939 K": None,
    "YELLOW 2925K":  None,
    "YELLOW 2927":   None,
}


def _extract_numbers(name: str):
    """Return all numeric tokens (e.g. 2730, 507) from a string."""
    return re.findall(r'\d{3,}', name)


with app.app_context():
    from models.database import db, RawMaterial

    lab_entries = RawMaterial.query.filter(
        RawMaterial.rawmaterialid.like('LAB_%')
    ).all()

    updated = 0
    skipped = 0
    no_match = 0

    for lab in lab_entries:
        lab_name = lab.rawmaterialname.strip()

        # Determine target RM ID
        rm_id = MANUAL_MAP.get(lab_name)

        if rm_id is None:
            # Skip entries explicitly mapped to None, or try auto-match
            if lab_name in MANUAL_MAP:
                print(f"  SKIP  {lab.rawmaterialid} — {lab_name} (no target)")
                skipped += 1
                continue
            # Auto-match: find all real RM entries whose name contains any
            # numeric token from the LAB name
            tokens = _extract_numbers(lab_name)
            if not tokens:
                print(f"  NO_MATCH  {lab.rawmaterialid} — {lab_name} (no numeric token)")
                no_match += 1
                continue
            candidate = None
            for token in tokens:
                matches = RawMaterial.query.filter(
                    RawMaterial.rawmaterialid.notlike('LAB_%'),
                    RawMaterial.rawmaterialname.ilike(f'%{token}%'),
                    RawMaterial.type == 'PG',
                ).all()
                if len(matches) == 1:
                    candidate = matches[0]
                    break
                elif len(matches) > 1:
                    # Pick the first — log for review
                    candidate = matches[0]
                    print(f"  MULTI  {lab_name} → token={token} → {[m.rawmaterialid for m in matches]}")
                    break
            if candidate is None:
                print(f"  NO_MATCH  {lab.rawmaterialid} — {lab_name}")
                no_match += 1
                continue
            rm_id = candidate.rawmaterialid

        # Update the target RM with LAB data
        target_rm = RawMaterial.query.get(rm_id)
        if target_rm is None:
            print(f"  MISSING  target RM {rm_id} not found (for {lab_name})")
            no_match += 1
            continue

        target_rm.full_tone_L = lab.full_tone_L
        target_rm.full_tone_a = lab.full_tone_a
        target_rm.full_tone_b = lab.full_tone_b
        target_rm.tint_tone_L = lab.tint_tone_L
        target_rm.tint_tone_a = lab.tint_tone_a
        target_rm.tint_tone_b = lab.tint_tone_b
        target_rm.full_tone_hex = lab.full_tone_hex
        target_rm.tint_tone_hex = lab.tint_tone_hex
        print(f"  UPDATED  {rm_id} ({target_rm.rawmaterialname}) ← LAB from {lab.rawmaterialid} ({lab_name})")
        updated += 1

        # Remove the synthetic entry
        db.session.delete(lab)

    db.session.commit()
    print(f"\nDone: {updated} RMs updated, {skipped} skipped (no match intended), {no_match} with no match found.")
    print("Re-run the backend to pick up changes.")
