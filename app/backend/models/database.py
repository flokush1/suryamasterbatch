from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Text, Float, Boolean, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

db = SQLAlchemy()


class RawMaterial(db.Model):
    __tablename__ = "raw_material"
    rawmaterialid = db.Column(String(50), primary_key=True)
    rawmaterialname = db.Column(String(200))
    current_price = db.Column(Float)
    current_price_date = db.Column(String(20))
    chemical_name = db.Column(String(200))
    last_price = db.Column(Float)
    last_price_date = db.Column(String(20))
    remarks = db.Column(Text)
    type = db.Column(String(10))       # PG, RM, PRM
    compliance = db.Column(String(20)) # NON-R, ROHS1, ROHS2, REACH
    # LAB values (populated from Lab_Values_Color.xlsx for PG type)
    full_tone_L = db.Column(Float)
    full_tone_a = db.Column(Float)
    full_tone_b = db.Column(Float)
    tint_tone_L = db.Column(Float)
    tint_tone_a = db.Column(Float)
    tint_tone_b = db.Column(Float)
    full_tone_hex = db.Column(String(10))
    tint_tone_hex = db.Column(String(10))
    # Pigment technical properties (from manufacturer shade card PDFs)
    ci_name = db.Column(String(20))          # Colour Index name e.g. "PY 110"
    chemistry = db.Column(String(100))       # e.g. "Isoindolinone", "Quinacridone"
    heat_resistance = db.Column(Float)       # Max processing temp °C
    light_fastness_tone = db.Column(Float)   # Blue Wool Scale 1–8 (full tone)
    light_fastness_tint = db.Column(Float)   # Blue Wool Scale 1–8 (tint)
    weather_fastness_tone = db.Column(Float) # Grey Scale 1–5 (full tone)
    weather_fastness_tint = db.Column(Float) # Grey Scale 1–5 (tint)
    bleed_pvc = db.Column(String(10))        # "Low" / None
    warp_hdpe = db.Column(String(10))        # "Low" / None

    recipes = relationship("ProductRawMaterialMap", back_populates="raw_material")
    stocks = relationship("Stock", back_populates="raw_material", foreign_keys="Stock.rawmaterialid")

    def to_dict(self):
        return {
            "rawmaterialid": self.rawmaterialid,
            "rawmaterialname": self.rawmaterialname,
            "current_price": self.current_price,
            "chemical_name": self.chemical_name,
            "type": self.type,
            "compliance": self.compliance,
            "lab": {
                "full_tone": {"L": self.full_tone_L, "a": self.full_tone_a, "b": self.full_tone_b},
                "tint_tone": {"L": self.tint_tone_L, "a": self.tint_tone_a, "b": self.tint_tone_b},
            } if self.full_tone_L is not None else None,
            "full_tone_hex": self.full_tone_hex,
            "tint_tone_hex": self.tint_tone_hex,
            "ci_name": self.ci_name,
            "chemistry": self.chemistry,
            "heat_resistance": self.heat_resistance,
            "light_fastness_tone": self.light_fastness_tone,
            "light_fastness_tint": self.light_fastness_tint,
            "weather_fastness_tone": self.weather_fastness_tone,
            "weather_fastness_tint": self.weather_fastness_tint,
        }


class Product(db.Model):
    __tablename__ = "product"
    id = db.Column(String(20), primary_key=True)
    name = db.Column(String(100))
    selling_price = db.Column(Float)
    remark = db.Column(Text)
    date_updated = db.Column(String(20))
    alphacode = db.Column(Text)       # JSON list stored as string
    slf_no = db.Column(String(50))
    ral_shade = db.Column(String(50))
    pantone_shade = db.Column(String(50))
    is_final_good = db.Column(Boolean, default=False)

    spec = relationship("ProductSpec", back_populates="product", uselist=False)
    recipe_items = relationship("ProductRawMaterialMap", back_populates="product")
    lab_results = relationship("LabResult", back_populates="product")

    def to_dict(self):
        import json
        try:
            codes = json.loads(self.alphacode.replace("'", '"')) if self.alphacode else []
        except Exception:
            codes = []
        return {
            "id": self.id,
            "name": self.name,
            "selling_price": self.selling_price,
            "remark": self.remark,
            "date_updated": self.date_updated,
            "alphacode": codes,
            "slf_no": self.slf_no,
            "ral_shade": self.ral_shade,
            "pantone_shade": self.pantone_shade,
            "is_final_good": self.is_final_good,
        }


