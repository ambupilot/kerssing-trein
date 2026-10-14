from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DB_DIR = DATA_DIR / "database"
ARCHIVE_DIR = DATA_DIR / "administratie"
DB_PATH = DB_DIR / "trein.db"
APP_TZ = ZoneInfo(os.getenv("TZ", "Europe/Amsterdam"))

DUTCH_DAYS = {
    0: "maandag",
    1: "dinsdag",
    2: "woensdag",
    3: "donderdag",
    4: "vrijdag",
    5: "zaterdag",
    6: "zondag",
}

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "heif", "pdf"}
UPLOAD_CATEGORIES = {
    "dienstlijst": "Dienstlijst",
    "european_instruction": "European Instruction",
}


class User(UserMixin):
    def __init__(self, user_id: int, username: str):
        self.id = str(user_id)
        self.username = username


def db_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def now_iso() -> str:
    return datetime.now(APP_TZ).isoformat(timespec="seconds")


def init_db() -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS duties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_date TEXT UNIQUE NOT NULL,
                service_number TEXT NOT NULL DEFAULT '',
                start_time TEXT,
                end_time TEXT,
                overrun_minutes INTEGER NOT NULL DEFAULT 0,
                not_worked INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                duty_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(duty_id) REFERENCES duties(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_attachments_duty_id ON attachments(duty_id);
            CREATE INDEX IF NOT EXISTS idx_duties_service_date ON duties(service_date);
            """
        )

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(duties)").fetchall()}
        if "not_worked" not in columns:
            conn.execute("ALTER TABLE duties ADD COLUMN not_worked INTEGER NOT NULL DEFAULT 0")

        username = os.getenv("ADMIN_USERNAME")
        password = os.getenv("ADMIN_PASSWORD")
        if username and password:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (username, password_hash, created_at)
                VALUES (?, ?, ?)
                """,
                (username, generate_password_hash(password), now_iso()),
            )


def week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    return monday, monday + timedelta(days=6)


def safe_week(iso_year: int, iso_week: int) -> tuple[int, int]:
    try:
        date.fromisocalendar(iso_year, iso_week, 1)
    except ValueError:
        current = date.today().isocalendar()
        return current.year, current.week
    return iso_year, iso_week


