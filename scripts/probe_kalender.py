"""Tijdelijke test: ruwe opbouw van de live-zoekantwoorden per route."""

import json
import time

from curl_cffi import requests

from fli.core.builders import build_flight_segments
from fli.models import Airport, FlightSearchFilters, MaxStops, PassengerInfo
from fli.search import SearchFlights

for van, naar in [("AMS", "OSD"), ("GRQ", "TRD"), ("DUS", "TRD"), ("AMS", "TRD")]:
    segs, tt = build_flight_segments(origin=Airport[van], destination=Airport[naar],
                                     departure_date="2027-01-29", return_date="2027-02-05")
    f = FlightSearchFilters(trip_type=tt, passenger_info=PassengerInfo(adults=1), flight_segments=segs,
                            stops=MaxStops.TWO_OR_FEWER_STOPS)
    t = time.monotonic()
    r = requests.post(SearchFlights.BASE_URL + "?hl=en&curr=EUR", data=f"f.req={f.encode()}",
                      impersonate="chrome", timeout=60,
                      headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"})
    d = time.monotonic() - t
    try:
        buiten = json.loads(r.text.split("\n", 2)[2].split("\n")[0] if r.text.startswith(")]}'") else r.text)
    except Exception:
        buiten = None
    info = ""
    try:
        regels = [l for l in r.text.splitlines() if l.startswith("[[")]
        outer = json.loads(regels[0])
        inner = json.loads(outer[0][2]) if outer[0][2] else None
        if inner is None:
            info = f"inner leeg; outer[0][:6]={str(outer[0][:6])[:200]}"
        else:
            info = (f"len {len(inner)}; [2]={'lijst %d' % len(inner[2][0]) if isinstance(inner[2], list) and inner[2] and inner[2][0] else repr(inner[2])[:40]}; "
                    f"[3]={'lijst %d' % len(inner[3][0]) if isinstance(inner[3], list) and inner[3] and inner[3][0] else repr(inner[3])[:40]}; "
                    f"vlag {str(inner[0])[:90]}")
    except Exception as e:
        info = f"parse {type(e).__name__}: {e}; begin {r.text[:200]!r}"
    print(f"{van}-{naar}: http {r.status_code}, {len(r.text)} tekens, {d:.1f}s, {info}")
    time.sleep(3)
