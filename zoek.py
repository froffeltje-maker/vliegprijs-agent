"""Vliegprijs-agent: zoekt de goedkoopste retourvlucht naar Jämtland/Trondheim.

Elke run controleert een deel van alle combinaties (vertrekluchthaven x bestemming
x vrijdag x verblijfsduur), de combinaties die het langst niet gecontroleerd zijn
eerst. Zo wordt na een paar runs alles gedekt zonder Google te overbelasten.
"""

import csv
import json
import os
import smtplib
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path

from fast_flights import FlightQuery, Passengers, create_query
from fast_flights.exceptions import FlightsNotFound
from primp import Client
from selectolax.lexbor import LexborHTMLParser

GOOGLE_FLIGHTS = "https://www.google.com/travel/flights"
# Zonder deze cookies toont Google in de EU eerst een cookie-toestemmingspagina.
TOESTEMMING_COOKIES = {
    "CONSENT": "YES+cb",
    "SOCS": "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiAo_CmBg",
}

ROOT = Path(__file__).parent
DATA = ROOT / "data"
PRIJZEN = DATA / "prijzen.json"
GESCHIEDENIS = DATA / "geschiedenis.csv"
RAPPORT = ROOT / "RAPPORT.md"

WEEKDAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
# Maatschappijen publiceren dienstregelingen zo'n 11 maanden vooruit.
BOEKINGSHORIZON_DAGEN = 340
MAX_FOUTEN_OP_RIJ = 8


def laad_json(pad, standaard):
    if pad.exists():
        return json.loads(pad.read_text(encoding="utf-8"))
    return standaard


def combinaties(cfg, vandaag):
    weekdag = WEEKDAGEN.index(cfg["vertrek_weekdag"])
    for periode in cfg["periodes"]:
        d = date.fromisoformat(periode["vertrek_van"])
        eind = date.fromisoformat(periode["vertrek_tot"])
        d += timedelta(days=(weekdag - d.weekday()) % 7)
        while d <= eind:
            if vandaag < d <= vandaag + timedelta(days=BOEKINGSHORIZON_DAGEN):
                for verblijf in range(cfg["min_verblijf_dagen"], cfg["max_verblijf_dagen"] + 1):
                    terug = d + timedelta(days=verblijf)
                    for van in cfg["vertrekluchthavens"]:
                        for naar in cfg["bestemmingen"]:
                            yield {
                                "sleutel": f"{van}-{naar}-{d}-{terug}",
                                "periode": periode["naam"],
                                "van": van,
                                "naar": naar,
                                "heen": d.isoformat(),
                                "terug": terug.isoformat(),
                            }
            d += timedelta(days=7)


def bouw_query(cfg, c):
    return create_query(
        flights=[
            FlightQuery(date=c["heen"], from_airport=c["van"], to_airport=c["naar"]),
            FlightQuery(date=c["terug"], from_airport=c["naar"], to_airport=c["van"]),
        ],
        trip="round-trip",
        seat="economy",
        passengers=Passengers(adults=cfg["volwassenen"]),
        language="nl",
        currency=cfg["valuta"],
        max_stops=cfg["max_overstappen"],
    )


class GeenResultatenpagina(Exception):
    """Google gaf geen resultatenpagina terug (toestemmingspagina, captcha of blokkade)."""


_client = None


def haal_html(query):
    # Eén sessie voor de hele run, zoals een gewone browser, in plaats van per verzoek.
    global _client
    if _client is None:
        _client = Client(impersonate="chrome_145", impersonate_os="macos", referer=True,
                         cookie_store=True)
    return _client.get(GOOGLE_FLIGHTS, params=query.params(), cookies=TOESTEMMING_COOKIES).text


