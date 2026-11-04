# Vlastní server tras (Valhalla) – postup

Zdarma na Oracle Cloud Always Free. Trasy pro Česko, Slovensko, Rakousko, Polsko, Německo a Maďarsko.
Hesla, karty a přihlašovací klíče zadáváš jen ty – Claudovi je neposílej.

## 1. Účet Oracle Cloud (asi 15 min)
1. https://www.oracle.com/cloud/free/ → **Start for free**.
2. Domovská oblast (Home Region): **Germany Central (Frankfurt)** – nejblíž, a nejde později změnit.
3. Karta slouží jen k ověření; u Always Free se nic neplatí. Účet nech jako **Always Free** (nepřecházej na Pay As You Go).

## 2. Server (asi 10 min)
1. Menu → **Compute → Instances → Create instance**.
2. Name: `motocesta-trasy`.
3. Image: **Canonical Ubuntu 24.04**. Shape: **Ampere → VM.Standard.A1.Flex, 2 OCPU, 12 GB**.
4. Boot volume: **150 GB**.
5. SSH keys: **Generate a key pair for me** → stáhni oba soubory a ulož je (bez nich se na server nedostaneš).
6. **Create**. Když napíše „Out of capacity“, zkus to za pár hodin znovu.
7. Na stránce serveru si opiš **Public IP address**.

## 3. Otevřít porty 80 a 443 (asi 5 min)
Instance → **Subnet** → **Security Lists → Default Security List → Add Ingress Rules**:
- Source CIDR `0.0.0.0/0`, Destination port `80`
- Source CIDR `0.0.0.0/0`, Destination port `443`

## 4. Spustit instalaci (1 příkaz)
V Terminálu na Macu (cestu ke klíči uprav podle toho, kam jsi ho uložil):
```
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@VEŘEJNÁ_IP
```
Na serveru:
```
curl -fsSL https://raw.githubusercontent.com/Derl4OO/MC-II-data/main/Tools/valhalla-server.sh | bash
```
Na konci vypíše **url** a **key**. Nejsou tajné jako heslo (aplikace je stejně stahuje z config.json), takže je můžeš poslat Claudovi.

## 5. Počkat 2–5 hodin a přepnout aplikaci
Claude zapíše url a key do `config/app.json` → push → workflow. Do té doby jedou trasy přes testovací server FOSSGIS, při výpadku přes Mapbox.

## Poznámky
- Oracle má teď zdarma 2 OCPU a 12 GB paměti (dřív 4 a 24); skript proto přidá 8 GB odkládací paměti.
- Aktualizace map: jednou za měsíc stačí na serveru `sudo docker restart valhalla` po smazání `~/valhalla/custom_files/valhalla_tiles.tar` (Claude připraví automaticky později).
- Hledání (Photon) zůstává zatím na veřejném serveru Komoot; vlastní přijde po trasách.
