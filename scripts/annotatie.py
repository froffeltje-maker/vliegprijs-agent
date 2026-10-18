"""Zet tekst van stdin om in één GitHub Actions-annotatie (titel als argument)."""

import sys

titel = sys.argv[1] if len(sys.argv) > 1 else "Uitvoer"
tekst = sys.stdin.read().replace("\r", "")[-3500:]
tekst = tekst.replace("%", "%25").replace("\n", "%0A")
titel = titel.replace("%", "%25").replace(",", "%2C").replace(":", "%3A")
print(f"::notice title={titel}::{tekst}")
