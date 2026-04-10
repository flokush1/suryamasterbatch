import sys, os
sys.path.insert(0, '.')
from app import create_app
app = create_app()
with app.app_context():
    from services.ml_engine import MLRecipeModel
    from services.color_engine import _TIO2_KS, predict_mixture_lab, Pigment
    
    # 1. Check _TIO2_KS values
    print('_TIO2_KS:', _TIO2_KS)
    print()
    
    # 2. TiO2 test
    pig = Pigment('RED', 38, 55, 40, 70, 30, 15)
    lab_no = predict_mixture_lab([(pig, 0.05)])
    lab_w3 = predict_mixture_lab([(pig, 0.05)], tio2_conc=0.3)
    lab_lo = predict_mixture_lab([(pig, 0.02)], tio2_conc=0.3)
    print(f'No TiO2: L={lab_no[0]:.4f}')
    print(f'With TiO2 0.3 (same pig): L={lab_w3[0]:.4f}')
    print(f'With TiO2 0.3, less pig:  L={lab_lo[0]:.4f}')
    print()
    
    # 3. Train ML and diagnose predicted_lab
    model = MLRecipeModel()
    model._train(app)
    preds = model.predict(45, 50, 30, 'PE', target=(45, 50, 30))
    if preds:
        sug = preds[0]
        print(f"ML predicted_lab: {sug.get('predicted_lab')}")
        print(f"ML pigment_system count: {len(sug.get('pigment_system', []))}")
        for c in sug.get('pigment_system', []):
            rmid = c['rawmaterialid']
            meta = model._pig_meta.get(rmid, {})
            print(f"  {rmid}: full_L={meta.get('full_tone_L')}, tint_L={meta.get('tint_tone_L')}")
