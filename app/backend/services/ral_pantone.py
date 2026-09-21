"""
RAL / Pantone shade lookup.

Resolves a customer code (e.g. "RAL 3020", "623 C", "PANTONE 302C") to a
stored L*a*b* target. Official spectrophotometer values (lab_source="std")
are preferred; otherwise LAB is derived from the shade's sRGB hex.
"""
import re
from typing import Optional, Tuple

from models.database import db, RalPantoneShade
from services.color_engine import hex_to_lab


# Normalise "PANTONE 623 C" / "PMS 623C" / "623 C" / "100-c" / "H010L50C45"
_SPACE_RE = re.compile(r"\s+")
_FINISH_RE = re.compile(r"\s+(C|U|CP|UP)$")
_PREFIX_RE = re.compile(r"^(PANTONE|PMS|RAL)\s+")
_DESIGN_HLC = re.compile(r"^H(\d+)L(\d+)C(\d+)$")
_DESIGN_NUMS = re.compile(r"^(\d{3})\s+(\d{2})\s+(\d{2})$")


def normalize_shade_code(code: str) -> str:
    s = _SPACE_RE.sub(" ", (code or "").strip().upper())
    s = s.replace("PMS ", "PANTONE ")
    hlc = _DESIGN_HLC.match(s.replace(" ", "").replace("-", ""))
    if hlc:
        return f"RAL {int(hlc.group(1)):03d} {int(hlc.group(2)):02d} {int(hlc.group(3)):02d}"
    if not s.startswith("RAL"):
        s = re.sub(r"-C$", "C", s)
        s = re.sub(r"-U$", "U", s)
        s = s.replace("-", " ")
    s = _SPACE_RE.sub(" ", s).strip()
    s = _FINISH_RE.sub(r"\1", s)
    rest = _PREFIX_RE.sub("", s)
    nums = _DESIGN_NUMS.match(rest)
    if nums:
        return f"RAL {nums.group(1)} {nums.group(2)} {nums.group(3)}"
    return s


def _bare_code(normalized: str) -> str:
    return _PREFIX_RE.sub("", normalized)


def find_shade(code: str) -> Optional[RalPantoneShade]:
    """Find a shade by exact, normalised, or prefix-stripped code."""
    raw = (code or "").strip()
    if not raw:
        return None

    shade = RalPantoneShade.query.filter(
        RalPantoneShade.shade_code.ilike(raw)
    ).first()
    if shade:
        return shade

    needle = normalize_shade_code(raw)
    bare = _bare_code(needle)
    candidates = (
        needle,
        f"PANTONE {bare}" if not needle.startswith("PANTONE") else None,
        f"RAL {bare}" if not needle.startswith("RAL") else None,
        bare,
    )
    wanted = {c for c in candidates if c}

    shades = RalPantoneShade.query.all()
    by_norm = {normalize_shade_code(s.shade_code): s for s in shades}
    for key in wanted:
        if key in by_norm:
            return by_norm[key]
    return None


def lab_for_shade(shade: RalPantoneShade) -> Optional[Tuple[float, float, float]]:
    """Stored LAB if present, otherwise hex → LAB."""
    if shade.L is not None and shade.a is not None and shade.b is not None:
        return (float(shade.L), float(shade.a), float(shade.b))
    if shade.hex_code:
        return hex_to_lab(shade.hex_code)
    return None


def resolve_shade(code: str) -> Optional[dict]:
    """Return a JSON-ready shade dict including lab, or None if unknown."""
    shade = find_shade(code)
    if shade is None:
        return None

    lab = lab_for_shade(shade)
    if lab is not None and (shade.L is None or shade.lab_source is None):
        shade.L, shade.a, shade.b = lab
        if not shade.lab_source:
            shade.lab_source = "hex"
        db.session.commit()

    payload = shade.to_dict()
    if payload["lab"] is None and lab is not None:
        payload["lab"] = {
            "L": round(lab[0], 2),
            "a": round(lab[1], 2),
            "b": round(lab[2], 2),
        }
        payload["lab_source"] = payload.get("lab_source") or "hex"
    return payload


def backfill_shade_lab() -> int:
    """Fill missing L/a/b from hex for rows already in the DB. Returns count updated."""
    updated = 0
    for shade in RalPantoneShade.query.filter(RalPantoneShade.L.is_(None)).all():
        lab = hex_to_lab(shade.hex_code) if shade.hex_code else None
        if lab is None:
            continue
        shade.L, shade.a, shade.b = lab
        if not shade.lab_source:
            shade.lab_source = "hex"
        updated += 1
    if updated:
        db.session.commit()
    return updated
