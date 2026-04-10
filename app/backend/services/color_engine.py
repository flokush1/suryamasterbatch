"""
Kubelka-Munk (K-M) color mixing engine.

Theory:
- For each pigment, full tone and tint tone (1:10 pigment:TiO2) LAB values are known.
- From tint tone LAB, K/S ratio for each wavelength channel can be derived.
- For a mixture, K/S values are additive weighted by concentration.
- Final R is computed from K/S, then converted to XYZ → LAB.

Simplified K-M approach used here (single-constant theory):
  K/S = (1 - R)^2 / (2 * R)  at each channel
  Mixture: (K/S)_mix = sum(ci * (K/S)_i)
  R_mix = 1 + (K/S) - sqrt((K/S)^2 + 2*(K/S))

We work directly in LAB space using the K-M approximation described by
Allen (1966) and Nobbs (1985), adapted for the simplified single wavelength
LAB channel model commonly used in practice.

For prediction, we use the tint tone data (pigment:TiO2 = 1:10) to extract
K and S coefficients and interpolate to other loadings.
"""
import math
from typing import List, Tuple, Optional


def lab_to_xyz(L: float, a: float, b: float) -> Tuple[float, float, float]:
    """Convert CIE L*a*b* to XYZ (D65 illuminant)."""
    fy = (L + 16) / 116
    fx = a / 500 + fy
    fz = fy - b / 200

    def f_inv(t):
        if t > 0.206897:
            return t ** 3
        return (t - 16 / 116) / 7.787

    X = 95.047 * f_inv(fx)
    Y = 100.000 * f_inv(fy)
    Z = 108.883 * f_inv(fz)
    return X, Y, Z


def xyz_to_lab(X: float, Y: float, Z: float) -> Tuple[float, float, float]:
    """Convert XYZ to CIE L*a*b* (D65 illuminant)."""
    def f(t):
        if t > 0.008856:
            return t ** (1 / 3)
        return 7.787 * t + 16 / 116

    fx = f(X / 95.047)
    fy = f(Y / 100.000)
    fz = f(Z / 108.883)

    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return L, a, b


def xyz_to_reflectance(X: float, Y: float, Z: float) -> Tuple[float, float, float]:
    """Per-channel reflectance from XYZ, normalised to the D65 white point
    (Xn=95.047, Yn=100.000, Zn=108.883).  All three values are in [0.001, 0.999]."""
    R = max(0.001, min(0.999, X / 95.047))
    G = max(0.001, min(0.999, Y / 100.000))
    B = max(0.001, min(0.999, Z / 108.883))
    return R, G, B


def reflectance_to_xyz(R: float, G: float, B: float) -> Tuple[float, float, float]:
    return R * 95.047, G * 100.0, B * 108.883


def ks_from_reflectance(R: float) -> float:
    """K/S ratio from reflectance using Kubelka-Munk single-constant theory."""
    R = max(0.001, min(0.999, R))
    return ((1 - R) ** 2) / (2 * R)


def reflectance_from_ks(ks: float) -> float:
    """Reflectance from K/S ratio."""
    return 1 + ks - math.sqrt(ks ** 2 + 2 * ks)


def lab_to_ks(L: float, a: float, b: float) -> Tuple[float, float, float]:
    """Compute K/S for each approximate channel from LAB."""
    X, Y, Z = lab_to_xyz(L, a, b)
    R, G, B = xyz_to_reflectance(X, Y, Z)
    return ks_from_reflectance(R), ks_from_reflectance(G), ks_from_reflectance(B)


def ks_to_lab(ks_r: float, ks_g: float, ks_b: float) -> Tuple[float, float, float]:
    R = reflectance_from_ks(ks_r)
    G = reflectance_from_ks(ks_g)
    B = reflectance_from_ks(ks_b)
    X, Y, Z = reflectance_to_xyz(R, G, B)
    return xyz_to_lab(X, Y, Z)


# ---------------------------------------------------------------------------
# TiO2 white-base K/S (module constant — needed by Pigment and predict_mixture_lab)
# Derived from typical rutile TiO2 full-tone: L≈99, a≈0, b≈1.5
# ---------------------------------------------------------------------------
_TIO2_KS: Tuple[float, float, float] = lab_to_ks(99.0, 0.0, 1.5)


# ---------------------------------------------------------------------------
# Pigment data structure
# ---------------------------------------------------------------------------

class Pigment:
    """
    Represents a single pigment with its full tone and tint tone LAB values.
    Tint tone is measured at pigment:TiO2 = 1:10 (i.e., 9.09% pigment loading).
    """
    TINT_CONCENTRATION = 1 / 11  # ~9.09% pigment in tint measurement

    def __init__(self, name: str,
                 full_L: float, full_a: float, full_b: float,
                 tint_L: float, tint_a: float, tint_b: float):
        self.name = name
        self.full_tone_lab = (full_L, full_a, full_b)
        self.tint_tone_lab = (tint_L, tint_a, tint_b)
        # Compute K/S of the tint-tone mixture (pigment + TiO2 together)
        self._ks_tint = lab_to_ks(tint_L, tint_a, tint_b)
        # Isolate the pigment's own K/S (per unit concentration, conc=1.0).
        # The tint measurement contains:
        #   K/S_tint = (1/11)*K/S_pig_unit + (10/11)*K/S_TiO2_unit
        # Solving: K/S_pig_unit = 11*K/S_tint - 10*K/S_TiO2_unit
        # Clamp to a small positive floor so dark channels don't go negative.
        self._ks_unit: Tuple[float, float, float] = tuple(
            max(1e-6, 11.0 * kt - 10.0 * kw)
            for kt, kw in zip(self._ks_tint, _TIO2_KS)
        )

    def ks_at_concentration(self, conc: float) -> Tuple[float, float, float]:
        """K/S contribution at pigment weight fraction `conc` (0 to 1)."""
        return tuple(k * conc for k in self._ks_unit)


