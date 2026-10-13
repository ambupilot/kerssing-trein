# Kerssing Trein

Eenvoudige webapp voor het registreren van treindiensten en bijbehorende documenten.

## Functies

- Eigen login met Flask-Login en gehasht wachtwoord
- Per dag: dienstnummer, begin- en eindtijd, uitloop en notitie
- Weekoverzicht met alle zeven dagen, diensttijd, uitloop en aantal bestanden
- Uploadsecties voor Dienstlijst en European Instructions
- Meerdere uploads tegelijk: JPG/JPEG/PNG/WEBP/HEIC/HEIF/PDF
- Unieke serverbestandsnamen, ook wanneer iOS telkens `image.jpg` aanlevert
- Opslag in `data/administratie/<jaar>/<week>/<dag>/`
- SQLite in `data/database/trein.db`
- Lokaal concept van dagvelden via `localStorage`
- Dubbel-submitbeveiliging in de browser
- `/health` geeft `{"status":"ok"}`
- Docker/Gunicorn, alleen gepubliceerd op `127.0.0.1:8089`

## Architectuur

De container is stateless. Alle persistente gegevens staan onder `./data`, dat als volume wordt gekoppeld aan `/app/data`.

```text
data/
├── database/
│   └── trein.db
└── administratie/
    └── 2026/
        └── 42/
            └── maandag/
                ├── dienstlijst-20261012-061200-a1b2c3d4e5.jpg
                └── european_instruction-20261012-084500-f6e7d8c9b0.pdf
```

De database-initialisatie gebruikt `CREATE TABLE IF NOT EXISTS` en `INSERT OR IGNORE`, zodat meerdere Gunicorn-workers veilig gelijktijdig kunnen starten.

## Lokaal ontwikkelen op macOS

```bash
git clone git@github.com:ambupilot/kerssing-trein.git
cd kerssing-trein
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Pas `.env` aan. Voor lokale ontwikkeling blijft `SESSION_COOKIE_SECURE=false`.

Start vervolgens:

```bash
flask --app app run --debug
```

Open `http://127.0.0.1:5000`.

## Docker lokaal

```bash
docker compose up -d --build
curl http://127.0.0.1:8089/health
```

## Productie

Zie [DEPLOYMENT.md](DEPLOYMENT.md).

## Opmerking over wachtwoordwijzigingen

De eerste gebruiker wordt alleen aangemaakt als de gebruikersnaam nog niet in de database staat. Een latere wijziging van `ADMIN_PASSWORD` in `.env` vervangt dus niet automatisch het bestaande wachtwoord. Dat voorkomt onverwachte accountwijzigingen bij een rebuild.
