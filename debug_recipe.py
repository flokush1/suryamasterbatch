"""Debug K-M recipe prediction issues."""
import sys
sys.path.insert(0, 'c:/Users/kushp/Downloads/SuryaMasterBatch/app/backend')
from app import create_app
app = create_app()

with app.app_context():
    from models.database import db, Product, RawMaterial, ProductRawMaterialMap
    from sqlalchemy import text

    # Check: which pigments (type=PG with LAB) do GREEN PE products use?
    # Product 40036 is GREEN PE
    prod = Product.query.get('40036')
    if prod:
        print(f"Product 40036: {prod.name}, alphacode={prod.alphacode[:80]}")
        items = ProductRawMaterialMap.query.filter_by(productid='40036').all()
        total_kg = sum(i.qtyinkg for i in items if i.qtyinkg)
        print(f"  Total recipe kg: {total_kg}")
        for item in items:
            rm = item.raw_material
            if rm:
                print(f"  RM={rm.rawmaterialid} name={rm.rawmaterialname} qty={item.qtyinkg} type={rm.type} labL={rm.full_tone_L}")
    print()

    # Check RM401 - is it used by any product?
    rm401 = RawMaterial.query.get('RM401')
    print(f"RM401: {rm401.rawmaterialname if rm401 else 'NOT FOUND'}, L={rm401.full_tone_L if rm401 else 'N/A'}")
    if rm401:
        ct = ProductRawMaterialMap.query.filter_by(rawmaterialid='RM401').count()
        print(f"  Used in {ct} recipes")
        samples = ProductRawMaterialMap.query.filter_by(rawmaterialid='RM401').limit(5).all()
        for s in samples:
            p = s.product
            print(f"  -> Product {s.productid} ({p.name if p else 'N/A'}), qty={s.qtyinkg}")
    print()

    # Check which pigments product 60007 (BLUE) uses
    prod2 = Product.query.get('60007')
    if prod2:
        print(f"Product 60007: {prod2.name}")
        items2 = ProductRawMaterialMap.query.filter_by(productid='60007').all()
        total_kg2 = sum(i.qtyinkg for i in items2 if i.qtyinkg)
        print(f"  Total recipe kg: {total_kg2}")
        for item2 in items2:
            rm = item2.raw_material
            if rm and rm.type == 'PG':
                print(f"  PG RM={rm.rawmaterialid} name={rm.rawmaterialname} qty={item2.qtyinkg} labL={rm.full_tone_L}")
