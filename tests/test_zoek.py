"""Tests voor de vliegprijs-agent. Google Flights wordt nagebootst met
pagina's in hetzelfde formaat als de echte, zodat ook de parser meedoet."""

import csv
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import zoek  # noqa: E402

PROJECT = Path(__file__).resolve().parent.parent


class VasteDatum(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 18)


def vlucht(prijs, maatschappijen=("KLM",), van="AMS", naar="TRD"):
    segment = [None] * 22
    segment[3], segment[4] = van, "Vertrek"
    segment[5], segment[6] = "Aankomst", naar
    segment[8], segment[10], segment[11] = [10, 5], [13], 175
    segment[17], segment[20], segment[21] = "Boeing 737", [2027, 1, 1], [2027, 1, 1]
    extra = [None] * 9
    extra[7], extra[8] = 90000, 100000
    f = [None] * 23
    f[0], f[1], f[2], f[22] = "KL", list(maatschappijen), [segment], extra
    return [f, [[None, prijs]]]


def pagina(beste=(), overige=()):
    payload = [None] * 8
    payload[2] = [list(beste)] if beste else None
    payload[3] = [list(overige)] if overige else [None]
    payload[7] = [None, [[["SKY", "SkyTeam"]], [["KL", "KLM"]]]]
    return ("<html><head><script class=\"ds:1\" nonce=\"x\">AF_initDataCallback({key: 'ds:1', "
            f"hash: '1', data:{json.dumps(payload)}, sideChannel: {{}}}});</script></head></html>")


GEEN_VLUCHTEN = ("<html><script class=\"ds:1\">AF_initDataCallback({key: 'ds:1', hash: '1', "
                 "data:null, errorHasStatus: true, sideChannel: {}});</script></html>")
TOESTEMMINGSPAGINA = "<html><body><form action='https://consent.google.com/save'>Alles accepteren</form></body></html>"


def laad_cfg():
    return json.loads((PROJECT / "config.json").read_text(encoding="utf-8"))


class TestCombinaties(unittest.TestCase):
    def test_alleen_vrijdagen_en_minimaal_7_dagen(self):
        cfg = laad_cfg()
        alle = list(zoek.combinaties(cfg, date(2026, 10, 18)))
        self.assertTrue(alle)
        for c in alle:
            heen, terug = date.fromisoformat(c["heen"]), date.fromisoformat(c["terug"])
            self.assertEqual(heen.weekday(), 4, c)
            self.assertGreaterEqual((terug - heen).days, 7)
            self.assertLessEqual((terug - heen).days, 10)

    def test_aantallen_eind_januari_eind_februari(self):
        cfg = laad_cfg()
        alle = list(zoek.combinaties(cfg, date(2026, 10, 18)))
        vrijdagen = sorted({c["heen"] for c in alle})
        self.assertEqual(vrijdagen[0], "2027-01-22")
        self.assertEqual(vrijdagen[-1], "2027-02-26")
        self.assertEqual(len(vrijdagen), 6)
        self.assertEqual(len(alle), 6 * 4 * 2 * 2)  # vrijdagen x verblijf x vertrek x bestemming

    def test_thuisprofiel_zelfde_routes_eigen_bestanden(self):
        thuis = json.loads((PROJECT / "config.thuis.json").read_text(encoding="utf-8"))
        self.assertEqual(set(thuis["vertrekluchthavens"]), {"AMS", "DUS"})
        self.assertEqual(len(list(zoek.combinaties(thuis, date(2026, 10, 18)))), 6 * 4 * 2 * 2)
        self.assertNotEqual(thuis["data_map"], "data")
        self.assertNotEqual(thuis["rapport"], "RAPPORT.md")

    def test_periodes_komen_binnen_boekingshorizon(self):
        cfg = laad_cfg()
        periodes = {c["periode"] for c in zoek.combinaties(cfg, date(2026, 10, 18))}
        self.assertEqual(periodes, {"Eind januari - eind februari 2027"})
        periodes = {c["periode"] for c in zoek.combinaties(cfg, date(2026, 11, 15))}
        self.assertIn("Oktober 2027", periodes)
        self.assertNotIn("Kerst 2027", periodes)
        periodes = {c["periode"] for c in zoek.combinaties(cfg, date(2027, 1, 10))}
        self.assertEqual(periodes, {"Eind januari - eind februari 2027", "Oktober 2027", "Kerst 2027"})

    def test_kerst_vrijdagen(self):
        cfg = laad_cfg()
        kerst = {c["heen"] for c in zoek.combinaties(cfg, date(2027, 3, 1)) if c["periode"] == "Kerst 2027"}
        self.assertEqual(kerst, {"2027-12-10", "2027-12-17", "2027-12-24"})

    def test_query_is_retour_met_juiste_route(self):
        cfg = laad_cfg()
        c = next(zoek.combinaties(cfg, date(2026, 10, 18)))
        q = zoek.bouw_query(cfg, c)
        self.assertEqual(q.get_trip_type(), "round-trip")
        heen, terug = q.flight_data
        self.assertEqual((heen.from_airport.airport, heen.to_airport.airport), (c["van"], c["naar"]))
        self.assertEqual((terug.from_airport.airport, terug.to_airport.airport), (c["naar"], c["van"]))
        self.assertEqual((heen.date, terug.date), (c["heen"], c["terug"]))
        self.assertIn("curr=EUR", q.url())


