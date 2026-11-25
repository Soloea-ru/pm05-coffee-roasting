import secrets
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import func, or_, select
from werkzeug.security import check_password_hash

from .models import (
    CLIENT_KINDS,
    DOCUMENT_CATEGORIES,
    PROCESSING,
    RECIPE_KINDS,
    ROAST_LEVELS,
    SPECIES,
    AdminAction,
    Client,
    CoffeeVariety,
    Document,
    RecipeComponent,
    RoastRecipe,
    Supplier,
    User,
    db,
)
from .services import (
    admin_required,
    current_user,
    delete_stored_file,
    ensure_csrf,
    log_action,
    paginate,
    save_upload,
)
from .validators import (
    validate_client,
    validate_document_meta,
    validate_recipe,
    validate_supplier,
    validate_variety,
)

bp = Blueprint("main", __name__)

NAV = [
    ("main.dashboard", "Сводка"),
    ("main.variety_list", "Сорта"),
    ("main.recipe_list", "Профили и бленды"),
    ("main.supplier_list", "Поставщики"),
    ("main.client_list", "Клиенты"),
    ("main.report_page", "Отчёты"),
    ("main.document_list", "Архив"),
    ("main.journal_list", "Журнал"),
]


def inject_template_context():
    return {
        "csrf": ensure_csrf(),
        "me": current_user(),
        "nav": NAV,
        "SPECIES": SPECIES,
        "PROCESSING": PROCESSING,
        "ROAST_LEVELS": ROAST_LEVELS,
        "RECIPE_KINDS": RECIPE_KINDS,
        "CLIENT_KINDS": CLIENT_KINDS,
        "DOCUMENT_CATEGORIES": DOCUMENT_CATEGORIES,
    }


@bp.before_request
def protect_post():
    if request.method == "POST":
        token = request.form.get("csrf_token", "")
        if not token or token != session.get("csrf"):
            abort(400)


def _page():
    return request.args.get("page", 1)


def variety_ids():
    return set(db.session.execute(select(CoffeeVariety.id)).scalars().all())


def replace_components(recipe, rows):
    recipe.components.clear()
    db.session.flush()
    for row in rows:
        recipe.components.append(
            RecipeComponent(variety_id=row["variety_id"], percent=row["percent"])
        )


def composition_label(recipe):
    parts = [
        f"{item.variety.name} {item.percent}%"
        for item in recipe.components
        if item.variety
    ]
    return " · ".join(parts) if parts else "—"


# --- auth ---


