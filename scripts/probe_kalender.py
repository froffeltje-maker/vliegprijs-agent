"""Tijdelijke test: wat stuurt Google terug op de live zoekfunctie vanaf GitHub?"""

from curl_cffi import requests

from fli.core.builders import build_flight_segments
from fli.models import Airport, FlightSearchFilters, MaxStops, PassengerInfo
from fli.search import SearchFlights

segs, tt = build_flight_segments(origin=Airport["DUS"], destination=Airport["TRD"],
                                 departure_date="2027-01-22", return_date="2027-01-29")
f = FlightSearchFilters(trip_type=tt, passenger_info=PassengerInfo(adults=1), flight_segments=segs,
                        stops=MaxStops.TWO_OR_FEWER_STOPS)
for params in ["", "?hl=nl&gl=NL&curr=EUR", "?hl=en&curr=EUR"]:
    r = requests.post(SearchFlights.BASE_URL + params, data=f"f.req={f.encode()}", impersonate="chrome",
                      headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"}, timeout=30)
    tekst = r.text
    print(f"[{params or 'geen params'}] status {r.status_code}, {len(tekst)} tekens, "
          f"'DUS' {tekst.count('DUS')}x, begin: {tekst[:160]!r}")
