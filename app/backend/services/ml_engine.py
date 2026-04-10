"""
ML Recipe Predictor
===================
Trains per-pigment RandomForest classifiers + GradientBoosting regressors from
all historical recipe data. At prediction time, given a target LAB + polymer,
it produces a recipe suggestion that is a *learned generalisation* — not a
simple nearest-neighbour lookup.

Why this genuinely learns (not retrieves):
------------------------------------------
- RandomForestClassifier splits the 12-dimensional feature space into
  non-linear decision regions.  For each region it predicts which pigments
  belong.  This works for colours that were *never* in the training set —
  the model interpolates based on the learned boundaries (e.g. "high a* AND
  negative b* → PV23 likely").

- GradientBoostingRegressor fits a smooth non-linear curve mapping
  (L*, a*, b*, chroma, hue, polymer) → concentration.  It can produce
  concentrations between any two observed values — genuine interpolation,
  not copying.

Training pipeline:
  1. Build corpus from all products with non-empty recipes.
     LAB source: measured LabResult rows (priority) → K-M predicted (fallback).
  2. Per-pigment that appears in ≥ MIN_SAMPLES recipes:
       - RandomForestClassifier  → P(pigment used | colour + polymer)
       - GradientBoostingRegressor → conc | pigment is used
  3. TiO2 fraction model: GradientBoosting on L* only (higher L* → more TiO2).
  4. Training runs in a background thread so app startup is instant.
"""

import json
import math
import logging
import threading
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POLYMERS = ["PE", "PP", "ABS", "SAN", "PVC", "OTHER"]

# Minimum appearances in recipes for a pigment to get its own model
MIN_SAMPLES = 3

# Chemical-name keywords that identify TiO2 / white pigment
TIO2_CHEM_KEYWORDS = ["PIGMENT WHITE", "TITANIUM DIOXIDE", "TITANIUM", "TIO2"]

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _poly_onehot(polymer: str) -> List[float]:
    p = polymer.upper()
    return [1.0 if p == poly else 0.0 for poly in POLYMERS]


def _feature_vector(L: float, a: float, b: float, polymer: str) -> List[float]:
    """
    12-dimensional feature vector used by all models.

    Dimensions 0-5   : colour descriptors
      0 : L* / 100                    (0→1)
      1 : a* / 128                    (-1→+1)
      2 : b* / 128                    (-1→+1)
      3 : chroma C* / 181             (0→1)  C* = sqrt(a²+b²)
      4 : sin(hue)                    (-1→+1) circular encoding avoids
      5 : cos(hue)                    (-1→+1) discontinuity at ±180°
    Dimensions 6-11  : polymer one-hot [PE, PP, ABS, SAN, PVC, OTHER]
    """
    C = math.sqrt(a ** 2 + b ** 2)
    h = math.atan2(b, a)
    return [
        L / 100.0,
        a / 128.0,
        b / 128.0,
        C / 181.0,
        math.sin(h),
        math.cos(h),
    ] + _poly_onehot(polymer)


# ---------------------------------------------------------------------------
# Model class
# ---------------------------------------------------------------------------

