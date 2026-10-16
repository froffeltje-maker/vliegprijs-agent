# Vliegprijs-agent Zwolle → Jämtland / Trondheim

Zoekt elke 2 uur (GitHub Actions) via Google Flights naar de goedkoopste retourvlucht
van een luchthaven binnen 2 uur van Zwolle naar Östersund (OSD) of Trondheim (TRD).
Heen op vrijdag, minimaal 7 dagen verblijf. Instellen in `config.json`.

- `RAPPORT.md`: actuele top-15 per reisperiode, met links naar Google Flights
- `data/geschiedenis.csv`: alle gevonden prijzen over tijd

## Meldingen (GitHub → Settings → Secrets and variables → Actions)
- E-mail: `SMTP_USER` (je Gmail-adres), `SMTP_PASS` (Gmail app-wachtwoord), optioneel `MAIL_TO`
- Telegram: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`

Je krijgt een melding bij een nieuwe laagste prijs per periode, of als een prijs onder
`altijd_melden_onder_eur` zakt. Periodes die nog niet te boeken zijn (oktober en kerst 2027)
worden automatisch meegenomen zodra ze binnen ~11 maanden vallen.

Tip: maak de repository openbaar, dan zijn de GitHub Actions-minuten onbeperkt gratis.
