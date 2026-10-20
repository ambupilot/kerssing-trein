# EI-testomgeving (niet operationeel)

De productie-app blijft op 127.0.0.1:8089 en gebruikt ./data.
Deze compose gebruikt **127.0.0.1:8091** en **./data-ei-test**. Publiceer de testomgeving uitsluitend via een eigen HTTPS-hostnaam met toegangsbeveiliging, niet via een publieke onbeveiligde poort.

## Op de VPS

```bash
cd /opt/web
git clone --branch feature/european-instructions https://github.com/ambupilot/kerssing-trein.git kerssing-trein-ei-test
cd kerssing-trein-ei-test
cp .env.example .env.ei-test
```

Vul in `.env.ei-test` **nieuwe testcredentials** en een eigen sterke `SECRET_KEY` in. Gebruik geen productiecredentials. Maak geen symlink naar de productie-`data` directory.

```bash
docker compose -f docker-compose.ei-test.yml up -d --build
curl -fsS http://127.0.0.1:8091/health
docker compose -f docker-compose.ei-test.yml logs --tail=80
```

Voeg vervolgens in de bestaande Caddy-configuratie een **afzonderlijke** HTTPS-testhost toe, bijvoorbeeld `ei-test.kerssing.nl`, met reverse proxy naar `127.0.0.1:8091`. Configureer DNS en HTTPS voordat je op de iPad test. **Wijzig de productiehost trein.kerssing.nl niet.**

## Tests

Op een ontwikkelmachine met geïnstalleerde dependencies:

```bash
python -m unittest discover -s tests -p 'test_ei_*.py' -v
```

iPad-acceptatietest:
1. Log online in op de testhost. Open `/ei/new`. Wacht tot 'Offlinebestanden beschikbaar' zichtbaar is.
2. Selecteer EI 1, vul identificatie, datum en tijd in; druk Aannemen. Controleer lokale opslag en Wake Lock status.
3. Zet vliegtuigmodus aan, sluit de tab en open dezelfde URL opnieuw. Controleer herstel van het concept. Let op: een volledige browser-/OS-herstart kan afwijkend gedrag vertonen.
4. Wijzig een veld offline; herstel internet; gebruik 'Synchroniseer met server'. Controleer de ontvangstbevestiging.
5. Controleer in de testdatabase `data-ei-test/database/trein.db` of `ei_snapshots` een registratie bevat. Gebruik daarvoor bijvoorbeeld `docker exec kerssing-trein-ei-test python -c 'import sqlite3; c=sqlite3.connect("/app/data/database/trein.db"); print(c.execute("SELECT record_id,revision,received_at FROM ei_snapshots ORDER BY received_at DESC LIMIT 5").fetchall())'`.
6. Test opnieuw synchroniseren (geen duplicaat), wisselen tussen apps, lage batterij, verlopen login en uitloggen. Uitloggen wist lokale EI-concepten; doe dit pas na synchronisatie.

## Bekende beperkingen

- Dit is een ontwikkelprototype, geen operationeel geldig EI-document.
- De officiële EI-velden zijn nog niet onafhankelijk gevalideerd.
- Alleen de huidige conceptregistratie is lokaal opgeslagen; er is nog geen archief-/dagstaatkoppeling of PDF-export.
- Server-snapshots zijn geen definitieve, ondertekende EI's.
- iOS kan Wake Lock intrekken en offline cache/IndexedDB onder opslagdruk verwijderen.
- Bij een verlopen sessie is synchronisatie niet mogelijk totdat opnieuw is ingelogd.
- Er is nog geen volledige test van de gebruikersisolatie bij gedeelde iPads uitgevoerd.
- **Niet gebruiken voor het daadwerkelijk aannemen van spoorweginstructies.**