def predict_mixture_lab(
    pigments_with_concentrations: List[Tuple["Pigment", float]],
    substrate_conc: float = 0.0,
    tio2_conc: float = 0.0,
    polymer_base_ks: Optional[Tuple[float, float, float]] = None,
) -> Tuple[float, float, float]:
    """
    Predict the LAB value of a pigment mixture using the Kubelka-Munk model.

    Args:
        pigments_withExact Matches in PE_concentrations: list of (Pigment, weight_fraction) tuples.
        substrate_conc: weight fraction of base polymer (no pigment contribution).
        tio2_conc: weight fraction of TiO2 white base.
        polymer_base_ks: optional K/S of the polymer base (if known); defaults to
                         near-clear polymer with very low K/S.

    Returns:
        Predicted (L, a, b) tuple.
    """
    # Start with polymer base K/S (nearly transparent / white polymer)
    if polymer_base_ks:
        ks_r, ks_g, ks_b = polymer_base_ks
    else:
        # Default: assume white/gray polymer base
        ks_r, ks_g, ks_b = 0.02, 0.02, 0.02

    # Add TiO2 contribution
    tio2_ks = tuple(k * tio2_conc for k in _TIO2_KS)
    ks_r += tio2_ks[0]
    ks_g += tio2_ks[1]
    ks_b += tio2_ks[2]

    # Add each pigment's contribution
    for pigment, conc in pigments_with_concentrations:
        pk = pigment.ks_at_concentration(conc)
        ks_r += pk[0]
        ks_g += pk[1]
        ks_b += pk[2]

    # Convert back to LAB
    return ks_to_lab(ks_r, ks_g, ks_b)


# ---------------------------------------------------------------------------
# Delta-E calculations
# ---------------------------------------------------------------------------

def delta_e_cie76(lab1: Tuple[float, float, float],
                  lab2: Tuple[float, float, float]) -> float:
    """CIE76 ΔE* (simple Euclidean in LAB space)."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab1, lab2)))


def delta_e_cie2000(lab1: Tuple[float, float, float],
                    lab2: Tuple[float, float, float]) -> float:
    """
    CIEDE2000 ΔE color difference — industry standard for color matching.
    Reference: Sharma et al. (2005).
    """
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    kL = kC = kH = 1.0

    # Step 1: C'ab
    C1 = math.sqrt(a1 ** 2 + b1 ** 2)
    C2 = math.sqrt(a2 ** 2 + b2 ** 2)
    C_avg_7 = ((C1 + C2) / 2) ** 7
    G = 0.5 * (1 - math.sqrt(C_avg_7 / (C_avg_7 + 25 ** 7)))
    a1p = a1 * (1 + G)
    a2p = a2 * (1 + G)
    C1p = math.sqrt(a1p ** 2 + b1 ** 2)
    C2p = math.sqrt(a2p ** 2 + b2 ** 2)

    # Step 2: h'
    def hprime(a, b):
        if a == 0 and b == 0:
            return 0
        h = math.degrees(math.atan2(b, a))
        return h + 360 if h < 0 else h

    h1p = hprime(a1p, b1)
    h2p = hprime(a2p, b2)

    # Step 3: ΔL', ΔC', Δh'
    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360

    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))

    # Step 4: CIEDE2000
    Lp_avg = (L1 + L2) / 2
    Cp_avg = (C1p + C2p) / 2

    if C1p * C2p == 0:
        hp_avg = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_avg = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hp_avg = (h1p + h2p + 360) / 2
    else:
        hp_avg = (h1p + h2p - 360) / 2

    T = (1
         - 0.17 * math.cos(math.radians(hp_avg - 30))
         + 0.24 * math.cos(math.radians(2 * hp_avg))
         + 0.32 * math.cos(math.radians(3 * hp_avg + 6))
         - 0.20 * math.cos(math.radians(4 * hp_avg - 63)))

    d_theta = 30 * math.exp(-((hp_avg - 275) / 25) ** 2)
    Cp_avg_7 = Cp_avg ** 7
    RC = 2 * math.sqrt(Cp_avg_7 / (Cp_avg_7 + 25 ** 7))
    SL = 1 + 0.015 * (Lp_avg - 50) ** 2 / math.sqrt(20 + (Lp_avg - 50) ** 2)
    SC = 1 + 0.045 * Cp_avg
    SH = 1 + 0.015 * Cp_avg * T
    RT = -math.sin(math.radians(2 * d_theta)) * RC

    dE = math.sqrt(
        (dLp / (kL * SL)) ** 2
        + (dCp / (kC * SC)) ** 2
        + (dHp / (kH * SH)) ** 2
        + RT * (dCp / (kC * SC)) * (dHp / (kH * SH))
    )
    return dE


def hex_to_lab(hex_color: str) -> Optional[Tuple[float, float, float]]:
    """Convert a hex color string (e.g. '#FF0000' or 'FF0000') to CIE L*a*b* (D65)."""
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0

        def linearize(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        rl, gl, bl = linearize(r), linearize(g), linearize(b)
        # Linear sRGB → XYZ D65 (IEC 61966-2-1, sRGB primaries)
        X = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) * 100
        Y = (0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl) * 100
        Z = (0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl) * 100
        return xyz_to_lab(X, Y, Z)
    except Exception:
        return None
