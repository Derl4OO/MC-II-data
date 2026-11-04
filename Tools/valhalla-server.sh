#!/usr/bin/env bash
# Vlastní server tras MotoCesty (Valhalla) na serveru s Ubuntu 24.04 (např. Hetzner, 8–16 GB paměti).
# Spuštění na serveru:  curl -fsSL https://raw.githubusercontent.com/Derl4OO/MC-II-data/main/Tools/valhalla-server.sh | bash
# Na konci vypíše adresu a klíč – ty patří do config/app.json (routing.url a routing.key).
set -euo pipefail

echo "== 1/5 Programy (Docker, Caddy pro HTTPS)"
sudo apt-get update -y
sudo apt-get install -y docker.io caddy curl openssl iptables-persistent
sudo systemctl enable --now docker

echo "== 2/5 Odkládací paměť 8 GB (sestavení Německa potřebuje víc paměti)"
if [ ! -f /swapfile ]; then
  sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo "== 3/5 Valhalla: Česko, Slovensko, Rakousko, Polsko, Německo, Maďarsko (sestavení trvá 2–5 hodin)"
URLS="https://download.geofabrik.de/europe/czech-republic-latest.osm.pbf https://download.geofabrik.de/europe/slovakia-latest.osm.pbf https://download.geofabrik.de/europe/austria-latest.osm.pbf https://download.geofabrik.de/europe/poland-latest.osm.pbf https://download.geofabrik.de/europe/germany-latest.osm.pbf https://download.geofabrik.de/europe/hungary-latest.osm.pbf"
mkdir -p "$HOME/valhalla/custom_files"
sudo docker rm -f valhalla 2>/dev/null || true
sudo docker run -d --name valhalla --restart unless-stopped -p 127.0.0.1:8002:8002 \
  -v "$HOME/valhalla/custom_files:/custom_files" -e tile_urls="$URLS" -e server_threads=2 \
  ghcr.io/valhalla/valhalla-scripted:latest

echo "== 4/5 HTTPS s klíčem (bez klíče server odpoví 403)"
KEY_FILE="$HOME/valhalla/klic.txt"
[ -f "$KEY_FILE" ] || openssl rand -hex 16 > "$KEY_FILE"
KEY=$(cat "$KEY_FILE")
IP=$(curl -fsS https://api.ipify.org)
HOST="$(echo "$IP" | tr . -).sslip.io"
sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$HOST {
	@app header X-MotoCesta-Key $KEY
	handle @app {
		reverse_proxy 127.0.0.1:8002
	}
	respond 403
}
CADDY
sudo systemctl restart caddy

echo "== 5/5 Brána serveru: porty 80 a 443"
sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 5 -p tcp --dport 80 -j ACCEPT
sudo iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 5 -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save

echo
echo "HOTOVO. Do config/app.json v MC-II-data (nebo pošli Claudovi):"
echo "  url: https://$HOST"
echo "  key: $KEY"
echo "Valhalla teď sestavuje mapová data (2–5 hodin). Průběh: sudo docker logs -f valhalla"
