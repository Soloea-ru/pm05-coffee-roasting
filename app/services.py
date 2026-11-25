import secrets
import uuid
from functools import wraps
from pathlib import Path

from flask import abort, current_app, redirect, request, session, url_for
from sqlalchemy import func, select
from werkzeug.utils import secure_filename

from .models import AdminAction, User, db

PER_PAGE = 4
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".csv", ".xlsx"}


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("main.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("main.login", next=request.path))
        if not user.is_admin():
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def log_action(action, entity, entity_id=None, details=""):
    user = current_user()
    if not user or not user.is_admin():
        return
    db.session.add(
        AdminAction(
            user_id=user.id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=(details or "")[:400],
        )
    )


def paginate(stmt, page, per_page=PER_PAGE):
    try:
        page = int(page or 1)
    except (TypeError, ValueError):
        page = 1
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.session.execute(count_stmt).scalar_one()
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    items = db.session.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()
    return items, total, page, pages


def save_upload(file_storage):
    if file_storage is None or not file_storage.filename:
        return None, "Выберите файл."
    filename = secure_filename(file_storage.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return None, "Допустимы PDF, TXT, PNG, JPG, CSV, XLSX."
    stored = f"{uuid.uuid4().hex}{suffix}"
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / stored
    file_storage.save(path)
    return {
        "original_name": filename[:255] or stored,
        "stored_name": stored,
        "mime_type": file_storage.mimetype or "application/octet-stream",
        "size_bytes": path.stat().st_size,
        "path": path,
    }, None


def delete_stored_file(stored_name):
    if not stored_name:
        return
    path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_name
    if path.is_file():
        path.unlink()


def ensure_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def format_duration(seconds):
    if seconds is None:
        return "—"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}:{rest:02d}"
