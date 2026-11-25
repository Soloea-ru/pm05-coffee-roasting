from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from .models import (
    Client,
    CoffeeVariety,
    Document,
    RecipeComponent,
    RoastRecipe,
    Supplier,
    User,
    db,
)


def seed_demo(upload_folder: Path):
    if db.session.execute(select(func.count()).select_from(User)).scalar():
        return

    admin = User(
        login="admin",
        password_hash=generate_password_hash("CoffeeAdmin123!", method="pbkdf2:sha256"),
        full_name="Анна Обжарова",
        role="admin",
    )
    viewer = User(
        login="guest",
        password_hash=generate_password_hash("Guest123!", method="pbkdf2:sha256"),
        full_name="Илья Смотров",
        role="viewer",
    )
    db.session.add_all([admin, viewer])
    db.session.flush()

    varieties = [
        CoffeeVariety(
            name="Иргачеффе хейрлум",
            species="arabica",
            origin_country="Эфиопия",
            region="Сидамо / Иргачеффе",
            farm="Кооператив Кочере",
            processing="washed",
            altitude_m=2050,
            sca_score=Decimal("87.5"),
            flavor_notes="жасмин, бергамот, лимонная цедра",
        ),
        CoffeeVariety(
            name="Уила катурра",
            species="arabica",
            origin_country="Колумбия",
            region="Уила",
            farm="Финка Эль Парраль",
            processing="washed",
            altitude_m=1720,
            sca_score=Decimal("85.0"),
            flavor_notes="карамель, красное яблоко, какао",
        ),
        CoffeeVariety(
            name="Серрадо жёлтый бурбон",
            species="arabica",
            origin_country="Бразилия",
            region="Минас-Жерайс, Серрадо",
            farm="Фазенда Лагоа",
            processing="natural",
            altitude_m=1100,
            sca_score=Decimal("83.5"),
            flavor_notes="фундук, молочный шоколад, сушёная вишня",
        ),
        CoffeeVariety(
            name="Ньери SL28",
            species="arabica",
            origin_country="Кения",
            region="Ньери",
            farm="Станция Тету",
            processing="washed",
            altitude_m=1780,
            sca_score=Decimal("88.0"),
            flavor_notes="чёрная смородина, грейпфрут, тростниковый сахар",
        ),
        CoffeeVariety(
            name="Уэуэтенанго бурбон",
            species="arabica",
            origin_country="Гватемала",
            region="Уэуэтенанго",
            farm="Финка Ла Эсперанса",
            processing="honey",
            altitude_m=1580,
            sca_score=Decimal("84.75"),
            flavor_notes="персик, сгущёнка, тёплые специи",
        ),
        CoffeeVariety(
            name="Манделинг",
            species="arabica",
            origin_country="Индонезия",
            region="Северная Суматра",
            farm="Кооператив Линтонг",
            processing="wet_hulled",
            altitude_m=1350,
            sca_score=Decimal("82.0"),
            flavor_notes="влажная земля, тёмная патока, кедр",
        ),
    ]
    db.session.add_all(varieties)
    db.session.flush()
    by_name = {row.name: row for row in varieties}

    recipes = [
        RoastRecipe(
            name="Фильтр Nordic Light",
            kind="profile",
            roast_level="light",
            charge_temp_c=196,
            drop_temp_c=205,
            duration_sec=570,
            development_pct=16,
            sample_batch_kg=Decimal("1.20"),
            notes="Короткое развитие, сохранить цветочную кислотность Иргачеффе.",
        ),
        RoastRecipe(
            name="Эспрессо Сити",
            kind="profile",
            roast_level="city",
            charge_temp_c=198,
            drop_temp_c=212,
            duration_sec=660,
            development_pct=19,
            sample_batch_kg=Decimal("2.50"),
            notes="Базовый профиль под рожок для Колумбии Уила.",
        ),
        RoastRecipe(
            name="Омни Full City",
            kind="profile",
            roast_level="full_city",
            charge_temp_c=200,
            drop_temp_c=216,
            duration_sec=720,
            development_pct=21,
            sample_batch_kg=Decimal("5.00"),
            notes="Плотное тело, шоколад. Образец 5 кг на 12-кг ростере.",
        ),
        RoastRecipe(
            name="Завтрак-бленд",
            kind="blend",
            roast_level="city",
            charge_temp_c=199,
            drop_temp_c=210,
            duration_sec=640,
            development_pct=18,
            sample_batch_kg=Decimal("3.00"),
            notes="60 % Бразилия + 40 % Колумбия. Стабильный эспрессо для кофеен.",
        ),
        RoastRecipe(
            name="Кения под V60",
            kind="profile",
            roast_level="light",
            charge_temp_c=195,
            drop_temp_c=204,
            duration_sec=530,
            development_pct=15,
            sample_batch_kg=Decimal("0.80"),
            notes="Небольшой образец под каппинг и воронку.",
        ),
    ]
    db.session.add_all(recipes)
    db.session.flush()

    db.session.add_all(
        [
            RecipeComponent(recipe_id=recipes[0].id, variety_id=by_name["Иргачеффе хейрлум"].id, percent=100),
            RecipeComponent(recipe_id=recipes[1].id, variety_id=by_name["Уила катурра"].id, percent=100),
            RecipeComponent(recipe_id=recipes[2].id, variety_id=by_name["Серрадо жёлтый бурбон"].id, percent=100),
            RecipeComponent(recipe_id=recipes[3].id, variety_id=by_name["Серрадо жёлтый бурбон"].id, percent=60),
            RecipeComponent(recipe_id=recipes[3].id, variety_id=by_name["Уила катурра"].id, percent=40),
            RecipeComponent(recipe_id=recipes[4].id, variety_id=by_name["Ньери SL28"].id, percent=100),
        ]
    )

    db.session.add_all(
        [
            Supplier(
                name="ООО «Зелёное зерно Север»",
                country="Россия",
                city="Москва",
                contact_name="Павел Седов",
                phone="+7 495 100-20-30",
                email="green@north-beans.example",
                specialty="Импорт микролотов Эфиопии и Кении",
            ),
            Supplier(
                name="Sidamo Highland Coop",
                country="Эфиопия",
                city="Ауаса",
                contact_name="Мескерем Абебе",
                phone="+251 11 000 0000",
                email="export@sidamo-highland.example",
                specialty="Мытая арабика Иргачеффе / Кочере",
            ),
            Supplier(
                name="Cerrado Gold Export",
                country="Бразилия",
                city="Патросиниу",
                contact_name="Лукас Алмейда",
                phone="+55 34 0000-0000",
                email="lots@cerrado-gold.example",
                specialty="Натуральный жёлтый бурбон, биг-бэги 60 кг",
            ),
            Supplier(
                name="Andean Harvest SAS",
                country="Колумбия",
                city="Нейва",
                contact_name="Камила Руис",
                phone="+57 8 000 0000",
                email="trade@andean-harvest.example",
                specialty="Катурра и кастильо с ферм Уилы",
            ),
            Supplier(
                name="Rift Valley Greens",
                country="Кения",
                city="Найроби",
                contact_name="Дэниел Кимани",
                phone="+254 20 000 0000",
                email="sl28@riftvalley.example",
                specialty="SL28/SL34, станции Ньери и Кириньяга",
            ),
        ]
    )

    db.session.add_all(
        [
            Client(
                name="Кофейня «На Мельнице»",
                kind="cafe",
                city="Казань",
                contact_name="Марина Юсупова",
                phone="+7 843 200-10-10",
                email="hello@na-melnitse.example",
                notes="Еженедельный эспрессо-бленд 6 кг.",
            ),
            Client(
                name="Обжарочная «Каланча»",
                kind="roastery",
                city="Москва",
                contact_name="Глеб Орлов",
                phone="+7 495 300-40-50",
                email="roast@kalancha.example",
                notes="Покупает зелёное зерно и профили, обжаривает у себя.",
            ),
            Client(
                name="Сеть «Зёрнышко»",
                kind="retail",
                city="Санкт-Петербург",
                contact_name="Ольга Ветрова",
                phone="+7 812 400-50-60",
                email="buy@zernyshko.example",
                notes="Фасовка 250 г, светлая фильтр-обжарка.",
            ),
            Client(
                name="Specialty-бар «Южный склон»",
                kind="cafe",
                city="Краснодар",
                contact_name="Артём Лоза",
                phone="+7 861 500-60-70",
                email="bar@yug-sklon.example",
                notes="Сезонные лоты Кении и Эфиопии.",
            ),
            Client(
                name="Офис-корнер «Байт и зерно»",
                kind="office",
                city="Екатеринбург",
                contact_name="Никита Барсуков",
                phone="+7 343 600-70-80",
                email="office@byte-bean.example",
                notes="Поставка молотого под эспрессо-точку.",
            ),
        ]
    )
    db.session.flush()

    upload_folder.mkdir(parents=True, exist_ok=True)
    samples = [
        (
            "contract-sidamo.txt",
            "Контракт на поставку мытой арабики Иргачеффе, урожай 2026.",
            "Договор с Sidamo Highland Coop",
            "contract",
        ),
        (
            "phyto-kenya.txt",
            "Фитосанитарный сертификат партии Ньери SL28, мешки 60 кг.",
            "Фитосертификат партии Кении",
            "certificate",
        ),
        (
            "cupping-yirg.txt",
            "Каппинг 24.10.2026: 87.5, жасмин / бергамот, чистая чашка.",
            "Каппинг-лист Иргачеффе",
            "cupping",
        ),
        (
            "invoice-sever.txt",
            "Счёт ООО «Зелёное зерно Север» за 10 мешков Бразилии Серрадо.",
            "Счёт на зелёное зерно Серрадо",
            "invoice",
        ),
    ]
    for stored, body, title, category in samples:
        path = upload_folder / stored
        path.write_text(body + "\n", encoding="utf-8")
        db.session.add(
            Document(
                title=title,
                category=category,
                original_name=stored.replace(".txt", ".txt"),
                stored_name=stored,
                mime_type="text/plain",
                size_bytes=path.stat().st_size,
                uploaded_by_id=admin.id,
            )
        )
    db.session.commit()
