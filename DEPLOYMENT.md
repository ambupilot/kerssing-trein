# Deployment Kerssing Trein

Doelmap op de VPS:

```text
/opt/web/kerssing-trein
```

Publieke URL:

```text
https://trein.kerssing.nl
```

## 1. Controleer of poort 8089 vrij is

```bash
sudo ss -ltnp | grep ':8089' || true
```

Als daar niets luistert, kan 8089 worden gebruikt.

## 2. Clone de repository

```bash
cd /opt/web
git clone git@github.com:ambupilot/kerssing-trein.git
cd /opt/web/kerssing-trein
```

## 3. Productie `.env`

```bash
cp .env.example .env
nano .env
```

Gebruik minimaal:

```dotenv
SECRET_KEY=<lange-willekeurige-sleutel>
ADMIN_USERNAME=martijn
ADMIN_PASSWORD=<sterk-wachtwoord>
SESSION_COOKIE_SECURE=true
TZ=Europe/Amsterdam
```

Genereer bijvoorbeeld een secret met:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Bescherm het bestand:

```bash
chmod 600 .env
```

## 4. Start Docker

```bash
docker compose up -d --build
docker compose ps
```

Controleer de health endpoint lokaal op de VPS:

```bash
curl -fsS http://127.0.0.1:8089/health
```

Verwacht:

```json
{"status":"ok"}
```

## 5. Caddy logbestand

```bash
sudo touch /var/log/caddy/trein.kerssing.nl.log
sudo chown caddy:caddy /var/log/caddy/trein.kerssing.nl.log
sudo chmod 640 /var/log/caddy/trein.kerssing.nl.log
```

## 6. Caddy-configuratie

Voeg aan `/etc/caddy/Caddyfile` toe:

```caddyfile
trein.kerssing.nl {
    encode zstd gzip

    header {
        Strict-Transport-Security "max-age=15552000"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    reverse_proxy 127.0.0.1:8089

    log {
        output file /var/log/caddy/trein.kerssing.nl.log
    }
}
```

Daarna:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 7. Externe test

```bash
curl -fsS https://trein.kerssing.nl/health
```

Controleer daarna in een browser:

```text
https://trein.kerssing.nl
```

## Updates

```bash
cd /opt/web/kerssing-trein
git pull
docker compose up -d --build
curl -fsS http://127.0.0.1:8089/health
```

`./data` staat buiten de container en wordt niet verwijderd door rebuilds.