class TestParser(unittest.TestCase):
    def test_beste_en_overige_vluchten_samen(self):
        r = zoek.lees_vluchten(pagina(beste=[vlucht(189)], overige=[vlucht(240), vlucht(310)]))
        self.assertEqual(sorted(f.price for f in r), [189, 240, 310])

    def test_alleen_beste_vluchten(self):
        r = zoek.lees_vluchten(pagina(beste=[vlucht(199, ("SAS",))]))
        self.assertEqual([(f.price, f.airlines) for f in r], [(199, ["SAS"])])

    def test_onvolledige_opties_worden_overgeslagen(self):
        zonder_prijs = vlucht(100)
        zonder_prijs[1] = []
        zonder_extras = vlucht(275, ("SAS",))
        zonder_extras[0][22] = None
        zonder_extras[0][2] = None
        r = zoek.lees_vluchten(pagina(beste=[zonder_prijs, None], overige=[zonder_extras]))
        self.assertEqual([(f.price, f.airlines) for f in r], [(275, ["SAS"])])

    def test_pagina_zonder_metadata(self):
        html = pagina(beste=[vlucht(330)]).replace('[null, [[["SKY", "SkyTeam"]], [["KL", "KLM"]]]]', "null")
        self.assertEqual([f.price for f in zoek.lees_vluchten(html)], [330])

    def test_toestemmingspagina_geeft_duidelijke_fout(self):
        with self.assertRaises(zoek.GeenResultatenpagina):
            zoek.lees_vluchten(TOESTEMMINGSPAGINA)

    def test_zoek_prijs_kiest_laagste(self):
        html = pagina(beste=[vlucht(250, ("KLM",))], overige=[vlucht(212, ("SAS", "KLM")), vlucht(0)])
        with mock.patch.object(zoek, "haal_html", return_value=html):
            self.assertEqual(zoek.zoek_prijs(None), (212, ["SAS", "KLM"]))

    def test_zoek_prijs_zonder_vluchten_probeert_opnieuw(self):
        with mock.patch.object(zoek, "haal_html", return_value=GEEN_VLUCHTEN) as h, \
                mock.patch.object(zoek.time, "sleep"):
            self.assertEqual(zoek.zoek_prijs(None), (None, []))
            self.assertEqual(h.call_count, 3)

    def test_zoek_prijs_tweede_poging_lukt(self):
        antwoorden = [GEEN_VLUCHTEN, pagina(overige=[vlucht(410)])]
        with mock.patch.object(zoek, "haal_html", side_effect=antwoorden), \
                mock.patch.object(zoek.time, "sleep") as slaap:
            self.assertEqual(zoek.zoek_prijs(None, wacht=5), (410, ["KLM"]))
            slaap.assert_called_once_with(5)

    def test_cookies_worden_meegestuurd(self):
        with mock.patch.object(zoek, "Client") as client:
            client.return_value.get.return_value.text = "ok"
            cfg = laad_cfg()
            zoek.haal_html(zoek.bouw_query(cfg, next(zoek.combinaties(cfg, date(2026, 10, 18)))))
            _, kwargs = client.return_value.get.call_args
            self.assertIn("SOCS", kwargs["cookies"])
            self.assertIn("tfs", kwargs["params"])


