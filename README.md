# Surya Masterbatch — Colour Formulation System

An intelligent colour matching and recipe formulation system for masterbatch manufacturing. Given a target colour in CIE L\*a\*b\* values, the system suggests pigment recipes using three complementary engines — exact product lookup, Kubelka-Munk physics, and a machine learning model.

---

## What It Does

1. **Colour Search** — Enter a target L\*a\*b\* value + polymer type. The system returns:
   - **Exact matches** from existing formulated products (with ΔE score)
   - **K-M suggestions** — new pigment combinations predicted by Kubelka-Munk physics
   - **ML suggestions** — combinations predicted by a trained RandomForest/GradientBoosting model

2. **Feedback Loop** — After testing a recipe on the production floor:
   - Mark it as correct (one click) → saves as a training data point
   - Enter actual spectrophotometer reading → system self-corrects K-M coefficients and retrains ML model over time

3. **Product & Raw Material Library** — Browse products, recipes, pigment properties, compliance, fastness ratings, stock levels

4. **RAL / Pantone Lookup** — Find standard shade codes and translate to L\*a\*b\*

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.11 · Flask 3 · Flask-SQLAlchemy |
| Database | SQLite (`surya.db`) |
| Colour Science | Kubelka-Munk (K/S back-calculation), CIEDE2000 |
| ML Model | scikit-learn — RandomForestClassifier + GradientBoostingRegressor |
| Frontend | React 19 · Vite · Tailwind CSS · Recharts |
| Deployment | Docker + nginx reverse proxy |

---

## Folder Structure

```
SuryaMasterBatch/
├── app/
│   ├── backend/
│   │   ├── app.py              # Flask app factory
│   │   ├── run.py              # Entry point (python run.py)
│   │   ├── import_data.py      # Imports all CSV/XLSX data into SQLite
│   │   ├── requirements.txt
│   │   ├── models/
│   │   │   └── database.py     # All SQLAlchemy models
│   │   ├── routes/
│   │   │   ├── search.py       # /api/search, /api/retrain, /api/ml-status
│   │   │   ├── feedback.py     # /api/feedback (POST/GET/PATCH)
│   │   │   ├── products.py     # /api/products
│   │   │   ├── lab.py          # /api/lab-results
│   │   │   └── materials.py    # /api/raw-materials, /api/stocks
│   │   └── services/
│   │       ├── color_engine.py # Kubelka-Munk maths + CIEDE2000
│   │       ├── ml_engine.py    # ML model training + K-M calibration
│   │       └── search_engine.py# Search orchestration
│   └── frontend/
│       └── src/
│           ├── pages/          # ColorSearch, Products, LabData, etc.
│           └── api.js          # All Axios API calls
├── *.csv / *.xlsx              # Source data files (used by import_data.py)
├── surya.db                    # Live SQLite database (NOT in git)
├── setup_and_start.bat         # One-click setup for Windows (local dev)
├── docker-compose.yml          # Docker deployment
└── COLOR_MATH.md               # Kubelka-Munk theory reference
```

---

## Quick Start — Local Development (Windows)

### Prerequisites
- Python 3.11+ — https://python.org
- Node.js 18+ — https://nodejs.org
- Git

### Option A — One-click (Windows)

```bat
setup_and_start.bat
```

This installs all dependencies, imports data, and starts both servers. Open **http://localhost:5173** in your browser.

### Option B — Manual

**1. Clone the repo**
```bash
git clone <repo-url>
cd SuryaMasterBatch
```

**2. Set up Python environment**
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r app/backend/requirements.txt
```

**3. Import data into database**
```bash
cd app/backend
python import_data.py
```
This reads the CSV and XLSX files at the project root and populates `surya.db`.

**4. Start the backend**
```bash
cd app/backend
python run.py
# API is now running at http://localhost:5000
```

**5. Start the frontend** (new terminal)
```bash
cd app/frontend
npm install
npm run dev
# UI is now running at http://localhost:5173
```

---

## Quick Start — Docker (Recommended for Production)

```bash
# Copy the sample env file and set a strong secret key
cp .env.example .env          # edit SECRET_KEY inside

# Build and start everything (first run imports all data)
docker compose up --build

# App is live at http://localhost
# API is at http://localhost/api/  (also directly on :5000)
```

To stop:
```bash
docker compose down          # stops containers, keeps database
docker compose down -v       # stops containers AND wipes database
```

---

## All API Endpoints

Base URL: `http://localhost:5000` (local) or `http://localhost/api` (Docker)

