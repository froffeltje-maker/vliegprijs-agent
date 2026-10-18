"""Tijdelijke test: werkt de prijskalender van Google Flights (via fli) vanaf GitHub?"""

from fli.core.builders import build_date_search_segments
from fli.models import Airport, DateSearchFilters, MaxStops, PassengerInfo
from fli.search import SearchDates

for van, naar in [("AMS", "OSD"), ("GRQ", "TRD"), ("FMO", "OSD"), ("DUS", "TRD")]:
    segs, tt = build_date_search_segments(origin=Airport[van], destination=Airport[naar],
                                          start_date="2027-01-22", trip_duration=7, is_round_trip=True)
    f = DateSearchFilters(trip_type=tt, passenger_info=PassengerInfo(adults=1), flight_segments=segs,
                          stops=MaxStops.TWO_OR_FEWER_STOPS, from_date="2027-01-22",
                          to_date="2027-02-26", duration=7)
    try:
        res = SearchDates().search(f, currency="EUR", language="nl", country="NL") or []
        vr = [(r.date[0].date().isoformat(), r.price) for r in res if r.date[0].weekday() == 4]
        print(f"{van}-{naar}: {len(res)} data, vrijdagen: {vr}")
    except Exception as e:
        print(f"{van}-{naar}: FOUT {type(e).__name__}: {e}")
