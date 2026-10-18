# Vliegprijs-agent Schiphol/Düsseldorf → Jämtland / Trondheim

Zoekt via Google Flights naar de goedkoopste retourvlucht naar Östersund (OSD) of Trondheim (TRD).
Heen op vrijdag, 7–10 dagen verblijf. Twee profielen:

Beide zoeken vanaf Schiphol (AMS) en Düsseldorf (DUS).

- **GitHub** (`config.json`): elke 2 uur, ook als je pc uit staat. Resultaten in `RAPPORT.md`.
- **Thuis** (`config.thuis.json`): op je eigen pc. Google geeft vanaf een thuisadres meestal meer
  resultaten (vooral voor Östersund) dan vanaf GitHub. Resultaten in `RAPPORT-thuis.md`.

- `RAPPORT.md`: actuele top-15 per reisperiode, met links naar Google Flights
- `data/geschiedenis.csv`: alle gevonden prijzen over tijd

## Meldingen (GitHub → Settings → Secrets and variables → Actions)
- E-mail: `SMTP_USER` (je Gmail-adres), `SMTP_PASS` (Gmail app-wachtwoord), optioneel `MAIL_TO`
- Telegram: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`

Je krijgt een melding bij een nieuwe laagste prijs per periode, of als een prijs onder
`altijd_melden_onder_eur` zakt. Periodes die nog niet te boeken zijn (oktober en kerst 2027)
worden automatisch meegenomen zodra ze binnen ~11 maanden vallen.

Tip: maak de repository openbaar, dan zijn de GitHub Actions-minuten onbeperkt gratis.

## Zelf draaien en testen
```
pip install -r requirements.txt
python zoek.py                               # één zoekronde
python -m unittest discover -s tests -v      # tests (zonder internet)
```

## Thuis laten draaien (Windows)
1. Download deze repository (groene knop **Code → Download ZIP**) en pak hem uit.
2. Installeer Python van python.org (vink *Add python.exe to PATH* aan).
3. Kopieer `thuis/geheim.env.voorbeeld` naar de hoofdmap als `geheim.env` en vul je Gmail-adres en app-wachtwoord in.
4. Rechtsklik op `thuis/installeer-taak.ps1` → **Uitvoeren met PowerShell**.

Handmatig één ronde: `python zoek.py --config config.thuis.json`
