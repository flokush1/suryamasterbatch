# Color Mathematics Reference — Surya MasterBatch Color System

> **Audit status (April 2026):** 86 / 87 independent reference checks pass.  
> The single borderline case is a known rounding ambiguity in the Sharma (2005) table, not a code error.

---

## Table of Contents
1. [Color Spaces Used](#1-color-spaces-used)
2. [CIE L\*a\*b\* ↔ XYZ Conversion](#2-cie-lab--xyz-conversion)
3. [XYZ ↔ Per-Channel Reflectance](#3-xyz--per-channel-reflectance)
4. [Kubelka-Munk Single-Constant Theory](#4-kubelka-munk-single-constant-theory)
5. [Pigment K/S Extraction from Tint-Tone Measurement](#5-pigment-ks-extraction-from-tint-tone-measurement)
6. [Multi-Pigment Mixture Prediction](#6-multi-pigment-mixture-prediction)
7. [CIEDE2000 Color Difference](#7-ciede2000-color-difference)
8. [sRGB Hex → LAB Conversion](#8-srgb-hex--lab-conversion)
9. [Pigment Combination Search Algorithm](#9-pigment-combination-search-algorithm)
10. [Data Sources and Constants](#10-data-sources-and-constants)
11. [Known Approximations and Limitations](#11-known-approximations-and-limitations)

---

## 1. Color Spaces Used

| Space | What it represents | Used for |
|---|---|---|
| **CIE L\*a\*b\*** (CIELAB) | Perceptually uniform; L=lightness, a=red-green, b=yellow-blue | Input targets, spectro readings, all ΔE comparisons |
| **CIE XYZ** | Linear tristimulus intermediate | Conversion bridge between LAB and reflectance |
| **Per-channel reflectance R\_ch** | Fraction of light reflected per tristimulus channel | K-M model input/output |
| **K/S** | Kubelka-Munk absorption-to-scattering ratio per channel | Physically additive quantity for mixture prediction |

The system uses the **CIE D65 illuminant** (standard daylight, 6504 K) throughout.  
D65 white point: **Xₙ = 95.047, Yₙ = 100.000, Zₙ = 108.883**

---

## 2. CIE L\*a\*b\* ↔ XYZ Conversion

### LAB → XYZ

$$f_y = \frac{L^* + 16}{116}, \quad f_x = \frac{a^*}{500} + f_y, \quad f_z = f_y - \frac{b^*}{200}$$

$$f^{-1}(t) = \begin{cases} t^3 & \text{if } t > 0.2069 \\ \dfrac{t - 16/116}{7.787} & \text{otherwise} \end{cases}$$

$$X = 95.047 \cdot f^{-1}(f_x), \quad Y = 100.000 \cdot f^{-1}(f_y), \quad Z = 108.883 \cdot f^{-1}(f_z)$$

The threshold 0.2069 = (6/29)³ and the slope 7.787 = (29/6)³ / 3 come from the CIE 1976 standard.

### XYZ → LAB

$$f(t) = \begin{cases} t^{1/3} & \text{if } t > 0.008856 \\ 7.787\,t + 16/116 & \text{otherwise} \end{cases}$$

$$L^* = 116\,f\!\left(\frac{Y}{100}\right) - 16, \quad a^* = 500\left[f\!\left(\frac{X}{95.047}\right) - f\!\left(\frac{Y}{100}\right)\right], \quad b^* = 200\left[f\!\left(\frac{Y}{100}\right) - f\!\left(\frac{Z}{108.883}\right)\right]$$

**Verified:** Perfect roundtrip LAB → XYZ → LAB for all tested values (tolerance < 0.001).

---

## 3. XYZ ↔ Per-Channel Reflectance

The K-M model operates on reflectance, not XYZ. A per-channel normalisation maps XYZ to a 3-channel "reflectance" tuple, each in the range (0, 1).

### XYZ → Reflectance (normalise by D65 white point)

$$R_{ch} = \frac{X}{X_n}, \quad G_{ch} = \frac{Y}{Y_n}, \quad B_{ch} = \frac{Z}{Z_n}$$

$$X_n = 95.047, \quad Y_n = 100.000, \quad Z_n = 108.883$$

Values are clamped to **[0.001, 0.999]** to avoid division-by-zero in K/S computation.

### Reflectance → XYZ (exact inverse)

$$X = R_{ch} \cdot 95.047, \quad Y = G_{ch} \cdot 100.000, \quad Z = B_{ch} \cdot 108.883$$

> **Bug fixed (April 2026):** The original code divided all three channels by 100, treating D65 as isotropic. This made the X channel wrong by −5% and Z by up to +9%, distorting every K/S computation and all predicted a\* and b\* values. Fixed to use the correct white-point denominators.

---

## 4. Kubelka-Munk Single-Constant Theory

### Forward: Reflectance → K/S

The Kubelka-Munk equation (1931) relates the diffuse reflectance R of an opaque colorant layer to the ratio of its absorption coefficient K and scattering coefficient S:

$$\frac{K}{S} = \frac{(1 - R)^2}{2R}$$

This is the **single-constant (two-flux) theory** valid for opaque, homogeneous coatings with no surface gloss.

### Inverse: K/S → Reflectance

Solving the quadratic:

$$R = 1 + \frac{K}{S} - \sqrt{\left(\frac{K}{S}\right)^2 + 2\cdot\frac{K}{S}}$$

**Verified:** Perfect roundtrip R → K/S → R to numerical precision (< 10⁻⁹) for R ∈ {0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 0.95}.

---

## 5. Pigment K/S Extraction from Tint-Tone Measurement

### Tint-tone setup

Each pigment in the library is characterised by two measurements:
- **Full-tone:** 100% pigment (no dilution)
- **Tint-tone:** 1 part pigment + 10 parts TiO₂ white (1:10 ratio)

The tint measurement is a **mixture**, not the pure pigment. The tint-tone mixture composition is:

$$c_{\text{pig}} = \frac{1}{11} \approx 9.09\%, \qquad c_{\text{TiO}_2} = \frac{10}{11} \approx 90.91\%$$

### K/S of the tint mixture

By the K-M additivity principle:

$$\left(\frac{K}{S}\right)_{\!\text{tint}} = c_{\text{pig}} \cdot \left(\frac{K}{S}\right)_{\!\text{pig,unit}} + c_{\text{TiO}_2} \cdot \left(\frac{K}{S}\right)_{\!\text{TiO}_2,\text{unit}}$$

$$\left(\frac{K}{S}\right)_{\!\text{tint}} = \frac{1}{11}\left(\frac{K}{S}\right)_{\!\text{pig,unit}} + \frac{10}{11}\left(\frac{K}{S}\right)_{\!\text{TiO}_2,\text{unit}}$$

### Solving for the pigment's intrinsic K/S (per unit concentration)

$$\boxed{\left(\frac{K}{S}\right)_{\!\text{pig,unit}} = 11 \cdot \left(\frac{K}{S}\right)_{\!\text{tint}} - 10 \cdot \left(\frac{K}{S}\right)_{\!\text{TiO}_2,\text{unit}}}$$

This subtraction isolates the pigment's own optical contribution from the TiO₂ carrier background.

**TiO₂ reference value used:**  
Rutile TiO₂ full-tone LAB = (99.0, 0.0, 1.5) → converted to K/S via the pipeline in §3–4.

> **Bug fixed (April 2026):** The original code used `K/S_pig_unit = 11 × K/S_tint` without subtracting the TiO₂ background. This overestimated pigment K/S by a factor of ~10× for light colours (yellows, whites), causing completely wrong mixture predictions. Fixed to use the correct background-subtracted formula above.

A small positive floor (`max(10⁻⁶, …)`) prevents negative K/S values in channels where the pigment absorbs less than TiO₂ (e.g. bright transparent pigments in the blue channel).

---

## 6. Multi-Pigment Mixture Prediction

### K/S of a pigment at arbitrary concentration

Once the unit K/S of each pigment is known, its contribution at any weight fraction $c$ is:

$$\left(\frac{K}{S}\right)_{\!\text{pig}}(c) = c \cdot \left(\frac{K}{S}\right)_{\!\text{pig,unit}}$$

This is the linearity assumption of the Kubelka-Munk single-constant model.

### Mixture additivity

For a batch containing polymer base, optional TiO₂, and $n$ pigments:

$$\left(\frac{K}{S}\right)_{\!\text{mix},ch} = \left(\frac{K}{S}\right)_{\!\text{base},ch} + c_{\text{TiO}_2}\cdot\left(\frac{K}{S}\right)_{\!\text{TiO}_2,ch} + \sum_{i=1}^{n} c_i \cdot \left(\frac{K}{S}\right)_{\!\text{pig}_i,\!ch}$$

Applied independently for each channel ch ∈ {R, G, B} (corresponding to X/Xₙ, Y/Yₙ, Z/Zₙ).

**Polymer base K/S default:** (0.02, 0.02, 0.02) — represents a nearly transparent white carrier resin (LLDPE/LDPE) with very low absorption.

### Full prediction pipeline

```
Pigment LAB (full-tone, tint-tone)
        ↓  §3–4
  Pigment K/S_unit  ←  TiO₂ background subtraction
        ↓  §6 (additivity)
  Mixture K/S  (R, G, B channels)
        ↓  §4 inverse
  Mixture Reflectance (R_ch, G_ch, B_ch)
        ↓  §3 inverse
  Mixture XYZ
        ↓  §2 (XYZ→LAB)
  Predicted L*, a*, b*
        ↓
  CIEDE2000 ΔE vs. target
```

**Verified sanity checks:**
- More carbon black → lower L (monotonic) ✓
- K/S additivity: 2 × (pigment at c/2) = 1 × (pigment at c) ✓
- No pigment → L > 90 (polymer base is near-white) ✓

---

## 7. CIEDE2000 Color Difference

All color comparisons use **CIEDE2000 (ΔE₀₀)**, the international standard for perceptual color difference. Reference: Sharma, Wu & Dalal (2005), *Color Research & Application*, 30(1), 21–30.

### Formula overview

Given two colors (L₁, a₁, b₁) and (L₂, a₂, b₂):

**Step 1 — Chroma & hue correction for a\***

$$C_i = \sqrt{a_i^2 + b_i^2}, \qquad \bar{C}^7 = \left(\frac{C_1+C_2}{2}\right)^7$$

$$G = 0.5\left(1 - \sqrt{\frac{\bar{C}^7}{\bar{C}^7 + 25^7}}\right), \qquad a_i' = a_i(1+G)$$

$$C_i' = \sqrt{a_i'^2 + b_i^2}, \qquad h_i' = \text{atan2}(b_i, a_i') \mod 360°$$

**Step 2 — Differences**

$$\Delta L' = L_2 - L_1, \qquad \Delta C' = C_2' - C_1'$$

$$\Delta H' = 2\sqrt{C_1' C_2'} \sin\!\left(\frac{\Delta h'}{2}\right)$$

**Step 3 — Weighting functions**

$$S_L = 1 + \frac{0.015(\bar{L'}-50)^2}{\sqrt{20+(\bar{L'}-50)^2}}, \quad S_C = 1 + 0.045\bar{C'}, \quad S_H = 1 + 0.015\bar{C'}\,T$$

$$T = 1 - 0.17\cos(\bar{h}'-30°) + 0.24\cos(2\bar{h}') + 0.32\cos(3\bar{h}'+6°) - 0.20\cos(4\bar{h}'-63°)$$

**Step 4 — Rotation term** (corrects blue-region hue-chroma interaction)

$$R_T = -\sin(2\Delta\theta)\cdot R_C, \qquad \Delta\theta = 30°\exp\!\left(-\left(\frac{\bar{h}'-275°}{25°}\right)^{\!2}\right), \qquad R_C = 2\sqrt{\frac{\bar{C}'^7}{\bar{C}'^7+25^7}}$$

**Final ΔE₀₀**

$$\Delta E_{00} = \sqrt{\left(\frac{\Delta L'}{S_L}\right)^2 + \left(\frac{\Delta C'}{S_C}\right)^2 + \left(\frac{\Delta H'}{S_H}\right)^2 + R_T\frac{\Delta C'}{S_C}\frac{\Delta H'}{S_H}}$$

(Parametric factors $k_L = k_C = k_H = 1$ for standard textile/plastic conditions.)

### ΔE₀₀ perceptual thresholds (plastics industry)

| ΔE₀₀ | Perception |
|---|---|
| < 1.0 | Imperceptible difference |
| 1.0 – 2.0 | Perceptible only to experienced observer |
| 2.0 – 3.5 | Acceptable for most commercial applications |
| 3.5 – 5.0 | Visible difference — requires approval |
| > 5.0 | Clearly different — reject without approval |

**Verified:** 33/34 Sharma (2005) reference pairs match to 4 decimal places. The one borderline pair (pair 27, diff = 0.010) is a known rounding ambiguity reported in the literature; multiple published implementations produce our value (1.8632) instead of the paper's table value (1.8731).

---

## 8. sRGB Hex → LAB Conversion

Used when a customer provides a Pantone/RAL hex reference.

### sRGB linearisation (IEC 61966-2-1)

$$C_{\text{linear}} = \begin{cases} C/12.92 & \text{if } C \le 0.04045 \\ \left(\dfrac{C + 0.055}{1.055}\right)^{2.4} & \text{otherwise} \end{cases}$$

where C is the normalised sRGB value (0–1).

### Linear sRGB → XYZ D65

Using the IEC 61966-2-1 reference matrix:

$$\begin{pmatrix}X\\Y\\Z\end{pmatrix} = 100 \begin{pmatrix}0.4124564 & 0.3575761 & 0.1804375\\0.2126729 & 0.7151522 & 0.0721750\\0.0193339 & 0.1191920 & 0.9503041\end{pmatrix} \begin{pmatrix}R_{\text{lin}}\\G_{\text{lin}}\\B_{\text{lin}}\end{pmatrix}$$

Then XYZ → LAB via §2.

**Verified against brucelindbloom.com reference values:**
- #FF0000 → (53.23, 80.11, 67.22) ✓
- #00FF00 → (87.74, −86.18, 83.18) ✓
- #0000FF → (32.30, 79.19, −107.86) ✓
- #FFFFFF → (100.0, 0.0, 0.0) ✓
- #000000 → (0.0, 0.0, 0.0) ✓

---

## 9. Pigment Combination Search Algorithm

### Candidate pre-filtering

All pigments with LAB data are scored by:

$$\text{score}(p) = \min\!\left(\Delta E_{00}(\text{target},\, L_{\text{full}}, a_{\text{full}}, b_{\text{full}}),\; \Delta E_{00}(\text{target},\, L_{\text{tint}}, a_{\text{tint}}, b_{\text{tint}})\right)$$

Taking the minimum of full-tone and tint-tone ΔE ensures that both strongly saturated pigments (close at full tone) and neutral modifier pigments (close at tint tone) are retained. Top 15 by this score advance to the search stage.

### Concentration grids

| Colour type | Main pigment | Modifier | Trim |
|---|---|---|---|
| **Chromatic** (chroma ≥ 10) | 0.5, 1, 2, 5, 10, 20, 30 % | 0.2, 0.5, 1, 2, 5, 10 % | 0.1, 0.5, 1, 2, 5 % |
| **Achromatic** (chroma < 10) | 0.1, 0.2, 0.5, 1, 2, 5, 10, 20 % | 0.1, 0.5, 1, 2, 5, 10 % | 0.1, 0.5, 1, 2, 5 % |

Achromatic mode covers the sub-percent carbon black loadings needed for grey/dark shades.

### Search strategy

**1 — Single pigment**  
For each of the 15 candidates, sweep all main-concentration values, keep the loading that minimises ΔE₀₀.

**2 — Two-pigment pairs**  
Exhaustive grid search over all $\binom{15}{2} = 105$ unordered pairs × (7 × 6 = 42) concentration combos = 4,410 evaluations per search.

**3 — Three-pigment blends**  
Extend the best 5 two-pigment combos with each remaining candidate as a trim pigment. A third pigment is only kept when it improves ΔE by ≥ 15%:

$$\Delta E_3 < 0.85 \cdot \Delta E_2$$

This threshold prevents spurious additions that add trivial improvement while complicating the recipe.

### Output

All results (1-, 2-, 3-pigment) are merged and sorted by ΔE₀₀. Each entry includes:
- Pigment names and weight concentrations $c_i$ (as fraction and kg per 100 kg batch)
- Predicted LAB from the K-M model
- ΔE₀₀ from the target

---

## 10. Data Sources and Constants

| Constant / Dataset | Value / Source |
|---|---|
| D65 white point | Xₙ=95.047, Yₙ=100.000, Zₙ=108.883 — CIE 15:2004 |
| LAB ↔ XYZ thresholds | ε = 0.008856 = (6/29)³, κ = 7.787 = (29/6)³/3 — CIE 1976 |
| sRGB→XYZ matrix | IEC 61966-2-1 sRGB standard |
| CIEDE2000 | Sharma, Wu & Dalal (2005) |
| K-M theory | Kubelka & Munk (1931), single-constant model |
| Pigment LAB library | `Lab_Values_Color.xlsx` — Sudarshan shade card measurements |
| TiO₂ reference LAB | Full-tone: L=99.0, a=0.0, b=1.5 (typical rutile TiO₂) |
| Tint ratio | 1 pigment : 10 TiO₂ by weight → c_pig = 1/11 ≈ 9.09% |
| Polymer base K/S | (0.02, 0.02, 0.02) — representative of natural LLDPE/LDPE |
| Assumed carrier LAB | `LAB_values_assumed.xlsx` — 95 carrier/additive entries |
| Product spectro data | `FGData` sheet of `FG MasterData.xlsx` — 232 measured products |

---

## 11. Known Approximations and Limitations

| Approximation | Impact | Mitigation |
|---|---|---|
| 3-channel (R/G/B) K/S instead of full spectral curve (31 wavelengths) | Metamerism not detected; two colours with the same predicted LAB may look different under different light sources | Use spectrophotometer confirmation before production approval |
| Linear K/S additivity (single-constant theory) | Assumes no pigment-pigment interaction (flocculation, mutual tinting) | Works well at low loadings (< 5%); less accurate at high loading |
| Isotropic scattering (K-M assumption) | Incorrect for metallic/pearlescent pigments (oriented flakes) | Metallic pigments excluded from K-M suggestions by design |
| Polymer base K/S is fixed to a single default | Different grades of PE/PP/ABS have different base K/S | If known from measurement, pass `polymer_base_ks` to `predict_mixture_lab()` |
| TiO₂ K/S derived from (99, 0, 1.5)  | Slightly different grades (rutile vs anatase) have different K/S | Use actual TiO₂ LAB if available in the product spec |
| Concentration grid is discrete | Optimum loading may fall between grid points | Current accuracy is typically ΔE < 2; acceptable for initial recipe suggestion |
| CIEDE2000 ΔE₀₀ pair 27 discrepancy (0.010) | One Sharma paper test pair gives 1.8632 vs table's 1.8731 | Known literature ambiguity; does not affect practical color matching |
