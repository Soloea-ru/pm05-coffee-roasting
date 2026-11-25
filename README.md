# Кофейная обжарка и поставки

Учебная административная панель для ПМ.05: учёт **сортов зелёного кофе**, **профилей обжарки и блендов**, **поставщиков зерна**, **клиентов** (кофейни и обжарочные), **сводных отчётов** и **архива документов**.

Смысл функций близок к производственным системам учёта обжарки (профили, образец партии, происхождение зерна, поставки). Это не копия чужого продукта, а своя учебная админка на Flask.

## Что умеет первый срез

- вход по логину и паролю, роль «администратор», сессии;
- CSRF на формах, пароли в PBKDF2 (SHA-256);
- списки с поиском, фильтром и постраничным выводом;
- создание, правка и удаление записей справочников;
- загрузка файлов в каталог `uploads/` (метаданные в MySQL, сами файлы не в git);
- журнал `admin_actions`: кто, когда, что сделал.

## Запуск с MySQL 8

```bash
cp .env.example .env
docker compose up -d
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

Откройте http://127.0.0.1:5000

Если MySQL уже стоит локально, создайте базу и пропишите её в `.env`:

```sql
CREATE DATABASE coffee_roasting CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

```
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=coffee
MYSQL_PASSWORD=coffee
MYSQL_DATABASE=coffee_roasting
```

Либо одной строкой (`DATABASE_URL` важнее отдельных `MYSQL_*`):

```
DATABASE_URL=mysql+pymysql://coffee:ПАРОЛЬ@127.0.0.1:3306/coffee_roasting?charset=utf8mb4
```

Пустую базу приложение само дополнит таблицами и учебными записями при первом запуске.

Windows:

```powershell
copy .env.example .env
docker compose up -d
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

## Учебные входы

| Логин | Пароль | Роль |
| --- | --- | --- |
| admin | CoffeeAdmin123! | администратор |
| guest | Guest123! | только просмотр запрещён (проверка роли) |

## Экраны

- `/login` — вход;
- `/admin` — сводка;
- `/admin/varieties` — сорта кофе;
- `/admin/recipes` — профили обжарки и бленды;
- `/admin/suppliers` — поставщики зелёного зерна;
- `/admin/clients` — клиенты;
- `/admin/reports` — сводные отчёты;
- `/admin/documents` — архив документов;
- `/admin/journal` — журнал действий.

## Тесты

Автотесты поднимают временный **SQLite**, MySQL для них не нужен:

```bash
.venv/bin/python -m unittest discover -s tests -t . -v
```

## Структура

- `app/models.py` — доступ к данным;
- `app/validators.py` и `app/services.py` — проверки, журнал, файлы;
- `app/routes.py` — маршруты и представление;
- `templates/` — Jinja2;
- `static/css/admin.css` — своя вёрстка панели;
- `uploads/` — файловый архив (не git-lfs).
