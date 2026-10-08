# MC-II-data

Data pro aplikaci **MotoCesta** (ČR + SK), sestavovaná automaticky jednou měsíčně z OpenStreetMap:

- `v1/roads/<x>_<y>.bin` – silnice po dlaždicích 0,075° × 0,05° (rychlostní limity, jednosměrky, tvar silnice) pro volnou jízdu,
- `v1/radars.json` – pevné radary,
- `v1/fuel.json` – čerpací stanice,
- `v1/meta.json` – datum sestavení a počty.

Soubory jsou na GitHub Pages: https://derl4oo.github.io/MC-II-data/v1/ – aplikace je stahuje odtud a veřejný Overpass používá jen jako zálohu.

Sestavení: `.github/workflows/data.yml` (osmium-tool + `scripts/build.py`, jen standardní Python).

## Licence dat
© přispěvatelé OpenStreetMap. Data jsou dostupná pod licencí [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/); odvozená databáze v tomto repozitáři je zveřejněná pod stejnou licencí. https://www.openstreetmap.org/copyright
