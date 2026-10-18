"""Tijdelijke test: live zoekfunctie zonder landinstelling, voor alle soorten routes."""

import time

from fli.core.builders import build_flight_segments
from fli.models import Airport, FlightSearchFilters, MaxStops, PassengerInfo
from fli.search import SearchFlights

routes = [("AMS", "OSD"), ("GRQ", "TRD"), ("FMO", "OSD"), ("DUS", "TRD"), ("BRE", "TRD"), ("EIN", "OSD"),
          ("DUS", "OSD"), ("RTM", "TRD"), ("NRN", "OSD"), ("DTM", "TRD")]
for van, naar in routes:
    segs, tt = build_flight_segments(origin=Airport[van], destination=Airport[naar],
                                     departure_date="2027-01-29", return_date="2027-02-05")
    f = FlightSearchFilters(trip_type=tt, passenger_info=PassengerInfo(adults=1), flight_segments=segs,
                            stops=MaxStops.TWO_OR_FEWER_STOPS)
    t = time.monotonic()
    try:
        res = SearchFlights()._fetch_flights(f, currency="EUR", language="en", country=None,
                                             capture_session=False) or []
        best = sorted((r for r in res if r.price), key=lambda r: r.price)[:2]
        txt = [(r.price, r.currency, sorted({str(getattr(l.airline, "value", l.airline)) for l in r.legs}))
               for r in best]
        print(f"{van}-{naar}: {len(res)} opties, goedkoopst {txt} ({time.monotonic()-t:.1f}s)")
    except Exception as e:
        print(f"{van}-{naar}: FOUT {type(e).__name__}: {str(e)[:150]}")
    time.sleep(2)