class MLRecipeModel:
    """
    Holds all trained models and exposes predict().
    Instantiate once; call train_async(app) at startup.
    """

    def __init__(self):
        self.is_trained = False
        self._training_error: Optional[str] = None
        self._pig_clf: Dict[str, object] = {}    # rm_id → RandomForestClassifier
        self._pig_reg: Dict[str, object] = {}    # rm_id → GradientBoostingRegressor
        self._tio2_reg = None                    # L* → TiO2 fraction
        self._pig_meta: Dict[str, Dict] = {}     # rm_id → display info
        self._tio2_rm_ids: set = set()
        self.stats: Dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train_async(self, app):
        """Start background training thread — does not block app startup."""
        t = threading.Thread(target=self._train, args=(app,), daemon=True)
        t.start()

    def predict(
        self,
        L: float,
        a: float,
        b: float,
        polymer: str,
        top_n: int = 3,
    ) -> List[Dict]:
        """
        Return up to top_n recipe suggestions as dicts.
        Suggestions range from 1-colorant to 3-colorant blends.
        Returns [] if model is not yet trained.
        """
        if not self.is_trained:
            return []

        feats = _feature_vector(L, a, b, polymer)

        # --- Score each trained pigment -----------------------------------
        scored: List[Tuple[str, float, float]] = []
        for rm_id, clf in self._pig_clf.items():
            try:
                prob = float(clf.predict_proba([feats])[0][1])
            except Exception:
                continue

            reg = self._pig_reg.get(rm_id)
            try:
                conc = max(0.001, float(reg.predict([feats])[0])) if reg else 0.01
            except Exception:
                conc = 0.01

            # Expected contribution: P(used) × predicted_concentration
            scored.append((rm_id, prob, conc))

        scored.sort(key=lambda x: x[1] * x[2], reverse=True)

        # --- Predicted TiO2 from L* ---------------------------------------
        tio2_frac = 0.0
        if self._tio2_reg:
            try:
                tio2_frac = max(0.0, float(self._tio2_reg.predict([[L / 100.0]])[0]))
            except Exception:
                pass

        # --- Build 1-, 2-, 3-colorant suggestions -------------------------
        suggestions = []
        for n_colorants in [1, 2, 3]:
            if len(scored) < n_colorants:
                continue
            pigs = scored[:n_colorants]
            sug = self._build_suggestion(pigs, tio2_frac, polymer)
            if sug:
                suggestions.append(sug)

        return suggestions[:top_n]

    # ------------------------------------------------------------------
    # Training internals
    # ------------------------------------------------------------------

    def _train(self, app):
        try:
            from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor  # noqa: F401
        except ImportError:
            self._training_error = "scikit-learn not installed — run: pip install scikit-learn"
            logger.error(self._training_error)
            return

        logger.info("ML: training started (background thread)…")
        try:
            with app.app_context():
                self._train_inner()
        except Exception as exc:
            logger.exception("ML: training failed")
            self._training_error = str(exc)

    def _train_inner(self):
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
        from models.database import Product, RawMaterial, LabResult
        from services.color_engine import Pigment, predict_mixture_lab

        # ── 1. Raw materials ───────────────────────────────────────────────
        all_rms: Dict[str, object] = {
            rm.rawmaterialid: rm for rm in RawMaterial.query.all()
        }

        # Identify TiO2 / white pigment IDs
        self._tio2_rm_ids = set()
        for rm_id, rm in all_rms.items():
            chem = (rm.chemical_name or "").upper()
            name = (rm.rawmaterialname or "").upper()
            if any(kw in chem for kw in TIO2_CHEM_KEYWORDS) or "TT " in name:
                self._tio2_rm_ids.add(rm_id)

        # ── 2. Measured LAB lookup ─────────────────────────────────────────
        measured: Dict[str, Dict[str, Tuple]] = {}
        for lr in LabResult.query.all():
            measured.setdefault(lr.product_id, {})[lr.polymer.upper()] = (
                lr.L, lr.a, lr.b
            )

        # ── 3. Build corpus ────────────────────────────────────────────────
        corpus: List[Dict] = []
        for prod in Product.query.all():
            recipe = prod.recipe_items
            if not recipe:
                continue
            total_kg = sum(r.qtyinkg or 0.0 for r in recipe)
            if total_kg < 0.01:
                continue

            lab_map = measured.get(prod.id, {})
            if lab_map:
                # One training sample per (product, measured_polymer) pair
                for polymer, lab in lab_map.items():
                    s = self._make_sample(recipe, all_rms, total_kg, lab, polymer)
                    if s:
                        corpus.append(s)
            else:
                # Fall back to K-M colour prediction
                polymer = self._infer_polymer(prod)
                lab = self._km_predict(recipe, all_rms, total_kg)
                if lab:
                    s = self._make_sample(recipe, all_rms, total_kg, lab, polymer)
                    if s:
                        corpus.append(s)

        self.stats["corpus_size"] = len(corpus)

        if len(corpus) < 5:
            logger.warning(
                f"ML: only {len(corpus)} training samples — need at least 5. "
                "Add more products with recipes to enable ML predictions."
            )
            return

        logger.info(f"ML: corpus = {len(corpus)} samples")

        # ── 4. Feature matrix ──────────────────────────────────────────────
        X_all = [_feature_vector(s["L"], s["a"], s["b"], s["polymer"]) for s in corpus]

        # ── 5. Count pigment appearances ───────────────────────────────────
        appearances: Dict[str, int] = {}
        for s in corpus:
            for rm_id in s["pigments"]:
                appearances[rm_id] = appearances.get(rm_id, 0) + 1

        trainable = [rm_id for rm_id, cnt in appearances.items() if cnt >= MIN_SAMPLES]
        self.stats["trainable_pigments"] = len(trainable)

        # Store display metadata
        for rm_id in trainable:
            rm = all_rms.get(rm_id)
            self._pig_meta[rm_id] = {
                "name": rm.rawmaterialname if rm else rm_id,
                "ci_name": getattr(rm, "ci_name", None),
                "full_tone_L": getattr(rm, "full_tone_L", None),
                "full_tone_a": getattr(rm, "full_tone_a", None),
                "full_tone_b": getattr(rm, "full_tone_b", None),
            }

        # ── 6. Per-pigment classifier + regressor ──────────────────────────
        n_clf = n_reg = 0
        for rm_id in trainable:
            y_cls = [1 if rm_id in s["pigments"] else 0 for s in corpus]
            if sum(y_cls) < MIN_SAMPLES:
                continue

            clf = RandomForestClassifier(
                n_estimators=150,
                max_depth=8,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=42,
                n_jobs=1,
            )
            try:
                clf.fit(X_all, y_cls)
                self._pig_clf[rm_id] = clf
                n_clf += 1
            except Exception as exc:
                logger.debug(f"ML: clf failed for {rm_id}: {exc}")
                continue

            # Regressor trained only on samples where pigment IS used
            X_reg = [X_all[i] for i, s in enumerate(corpus) if rm_id in s["pigments"]]
            y_reg = [s["pigments"][rm_id] for s in corpus if rm_id in s["pigments"]]
            if len(X_reg) < 3:
                continue

            reg = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.1,
                min_samples_leaf=2,
                random_state=42,
            )
            try:
                reg.fit(X_reg, y_reg)
                self._pig_reg[rm_id] = reg
                n_reg += 1
            except Exception as exc:
                logger.debug(f"ML: reg failed for {rm_id}: {exc}")

        # ── 7. TiO2 fraction model (L* only) ──────────────────────────────
        X_tio2 = [[s["L"] / 100.0] for s in corpus if s["tio2"] > 0.001]
        y_tio2 = [s["tio2"] for s in corpus if s["tio2"] > 0.001]
        if len(X_tio2) >= 5:
            tio2_reg = GradientBoostingRegressor(
                n_estimators=80, max_depth=3, learning_rate=0.1, random_state=42
            )
            try:
                tio2_reg.fit(X_tio2, y_tio2)
                self._tio2_reg = tio2_reg
            except Exception:
                pass

        self.is_trained = True
        logger.info(
            f"ML: ready — corpus={len(corpus)}, pig_clf={n_clf}, "
            f"pig_reg={n_reg}, tio2={'yes' if self._tio2_reg else 'no'}"
        )

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_polymer(prod) -> str:
        """Derive polymer from alpha_code prefix (E→PE, C→PP, S→ABS)."""
        try:
            codes = json.loads((prod.alphacode or "").replace("'", '"'))
        except Exception:
            codes = []
        prefix_map = {"E": "PE", "C": "PP", "S": "ABS", "O": "OTHER"}
        for code in codes:
            ch = str(code)[0].upper() if code else ""
            if ch in prefix_map:
                return prefix_map[ch]
        return "PE"

    @staticmethod
    def _km_predict(recipe, all_rms, total_kg) -> Optional[Tuple[float, float, float]]:
        """Predict LAB via K-M model for a product without a LabResult."""
        from services.color_engine import Pigment, predict_mixture_lab
        pigs = []
        for r in recipe:
            rm = all_rms.get(r.rawmaterialid)
            if rm and rm.type == "PG" and rm.full_tone_L is not None:
                try:
                    pig = Pigment(
                        name=rm.rawmaterialid,
                        full_L=rm.full_tone_L,
                        full_a=rm.full_tone_a or 0.0,
                        full_b=rm.full_tone_b or 0.0,
                        tint_L=rm.tint_tone_L or rm.full_tone_L,
                        tint_a=rm.tint_tone_a or 0.0,
                        tint_b=rm.tint_tone_b or 0.0,
                    )
                    pigs.append((pig, (r.qtyinkg or 0.0) / total_kg))
                except Exception:
                    pass
        if not pigs:
            return None
        try:
            return predict_mixture_lab(pigs)
        except Exception:
            return None

    def _make_sample(self, recipe, all_rms, total_kg, lab, polymer) -> Optional[Dict]:
        pig_fracs: Dict[str, float] = {}
        tio2_frac = 0.0
        for r in recipe:
            rm = all_rms.get(r.rawmaterialid)
            if not rm or not r.qtyinkg:
                continue
            frac = r.qtyinkg / total_kg
            if rm.type == "PG":
                if r.rawmaterialid in self._tio2_rm_ids:
                    tio2_frac += frac
                else:
                    pig_fracs[r.rawmaterialid] = (
                        pig_fracs.get(r.rawmaterialid, 0.0) + frac
                    )
        if not pig_fracs and tio2_frac < 0.001:
            return None   # no coloring pigments — not useful for training
        return {
            "L": float(lab[0]),
            "a": float(lab[1]),
            "b": float(lab[2]),
            "polymer": polymer,
            "pigments": pig_fracs,
            "tio2": tio2_frac,
        }

    def _build_suggestion(self, pigs, tio2_frac, polymer) -> Optional[Dict]:
        pig_total = sum(c for _, _, c in pigs)
        base_frac = max(0.0, 1.0 - pig_total - tio2_frac)
        grand_total = pig_total + tio2_frac + base_frac

        if grand_total < 1e-9:
            return None

        components = []

        # Colorants
        for rm_id, prob, conc in pigs:
            meta = self._pig_meta.get(rm_id, {})
            pct = round((conc / grand_total) * 100, 3)
            components.append({
                "rawmaterialid": rm_id,
                "name": meta.get("name", rm_id),
                "ci_name": meta.get("ci_name"),
                "role": "colorant",
                "pct": pct,
                "kg_per_100kg": pct,
                "confidence_pct": round(prob * 100, 1),
                "full_tone_L": meta.get("full_tone_L"),
                "full_tone_a": meta.get("full_tone_a"),
                "full_tone_b": meta.get("full_tone_b"),
            })

        # TiO2
        if tio2_frac > 0.005:
            pct = round((tio2_frac / grand_total) * 100, 2)
            components.append({
                "rawmaterialid": "TIO2",
                "name": "TiO₂ (white pigment)",
                "role": "opacity",
                "pct": pct,
                "kg_per_100kg": pct,
                "confidence_pct": 100.0,
                "full_tone_L": 99.0,
                "full_tone_a": 0.0,
                "full_tone_b": 1.5,
            })

        # Base resin
        base_pct = round((base_frac / grand_total) * 100, 2)
        components.append({
            "rawmaterialid": "BASE",
            "name": f"{polymer} base resin + fillers",
            "role": "carrier",
            "pct": base_pct,
            "kg_per_100kg": base_pct,
            "confidence_pct": 100.0,
        })

        colorant_confs = [c["confidence_pct"] for c in components if c["role"] == "colorant"]
        avg_conf = sum(colorant_confs) / max(1, len(colorant_confs))

        return {
            "components": components,
            "n_colorants": len(pigs),
            "avg_confidence_pct": round(avg_conf, 1),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_model: Optional[MLRecipeModel] = None


def init_ml_model(app) -> None:
    """
    Call once at application startup (after DB is ready).
    Training runs in a background thread — startup is not blocked.
    """
    global _model
    _model = MLRecipeModel()
    _model.train_async(app)


def get_ml_suggestions(
    L: float,
    a: float,
    b: float,
    polymer: str,
    top_n: int = 3,
) -> List[Dict]:
    """Return ML recipe suggestions. Returns [] if model is still training."""
    if _model is None or not _model.is_trained:
        return []
    return _model.predict(L, a, b, polymer, top_n=top_n)


def get_ml_status() -> Dict:
    """Status dict for health-check / debug endpoint."""
    if _model is None:
        return {"status": "not_initialized"}
    if _model._training_error:
        return {"status": "error", "detail": _model._training_error}
    if not _model.is_trained:
        return {"status": "training"}
    return {
        "status": "ready",
        "corpus_size": _model.stats.get("corpus_size", 0),
        "trainable_pigments": _model.stats.get("trainable_pigments", 0),
    }
