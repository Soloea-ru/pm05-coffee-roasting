import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from werkzeug.security import check_password_hash

from app import create_app
from app.config import mysql_uri
from app.models import AdminAction, Client, CoffeeVariety, Document, RoastRecipe, User, db
from app.validators import validate_recipe, validate_variety


class ConfigTests(unittest.TestCase):
    def test_database_url_wins_over_mysql_parts(self):
        env = {
            "DATABASE_URL": "mysql+pymysql://a:b@db:3306/app?charset=utf8mb4",
            "MYSQL_USER": "ignored",
            "MYSQL_PASSWORD": "ignored",
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_PORT": "3306",
            "MYSQL_DATABASE": "kofe_obzharka",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(mysql_uri(), env["DATABASE_URL"])

    def test_mysql_password_is_url_quoted(self):
        env = {
            "DATABASE_URL": "",
            "MYSQL_USER": "kofe",
            "MYSQL_PASSWORD": "p@ss:w/rd",
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_PORT": "3306",
            "MYSQL_DATABASE": "kofe_obzharka",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(
                mysql_uri(),
                "mysql+pymysql://kofe:p%40ss%3Aw%2Frd@127.0.0.1:3306/kofe_obzharka?charset=utf8mb4",
            )


class ValidatorTests(unittest.TestCase):
    def test_variety_requires_name_and_country(self):
        errors, _cleaned = validate_variety({"species": "arabica", "processing": "washed"})
        self.assertIn("name", errors)
        self.assertIn("origin_country", errors)

    def test_profile_rejects_blend_composition(self):
        class Form(dict):
            def getlist(self, key):
                return self[key]

        form = Form({
            "name": "Тест",
            "kind": "profile",
            "roast_level": "city",
            "charge_temp_c": "198",
            "drop_temp_c": "210",
            "duration_sec": "600",
            "development_pct": "18",
            "sample_batch_kg": "1",
            "variety_id": ["1", "2"],
            "percent": ["60", "40"],
        })
        errors, _cleaned = validate_recipe(form, {1, 2})
        self.assertIn("kind", errors)


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{root / 'test.db'}",
            "UPLOAD_FOLDER": root / "uploads",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def csrf(self):
        with self.client.session_transaction() as sess:
            sess["csrf"] = "test-csrf"
            return sess["csrf"]

    def post(self, url, **fields):
        fields["csrf_token"] = self.csrf()
        return self.client.post(url, data=fields, follow_redirects=False)

    def login(self, login="admin", password="KofeAdmin123!"):
        return self.post("/login", login=login, password=password)

    def test_password_is_pbkdf2(self):
        with self.app.app_context():
            user = db.session.execute(select(User).where(User.login == "admin")).scalar_one()
            self.assertTrue(user.password_hash.startswith("pbkdf2:sha256"))
            self.assertTrue(check_password_hash(user.password_hash, "KofeAdmin123!"))

    def test_login_form_includes_csrf_token(self):
        response = self.client.get("/login")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertRegex(html, r'name="csrf_token" value="[0-9a-f]{32}"')

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_guest_cannot_open_admin(self):
        self.login("guest", "Guest123!")
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 403)
        self.assertIn("администратору", response.get_data(as_text=True))

    def test_bad_csrf_is_rejected(self):
        self.login()
        response = self.client.post(
            "/admin/clients/new",
            data={"csrf_token": "wrong", "name": "X", "kind": "cafe", "city": "Казань"},
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_login_opens_dashboard_and_journal(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        home = self.client.get("/admin")
        self.assertEqual(home.status_code, 200)
        self.assertIn("Сводка обжарочной", home.get_data(as_text=True))
        with self.app.app_context():
            action = db.session.execute(
                select(AdminAction).where(AdminAction.action == "login")
            ).scalar_one()
            self.assertEqual(action.entity, "session")

    def test_variety_list_filter_and_pagination(self):
        self.login()
        page1 = self.client.get("/admin/varieties")
        text = page1.get_data(as_text=True)
        self.assertEqual(page1.status_code, 200)
        self.assertIn("Серрадо", text)
        self.assertIn("стр. 1 из 2", text)
        page2 = self.client.get("/admin/varieties?page=2")
        self.assertIn("Иргачеффе", page2.get_data(as_text=True))
        ethiopia = self.client.get("/admin/varieties?country=Эфиопия")
        body = ethiopia.get_data(as_text=True)
        self.assertIn("Иргачеффе", body)
        self.assertNotIn("Манделинг", body)

    def test_variety_crud(self):
        self.login()
        created = self.post(
            "/admin/varieties/new",
            name="Пакамара Гватемала",
            species="arabica",
            origin_country="Гватемала",
            region="Антигуа",
            farm="Финка Пуэбло",
            processing="washed",
            altitude_m="1550",
            sca_score="86",
            flavor_notes="какао, цветы",
        )
        self.assertEqual(created.status_code, 302)
        with self.app.app_context():
            row = db.session.execute(
                select(CoffeeVariety).where(CoffeeVariety.name == "Пакамара Гватемала")
            ).scalar_one()
            item_id = row.id
        edited = self.post(
            f"/admin/varieties/{item_id}/edit",
            name="Пакамара Антигуа",
            species="arabica",
            origin_country="Гватемала",
            region="Антигуа",
            farm="Финка Пуэбло",
            processing="honey",
            altitude_m="1550",
            sca_score="86.5",
            flavor_notes="какао",
        )
        self.assertEqual(edited.status_code, 302)
        deleted = self.post(f"/admin/varieties/{item_id}/delete")
        self.assertEqual(deleted.status_code, 302)
        with self.app.app_context():
            gone = db.session.execute(
                select(CoffeeVariety).where(CoffeeVariety.name == "Пакамара Антигуа")
            ).scalar_one_or_none()
            self.assertIsNone(gone)

    def test_cannot_delete_variety_used_in_recipe(self):
        self.login()
        with self.app.app_context():
            item_id = db.session.execute(
                select(CoffeeVariety.id).where(CoffeeVariety.name == "Иргачеффе хейрлум")
            ).scalar_one()
        page = self.client.get(f"/admin/varieties/{item_id}/delete")
        self.assertIn("рецептур", page.get_data(as_text=True))
        self.post(f"/admin/varieties/{item_id}/delete")
        with self.app.app_context():
            still = db.session.get(CoffeeVariety, item_id)
            self.assertIsNotNone(still)

    def test_client_create_and_reports(self):
        self.login()
        created = self.post(
            "/admin/clients/new",
            name="Бар «Дрожжи»",
            kind="cafe",
            city="Пермь",
            contact_name="Лена",
            phone="+7 342 100-20-30",
            email="bar@drozzhi.example",
            notes="фильтр по пятницам",
        )
        self.assertEqual(created.status_code, 302)
        reports = self.client.get("/admin/reports")
        self.assertEqual(reports.status_code, 200)
        self.assertIn("Сорта по странам", reports.get_data(as_text=True))
        with self.app.app_context():
            self.assertIsNotNone(
                db.session.execute(select(Client).where(Client.name == "Бар «Дрожжи»")).scalar_one()
            )

    def test_document_upload(self):
        self.login()
        payload = {
            "csrf_token": self.csrf(),
            "title": "Каппинг Бразилии",
            "category": "cupping",
            "file": (BytesIO("чашка чистая, орех\n".encode("utf-8")), "cupping.txt"),
        }
        response = self.client.post(
            "/admin/documents/new",
            data=payload,
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            doc = db.session.execute(
                select(Document).where(Document.title == "Каппинг Бразилии")
            ).scalar_one()
            stored = Path(self.app.config["UPLOAD_FOLDER"]) / doc.stored_name
            self.assertTrue(stored.is_file())

    def test_invalid_recipe_stays_on_form(self):
        self.login()
        with self.app.app_context():
            vid = db.session.execute(select(CoffeeVariety.id)).scalars().first()
        response = self.post(
            "/admin/recipes/new",
            name="Сломанный бленд",
            kind="blend",
            roast_level="city",
            charge_temp_c="198",
            drop_temp_c="210",
            duration_sec="600",
            development_pct="18",
            sample_batch_kg="1",
            variety_id=str(vid),
            percent="100",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("минимум из двух сортов", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertIsNone(
                db.session.execute(
                    select(RoastRecipe).where(RoastRecipe.name == "Сломанный бленд")
                ).scalar_one_or_none()
            )

    def test_missing_page_is_404(self):
        self.login()
        response = self.client.get("/admin/no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Такой страницы нет", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
