#!/usr/bin/env python3
"""
Startup script for the Surya Masterbatch backend.
Run from the app/backend/ directory:
    python run.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.database import db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    print("Starting Surya Masterbatch API on http://localhost:5000")
    app.run(debug=True, port=5000, host="0.0.0.0")
