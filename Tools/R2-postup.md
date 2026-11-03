# Cloudflare R2 pro data MotoCesty – postup (dělá Julien, klíče nikomu neposílej)

R2 = úložiště souborů u Cloudflare. 10 GB zdarma, stahování zdarma. Celá Evropa se vejde (GitHub Pages má jen 1 GB).

## 1. Vytvoření úložiště
1. Přihlas se na dash.cloudflare.com (stejný účet jako server počasí).
2. Vlevo **R2 Object Storage** → při prvním otevření potvrď zapnutí R2 (chce platební kartu, ale do 10 GB se nic neplatí).
3. **Create bucket** → název `motocesta-data`, umístění **Automatic** (nebo Eastern Europe) → Create.

## 2. Veřejný přístup (aby aplikace mohly data stahovat)
1. V bucketu `motocesta-data` → **Settings** → **Public access** → **R2.dev subdomain** → **Allow Access**.
2. Zkopíruj adresu, která se ukáže (tvar `https://pub-….r2.dev`), a pošli mi ji – ta není tajná.
   (Později ji nahradíme vlastní doménou, např. data.motocesta.cz – stejné nastavení, „Custom Domains“.)
3. Ještě v Settings → **CORS Policy** → Add CORS policy → vlož:
   `[{"AllowedOrigins":["*"],"AllowedMethods":["GET","HEAD"],"AllowedHeaders":["*"],"MaxAgeSeconds":86400}]`
   (kvůli náhledu mapy v prohlížeči; aplikacím to nevadí).

## 3. Klíč pro nahrávání (jen pro GitHub, nikomu ho neposílej)
1. R2 → **Manage R2 API Tokens** (vpravo nahoře) → **Create API token**.
2. Název `motocesta-github`, oprávnění **Object Read & Write**, omezit na bucket **motocesta-data** → Create.
3. Ukáže se **Access Key ID** a **Secret Access Key** – nech stránku otevřenou pro další krok.
4. Account ID je na stránce R2 vpravo („Account ID“).

## 4. Vložení do GitHubu
V repozitáři MC-II-data na github.com → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, postupně:
- `R2_BUCKET` = `motocesta-data`
- `R2_ACCOUNT_ID` = tvoje Account ID
- `R2_ACCESS_KEY_ID` = Access Key ID
- `R2_SECRET_ACCESS_KEY` = Secret Access Key

Hotovo. Workflow „Data MotoCesta (Evropa)“ pak sám nahraje celá data do R2 a GitHub Pages dostane zkrácenou kopii pro dnešní aplikace.
Hotovo 3. 11. 2026: veřejná adresa https://pub-15c918f368aa43dc85e3ec15c72e311c.r2.dev (data v /v1/). Napiš mi jen „R2 hotovo“ a veřejnou adresu z kroku 2 – přepnu na ni styl mapy a aplikace (přes vzdálený config.json).