class TestGeheimen(unittest.TestCase):
    def test_laad_geheimen(self):
        map_ = Path(tempfile.mkdtemp())
        pad = map_ / "geheim.env"
        pad.write_text("# commentaar\nVLIEG_TEST_A = waarde=met=is\n\nVLIEG_TEST_B=x\n", encoding="utf-8")
        with mock.patch.dict(zoek.os.environ, {"VLIEG_TEST_B": "al gezet"}):
            zoek.laad_geheimen(pad)
            self.assertEqual(zoek.os.environ["VLIEG_TEST_A"], "waarde=met=is")
            self.assertEqual(zoek.os.environ["VLIEG_TEST_B"], "al gezet")
        zoek.os.environ.pop("VLIEG_TEST_A", None)
        shutil.rmtree(map_)
        zoek.laad_geheimen(map_ / "bestaat-niet.env")


class TestRun(unittest.TestCase):
    def setUp(self):
        self.map = Path(tempfile.mkdtemp())
        cfg = laad_cfg()
        cfg["zoekopdrachten_per_run"] = 10
        cfg["pauze_seconden"] = 0
        (self.map / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        data = self.map / "data"
        self.patches = [
            mock.patch.object(zoek, "ROOT", self.map),
            mock.patch.object(zoek, "DATA", data),
            mock.patch.object(zoek, "PRIJZEN", data / "prijzen.json"),
            mock.patch.object(zoek, "GESCHIEDENIS", data / "geschiedenis.csv"),
            mock.patch.object(zoek, "RAPPORT", self.map / "RAPPORT.md"),
            mock.patch.object(zoek, "date", VasteDatum),
            mock.patch.object(zoek.time, "sleep"),
        ]
        for p in self.patches:
            p.start()
        self.meldingen = []
        p = mock.patch.object(zoek, "stuur_melding", lambda o, t: self.meldingen.append((o, t)))
        p.start()
        self.patches.append(p)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.map)

    def draai(self, prijs_per_query):
        def nep_html(query):
            p = prijs_per_query(query)
            if isinstance(p, Exception):
                raise p
            return GEEN_VLUCHTEN if p is None else pagina(beste=[vlucht(p)])
        with mock.patch.object(zoek, "haal_html", side_effect=nep_html):
            zoek.main()
        return json.loads((self.map / "data" / "prijzen.json").read_text(encoding="utf-8"))

    def test_eerste_run_slaat_op_rapporteert_en_meldt(self):
        prijzen = self.draai(lambda q: 300)
        self.assertEqual(len(prijzen), 10)
        rapport = (self.map / "RAPPORT.md").read_text(encoding="utf-8")
        self.assertIn("€300", rapport)
        self.assertIn("google.com/travel/flights", rapport)
        with (self.map / "data" / "geschiedenis.csv").open(encoding="utf-8") as f:
            self.assertEqual(len(list(csv.reader(f))), 11)  # kop + 10
        self.assertEqual(len(self.meldingen), 1)
        self.assertIn("€300", self.meldingen[0][0])

    def test_tweede_run_controleert_nieuwe_combinaties(self):
        eerste = set(self.draai(lambda q: 300))
        tweede = set(self.draai(lambda q: 300))
        self.assertEqual(len(tweede), 20)
        self.assertTrue(eerste < tweede)

    def test_geen_melding_als_niet_goedkoper(self):
        self.draai(lambda q: 300)
        self.meldingen.clear()
        self.draai(lambda q: 320)
        self.assertEqual(self.meldingen, [])

    def test_melding_bij_nieuw_record(self):
        self.draai(lambda q: 300)
        self.meldingen.clear()
        self.draai(lambda q: 279)
        self.assertEqual(len(self.meldingen), 1)
        self.assertIn("nieuwe laagste prijs", self.meldingen[0][1])

    def test_melding_onder_drempel_ook_zonder_record(self):
        self.draai(lambda q: 150)
        self.meldingen.clear()
        self.draai(lambda q: 199)
        self.assertEqual(len(self.meldingen), 1)
        self.assertIn("onder €250", self.meldingen[0][1])

    def test_geen_vluchten_wordt_bijgehouden_zonder_melding(self):
        prijzen = self.draai(lambda q: None)
        self.assertEqual(len(prijzen), 10)
        self.assertTrue(all(r["prijs"] is None for r in prijzen.values()))
        self.assertEqual(self.meldingen, [])

    def test_leeg_antwoord_bewaart_oude_prijs(self):
        self.draai(lambda q: 300)
        cfg = json.loads((self.map / "config.json").read_text(encoding="utf-8"))
        cfg["zoekopdrachten_per_run"] = 1296
        (self.map / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        prijzen = self.draai(lambda q: None)
        met_prijs = [r for r in prijzen.values() if r["prijs"]]
        self.assertEqual(len(met_prijs), 10)
        self.assertTrue(all(r["prijs"] == 300 for r in met_prijs))
        self.assertIn("€300", (self.map / "RAPPORT.md").read_text(encoding="utf-8"))

    def test_eigen_datamap_per_profiel(self):
        cfg = json.loads((self.map / "config.json").read_text(encoding="utf-8"))
        cfg.update({"data_map": "data-thuis", "rapport": "RAPPORT-thuis.md"})
        (self.map / "thuis.json").write_text(json.dumps(cfg), encoding="utf-8")
        with mock.patch.object(zoek, "haal_html", return_value=pagina(beste=[vlucht(300)])):
            zoek.main("thuis.json")
        self.assertTrue((self.map / "data-thuis" / "prijzen.json").exists())
        self.assertTrue((self.map / "RAPPORT-thuis.md").exists())
        self.assertFalse((self.map / "RAPPORT.md").exists())

    def test_stopt_bij_blokkade(self):
        aanroepen = []

        def geblokkeerd(q):
            aanroepen.append(q)
            return zoek.GeenResultatenpagina("toestemmingspagina")
        with self.assertRaises(SystemExit):
            self.draai(geblokkeerd)
        self.assertEqual(len(aanroepen), zoek.MAX_FOUTEN_OP_RIJ)

    def test_stopt_bij_tijdsbudget(self):
        klok = iter(range(0, 10000, 400))  # elke zoekopdracht 'duurt' 400 seconden
        with mock.patch.object(zoek.time, "monotonic", lambda: next(klok)):
            prijzen = self.draai(lambda q: 300)
        self.assertEqual(len(prijzen), 3)  # start 0; na 400, 800, 1200 s door; bij 1600 s (> 25 min) stop

    def test_losse_fout_stopt_run_niet(self):
        teller = iter(range(100))

        def soms_fout(q):
            return RuntimeError("time-out") if next(teller) == 3 else 300
        prijzen = self.draai(soms_fout)
        self.assertEqual(len(prijzen), 9)


if __name__ == "__main__":
    unittest.main()
