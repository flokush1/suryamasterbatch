#!/bin/sh
# docker-entrypoint.sh — Initialises the database on first run, then starts Flask.
set -e

# Ensure the DB directory exists (Docker volume may not create it automatically)
DB_DIR=$(dirname "$DB_PATH")
mkdir -p "$DB_DIR"

# On first run (no database file) import all CSV/Excel data into SQLite
if [ ! -f "$DB_PATH" ]; then
    echo "============================================"
    echo " Surya Masterbatch — First-run data import"
    echo " DATA_DIR : $DATA_DIR"
    echo " DB_PATH  : $DB_PATH"
    echo "============================================"
    python import_data.py
    echo "[entrypoint] Data import complete."
else
    echo "[entrypoint] Database already exists at $DB_PATH — skipping import."
    echo "[entrypoint] To force re-import: delete the volume and restart."
fi

echo "[entrypoint] Starting Flask API on 0.0.0.0:5000 ..."
exec python run.py