@bp.route("/", methods=["GET"])
def home():
    user = current_user()
    if user and user.is_admin():
        return redirect(url_for("main.dashboard"))
    if user:
        abort(403)
    return redirect(url_for("main.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("main.home"))
    error = None
    form_login = ""
    if request.method == "POST":
        form_login = " ".join(request.form.get("login", "").split()).lower()
        password = request.form.get("password", "")
        user = None
        if form_login:
            user = db.session.execute(
                select(User).where(User.login == form_login)
            ).scalar_one_or_none()
        if not user or not check_password_hash(user.password_hash, password):
            error = "Неверный логин или пароль."
        else:
            session.clear()
            session["user_id"] = user.id
            session["csrf"] = secrets.token_hex(16)
            if user.is_admin():
                log_action("login", "session", user.id, f"вход {user.login}")
                db.session.commit()
                return redirect(url_for("main.dashboard"))
            return redirect(url_for("main.home"))
    return render_template("login.html", error=error, form_login=form_login), (
        400 if error else 200
    )


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


# --- dashboard / reports / journal ---


@bp.get("/admin")
@admin_required
def dashboard():
    counts = {
        "varieties": db.session.execute(select(func.count()).select_from(CoffeeVariety)).scalar_one(),
        "recipes": db.session.execute(select(func.count()).select_from(RoastRecipe)).scalar_one(),
        "suppliers": db.session.execute(select(func.count()).select_from(Supplier)).scalar_one(),
        "clients": db.session.execute(select(func.count()).select_from(Client)).scalar_one(),
        "documents": db.session.execute(select(func.count()).select_from(Document)).scalar_one(),
        "actions": db.session.execute(select(func.count()).select_from(AdminAction)).scalar_one(),
    }
    recent = db.session.execute(
        select(AdminAction).order_by(AdminAction.created_at.desc(), AdminAction.id.desc()).limit(5)
    ).scalars().all()
    return render_template("dashboard.html", counts=counts, recent=recent)


@bp.get("/admin/reports")
@admin_required
def report_page():
    origin_rows = db.session.execute(
        select(CoffeeVariety.origin_country, func.count())
        .group_by(CoffeeVariety.origin_country)
        .order_by(func.count().desc(), CoffeeVariety.origin_country)
    ).all()
    roast_rows = db.session.execute(
        select(RoastRecipe.roast_level, func.count())
        .group_by(RoastRecipe.roast_level)
        .order_by(func.count().desc())
    ).all()
    kind_rows = db.session.execute(
        select(RoastRecipe.kind, func.count()).group_by(RoastRecipe.kind)
    ).all()
    client_rows = db.session.execute(
        select(Client.kind, func.count()).group_by(Client.kind)
    ).all()
    supplier_rows = db.session.execute(
        select(Supplier.country, func.count())
        .group_by(Supplier.country)
        .order_by(func.count().desc(), Supplier.country)
    ).all()
    batch_sum = db.session.execute(
        select(func.coalesce(func.sum(RoastRecipe.sample_batch_kg), 0))
    ).scalar_one()
    return render_template(
        "reports.html",
        origin_rows=origin_rows,
        roast_rows=roast_rows,
        kind_rows=kind_rows,
        client_rows=client_rows,
        supplier_rows=supplier_rows,
        batch_sum=batch_sum,
        variety_total=db.session.execute(select(func.count()).select_from(CoffeeVariety)).scalar_one(),
        recipe_total=db.session.execute(select(func.count()).select_from(RoastRecipe)).scalar_one(),
        supplier_total=db.session.execute(select(func.count()).select_from(Supplier)).scalar_one(),
        client_total=db.session.execute(select(func.count()).select_from(Client)).scalar_one(),
    )


@bp.get("/admin/journal")
@admin_required
def journal_list():
    q = " ".join(request.args.get("q", "").split())
    stmt = select(AdminAction).order_by(AdminAction.created_at.desc(), AdminAction.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.join(User, User.id == AdminAction.user_id).where(
            or_(
                AdminAction.action.ilike(like),
                AdminAction.entity.ilike(like),
                AdminAction.details.ilike(like),
                User.login.ilike(like),
            )
        )
    items, total, page, pages = paginate(stmt, _page())
    return render_template(
        "journal.html", items=items, total=total, page=page, pages=pages, q=q
    )


# --- varieties ---


@bp.get("/admin/varieties")
@admin_required
def variety_list():
    q = " ".join(request.args.get("q", "").split())
    country = request.args.get("country", "").strip()
    stmt = select(CoffeeVariety).order_by(CoffeeVariety.origin_country, CoffeeVariety.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                CoffeeVariety.name.ilike(like),
                CoffeeVariety.region.ilike(like),
                CoffeeVariety.farm.ilike(like),
                CoffeeVariety.flavor_notes.ilike(like),
            )
        )
    if country:
        stmt = stmt.where(CoffeeVariety.origin_country == country)
    items, total, page, pages = paginate(stmt, _page())
    countries = db.session.execute(
        select(CoffeeVariety.origin_country).distinct().order_by(CoffeeVariety.origin_country)
    ).scalars().all()
    return render_template(
        "varieties/list.html",
        items=items,
        total=total,
        page=page,
        pages=pages,
        q=q,
        country=country,
        countries=countries,
    )


@bp.route("/admin/varieties/new", methods=["GET", "POST"])
@admin_required
def variety_new():
    errors, form = {}, _empty_variety()
    if request.method == "POST":
        errors, form = validate_variety(request.form)
        if not errors:
            row = CoffeeVariety(**form)
            db.session.add(row)
            db.session.flush()
            log_action("create", "variety", row.id, row.name)
            db.session.commit()
            flash("Сорт добавлен в каталог.", "success")
            return redirect(url_for("main.variety_list"))
    return render_template("varieties/form.html", errors=errors, form=form, item=None), (
        400 if errors else 200
    )


@bp.route("/admin/varieties/<int:item_id>/edit", methods=["GET", "POST"])
@admin_required
def variety_edit(item_id):
    item = db.session.get(CoffeeVariety, item_id) or abort(404)
    errors, form = {}, _variety_form(item)
    if request.method == "POST":
        errors, form = validate_variety(request.form)
        if not errors:
            for key, value in form.items():
                setattr(item, key, value)
            log_action("update", "variety", item.id, item.name)
            db.session.commit()
            flash("Сорт обновлён.", "success")
            return redirect(url_for("main.variety_list"))
    return render_template("varieties/form.html", errors=errors, form=form, item=item), (
        400 if errors else 200
    )


@bp.route("/admin/varieties/<int:item_id>/delete", methods=["GET", "POST"])
@admin_required
def variety_delete(item_id):
    item = db.session.get(CoffeeVariety, item_id) or abort(404)
    used = db.session.execute(
        select(func.count()).select_from(RecipeComponent).where(RecipeComponent.variety_id == item.id)
    ).scalar_one()
    if request.method == "POST":
        if used:
            flash("Сорт входит в рецептуру — сначала уберите его из профиля или бленда.", "error")
            return redirect(url_for("main.variety_delete", item_id=item.id))
        log_action("delete", "variety", item.id, item.name)
        db.session.delete(item)
        db.session.commit()
        flash("Сорт удалён.", "success")
        return redirect(url_for("main.variety_list"))
    return render_template("confirm_delete.html", item=item, used=used, catalog="сорт кофе")


def _empty_variety():
    return {
        "name": "",
        "species": "arabica",
        "origin_country": "",
        "region": "",
        "farm": "",
        "processing": "washed",
        "altitude_m": None,
        "sca_score": None,
        "flavor_notes": "",
    }


def _variety_form(item):
    return {
        "name": item.name,
        "species": item.species,
        "origin_country": item.origin_country,
        "region": item.region,
        "farm": item.farm,
        "processing": item.processing,
        "altitude_m": item.altitude_m,
        "sca_score": item.sca_score,
        "flavor_notes": item.flavor_notes,
    }


# --- recipes ---


@bp.get("/admin/recipes")
@admin_required
def recipe_list():
    q = " ".join(request.args.get("q", "").split())
    roast_level = request.args.get("roast_level", "").strip()
    stmt = select(RoastRecipe).order_by(RoastRecipe.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(RoastRecipe.name.ilike(like), RoastRecipe.notes.ilike(like)))
    if roast_level:
        stmt = stmt.where(RoastRecipe.roast_level == roast_level)
    items, total, page, pages = paginate(stmt, _page())
    return render_template(
        "recipes/list.html",
        items=items,
        total=total,
        page=page,
        pages=pages,
        q=q,
        roast_level=roast_level,
        composition_label=composition_label,
    )


@bp.route("/admin/recipes/new", methods=["GET", "POST"])
@admin_required
def recipe_new():
    errors, form = {}, _empty_recipe()
    varieties = _varieties()
    if request.method == "POST":
        errors, form = validate_recipe(request.form, variety_ids())
        if not errors:
            components = form.pop("components")
            row = RoastRecipe(**form)
            db.session.add(row)
            db.session.flush()
            replace_components(row, components)
            log_action("create", "recipe", row.id, row.name)
            db.session.commit()
            flash("Рецептура сохранена.", "success")
            return redirect(url_for("main.recipe_list"))
        form.setdefault("components", [])
    return render_template(
        "recipes/form.html", errors=errors, form=form, item=None, varieties=varieties
    ), (400 if errors else 200)


@bp.route("/admin/recipes/<int:item_id>/edit", methods=["GET", "POST"])
@admin_required
def recipe_edit(item_id):
    item = db.session.get(RoastRecipe, item_id) or abort(404)
    errors, form = {}, _recipe_form(item)
    varieties = _varieties()
    if request.method == "POST":
        errors, form = validate_recipe(request.form, variety_ids())
        if not errors:
            components = form.pop("components")
            for key, value in form.items():
                setattr(item, key, value)
            replace_components(item, components)
            log_action("update", "recipe", item.id, item.name)
            db.session.commit()
            flash("Рецептура обновлена.", "success")
            return redirect(url_for("main.recipe_list"))
        form.setdefault("components", [])
    return render_template(
        "recipes/form.html", errors=errors, form=form, item=item, varieties=varieties
    ), (400 if errors else 200)


@bp.route("/admin/recipes/<int:item_id>/delete", methods=["GET", "POST"])
@admin_required
def recipe_delete(item_id):
    item = db.session.get(RoastRecipe, item_id) or abort(404)
    if request.method == "POST":
        log_action("delete", "recipe", item.id, item.name)
        db.session.delete(item)
        db.session.commit()
        flash("Рецептура удалена.", "success")
        return redirect(url_for("main.recipe_list"))
    return render_template("confirm_delete.html", item=item, used=0, catalog="рецептуру")


def _varieties():
    return db.session.execute(
        select(CoffeeVariety).order_by(CoffeeVariety.origin_country, CoffeeVariety.name)
    ).scalars().all()


def _empty_recipe():
    return {
        "name": "",
        "kind": "profile",
        "roast_level": "city",
        "charge_temp_c": 198,
        "drop_temp_c": 210,
        "duration_sec": 600,
        "development_pct": 18,
        "sample_batch_kg": "1.00",
        "notes": "",
        "components": [{"variety_id": "", "percent": 100}],
    }


def _recipe_form(item):
    return {
        "name": item.name,
        "kind": item.kind,
        "roast_level": item.roast_level,
        "charge_temp_c": item.charge_temp_c,
        "drop_temp_c": item.drop_temp_c,
        "duration_sec": item.duration_sec,
        "development_pct": item.development_pct,
        "sample_batch_kg": item.sample_batch_kg,
        "notes": item.notes,
        "components": [
            {"variety_id": row.variety_id, "percent": row.percent} for row in item.components
        ]
        or [{"variety_id": "", "percent": 100}],
    }


# --- suppliers ---


@bp.get("/admin/suppliers")
@admin_required
def supplier_list():
    q = " ".join(request.args.get("q", "").split())
    country = request.args.get("country", "").strip()
    stmt = select(Supplier).order_by(Supplier.country, Supplier.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Supplier.name.ilike(like),
                Supplier.city.ilike(like),
                Supplier.specialty.ilike(like),
                Supplier.contact_name.ilike(like),
            )
        )
    if country:
        stmt = stmt.where(Supplier.country == country)
    items, total, page, pages = paginate(stmt, _page())
    countries = db.session.execute(
        select(Supplier.country).distinct().order_by(Supplier.country)
    ).scalars().all()
    return render_template(
        "suppliers/list.html",
        items=items,
        total=total,
        page=page,
        pages=pages,
        q=q,
        country=country,
        countries=countries,
    )


@bp.route("/admin/suppliers/new", methods=["GET", "POST"])
@admin_required
def supplier_new():
    errors, form = {}, _empty_party()
    if request.method == "POST":
        errors, form = validate_supplier(request.form)
        if not errors:
            row = Supplier(**form)
            db.session.add(row)
            db.session.flush()
            log_action("create", "supplier", row.id, row.name)
            db.session.commit()
            flash("Поставщик добавлен.", "success")
            return redirect(url_for("main.supplier_list"))
    return render_template("suppliers/form.html", errors=errors, form=form, item=None), (
        400 if errors else 200
    )


@bp.route("/admin/suppliers/<int:item_id>/edit", methods=["GET", "POST"])
@admin_required
def supplier_edit(item_id):
    item = db.session.get(Supplier, item_id) or abort(404)
    errors, form = {}, _party_form(item)
    if request.method == "POST":
        errors, form = validate_supplier(request.form)
        if not errors:
            for key, value in form.items():
                setattr(item, key, value)
            log_action("update", "supplier", item.id, item.name)
            db.session.commit()
            flash("Поставщик обновлён.", "success")
            return redirect(url_for("main.supplier_list"))
    return render_template("suppliers/form.html", errors=errors, form=form, item=item), (
        400 if errors else 200
    )


@bp.route("/admin/suppliers/<int:item_id>/delete", methods=["GET", "POST"])
@admin_required
def supplier_delete(item_id):
    item = db.session.get(Supplier, item_id) or abort(404)
    if request.method == "POST":
        log_action("delete", "supplier", item.id, item.name)
        db.session.delete(item)
        db.session.commit()
        flash("Поставщик удалён.", "success")
        return redirect(url_for("main.supplier_list"))
    return render_template("confirm_delete.html", item=item, used=0, catalog="поставщика")


# --- clients ---


@bp.get("/admin/clients")
@admin_required
def client_list():
    q = " ".join(request.args.get("q", "").split())
    kind = request.args.get("kind", "").strip()
    stmt = select(Client).order_by(Client.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Client.name.ilike(like),
                Client.city.ilike(like),
                Client.contact_name.ilike(like),
                Client.notes.ilike(like),
            )
        )
    if kind:
        stmt = stmt.where(Client.kind == kind)
    items, total, page, pages = paginate(stmt, _page())
    return render_template(
        "clients/list.html",
        items=items,
        total=total,
        page=page,
        pages=pages,
        q=q,
        kind=kind,
    )


