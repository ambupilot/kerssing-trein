from __future__ import annotations

import io
import json
import re
import os
import sqlite3
import uuid
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for, jsonify, make_response
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFError, CSRFProtect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
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
            CREATE TABLE IF NOT EXISTS ei_snapshots (
                record_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                payload TEXT NOT NULL,
                received_at TEXT NOT NULL,
                PRIMARY KEY(record_id, revision),
                FOREIGN KEY(owner_id) REFERENCES users(id)
            );

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

    @app.post("/api/ei/sync")
    @login_required
    def ei_sync():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="Ongeldige JSON"), 400
        record_id = payload.get("recordId")
        revision = payload.get("revision")
        selected = payload.get("selected")
        if not isinstance(record_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", record_id):
            return jsonify(error="Ongeldige registratie-ID"), 400
        try:
            uuid.UUID(record_id)
        except ValueError:
            return jsonify(error="Ongeldige registratie-ID"), 400
        if type(revision) is not int or revision < 1 or revision > 100000000:
            return jsonify(error="Ongeldige revisie"), 400
        if not isinstance(selected, list) or not selected or len(selected) > 10 or any(str(n) not in {str(i) for i in range(1, 9)} | {"90", "95"} for n in selected):
            return jsonify(error="Ongeldige EI-selectie"), 400
        if not isinstance(payload.get("identification"), str) or not 0 < len(payload["identification"].strip()) <= 120:
            return jsonify(error="Identificatienummer ontbreekt"), 400
        try:
            date.fromisoformat(payload["date"])
            datetime.strptime(payload["time"], "%H:%M")
        except (KeyError, TypeError, ValueError):
            return jsonify(error="Datum of tijd ongeldig"), 400
        if not isinstance(payload.get("details"), dict) or not isinstance(payload.get("checks"), dict):
            return jsonify(error="Formuliervelden ongeldig"), 400
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) > 100000:
            return jsonify(error="Registratie te groot"), 413
        with db_connection() as conn:
            owner = conn.execute("SELECT owner_id FROM ei_snapshots WHERE record_id = ? LIMIT 1", (record_id,)).fetchone()
            if owner and owner["owner_id"] != int(current_user.id):
                return jsonify(error="Registratie behoort aan andere gebruiker"), 403
            existing = conn.execute("SELECT payload FROM ei_snapshots WHERE record_id = ? AND revision = ?", (record_id, revision)).fetchone()
            if existing:
                if existing["payload"] != encoded:
                    return jsonify(error="Revisieconflict: lokale gegevens behouden"), 409
            else:
                conn.execute("INSERT INTO ei_snapshots (record_id, revision, owner_id, payload, received_at) VALUES (?, ?, ?, ?, ?)",
                             (record_id, revision, int(current_user.id), encoded, now_iso()))
        return jsonify(status="stored", record_id=record_id, revision=revision)

    @app.get("/ei/offline")
    @login_required
    def ei_offline_page():
        response = make_response(redirect(url_for("ei_new")))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/ei/new")
    @login_required
    def ei_new():
        ei_types = [
            (1, "Toestemming een EOA/stoptonend sein te passeren", "#F5B3B4"),
            (2, "Toestemming tot doorrijden na TRIP", "#D2D4D4"),
            (3, "Verplichting om stil te blijven staan", "#EDD0E0"),
            (4, "Intrekking van een instructie", "#FFF0BD"),
            (5, "Verplichting om de snelheid te beperken", "#AFD2EB"),
            (6, "Verplichting om te rijden op zicht", "#F5F09B"),
            (7, "Toestemming om te vertrekken", "#D2D4D4"),
            (8, "Toestemming om een defecte overweg te passeren", "#F8C4A7"),
            (90, "Controleren van de infrastructuur", "#B8DDB4"),
            (95, "Aanvullende opdracht", "#E1E1E1"),
        ]
        return render_template("ei.html", ei_types=ei_types)

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

    @app.get("/week/<int:iso_year>/<int:iso_week>/zip")
    @login_required
    def week_zip(iso_year: int, iso_week: int):
        iso_year, iso_week = safe_week(iso_year, iso_week)
        week_dir = ARCHIVE_DIR / str(iso_year) / f"{iso_week:02d}"

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if week_dir.is_dir():
                for path in sorted(week_dir.rglob("*")):
                    if path.is_file():
                        archive.write(path, arcname=path.relative_to(week_dir))
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{iso_year}-{iso_week:02d}.zip",
        )

    @app.get("/week/<int:iso_year>/<int:iso_week>/pdf")
    @login_required
    def week_pdf(iso_year: int, iso_week: int):
        iso_year, iso_week = safe_week(iso_year, iso_week)
        monday, sunday = week_bounds(iso_year, iso_week)

        with db_connection() as conn:
            rows = conn.execute(
                """
                SELECT d.*,
                       SUM(CASE WHEN a.category = 'dienstlijst' THEN 1 ELSE 0 END) AS dienstlijst_count,
                       SUM(CASE WHEN a.category = 'european_instruction' THEN 1 ELSE 0 END) AS instruction_count,
                       COUNT(a.id) AS attachment_count
                FROM duties d
                LEFT JOIN attachments a ON a.duty_id = d.id
                WHERE d.service_date BETWEEN ? AND ?
                GROUP BY d.id
                ORDER BY d.service_date
                """,
                (monday.isoformat(), sunday.isoformat()),
            ).fetchall()

        by_date = {row["service_date"]: row for row in rows}
        total_minutes = 0
        total_overrun = 0

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=14 * mm,
            leftMargin=14 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            title=f"Treindiensten week {iso_week} - {iso_year}",
            author="Kerssing Trein",
        )
        styles = getSampleStyleSheet()
        small = ParagraphStyle(
            "Small",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=10.5,
            spaceAfter=0,
        )
        note_style = ParagraphStyle(
            "Note",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#4b5563"),
            leftIndent=4 * mm,
            spaceBefore=2 * mm,
            spaceAfter=3 * mm,
        )

        story = [
            Paragraph(f"Treindiensten - week {iso_week} / {iso_year}", styles["Title"]),
            Paragraph(
                f"{monday.strftime('%d-%m-%Y')} t/m {sunday.strftime('%d-%m-%Y')}",
                styles["BodyText"],
            ),
            Spacer(1, 5 * mm),
        ]

        table_data = [[
            "Dag",
            "Datum",
            "Status / dienst",
            "Tijd",
            "Uitloop",
            "Bijlagen",
        ]]

        notes = []
        for offset in range(7):
            current_date = monday + timedelta(days=offset)
            row = by_date.get(current_date.isoformat())

            if row is None:
                status = "Niet ingevuld"
                time_text = "-"
                overrun_text = "-"
                attachments_text = "-"
            elif row["not_worked"]:
                status = "Niet gewerkt"
                time_text = "-"
                overrun_text = "-"
                attachments_text = "-"
            else:
                duty_minutes = parse_span_minutes(row["start_time"], row["end_time"])
                total_minutes += duty_minutes
                total_overrun += max(0, row["overrun_minutes"] or 0)
                status = f"Dienst {row['service_number'] or '-'}"
                time_text = f"{row['start_time'] or '-'} - {row['end_time'] or '-'}"
                overrun_text = format_minutes(row["overrun_minutes"])
                parts = []
                if row["dienstlijst_count"]:
                    parts.append(f"Dienstlijst: {row['dienstlijst_count']}")
                if row["instruction_count"]:
                    parts.append(f"EI: {row['instruction_count']}")
                attachments_text = ", ".join(parts) if parts else "Geen"

            table_data.append([
                DUTCH_DAYS[current_date.weekday()].capitalize(),
                current_date.strftime("%d-%m-%Y"),
                status,
                time_text,
                overrun_text,
                attachments_text,
            ])

            if row and row["notes"]:
                notes.append(
                    (
                        DUTCH_DAYS[current_date.weekday()].capitalize(),
                        current_date.strftime("%d-%m-%Y"),
                        row["notes"],
                    )
                )

        table = Table(
            table_data,
            colWidths=[27 * mm, 25 * mm, 40 * mm, 30 * mm, 22 * mm, 38 * mm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("LEADING", (0, 0), (-1, -1), 10.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        story.append(Spacer(1, 5 * mm))

        summary = Table([
            ["Totaal diensttijd", format_minutes(total_minutes)],
            ["Totaal uitloop", format_minutes(total_overrun)],
        ], colWidths=[45 * mm, 35 * mm])
        summary.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d1d5db")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(summary)

        if notes:
            story.append(Spacer(1, 6 * mm))
            story.append(Paragraph("Notities", styles["Heading2"]))
            for day_name, date_text, note in notes:
                story.append(Paragraph(
                    f"<b>{day_name} {date_text}</b><br/>{note}",
                    note_style,
                ))

        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph(
            "Bijlagen zijn niet in deze PDF opgenomen. De kolom 'Bijlagen' vermeldt of een Dienstlijst en/of European Instructions aanwezig zijn. "
            "Gebruik de ZIP-export om de originele bestanden van deze week te downloaden.",
            small,
        ))

        doc.build(story)
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{iso_year}-{iso_week:02d}.pdf",
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
