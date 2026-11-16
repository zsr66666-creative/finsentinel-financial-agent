#!/usr/bin/env bash
# Add trusted public-IP TLS without stopping HTTP or modifying application services.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run from the Alibaba root console.'; exit 1; }
ip=120.24.108.60
site=/etc/nginx/sites-available/finsentinel
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec 9>/run/lock/finsentinel-ip-https.lock
flock -n 9 || { echo 'Another HTTPS installation is running.'; exit 1; }
cd "$root"
sha256sum -c SHA256SUMS
command -v nginx >/dev/null
command -v python3 >/dev/null
python3 -c 'import sys; assert sys.version_info >= (3,10)'
[[ -f "$site" && ! -L "$site" ]]
[[ "$(readlink -f /etc/nginx/sites-enabled/finsentinel)" == "$site" ]]
nginx -t
systemctl is-active --quiet nginx
systemctl is-active --quiet finsentinel-frontend
systemctl is-active --quiet finsentinel-backend
work="$(mktemp -d /root/finsentinel-ip-https-XXXXXXXX)"
python3 scripts/ip_https.py http --ip "$ip" --source "$site" --output "$work/http.conf"
python3 scripts/ip_https.py https --ip "$ip" --source "$work/http.conf" --output "$work/https.conf"
echo "Backup and acceptance records: $work"

certbot=/opt/finsentinel-certbot/bin/certbot
if [[ ! -x "$certbot" ]]; then
    apt-get update
    apt-get install -y python3-venv ca-certificates
    python3 -m venv /opt/finsentinel-certbot
fi
/opt/finsentinel-certbot/bin/python -m pip install --disable-pip-version-check --timeout 30 'certbot==5.10.0'
[[ "$("$certbot" --version)" == 'certbot 5.10.0' ]]
"$certbot" --help all > "$work/certbot-help.txt"
grep -q -- '--ip-address' "$work/certbot-help.txt"
grep -q -- '--preferred-profile' "$work/certbot-help.txt"

timer=finsentinel-ip-cert-renew.timer
service=finsentinel-ip-cert-renew.service
hook=/etc/letsencrypt/renewal-hooks/deploy/finsentinel-ip-nginx
renew=/usr/local/sbin/finsentinel-ip-cert-renew
managed=("/etc/systemd/system/$timer" "/etc/systemd/system/$service" "$hook" "$renew")
cp -a "$site" "$work/original.conf"
systemctl is-enabled "$timer" > "$work/timer-enabled" 2>/dev/null || true
systemctl is-active "$timer" > "$work/timer-active" 2>/dev/null || true
for index in "${!managed[@]}"; do
    path="${managed[$index]}"
    [[ ! -L "$path" ]] || { echo "Refusing symlink: $path"; exit 1; }
    if [[ -e "$path" ]]; then cp -a "$path" "$work/managed-$index"; fi
done

rollback() {
    code=$?
    trap - EXIT
    if [[ $code -ne 0 ]]; then
        echo 'HTTPS setup failed; restoring pre-run Nginx and renewal configuration.' >&2
        set +e
        systemctl stop "$timer"
        cp -a "$work/original.conf" "$site"
        for index in "${!managed[@]}"; do
            path="${managed[$index]}"
            if [[ -e "$work/managed-$index" ]]; then
                cp -a "$work/managed-$index" "$path"
            else
                rm -f -- "$path"
            fi
        done
        systemctl daemon-reload
        if grep -qx enabled "$work/timer-enabled"; then
            systemctl enable "$timer"
        else
            systemctl disable "$timer"
        fi
        if grep -qx active "$work/timer-active"; then systemctl start "$timer"; fi
        if nginx -t; then
            systemctl reload nginx || echo 'URGENT: Nginx reload failed; inspect journal.' >&2
        else
            echo "URGENT: restored Nginx failed validation. Backup: $work" >&2
        fi
        echo "Existing certificates/accounts retained. Logs: $work" >&2
    fi
    exit "$code"
}
trap rollback EXIT

