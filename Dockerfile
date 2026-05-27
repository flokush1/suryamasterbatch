# ── Surya Masterbatch — Backend Image ────────────────────────────────────────
# Builds the Flask API server.
# Data files (CSVs + Excel) are baked into /data at build time.
# The SQLite database is persisted via a Docker volume mounted at /db.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY app/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY app/backend/ ./

# Copy all data files (CSVs + Excel) into /data inside the image
COPY alphacode.csv              /data/
COPY clientproductmapping.csv   /data/
COPY lab_results.csv            /data/
COPY pigment_properties.csv     /data/
COPY product_spec.csv           /data/
COPY productrawmaterialmap.csv  /data/
COPY products.csv               /data/
COPY ral_pantone_shade.csv      /data/
COPY raw_material.csv           /data/
COPY stocks.csv                 /data/
COPY "Lab_Values_Color.xlsx"    /data/
COPY "FG MasterData (1).xlsx"   /data/

# Environment variables
ENV DATA_DIR=/data
ENV DB_PATH=/db/surya.db
ENV PYTHONUNBUFFERED=1

# Volume for the SQLite database (persists across container restarts)
VOLUME ["/db"]

EXPOSE 5000

# Entrypoint: initialises DB on first run, then starts the server
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