def lees_vluchten(html):
    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        raise GeenResultatenpagina(
            "geen Google Flights-resultaten ontvangen (toestemmingspagina, captcha of blokkade?)")
    data = script.text().split("data:", 1)[1].rsplit(",", 1)[0]
    if data.endswith("errorHasStatus: true"):
        raise FlightsNotFound("geen vluchten gevonden")
    payload = json.loads(data)
    # payload[2] = 'beste vluchten', payload[3] = 'andere vluchten'. De parser van
    # fast-flights leest alleen payload[3] en struikelt over ontbrekende extra's,
    # dus we lezen hier zelf alleen wat we nodig hebben: prijs en maatschappijen.
    vluchten = []
    for lijst in (_veilig(payload, 2, 0), _veilig(payload, 3, 0)):
        for optie in lijst or []:
            prijs = _veilig(optie, 1, 0, 1)
            if isinstance(prijs, (int, float)) and prijs > 0:
                maatschappijen = _veilig(optie, 0, 1)
                vluchten.append(Vlucht(int(prijs), list(maatschappijen or [])))
    return vluchten


def _veilig(obj, *indexen):
    for i in indexen:
        try:
            obj = obj[i]
        except (IndexError, KeyError, TypeError):
            return None
    return obj


class Vlucht:
    def __init__(self, price, airlines):
        self.price, self.airlines = price, airlines


_voorbeelden = {}


def bewaar_voorbeeld(soort, html):
    """Bewaar per run een paar ruwe pagina's per soort, om de uitleeslogica te controleren."""
    if not os.environ.get("BEWAAR_VOORBEELDEN"):
        return
    n = _voorbeelden.get(soort, 0)
    if n >= 2:
        return
    _voorbeelden[soort] = n + 1
    map_ = DATA / "voorbeelden"
    map_.mkdir(parents=True, exist_ok=True)
    (map_ / f"{soort}-{n + 1}.html").write_text(html, encoding="utf-8")


def zoek_prijs(query, pogingen=3, wacht=15):
    """Geeft (laagste prijs, maatschappijen) terug, of (None, []) als er niets is.

    Google geeft bij veel verzoeken achter elkaar soms een leeg antwoord of een
    foutstatus terug in plaats van resultaten; dan wachten we en proberen opnieuw.
    """
    for poging in range(1, pogingen + 1):
        html = haal_html(query)
        try:
            resultaten = lees_vluchten(html)
        except FlightsNotFound:
            bewaar_voorbeeld("geen-vluchten", html)
            resultaten = []
        except Exception:
            bewaar_voorbeeld("fout", html)
            raise
        opties = [r for r in resultaten if r.price and r.price > 0]
        if opties:
            bewaar_voorbeeld("ok", html)
            beste = min(opties, key=lambda r: r.price)
            return beste.price, beste.airlines
        if poging < pogingen:
            time.sleep(wacht * poging)
    bewaar_voorbeeld("leeg", html)
    return None, []


def stuur_melding(onderwerp, tekst, html=None):
    verstuurd = False
    if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"):
        msg = EmailMessage()
        msg["Subject"] = onderwerp
        msg["From"] = os.environ["SMTP_USER"]
        msg["To"] = os.environ.get("MAIL_TO") or os.environ["SMTP_USER"]
        msg.set_content(tekst)
        if html:
            msg.add_alternative(html, subtype="html")
        with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        verstuurd = True
    if os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        data = urllib.parse.urlencode({
            "chat_id": os.environ["TELEGRAM_CHAT_ID"],
            "text": f"{onderwerp}\n\n{tekst}",
            "disable_web_page_preview": "true",
        }).encode()
        url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage"
        urllib.request.urlopen(url, data=data, timeout=30)
        verstuurd = True
    print(("Melding verstuurd: " if verstuurd else "Geen meldkanaal ingesteld: ") + onderwerp)


def beschrijf(cfg, r):
    van = cfg["vertrekluchthavens"].get(r["van"], r["van"])
    naar = cfg["bestemmingen"].get(r["naar"], r["naar"])
    maatschappijen = ", ".join(r.get("maatschappijen") or []) or "?"
    return (f"€{r['prijs']}  {van} ({r['van']}) → {naar} ({r['naar']})\n"
            f"   heen vr {r['heen']}, terug {r['terug']}  [{maatschappijen}]\n"
            f"   {r['url']}")