@bp.route("/admin/clients/new", methods=["GET", "POST"])
@admin_required
def client_new():
    errors, form = {}, _empty_client()
    if request.method == "POST":
        errors, form = validate_client(request.form)
        if not errors:
            row = Client(**form)
            db.session.add(row)
            db.session.flush()
            log_action("create", "client", row.id, row.name)
            db.session.commit()
            flash("Клиент добавлен.", "success")
            return redirect(url_for("main.client_list"))
    return render_template("clients/form.html", errors=errors, form=form, item=None), (
        400 if errors else 200
    )


@bp.route("/admin/clients/<int:item_id>/edit", methods=["GET", "POST"])
@admin_required
def client_edit(item_id):
    item = db.session.get(Client, item_id) or abort(404)
    errors, form = {}, _client_form(item)
    if request.method == "POST":
        errors, form = validate_client(request.form)
        if not errors:
            for key, value in form.items():
                setattr(item, key, value)
            log_action("update", "client", item.id, item.name)
            db.session.commit()
            flash("Клиент обновлён.", "success")
            return redirect(url_for("main.client_list"))
    return render_template("clients/form.html", errors=errors, form=form, item=item), (
        400 if errors else 200
    )


@bp.route("/admin/clients/<int:item_id>/delete", methods=["GET", "POST"])
@admin_required
def client_delete(item_id):
    item = db.session.get(Client, item_id) or abort(404)
    if request.method == "POST":
        log_action("delete", "client", item.id, item.name)
        db.session.delete(item)
        db.session.commit()
        flash("Клиент удалён.", "success")
        return redirect(url_for("main.client_list"))
    return render_template("confirm_delete.html", item=item, used=0, catalog="клиента")


