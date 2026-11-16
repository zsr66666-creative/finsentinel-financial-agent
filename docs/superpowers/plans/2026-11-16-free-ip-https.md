# Free IP HTTPS implementation plan

Architecture: focused Python config renderer/TLS smoke + root Bash orchestration + systemd renewal. Uses approved existing ECS IP, no app/database/index changes.

- [x] Write failing renderer tests: preserve proxy paths/headers and comments, support IPv4/IPv6 port80 listeners, exact IP, reject multi-server/SSL/includes/unbalanced configs/competing challenges, re-run idempotency, stage-vs-production separation.
- [x] Implement validated Nginx parser/renderer and loopback trusted-IP TLS checker. Keep original HTTP service while adding HTTPS.
- [x] Installer: pinned isolated Certbot, exact package manifest, preflight, backup, HTTPchallenge, staging+production issuance, TLS checks, renewal dry-run/timer and rollback. No restart or automatic firewall edits.
- [ ] Test full backend+CI shell syntax, independent safety review; document operator security group rule and external/manual acceptance boundary.
- [ ] Commit/push, verify GitHub CI, create hash-verified source-only archive and one ECS command. Actual cloud signing and public HTTPS not claimed until logs/probes.