def day_archive_dir(service_date: date) -> Path:
    iso = service_date.isocalendar()
    return ARCHIVE_DIR / str(iso.year) / f"{iso.week:02d}" / DUTCH_DAYS[service_date.weekday()]


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_span_minutes(start_time: str | None, end_time: str | None) -> int:
    if not start_time or not end_time:
        return 0
    try:
        start = datetime.strptime(start_time, "%H:%M")
        end = datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return 0
    minutes = int((end - start).total_seconds() // 60)
    if minutes < 0:
        minutes += 24 * 60
    return minutes


def format_minutes(minutes: int | None) -> str:
    value = max(0, int(minutes or 0))
    return f"{value // 60}:{value % 60:02d}"


def attachment_display_rows(rows: list[sqlite3.Row]) -> list[dict]:
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["category"]] = totals.get(row["category"], 0) + 1

    counters: dict[str, int] = {}
    result = []
    for row in rows:
        category = row["category"]
        counters[category] = counters.get(category, 0) + 1
        label = UPLOAD_CATEGORIES.get(category, "Bestand")
        if category == "european_instruction" or totals.get(category, 0) > 1:
            label = f"{label} {counters[category]}"
        try:
            display_time = datetime.fromisoformat(row["created_at"]).astimezone(APP_TZ).strftime("%H:%M")
        except (TypeError, ValueError):
            display_time = "--:--"
        result.append({"row": row, "label": label, "display_time": display_time})
    return result


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "development-only-change-me")
    app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = app.config["SESSION_COOKIE_SECURE"]
    app.config["WTF_CSRF_TIME_LIMIT"] = None

    CSRFProtect(app)
    login_manager = LoginManager(app)
    login_manager.login_view = "login"
    login_manager.login_message = "Log eerst in om deze pagina te bekijken."

    @login_manager.user_loader
    def load_user(user_id: str):
        with db_connection() as conn:
            row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(row["id"], row["username"]) if row else None

    @app.context_processor
    def inject_helpers():
        return {
            "DUTCH_DAYS": DUTCH_DAYS,
            "format_minutes": format_minutes,
        }

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return render_template(
            "csrf_error.html",
            reason=error.description,
        ), 400

    @app.errorhandler(413)
    def payload_too_large(_error):
        flash("De geselecteerde bestanden zijn samen te groot. Kies kleinere bestanden of upload ze in delen.", "error")
        return redirect(request.referrer or url_for("week"))

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("week"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            with db_connection() as conn:
                row = conn.execute(
                    "SELECT id, username, password_hash FROM users WHERE username = ?",
                    (username,),
                ).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                login_user(User(row["id"], row["username"]), remember=True)
                return redirect(url_for("week"))
            flash("Onjuiste gebruikersnaam of wachtwoord.", "error")
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        return redirect(url_for("week"))

    @app.route("/week")
    @login_required
    def week():
        today_iso = date.today().isocalendar()
        iso_year = request.args.get("year", type=int) or today_iso.year
        iso_week = request.args.get("week", type=int) or today_iso.week
        iso_year, iso_week = safe_week(iso_year, iso_week)
        monday, sunday = week_bounds(iso_year, iso_week)

        with db_connection() as conn:
            rows = conn.execute(
                """
                SELECT d.*,
                       (SELECT COUNT(*) FROM attachments a WHERE a.duty_id = d.id) AS attachment_count
                FROM duties d
                WHERE service_date BETWEEN ? AND ?
                ORDER BY service_date
                """,
                (monday.isoformat(), sunday.isoformat()),
            ).fetchall()

        by_date = {row["service_date"]: row for row in rows}
        days = []
        total_minutes = 0
        total_overrun = 0
        for offset in range(7):
            current_date = monday + timedelta(days=offset)
            row = by_date.get(current_date.isoformat())
            duty_minutes = (
                parse_span_minutes(row["start_time"], row["end_time"])
                if row and not row["not_worked"]
                else 0
            )
            if row and not row["not_worked"]:
                total_minutes += duty_minutes
                total_overrun += max(0, row["overrun_minutes"] or 0)
            days.append({"date": current_date, "row": row, "duty_minutes": duty_minutes})

        prev_iso = (monday - timedelta(days=7)).isocalendar()
        next_iso = (monday + timedelta(days=7)).isocalendar()
        return render_template(
            "week.html",
            iso_year=iso_year,
            iso_week=iso_week,
            monday=monday,
            sunday=sunday,
            days=days,
            total_minutes=total_minutes,
            total_overrun=total_overrun,
            prev_year=prev_iso.year,
            prev_week=prev_iso.week,
            next_year=next_iso.year,
            next_week=next_iso.week,
        )

    @app.route("/dag/<service_date>", methods=["GET", "POST"])
    @login_required
    def day(service_date: str):
        try:
            service_day = date.fromisoformat(service_date)
        except ValueError:
            abort(404)

        if request.method == "POST":
            not_worked = request.form.get("not_worked") == "1"
            service_number = "" if not_worked else request.form.get("service_number", "").strip()
            start_time = None if not_worked else (request.form.get("start_time") or None)
            end_time = None if not_worked else (request.form.get("end_time") or None)
            overrun_minutes = 0 if not_worked else max(0, request.form.get("overrun_minutes", type=int) or 0)
            notes = request.form.get("notes", "").strip()
            timestamp = now_iso()

            with db_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO duties (
                        service_date, service_number, start_time, end_time,
                        overrun_minutes, not_worked, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(service_date) DO UPDATE SET
                        service_number = excluded.service_number,
                        start_time = excluded.start_time,
                        end_time = excluded.end_time,
                        overrun_minutes = excluded.overrun_minutes,
                        not_worked = excluded.not_worked,
                        notes = excluded.notes,
                        updated_at = excluded.updated_at
                    """,
                    (
                        service_day.isoformat(), service_number, start_time, end_time,
                        overrun_minutes, int(not_worked), notes, timestamp, timestamp,
                    ),
                )
            flash("Dag opgeslagen.", "success")
            return redirect(url_for("day", service_date=service_day.isoformat(), saved="1"))

        with db_connection() as conn:
            row = conn.execute("SELECT * FROM duties WHERE service_date = ?", (service_day.isoformat(),)).fetchone()
            attachments = []
            if row:
                attachments = conn.execute(
                    "SELECT * FROM attachments WHERE duty_id = ? ORDER BY created_at, id",
                    (row["id"],),
                ).fetchall()

        by_category = {key: [] for key in UPLOAD_CATEGORIES}
        for item in attachment_display_rows(attachments):
            by_category.setdefault(item["row"]["category"], []).append(item)

        return render_template(
            "day.html",
            d=service_day,
            row=row,
            duty_minutes=(
                parse_span_minutes(row["start_time"], row["end_time"])
                if row and not row["not_worked"]
                else 0
            ),
            attachments=by_category,
        )

    @app.post("/dag/<service_date>/verwijderen")
    @login_required
    def delete_day(service_date: str):
        try:
            service_day = date.fromisoformat(service_date)
        except ValueError:
            abort(404)

        filenames = []
        with db_connection() as conn:
            row = conn.execute(
                "SELECT id FROM duties WHERE service_date = ?",
                (service_day.isoformat(),),
            ).fetchone()
            if row:
                filenames = [
                    item["filename"]
                    for item in conn.execute(
                        "SELECT filename FROM attachments WHERE duty_id = ?",
                        (row["id"],),
                    ).fetchall()
                ]
                conn.execute("DELETE FROM duties WHERE id = ?", (row["id"],))

        archive_dir = day_archive_dir(service_day)
        for filename in filenames:
            try:
                (archive_dir / filename).unlink(missing_ok=True)
            except OSError:
                pass
        try:
            archive_dir.rmdir()
        except OSError:
            pass

        flash("Dag leeggemaakt.", "success")
        return redirect(url_for("day", service_date=service_day.isoformat(), cleared="1"))

    @app.post("/dag/<service_date>/upload/<category>")
    @login_required
    def upload_files(service_date: str, category: str):
        if category not in UPLOAD_CATEGORIES:
            abort(404)
        try:
            service_day = date.fromisoformat(service_date)
        except ValueError:
            abort(404)

        files = [f for f in request.files.getlist("attachments") if f and f.filename]
        if not files:
            flash("Kies eerst één of meer bestanden.", "error")
            return redirect(url_for("day", service_date=service_day.isoformat()))

        invalid = [f.filename for f in files if not allowed_file(f.filename)]
        if invalid:
            flash("Niet toegestaan bestandstype: " + ", ".join(invalid), "error")
            return redirect(url_for("day", service_date=service_day.isoformat()))

        archive_dir = day_archive_dir(service_day)
        archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now_iso()

        with db_connection() as conn:
            duty = conn.execute("SELECT id FROM duties WHERE service_date = ?", (service_day.isoformat(),)).fetchone()
            if duty is None:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO duties (
                        service_date, service_number, start_time, end_time,
                        overrun_minutes, not_worked, notes, created_at, updated_at
                    ) VALUES (?, '', NULL, NULL, 0, 0, '', ?, ?)
                    """,
                    (service_day.isoformat(), timestamp, timestamp),
                )
                duty = conn.execute("SELECT id FROM duties WHERE service_date = ?", (service_day.isoformat(),)).fetchone()

            saved_count = 0
            for upload in files:
                original_name = secure_filename(upload.filename) or "bestand"
                extension = original_name.rsplit(".", 1)[1].lower()
                file_stamp = datetime.now(APP_TZ).strftime("%Y%m%d-%H%M%S")
                unique_name = f"{category}-{file_stamp}-{uuid.uuid4().hex[:10]}.{extension}"
                upload.save(archive_dir / unique_name)
                conn.execute(
                    """
                    INSERT INTO attachments (duty_id, category, filename, original_name, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (duty["id"], category, unique_name, original_name, now_iso()),
                )
                saved_count += 1

        label = UPLOAD_CATEGORIES[category]
        flash(f"{saved_count} bestand(en) toegevoegd aan {label}.", "success")
        return redirect(url_for("day", service_date=service_day.isoformat()))

    @app.get("/bijlage/<int:attachment_id>")
    @login_required
    def attachment(attachment_id: int):
        with db_connection() as conn:
            row = conn.execute(
                """
                SELECT a.*, d.service_date
                FROM attachments a
                JOIN duties d ON d.id = a.duty_id
                WHERE a.id = ?
                """,
                (attachment_id,),
            ).fetchone()
        if not row:
            abort(404)
        path = day_archive_dir(date.fromisoformat(row["service_date"])) / row["filename"]
        if not path.is_file():
            abort(404)
        return send_file(path, download_name=row["original_name"], as_attachment=False)

    @app.post("/bijlage/<int:attachment_id>/verwijderen")
    @login_required
    def delete_attachment(attachment_id: int):
        with db_connection() as conn:
            row = conn.execute(
                """
                SELECT a.*, d.service_date
                FROM attachments a
                JOIN duties d ON d.id = a.duty_id
                WHERE a.id = ?
                """,
                (attachment_id,),
            ).fetchone()
            if not row:
                abort(404)
            service_day = date.fromisoformat(row["service_date"])
            conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        path = day_archive_dir(service_day) / row["filename"]
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        flash("Bijlage verwijderd.", "success")
        return redirect(url_for("day", service_date=service_day.isoformat()))

    return app


init_db()
app = create_app()