def _empty_party():
    return {
        "name": "",
        "country": "",
        "city": "",
        "contact_name": "",
        "phone": "",
        "email": "",
        "specialty": "",
    }


def _party_form(item):
    return {
        "name": item.name,
        "country": item.country,
        "city": item.city,
        "contact_name": item.contact_name,
        "phone": item.phone,
        "email": item.email,
        "specialty": item.specialty,
    }


def _empty_client():
    return {
        "name": "",
        "kind": "cafe",
        "city": "",
        "contact_name": "",
        "phone": "",
        "email": "",
        "notes": "",
    }


def _client_form(item):
    return {
        "name": item.name,
        "kind": item.kind,
        "city": item.city,
        "contact_name": item.contact_name,
        "phone": item.phone,
        "email": item.email,
        "notes": item.notes,
    }


# --- documents ---


@bp.get("/admin/documents")
@admin_required
def document_list():
    q = " ".join(request.args.get("q", "").split())
    category = request.args.get("category", "").strip()
    stmt = select(Document).order_by(Document.created_at.desc(), Document.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Document.title.ilike(like), Document.original_name.ilike(like))
        )
    if category:
        stmt = stmt.where(Document.category == category)
    items, total, page, pages = paginate(stmt, _page())
    return render_template(
        "documents/list.html",
        items=items,
        total=total,
        page=page,
        pages=pages,
        q=q,
        category=category,
    )


