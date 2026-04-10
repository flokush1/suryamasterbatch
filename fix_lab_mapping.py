"""
Script to:
1. Show all LAB_xxx pigments vs actual PG raw materials
2. Match by name and update real RM entries with LAB data
3. Remove synthetic LAB_xxx entries
"""
import sys
sys.path.insert(0, 'c:/Users/kushp/Downloads/SuryaMasterBatch/app/backend')
from app import create_app
app = create_app()

with app.app_context():
    from models.database import db, RawMaterial
    from sqlalchemy import text

    # Show all LAB_xxx pigments
    lab_pigs = RawMaterial.query.filter(RawMaterial.rawmaterialid.like('LAB_%')).all()
    print('=== LAB_xxx pigments (from Excel) ===')
    for p in lab_pigs:
        print(f'  {p.rawmaterialid}: "{p.rawmaterialname}" L={p.full_tone_L}')

    print()
    # Show all PG raw materials in recipes
    pg_in_recipes = db.session.execute(text('''
        SELECT DISTINCT rm.rawmaterialid, rm.rawmaterialname
        FROM raw_material rm
        JOIN product_raw_material_map prm ON rm.rawmaterialid = prm.rawmaterialid
        WHERE rm.type = 'PG'
        ORDER BY rm.rawmaterialname
    ''')).fetchall()
    print('=== PG materials in recipes ===')
    for r in pg_in_recipes:
        print(f'  {r[0]}: "{r[1]}"')