class ProductSpec(db.Model):
    __tablename__ = "product_spec"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(String(20), ForeignKey("product.id"))
    carrier_resin = db.Column(String(100))
    material_form = db.Column(String(50))
    appearance_colour = db.Column(String(100))
    hardness = db.Column(Float)
    moisture_content = db.Column(Float)
    antioxidant_content = db.Column(Float)
    ash_content = db.Column(Float)
    specific_gravity = db.Column(Float)
    bulk_density = db.Column(Float)
    caco3_content = db.Column(Float)
    tio2_percentage = db.Column(Float)
    mfr = db.Column(Float)
    weather_fastness = db.Column(Float)
    light_fastness = db.Column(Float)
    colour_migration = db.Column(Float)
    dispersion = db.Column(String(50))
    melting_temperature = db.Column(Float)
    heat_stability = db.Column(Float)
    toxicity = db.Column(String(100))
    spec_compliance = db.Column(String(50))
    higher_olefin_constituent = db.Column(String(100))
    cbc = db.Column(String(50))
    carbon_type = db.Column(String(50))
    volatile_matter_content = db.Column(Float)
    toluene_extract = db.Column(Float)
    let_down_ratio = db.Column(String(50))
    ral_pantone_ci = db.Column(String(100))

    product = relationship("Product", back_populates="spec")

    def to_dict(self):
        return {
            "carrier_resin": self.carrier_resin,
            "weather_fastness": self.weather_fastness,
            "light_fastness": self.light_fastness,
            "heat_stability": self.heat_stability,
            "spec_compliance": self.spec_compliance,
            "let_down_ratio": self.let_down_ratio,
            "dispersion": self.dispersion,
        }


class ProductRawMaterialMap(db.Model):
    __tablename__ = "product_raw_material_map"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    productid = db.Column(String(20), ForeignKey("product.id"))
    rawmaterialid = db.Column(String(50), ForeignKey("raw_material.rawmaterialid"))
    qtyinkg = db.Column(Float)

    product = relationship("Product", back_populates="recipe_items")
    raw_material = relationship("RawMaterial", back_populates="recipes")

    def to_dict(self):
        rm = self.raw_material
        return {
            "rawmaterialid": self.rawmaterialid,
            "rawmaterialname": rm.rawmaterialname if rm else None,
            "qtyinkg": self.qtyinkg,
            "rm_type": rm.type if rm else None,
            "chemical_name": rm.chemical_name if rm else None,
            "ci_name": rm.ci_name if rm else None,
            "full_tone_L": rm.full_tone_L if rm else None,
            "full_tone_a": rm.full_tone_a if rm else None,
            "full_tone_b": rm.full_tone_b if rm else None,
        }


class AlphaCode(db.Model):
    __tablename__ = "alpha_code"
    alpha_code = db.Column(String(20), primary_key=True)
    polymer = db.Column(String(20))
    product_type = db.Column(String(50))
    compliance = db.Column(String(20))
    application = db.Column(String(50))
    sub_application = db.Column(String(50))
    code1 = db.Column(String(5))
    code2 = db.Column(String(5))
    code3 = db.Column(String(5))
    code4 = db.Column(String(5))
    code5 = db.Column(String(5))
    product_code = db.Column(String(20))
    gross_margin = db.Column(Float)

    def to_dict(self):
        return {
            "alpha_code": self.alpha_code,
            "polymer": self.polymer,
            "product_type": self.product_type,
            "compliance": self.compliance,
            "application": self.application,
            "sub_application": self.sub_application,
            "product_code": self.product_code,
            "gross_margin": self.gross_margin,
        }


class RalPantoneShade(db.Model):
    __tablename__ = "ral_pantone_shade"
    shade_code = db.Column(String(30), primary_key=True)
    color_name = db.Column(String(100))
    hex_code = db.Column(String(10))

    def to_dict(self):
        return {
            "shade_code": self.shade_code,
            "color_name": self.color_name,
            "hex_code": self.hex_code,
        }


class Stock(db.Model):
    __tablename__ = "stock"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    rawmaterialid = db.Column(String(50), ForeignKey("raw_material.rawmaterialid"), nullable=True)
    rawmaterialname = db.Column(String(200))
    available_stocks = db.Column(Float)
    particulars_name = db.Column(String(200))
    last_updated = db.Column(String(20))

    raw_material = relationship("RawMaterial", back_populates="stocks", foreign_keys=[rawmaterialid])

    def to_dict(self):
        return {
            "rawmaterialid": self.rawmaterialid,
            "rawmaterialname": self.rawmaterialname,
            "available_stocks": self.available_stocks,
            "particulars_name": self.particulars_name,
            "last_updated": self.last_updated,
        }


class LabResult(db.Model):
    """Stores measured LAB values for products in specific polymers — feeds the learning model."""
    __tablename__ = "lab_result"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    product_id = db.Column(String(20), ForeignKey("product.id"))
    polymer = db.Column(String(20))
    L = db.Column(Float)
    a = db.Column(Float)
    b = db.Column(Float)
    measured_date = db.Column(String(20))
    notes = db.Column(Text)
    created_at = db.Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="lab_results")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "polymer": self.polymer,
            "L": self.L,
            "a": self.a,
            "b": self.b,
            "measured_date": self.measured_date,
            "notes": self.notes,
        }


class ClientProductMapping(db.Model):
    __tablename__ = "client_product_mapping"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    client_id = db.Column(String(50))
    product_id = db.Column(String(20), ForeignKey("product.id"))
    premium_disc = db.Column(Float)
    alphacode = db.Column(String(20))

    def to_dict(self):
        return {
            "client_id": self.client_id,
            "product_id": self.product_id,
            "premium_disc": self.premium_disc,
            "alphacode": self.alphacode,
        }