@bp.route("/admin/documents/new", methods=["GET", "POST"])
@admin_required
def document_new():
    errors, form = {}, {"title": "", "category": "other"}
    if request.method == "POST":
        errors, form = validate_document_meta(request.form)
        stored, file_error = save_upload(request.files.get("file"))
        if file_error:
            errors["file"] = file_error
        if not errors:
            row = Document(
                title=form["title"],
                category=form["category"],
                original_name=stored["original_name"],
                stored_name=stored["stored_name"],
                mime_type=stored["mime_type"],
                size_bytes=stored["size_bytes"],
                uploaded_by_id=current_user().id,
            )
            db.session.add(row)
            db.session.flush()
            log_action("create", "document", row.id, row.title)
            db.session.commit()
            flash("Документ помещён в архив.", "success")
            return redirect(url_for("main.document_list"))
        if stored:
            Path(stored["path"]).unlink(missing_ok=True)
    return render_template("documents/form.html", errors=errors, form=form, item=None), (
        400 if errors else 200
    )


@bp.route("/admin/documents/<int:item_id>/edit", methods=["GET", "POST"])
@admin_required
def document_edit(item_id):
    item = db.session.get(Document, item_id) or abort(404)
    errors, form = {}, {"title": item.title, "category": item.category}
    if request.method == "POST":
        errors, form = validate_document_meta(request.form)
        new_file = request.files.get("file")
        stored = None
        if new_file and new_file.filename:
            stored, file_error = save_upload(new_file)
            if file_error:
                errors["file"] = file_error
        if not errors:
            item.title = form["title"]
            item.category = form["category"]
            if stored:
                delete_stored_file(item.stored_name)
                item.original_name = stored["original_name"]
                item.stored_name = stored["stored_name"]
                item.mime_type = stored["mime_type"]
                item.size_bytes = stored["size_bytes"]
            log_action("update", "document", item.id, item.title)
            db.session.commit()
            flash("Карточка документа обновлена.", "success")
            return redirect(url_for("main.document_list"))
        if stored:
            Path(stored["path"]).unlink(missing_ok=True)
    return render_template("documents/form.html", errors=errors, form=form, item=item), (
        400 if errors else 200
    )


@bp.route("/admin/documents/<int:item_id>/delete", methods=["GET", "POST"])
@admin_required
def document_delete(item_id):
    item = db.session.get(Document, item_id) or abort(404)
    if request.method == "POST":
        log_action("delete", "document", item.id, item.title)
        delete_stored_file(item.stored_name)
        db.session.delete(item)
        db.session.commit()
        flash("Документ удалён из архива.", "success")
        return redirect(url_for("main.document_list"))
    return render_template("confirm_delete.html", item=item, used=0, catalog="документ")


@bp.get("/admin/documents/<int:item_id>/file")
@admin_required
def document_file(item_id):
    item = db.session.get(Document, item_id) or abort(404)
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    path = folder / item.stored_name
    if not path.is_file():
        abort(404)
    return send_from_directory(
        folder,
        item.stored_name,
        as_attachment=True,
        download_name=item.original_name,
    )
