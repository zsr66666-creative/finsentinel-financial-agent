# Free public-IP HTTPS on ECS

This optional installer adds Let's Encrypt public IPv4 TLS for `120.24.108.60`.
It requires no purchased domain or certificate. Existing ECS/network charges remain.
This is HTTPS for an IP address, not registration of a free domain.

Official references:

- https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability
- https://letsencrypt.org/2026/03/11/shorter-certs-certbot
- https://letsencrypt.org/docs/profiles/

IP certificates use the `shortlived` profile (160 hours), so renewal is mandatory.
The installer pins Certbot 5.10.0 in `/opt/finsentinel-certbot`; the application's
Python environment, database, frontend, corpus and encoder are unchanged.
By running it you agree to the CA subscriber agreement. It registers without
email; do not rely on expiry emails. Watch the renewal service/timer.

## Operator steps

1. Alibaba ECS console → instance → security group → inbound rule: allow TCP
   **443**, source `0.0.0.0/0`. Keep existing TCP80 for HTTP-01 renewal. Do not
   expose backend8000 or encoder8081. If a host firewall is active it must also
   allow443. The script does not change either firewall.
2. Upload the published source archive to `/root/`, verify its published SHA256,
   extract to a fresh root-only directory, then run `bash -n` and the installer.
   This is a source-only delivery; Certbot dependencies and ACME issuance still
   require outgoing internet access. PyPI/ACME failure leaves HTTP available.
3. Send the complete installer output for external verification. Open
   `https://120.24.108.60/` in a browser and verify no certificate warning,
   login, company pages, search and comparison. Check browser static assets.

## Installation behavior and boundaries

- Requires a healthy Nginx HTTP site with exactly one IP `server` block; rejects
  custom includes, existing unrelated TLS and ambiguous configs before mutation.
- Backs up the original site and managed renewal files under
  `/root/finsentinel-ip-https-*`. Backups stay outside `sites-enabled`.
- Adds webroot challenge, tests local routing, then staging issuance verifies
  external80. Staging uses separate directories and is never served to users.
- Production signing adds TLS1.2/1.3 and preserves the existing proxy routes.
  Loopback TLS uses the real public-IP SAN and system CA trust, never `-k`.
- Performs renewal dry-run with reload hook, then enables a twice-daily timer
  with random delay and persistence. Nginx is reloaded, never stopped for signing.
- On installer failure, restores pre-run Nginx/managed renewal config and timer
  state. Certbot environment, ACME account/certificates and diagnostic files remain.
- HTTP stays available; this phase adds no forced redirect or HSTS. Enable
  redirects only after independently verifying public443. Public HTTPS acceptance
  is separate from local smoke tests; security group/network may still block it.
- Existing demo login remains demo login. TLS does not add real authentication.

## Routine checks

```bash
systemctl list-timers finsentinel-ip-cert-renew.timer --no-pager
journalctl -u finsentinel-ip-cert-renew.service -n 40 --no-pager
/opt/finsentinel-certbot/bin/certbot certificates --cert-name finsentinel-ip
curl --fail --max-time 15 https://120.24.108.60/health
```

The renewal service is oneshot and normally inactive between runs. Inspect its
exit status/logs, not `is-active` alone. If fewer than24h remain, repair renewal
immediately; certificates expire in under7days. Never post private keys or ACME
account material in logs/chat. Repeated staging/production issuance can hit CA
rate limits; inspect the first error before retrying.

## Build/test

```bash
python -m pytest backend/tests/test_ip_https.py
bash -n deploy/ecs/install-ip-https.sh
python scripts/package_ip_https.py --output work/finsentinel-ip-https.tar.gz
```

Only committed installer/helper/docs/tests and integrity metadata enter the
archive. No certificates, secrets, PDFs, models or application builds are shipped.
