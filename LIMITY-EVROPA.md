# MotoCesta – rychlostní limity pro celou Evropu (návrh)

Stav 25. 10. 2026. Cíl: na každé silnici správný limit, levně, vlastním řešením (žádný cizí kód – jen otevřená data OpenStreetMap a pravidla ze zákonů jednotlivých států).

## 1. Princip
- Zdroj dat: **OpenStreetMap (OSM)**, licence ODbL – smíme je používat i komerčně s uvedením zdroje („© přispěvatelé OpenStreetMap“, už máme) a odvozená databáze limitů zůstává pod ODbL (naše dlaždice jsou stejně veřejné).
- Pravidla „co platí, když u silnice nic není“ bereme **přímo ze zákonů** (CZ zákon 361/2000 Sb. § 18, SK 8/2009 Z. z. § 16, …) – žádné kopírování z jiných aplikací.
- Všechno se počítá **jednou měsíčně (nebo týdně) na serveru** v našem repozitáři MC-II-data (GitHub Actions – u veřejného repozitáře zdarma). Telefon jen stahuje hotové dlaždice po okolí trasy a drží je 35 dní. Žádné placené dotazy za jízdy.

## 2. Pořadí, jak se limit určí (pro každý úsek silnice)
1. **Zapsaný limit** (`maxspeed`, i jen pro jeden směr).
2. **Druh limitu / zóna** (`maxspeed:type`, `source:maxspeed`, `zone:traffic`, `zone:maxspeed`, např. `CZ:urban`, `DE:rural`) → limit podle zákona dané země.
3. **Značky začátku a konce obce** (`traffic_sign=city_limit`, české IS 12a/b, slovenské IS 36/37, jinde jejich ekvivalenty): úsek se rozdělí přesně u značky.
4. **Zástavba** (plochy `landuse=residential/retail/commercial`) – jen když nic z předchozího není; změna se přitáhne k nejbližší značce obce do 400 m.
5. **Druh silnice** (dálnice, silnice pro motorová vozidla, obytná zóna) → zákonný limit země.
6. **Dočasné limity** (stavby, objížďky) – hlášení jezdců „Dočasný limit“ (už máme).

Hotovo v MC-II-data (25. 10. 2026): body 1, 2 (včetně `zone:traffic`, `zone:maxspeed` a limitu jen pro jeden směr), 3 (značky obcí), 4 a 5 pro CZ + SK.

## 3. Tabulka pravidel podle zemí (rozšiřitelná)
Jeden soubor pravidel (např. `rules/<země>.json`): výchozí limit v obci, mimo obec, silnice pro motorová vozidla, dálnice, obytná zóna; zvlášť pro motocykly, kde se liší; vzory značek obce. **Každé číslo se před nasazením ověří v textu zákona dané země** (odkaz na zákon je přímo v souboru).

Orientačně (k ověření): CZ 50/90/110/130, SK 50/90/130, AT 50/100/130, DE 50/100/bez limitu (doporučeno 130), PL 50/90/100–120/140, HU 50/90/110/130.

## 4. Kontrola kvality (aby limity byly správné)
- **Úroveň jistoty u každého úseku:** zapsaný / podle zóny / podle značky obce = vysoká, jen podle zástavby = střední. Aplikace může střední jistotu odlišit (např. tenčí okraj značky) – rozhodne se po testech.
- **Automatické kontroly při každém sestavení:** podíl silnic bez limitu, úseky, kde zástavba a značky nesouhlasí, náhlé změny proti minulému měsíci → přehled v `meta.json` a zastavení nasazení při velké odchylce.
- **Testovací trasy** (Jívová → Šternberk, Olomouc → Pustevny…) s ručně ověřenými limity – kontrola po každém sestavení.
- **Tlačítko „Špatný limit“** za jízdy (do hlášení): uloží místo a co aplikace ukázala (Firestore, zdarma). Jednou měsíčně se chyby opraví **přímo v OSM** – zlepší se to pro všechny a příští sestavení už je má správně.
- V navigaci se navíc porovná s limitem z Mapboxu (`maxspeed` v trase – je v ceně navigace); když se liší, platí zapsaný OSM limit a rozdíl se zaznamená ke kontrole.

## 5. Rozšíření na Evropu
- **Data po zemích** z Geofabriku; sestavení jako matice (každá země zvlášť, souběžně), přestavuje se jen země, kde se data změnila.
- **Úložiště:** GitHub Pages má limit asi 1 GB – pro Evropu přejít na **Cloudflare R2** (10 GB zdarma, bez poplatků za stahování; Cloudflare už máme kvůli počasí). Nad 10 GB asi 0,015 $/GB měsíčně.
- **V telefonu:** dlaždice jen kolem plánované trasy a polohy, 35 dní v mezipaměti – jedna jízda typicky stovky kB dat.
- **Postup:** 1) CZ + SK (teď); 2) sousedé PL, AT, DE, HU (do léta 2027); 3) další země podle toho, kde uživatelé jezdí (z anonymní statistiky).

## 6. Co zbývá udělat
- [ ] Pushnout MC-II-data a spustit workflow „Data MotoCesta“, v `meta.json` zkontrolovat `urbanCells` a `citySigns`.
- [ ] Testovací trasy s ověřenými limity + automatická kontrola.
- [ ] Tlačítko „Špatný limit“ v hlášeních (iOS + Android) a měsíční oprava v OSM.
- [ ] Soubor pravidel po zemích (ověřit zákony) a sestavení po zemích.
- [ ] Přechod úložiště na Cloudflare R2, až data přesáhnou ~800 MB.