KOPPEN = ["Prijs", "Route", "Heen (vr)", "Terug", "Maatschappij", "Prijs gezien"]
GEEN_PRIJZEN = "Nog geen prijzen (nog niet te boeken of nog niet gecontroleerd)."


def rapport_inhoud(cfg, prijzen):
    """Gedeelde inhoud van RAPPORT.md en de e-mail: kop, en per periode de top-15."""
    nu = datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M")
    intro = (f"Laatst bijgewerkt: {nu}. Retour, {cfg['volwassenen']} volwassene(n), "
             f"heen op {cfg['vertrek_weekdag']}, {cfg['min_verblijf_dagen']}–"
             f"{cfg['max_verblijf_dagen']} dagen verblijf.")
    periodes = []
    for periode in cfg["periodes"]:
        rijen = sorted((r for r in prijzen.values()
                        if r["periode"] == periode["naam"] and r.get("prijs")),
                       key=lambda r: r["prijs"])
        periodes.append((periode["naam"], rijen[:15]))
    totaal = sum(1 for _ in combinaties(cfg, date.today()))
    gedaan = sum(1 for r in prijzen.values() if r.get("gecontroleerd"))
    voet = f"{gedaan} gecontroleerde combinaties; {totaal} nu te boeken combinaties in totaal."
    return intro, periodes, voet


def _cellen(r):
    return [f"€{r['prijs']}", f"{r['van']} → {r['naar']}", r["heen"], r["terug"],
            ", ".join(r.get("maatschappijen") or []),
            (r.get("bevestigd") or r["gecontroleerd"])[:16].replace("T", " ")]


def schrijf_rapport(cfg, prijzen):
    intro, periodes, voet = rapport_inhoud(cfg, prijzen)
    regels = ["# Vliegprijzen naar Jämtland / Trondheim", "", intro, ""]
    for naam, rijen in periodes:
        regels += [f"## {naam}", ""]
        if not rijen:
            regels += [f"_{GEEN_PRIJZEN}_", ""]
            continue
        regels += ["| " + " | ".join(KOPPEN) + " |", "|---:|---|---|---|---|---|"]
        for r in rijen:
            cellen = _cellen(r)
            cellen[0] = f"[{cellen[0]}]({r['url']})"
            regels.append("| " + " | ".join(cellen) + " |")
        regels.append("")
    regels += [f"_{voet}_", ""]
    RAPPORT.write_text("\n".join(regels), encoding="utf-8")


def rapport_html(cfg, prijzen, te_melden):
    """Dezelfde tabellen als RAPPORT.md, als HTML-mail; gemelde opties gemarkeerd."""
    intro, periodes, voet = rapport_inhoud(cfg, prijzen)
    gemeld = {r["sleutel"] for _, _, r in te_melden}
    td = "padding:5px 8px;border:1px solid #d0d7de;white-space:nowrap;font-size:13px;"
    delen = ['<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
             'color:#1f2328;font-size:14px;line-height:1.5">',
             '<h1 style="font-size:22px;margin:0 0 8px">Vliegprijzen naar Jämtland / Trondheim</h1>']
    for p, reden, r in te_melden:
        delen.append(f'<p style="margin:4px 0;padding:8px 12px;background:#fff8c5;border-radius:6px">'
                     f'<b>{escape(p)} – {escape(reden)}:</b> €{r["prijs"]} {escape(r["van"])} → '
                     f'{escape(r["naar"])}, heen vr {escape(r["heen"])}, terug {escape(r["terug"])}</p>')
    delen.append(f'<p style="color:#59636e">{escape(intro)}</p>')
    for naam, rijen in periodes:
        delen.append(f'<h2 style="font-size:18px;margin:20px 0 8px;padding-bottom:4px;'
                     f'border-bottom:1px solid #d0d7de">{escape(naam)}</h2>')
        if not rijen:
            delen.append(f"<p><i>{escape(GEEN_PRIJZEN)}</i></p>")
            continue
        kop = "".join(f'<th style="{td}background:#f6f8fa;text-align:{"right" if i == 0 else "left"}">'
                      f"{escape(k)}</th>" for i, k in enumerate(KOPPEN))
        rijen_html = []
        for r in rijen:
            cellen = [escape(c) for c in _cellen(r)]
            cellen[0] = f'<a href="{escape(r["url"])}" style="color:#0969da">{cellen[0]}</a>'
            achtergrond = "background:#fff8c5;font-weight:600;" if r["sleutel"] in gemeld else ""
            rijen_html.append("<tr>" + "".join(
                f'<td style="{td}{achtergrond}text-align:{"right" if i == 0 else "left"}">{c}</td>'
                for i, c in enumerate(cellen)) + "</tr>")
        delen.append(f'<div style="overflow-x:auto"><table style="border-collapse:collapse">'
                     f'<tr>{kop}</tr>{"".join(rijen_html)}</table></div>')
    delen.append(f'<p style="color:#59636e"><i>{escape(voet)}</i></p></div>')
    return "".join(delen)


