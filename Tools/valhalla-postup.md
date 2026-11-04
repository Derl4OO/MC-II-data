# Server tras (Valhalla) – plán

Rozhodnuto 4. 11. 2026 (Julien): Oracle Cloud ne (zablokoval registraci). Pořadí:

1. **Teď – testování:** veřejný server FOSSGIS (config/app.json), při výpadku Mapbox. Zdarma, bez registrace, jen pro pár testerů.
2. **Před širším testem s motorkáři:** Stadia Maps (hostovaná Valhalla, free plán 200 000 kreditů/měsíc = asi 10 000 tras, jen vývoj a testování). V aplikaci drobná úprava (klíč jako `api_key` v adrese).
3. **Před vydáním:** placený plán Stadia Maps (ověřit, který plán obsahuje trasy), nebo vlastní server u Hetzneru se skriptem `valhalla-server.sh` (Ubuntu 24.04; skript nainstaluje Valhallu pro CZ, SK, AT, PL, DE, HU, HTTPS a klíč).

Účty, karty a hesla zakládá a zadává jen Julien.