### Colour Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/search` | Main colour search — returns exact matches, K-M suggestions, ML suggestions |
| `GET` | `/api/ml-status` | Check if ML model is trained/ready |
| `POST` | `/api/retrain` | Trigger ML model retrain from all feedback + lab data |
| `GET` | `/api/pigments?compliance=REACH` | List pigments (filter by compliance) |
| `GET` | `/api/ral-pantone?q=red` | Search RAL / Pantone shade codes |
| `GET` | `/api/cost/<product_id>` | Recipe cost estimate |

**Search request body:**
```json
{
  "target_L": 50.0,
  "target_a": 25.0,
  "target_b": 10.0,
  "polymer": "PE",
  "compliance": "REACH",
  "light_fastness": 6,
  "weather_fastness": 4,
  "heat_stability": 200,
  "top_n": 10
}
```

### Products

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/products?name=RED&polymer=PE` | List / search products |
| `GET` | `/api/products/<id>` | Full product detail with spec and recipe |
| `GET` | `/api/products/<id>/recipe` | Recipe only (list of raw materials + quantities) |
| `GET` | `/api/alpha-codes?polymer=PE` | Alpha code lookup |

### Lab Results

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/lab-results?product_id=30016` | Get measured LAB readings for a product |
| `POST` | `/api/lab-results` | Add a spectrophotometer reading |
| `DELETE` | `/api/lab-results/<id>` | Remove a reading |

### Raw Materials & Stock

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/raw-materials?type=PG&q=yellow` | List pigments / resins / additives |
| `GET` | `/api/raw-materials/<rm_id>` | Single material detail + stock |
| `GET` | `/api/stocks?q=carbon` | List all stock levels |

### Feedback (Learning Loop)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/feedback` | Submit feedback on a search suggestion |
| `GET` | `/api/feedback?suggestion_type=recipe` | List all feedback records |
| `PATCH` | `/api/feedback/<id>/confirm` | Add actual measured LAB to an existing feedback record |

**Feedback request body:**
```json
{
  "suggestion_type": "recipe",
  "target_lab": { "L": 50, "a": 10, "b": -5 },
  "polymer": "PE",
  "delta_e": 1.2,
  "product_id": "30016",
  "confirmed_L": 49.8,
  "confirmed_a": 10.1,
  "confirmed_b": -4.9,
  "notes": "Batch #A2201"
}
```
`suggestion_type` can be `"recipe"`, `"pigment_km"`, `"ml"`, or `"custom"`.

---

## How the Learning Loop Works

```
User searches colour → System returns 3 types of suggestions
         ↓
User tests recipe on production floor
         ↓
  ┌──────────────────────────────────┐
  │  "Yes, correct" (one click)      │  → Saves FeedbackRecord
  │  "Correction needed" (+ actual   │  → Saves FeedbackRecord
  │   spectrophotometer L*a*b*)      │    + LabResult with measured colour
  └──────────────────────────────────┘
         ↓
POST /api/retrain
         ↓
  ML model: new Product+recipe+LabResult rows are added to training corpus
            → RandomForest/GradientBoosting retrained on expanded data

  K-M model: confirmed single-colorant observations are used to back-calculate
             per-pigment K/S scale corrections
             → future K-M mixture predictions become more accurate
```

---

## Re-importing Data

If you update any of the source CSV/XLSX files:

```bash
cd app/backend
python import_data.py
```

This is safe to re-run — it upserts existing records.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `surya-masterbatch-dev-key` | Flask secret key — **change in production** |
| `DB_PATH` | `<project_root>/surya.db` | Path to SQLite database file |
| `DATA_DIR` | Project root | Directory containing source CSV/XLSX files |

---

## Polymer Codes

| Code | Material |
|---|---|
| `PE` | Polyethylene (LDPE/HDPE/LLDPE) |
| `PP` | Polypropylene |
| `ABS` | Acrylonitrile Butadiene Styrene |
| `SAN` | Styrene Acrylonitrile |
| `PVC` | Polyvinyl Chloride |
| `OTHER` | All other polymers |

---

## Compliance Codes

| Code | Standard |
|---|---|
| `NON-R` | No restriction |
| `ROHS1` | RoHS Directive 2002/95/EC |
| `ROHS2` | RoHS Directive 2011/65/EU |
| `REACH` | REACH Regulation (EC) 1907/2006 |