# No keys or account material is included in this source package.
install -d -m 755 /var/www/finsentinel-acme/.well-known/acme-challenge
if grep -q '^# BEGIN FINSENTINEL MANAGED IP HTTPS$' "$work/original.conf"; then
    # The renderer already validated this managed suffix; keep live TLS on reruns.
    install -m 644 "$work/original.conf" "$site"
else
    install -m 644 "$work/http.conf" "$site"
fi
nginx -t
systemctl reload nginx
challenge="finsentinel-preflight-$(python3 -c 'import secrets; print(secrets.token_hex(12))')"
printf '%s' "$challenge" > "/var/www/finsentinel-acme/.well-known/acme-challenge/$challenge"
chmod 644 "/var/www/finsentinel-acme/.well-known/acme-challenge/$challenge"
python3 - "$ip" "$challenge" <<'PY'
import sys, urllib.request
ip, token = sys.argv[1:]
req = urllib.request.Request('http://127.0.0.1/.well-known/acme-challenge/' + token, headers={'Host':ip})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=15) as response:
    assert response.read().decode() == token, 'Challenge webroot mismatch'
print('PASS local HTTP challenge; staging CA will verify public port 80 next')
PY
rm -f -- "/var/www/finsentinel-acme/.well-known/acme-challenge/$challenge"

common=(certonly --non-interactive --agree-tos --register-unsafely-without-email
    --preferred-profile shortlived --webroot --webroot-path /var/www/finsentinel-acme
    --ip-address "$ip" --cert-name finsentinel-ip)
# Staging account and certificates never share production paths or enter Nginx.
"$certbot" "${common[@]}" --staging \
    --config-dir "$work/staging/config" --work-dir "$work/staging/work" --logs-dir "$work/staging/logs"
"$certbot" "${common[@]}" --keep-until-expiring
install -m 644 "$work/https.conf" "$site"
nginx -t
systemctl reload nginx
python3 scripts/ip_https.py smoke --ip "$ip" | tee "$work/https-smoke.txt"

install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
cat > "$hook" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
HOOK
chmod 700 "$hook"
cat > "$renew" <<'RENEW'
#!/usr/bin/env bash
set -euo pipefail
# Serialize renewal with installer to avoid rollback/configuration races.
exec 9>/run/lock/finsentinel-ip-https.lock
/usr/bin/flock -w 900 9
/opt/finsentinel-certbot/bin/certbot renew --cert-name finsentinel-ip --quiet --no-random-sleep-on-renew
RENEW
chmod 700 "$renew"
cat > "/etc/systemd/system/$service" <<'SERVICE'
[Unit]
Description=Renew FinSentinel short-lived public-IP certificate
Wants=network-online.target
After=network-online.target nginx.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/finsentinel-ip-cert-renew
TimeoutStartSec=15min
SERVICE
cat > "/etc/systemd/system/$timer" <<'TIMER'
[Unit]
Description=Check FinSentinel IP certificate twice daily

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=30min
Persistent=true
Unit=finsentinel-ip-cert-renew.service

[Install]
WantedBy=timers.target
TIMER
systemd-analyze verify "/etc/systemd/system/$service" "/etc/systemd/system/$timer"
"$certbot" renew --cert-name finsentinel-ip --dry-run --run-deploy-hooks --no-random-sleep-on-renew
systemctl daemon-reload
systemctl enable --now "$timer"
systemctl is-active --quiet "$timer"
systemctl list-timers "$timer" --no-pager
nginx -t
echo "PASS local trusted IP HTTPS and renewal dry-run. Records: $work"
echo "PUBLIC ACCEPTANCE PENDING: allow inbound TCP 443 in ECS security group, then open https://$ip/"
echo 'HTTP remains available; public port 80 must remain open for automatic renewal. No redirect/HSTS added.'
