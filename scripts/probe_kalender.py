"""Tijdelijke test: geeft de live zoekfunctie van Google Flights (via fli) resultaten vanaf GitHub?"""

import time

from fli.core.builders import build_flight_segments
from fli.models import Airport, FlightSearchFilters, MaxStops, PassengerInfo
from fli.search import SearchFlights

for van, naar in [("AMS", "OSD"), ("GRQ", "TRD"), ("FMO", "OSD"), ("DUS", "TRD"), ("BRE", "TRD"), ("EIN", "OSD")]:
    segs, tt = build_flight_segments(origin=Airport[van], destination=Airport[naar],
                                     departure_date="2027-01-29", return_date="2027-02-05")
    f = FlightSearchFilters(trip_type=tt, passenger_info=PassengerInfo(adults=1), flight_segments=segs,
                            stops=MaxStops.TWO_OR_FEWER_STOPS)
    t = time.monotonic()
    try:
        s = SearchFlights()
        res = s._fetch_flights(f, currency="EUR", language="nl", country="NL", capture_session=False) or []
        prijzen = sorted(r.price for r in res if r.price)
        al = sorted({l.airline.name if hasattr(l.airline, "name") else str(l.airline) for r in res[:3] for l in r.legs})
        print(f"{van}-{naar}: {len(res)} opties, laagste {prijzen[:3]}, mij {al} ({time.monotonic()-t:.1f}s)")
    except Exception as e:
        print(f"{van}-{naar}: FOUT {type(e).__name__}: {str(e)[:200]}")
    time.sleep(2)
