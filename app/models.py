from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

db = SQLAlchemy()

SPECIES = {
    "arabica": "Арабика",
    "robusta": "Робуста",
    "liberica": "Либерика",
}

PROCESSING = {
    "washed": "Мытая",
    "natural": "Натуральная",
    "honey": "Ханни",
    "wet_hulled": "Полумытая (гилинг басах)",
    "other": "Другая",
}

ROAST_LEVELS = {
    "light": "Светлая (Light / Nordic)",
    "city": "Сити (City)",
    "full_city": "Фулл-сити (Full City)",
    "vienna": "Венская (Vienna)",
    "french": "Французская (French)",
}

RECIPE_KINDS = {
    "profile": "Профиль обжарки",
    "blend": "Бленд",
}

CLIENT_KINDS = {
    "cafe": "Кофейня",
    "roastery": "Обжарочная",
    "retail": "Розница / сеть",
    "office": "Офис / корнер",
}

DOCUMENT_CATEGORIES = {
    "contract": "Контракт / договор",
    "certificate": "Сертификат / фитосанитария",
    "cupping": "Каппинг-лист",
    "invoice": "Счёт / поставка",
    "other": "Прочее",
}


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(Integer, primary_key=True)
    login = db.Column(String(32), unique=True, nullable=False)
    password_hash = db.Column(String(255), nullable=False)
    full_name = db.Column(String(120), nullable=False)
    role = db.Column(String(16), nullable=False, default="viewer")
    created_at = db.Column(DateTime, nullable=False, default=datetime.now)

    def is_admin(self):
        return self.role == "admin"


class CoffeeVariety(db.Model):
    __tablename__ = "coffee_varieties"

    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(120), nullable=False)
    species = db.Column(String(16), nullable=False, default="arabica")
    origin_country = db.Column(String(80), nullable=False)
    region = db.Column(String(120), nullable=False, default="")
    farm = db.Column(String(160), nullable=False, default="")
    processing = db.Column(String(24), nullable=False, default="washed")
    altitude_m = db.Column(Integer)
    sca_score = db.Column(Numeric(4, 1))
    flavor_notes = db.Column(String(240), nullable=False, default="")
    created_at = db.Column(DateTime, nullable=False, default=datetime.now)

    components = relationship("RecipeComponent", back_populates="variety")


class RoastRecipe(db.Model):
    __tablename__ = "roast_recipes"

    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(120), nullable=False)
    kind = db.Column(String(16), nullable=False, default="profile")
    roast_level = db.Column(String(24), nullable=False, default="city")
    charge_temp_c = db.Column(Integer, nullable=False)
    drop_temp_c = db.Column(Integer, nullable=False)
    duration_sec = db.Column(Integer, nullable=False)
    development_pct = db.Column(Integer, nullable=False)
    sample_batch_kg = db.Column(Numeric(6, 2), nullable=False, default=1)
    notes = db.Column(Text, nullable=False, default="")
    created_at = db.Column(DateTime, nullable=False, default=datetime.now)

    components = relationship(
        "RecipeComponent",
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeComponent.id",
    )


class RecipeComponent(db.Model):
    __tablename__ = "recipe_components"
    __table_args__ = (
        UniqueConstraint("recipe_id", "variety_id", name="uq_recipe_variety"),
    )

    id = db.Column(Integer, primary_key=True)
    recipe_id = db.Column(
        Integer, ForeignKey("roast_recipes.id", ondelete="CASCADE"), nullable=False
    )
    variety_id = db.Column(
        Integer, ForeignKey("coffee_varieties.id"), nullable=False
    )
    percent = db.Column(Integer, nullable=False)

    recipe = relationship("RoastRecipe", back_populates="components")
    variety = relationship("CoffeeVariety", back_populates="components")


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(160), nullable=False)
    country = db.Column(String(80), nullable=False)
    city = db.Column(String(80), nullable=False, default="")
    contact_name = db.Column(String(120), nullable=False, default="")
    phone = db.Column(String(32), nullable=False, default="")
    email = db.Column(String(120), nullable=False, default="")
    specialty = db.Column(String(200), nullable=False, default="")
    created_at = db.Column(DateTime, nullable=False, default=datetime.now)


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(160), nullable=False)
    kind = db.Column(String(16), nullable=False, default="cafe")
    city = db.Column(String(80), nullable=False)
    contact_name = db.Column(String(120), nullable=False, default="")
    phone = db.Column(String(32), nullable=False, default="")
    email = db.Column(String(120), nullable=False, default="")
    notes = db.Column(String(240), nullable=False, default="")
    created_at = db.Column(DateTime, nullable=False, default=datetime.now)


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(Integer, primary_key=True)
    title = db.Column(String(160), nullable=False)
    category = db.Column(String(24), nullable=False, default="other")
    original_name = db.Column(String(255), nullable=False)
    stored_name = db.Column(String(80), nullable=False, unique=True)
    mime_type = db.Column(String(120), nullable=False, default="application/octet-stream")
    size_bytes = db.Column(Integer, nullable=False, default=0)
    uploaded_by_id = db.Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = db.Column(DateTime, nullable=False, default=datetime.now)

    uploaded_by = relationship("User")


class AdminAction(db.Model):
    __tablename__ = "admin_actions"

    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey("users.id"), nullable=False)
    action = db.Column(String(32), nullable=False)
    entity = db.Column(String(32), nullable=False)
    entity_id = db.Column(Integer)
    details = db.Column(String(400), nullable=False, default="")
    created_at = db.Column(DateTime, nullable=False, default=datetime.now)

    user = relationship("User")