def gebruik_mappen(cfg):
    """Een eigen datamap/rapport per config, zodat GitHub en thuis elkaar niet storen."""
    global DATA, PRIJZEN, GESCHIEDENIS, RAPPORT
    if "data_map" in cfg:
        DATA = ROOT / cfg["data_map"]
        PRIJZEN = DATA / "prijzen.json"
        GESCHIEDENIS = DATA / "geschiedenis.csv"
    if "rapport" in cfg:
        RAPPORT = ROOT / cfg["rapport"]


def laad_geheimen(pad):
    """Lees KEY=waarde-regels (bijv. SMTP_USER) uit een lokaal bestand, voor gebruik thuis."""
    if not pad.exists():
        return
    for regel in pad.read_text(encoding="utf-8").splitlines():
        regel = regel.strip()
        if regel and not regel.startswith("#") and "=" in regel:
            sleutel, waarde = regel.split("=", 1)
            os.environ.setdefault(sleutel.strip(), waarde.strip())


def main(config_naam="config.json"):
    cfg = json.loads((ROOT / config_naam).read_text(encoding="utf-8"))
    gebruik_mappen(cfg)
    DATA.mkdir(exist_ok=True)
    prijzen = laad_json(PRIJZEN, {})
    vandaag = date.today()

    # Records per periode vóór deze run, om nieuwe laagterecords te herkennen.
    record_voor = {}
    for r in prijzen.values():
        if r.get("prijs") and r["heen"] > vandaag.isoformat():
            p = r["periode"]
            record_voor[p] = min(record_voor.get(p, r["prijs"]), r["prijs"])

    alle = list(combinaties(cfg, vandaag))
    alle.sort(key=lambda c: prijzen.get(c["sleutel"], {}).get("gecontroleerd", ""))
    te_doen = alle[: cfg["zoekopdrachten_per_run"]]
    print(f"{len(alle)} combinaties te boeken, deze run: {len(te_doen)}")

    nieuw_geschiedenis = not GESCHIEDENIS.exists()
    fouten_op_rij = 0
    gevonden = []
    aantal_gezocht = aantal_met_prijs = 0
    with GESCHIEDENIS.open("a", newline="", encoding="utf-8") as f:
        schrijver = csv.writer(f)
        if nieuw_geschiedenis:
            schrijver.writerow(["tijd", "periode", "van", "naar", "heen", "terug", "prijs", "maatschappijen"])
        start = time.monotonic()
        for c in te_doen:
            if time.monotonic() - start > cfg.get("max_minuten_per_run", 25) * 60:
                print("Tijdsbudget op, run gestopt; de rest volgt in de volgende run.")
                break
            query = bouw_query(cfg, c)
            try:
                prijs, maatschappijen = zoek_prijs(query, wacht=cfg["pauze_seconden"] * 3)
                fouten_op_rij = 0
            except Exception as e:
                fouten_op_rij += 1
                print(f"  fout bij {c['sleutel']}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
                if fouten_op_rij >= MAX_FOUTEN_OP_RIJ:
                    print("Te veel fouten op rij (geblokkeerd?), run gestopt.")
                    break
                time.sleep(cfg["pauze_seconden"] * 3)
                continue
            tijd = datetime.now(timezone.utc).isoformat(timespec="seconds")
            vorig = prijzen.get(c["sleutel"], {})
            if prijs:
                r = {**c, "prijs": prijs, "maatschappijen": maatschappijen,
                     "url": query.url(), "gecontroleerd": tijd, "bevestigd": tijd}
                aantal_met_prijs += 1
            else:
                # Een leeg antwoord kan ook afremming door Google zijn: oude prijs bewaren.
                r = {**c, "prijs": vorig.get("prijs"), "maatschappijen": vorig.get("maatschappijen", []),
                     "url": query.url(), "gecontroleerd": tijd, "bevestigd": vorig.get("bevestigd")}
            prijzen[c["sleutel"]] = r
            aantal_gezocht += 1
            print(f"  {c['sleutel']}: {'€' + str(prijs) if prijs else 'geen vluchten'}")
            if prijs:
                schrijver.writerow([tijd, c["periode"], c["van"], c["naar"], c["heen"],
                                    c["terug"], prijs, " ".join(maatschappijen)])
                gevonden.append(r)
            time.sleep(cfg["pauze_seconden"])

    print(f"Klaar: {aantal_met_prijs} van {aantal_gezocht} zoekopdrachten gaven een prijs.")

    # Verlopen vertrekdata en combinaties die niet meer in config.json staan opruimen.
    geldig = {c["sleutel"] for c in alle}
    prijzen = {k: v for k, v in prijzen.items() if k in geldig}
    PRIJZEN.write_text(json.dumps(prijzen, ensure_ascii=False, indent=1), encoding="utf-8")
    schrijf_rapport(cfg, prijzen)

    meldcfg = cfg["melding"]
    te_melden = []
    for periode in cfg["periodes"]:
        p = periode["naam"]
        kandidaten = sorted((r for r in gevonden if r["periode"] == p), key=lambda r: r["prijs"])
        if not kandidaten:
            continue
        beste = kandidaten[0]
        if meldcfg.get("bij_nieuwe_laagste_prijs_per_periode") and beste["prijs"] < record_voor.get(p, 10**9):
            te_melden.append((p, "nieuwe laagste prijs", beste))
        elif beste["prijs"] < meldcfg.get("altijd_melden_onder_eur", 0):
            te_melden.append((p, f"onder €{meldcfg['altijd_melden_onder_eur']}", beste))
    if te_melden:
        laagste = min(r["prijs"] for _, _, r in te_melden)
        onderwerp = f"✈️ Vliegprijs-alert: vanaf €{laagste} naar Jämtland/Trondheim"
        tekst = "\n\n".join(f"{p} – {reden}:\n{beschrijf(cfg, r)}" for p, reden, r in te_melden)
        stuur_melding(onderwerp, tekst, rapport_html(cfg, prijzen, te_melden))

    if fouten_op_rij >= MAX_FOUTEN_OP_RIJ and not gevonden:
        sys.exit(1)


if __name__ == "__main__":
    laad_geheimen(ROOT / "geheim.env")
    config_naam = sys.argv[sys.argv.index("--config") + 1] if "--config" in sys.argv else "config.json"
    if "--testmail" in sys.argv:
        cfg = json.loads((ROOT / config_naam).read_text(encoding="utf-8"))
        gebruik_mappen(cfg)
        stuur_melding("✈️ Testmelding vliegprijs-agent",
                      "Als je dit leest, werken de meldingen. Je krijgt voortaan bericht bij "
                      "een nieuwe laagste prijs per reisperiode.",
                      rapport_html(cfg, laad_json(PRIJZEN, {}), []))
    else:
        main(config_naam)
