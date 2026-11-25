import re
from decimal import Decimal, InvalidOperation

from .models import (
    CLIENT_KINDS,
    DOCUMENT_CATEGORIES,
    PROCESSING,
    RECIPE_KINDS,
    ROAST_LEVELS,
    SPECIES,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[+\d][\d\s\-()]{5,31}$")


def _text(form, key, max_len=160):
    return " ".join(str(form.get(key, "")).split())[:max_len]


def _req(cleaned, errors, key, label, min_len=2, max_len=160):
    value = cleaned.get(key, "")
    if len(value) < min_len:
        errors[key] = f"Укажите {label}."
    elif len(value) > max_len:
        errors[key] = f"{label.capitalize()} слишком длинное."
    return value


def _choice(form, errors, key, options, label):
    value = str(form.get(key, "")).strip()
    if value not in options:
        errors[key] = f"Выберите {label}."
        return ""
    return value


def _int(form, errors, key, label, minimum, maximum, required=True):
    raw = str(form.get(key, "")).strip().replace(",", ".")
    if not raw:
        if required:
            errors[key] = f"Укажите {label}."
        return None
    try:
        value = int(Decimal(raw))
    except (InvalidOperation, ValueError):
        errors[key] = f"{label.capitalize()} должно быть числом."
        return None
    if value < minimum or value > maximum:
        errors[key] = f"{label.capitalize()}: от {minimum} до {maximum}."
        return None
    return value


def _decimal(form, errors, key, label, minimum, maximum, required=True):
    raw = str(form.get(key, "")).strip().replace(",", ".")
    if not raw:
        if required:
            errors[key] = f"Укажите {label}."
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        errors[key] = f"{label.capitalize()} должно быть числом."
        return None
    if value < Decimal(str(minimum)) or value > Decimal(str(maximum)):
        errors[key] = f"{label.capitalize()}: от {minimum} до {maximum}."
        return None
    return value


def _optional_contact(cleaned, errors):
    email = cleaned.get("email", "")
    phone = cleaned.get("phone", "")
    if email and not EMAIL_RE.match(email):
        errors["email"] = "Некорректный email."
    if phone and not PHONE_RE.match(phone):
        errors["phone"] = "Некорректный телефон."


def validate_variety(form):
    errors = {}
    cleaned = {
        "name": _text(form, "name", 120),
        "species": _choice(form, errors, "species", SPECIES, "вид кофе"),
        "origin_country": _text(form, "origin_country", 80),
        "region": _text(form, "region", 120),
        "farm": _text(form, "farm", 160),
        "processing": _choice(form, errors, "processing", PROCESSING, "обработку"),
        "altitude_m": _int(form, errors, "altitude_m", "высоту, м", 0, 3500, required=False),
        "sca_score": _decimal(form, errors, "sca_score", "оценку SCA", 0, 100, required=False),
        "flavor_notes": _text(form, "flavor_notes", 240),
    }
    _req(cleaned, errors, "name", "название сорта")
    _req(cleaned, errors, "origin_country", "страну происхождения", min_len=2, max_len=80)
    return errors, cleaned


def parse_components(form, variety_ids):
    ids = form.getlist("variety_id") if hasattr(form, "getlist") else form.get("variety_id", [])
    percents = form.getlist("percent") if hasattr(form, "getlist") else form.get("percent", [])
    if isinstance(ids, str):
        ids = [ids]
    if isinstance(percents, str):
        percents = [percents]
    rows = []
    errors = {}
    seen = set()
    for raw_id, raw_pct in zip(ids, percents):
        vid = str(raw_id).strip()
        pct = str(raw_pct).strip()
        if not vid and not pct:
            continue
        if not vid.isdigit() or int(vid) not in variety_ids:
            errors["components"] = "Выберите сорт из справочника."
            continue
        variety_id = int(vid)
        try:
            percent = int(pct)
        except ValueError:
            errors["components"] = "Доля должна быть целым числом."
            continue
        if percent < 1 or percent > 100:
            errors["components"] = "Доля каждого сорта: от 1 до 100 %."
            continue
        if variety_id in seen:
            errors["components"] = "Один сорт нельзя указать дважды."
            continue
        seen.add(variety_id)
        rows.append({"variety_id": variety_id, "percent": percent})
    if not rows:
        errors["components"] = "Добавьте хотя бы один сорт в состав."
    elif sum(row["percent"] for row in rows) != 100:
        errors["components"] = "Сумма долей должна быть ровно 100 %."
    return errors, rows


def validate_recipe(form, variety_ids):
    errors = {}
    cleaned = {
        "name": _text(form, "name", 120),
        "kind": _choice(form, errors, "kind", RECIPE_KINDS, "тип рецептуры"),
        "roast_level": _choice(form, errors, "roast_level", ROAST_LEVELS, "степень обжарки"),
        "charge_temp_c": _int(form, errors, "charge_temp_c", "температуру загрузки, °C", 150, 250),
        "drop_temp_c": _int(form, errors, "drop_temp_c", "температуру выгрузки, °C", 170, 260),
        "duration_sec": _int(form, errors, "duration_sec", "время обжарки, сек", 300, 1800),
        "development_pct": _int(form, errors, "development_pct", "развитие, %", 8, 35),
        "sample_batch_kg": _decimal(
            form, errors, "sample_batch_kg", "массу образца, кг", 0.1, 60
        ),
        "notes": _text(form, "notes", 2000),
    }
    _req(cleaned, errors, "name", "название рецептуры")
    charge = cleaned.get("charge_temp_c")
    drop = cleaned.get("drop_temp_c")
    if charge is not None and drop is not None and drop <= charge:
        errors["drop_temp_c"] = "Выгрузка должна быть теплее загрузки."
    comp_errors, components = parse_components(form, variety_ids)
    errors.update(comp_errors)
    cleaned["components"] = components
    if cleaned.get("kind") == "profile" and len(components) > 1:
        errors["kind"] = "Профиль обжарки — один сорт на 100 %. Для смеси выберите «Бленд»."
    if cleaned.get("kind") == "blend" and len(components) < 2:
        errors["kind"] = "Бленд состоит минимум из двух сортов."
    return errors, cleaned


def validate_supplier(form):
    errors = {}
    cleaned = {
        "name": _text(form, "name", 160),
        "country": _text(form, "country", 80),
        "city": _text(form, "city", 80),
        "contact_name": _text(form, "contact_name", 120),
        "phone": _text(form, "phone", 32),
        "email": _text(form, "email", 120).lower(),
        "specialty": _text(form, "specialty", 200),
    }
    _req(cleaned, errors, "name", "название поставщика")
    _req(cleaned, errors, "country", "страну", min_len=2, max_len=80)
    _optional_contact(cleaned, errors)
    return errors, cleaned


def validate_client(form):
    errors = {}
    cleaned = {
        "name": _text(form, "name", 160),
        "kind": _choice(form, errors, "kind", CLIENT_KINDS, "тип клиента"),
        "city": _text(form, "city", 80),
        "contact_name": _text(form, "contact_name", 120),
        "phone": _text(form, "phone", 32),
        "email": _text(form, "email", 120).lower(),
        "notes": _text(form, "notes", 240),
    }
    _req(cleaned, errors, "name", "название клиента")
    _req(cleaned, errors, "city", "город", min_len=2, max_len=80)
    _optional_contact(cleaned, errors)
    return errors, cleaned


def validate_document_meta(form):
    errors = {}
    cleaned = {
        "title": _text(form, "title", 160),
        "category": _choice(form, errors, "category", DOCUMENT_CATEGORIES, "категорию"),
    }
    _req(cleaned, errors, "title", "название документа")
    return errors, cleaned
