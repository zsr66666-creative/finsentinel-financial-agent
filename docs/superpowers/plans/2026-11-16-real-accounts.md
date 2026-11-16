# Real accounts implementation plan

**Goal:** Replace demo identity with administrator-provisioned server accounts on ECS HTTPS.
**Architecture:** PostgreSQL users, opaque server sessions, role middleware, same-origin CSRF; existing evidence contracts untouched.
**Tech stack:** FastAPI, SQLAlchemy, stdlib scrypt, Pillow for avatar decoding, Next.js.

Approved spec: docs/superpowers/specs/2026-11-16-real-accounts-design.md.

## Shared interface contract

AUTH_ENABLED defaults false for legacy local fixtures; production deployment enables true and cannot fallback on errors. AUTH_ORIGIN=https://120.24.108.60; AUTH_COOKIE_SECURE defaults true. Auth routes prefix /api/v1/auth.
User JSON: {id, username, nickname, avatar, role: viewer|reviewer|admin, enabled, must_change_password}. Session GET /session returns {user, csrf_token}; anonymous 401. POST /login {username,password} returns session envelope and HttpOnly cookie. All writes require exact Origin; authenticated writes require X-CSRF-Token. POST /logout {}, POST /password {current_password,new_password} returns 204 and revokes all sessions (login again). POST /profile {nickname,avatar} returns user. GET /users returns {items:[user]}; POST /users {username,password,role,nickname} returns user. POST /users/{id} {enabled?,role?,password?} returns user. Password reset sets must_change_password true; roles/edit/disable invalidate sessions. API errors use detail identifiers.

New reviewer payload sends no reviewer field. Server injects immutable user_id/username and nickname snapshot. Legacy auth-disabled fixtures retain original token behavior. Source-ingestion bearer remains narrow machine credential. Public API protected in account mode except /health, auth/login; session/logout/password exceptions permit forced password rotation.

## Task 1: auth backend
- [ ] Write failing tests for password hash, migration idempotence, session/cookie, CSRF, roles, disabled/expired sessions, admin provisioning and last admin.
- [ ] Implement backend/app/auth/* and scripts/manage_accounts.py (migrate/bootstrap interactive).
- [ ] Wire middleware/routes, role matrix, identity injection for reviews; preserve auth-disabled tests.
- [ ] Run targeted then complete backend tests; review diff for identity and privilege bypass.

## Task 2: frontend
- [ ] Replace demo context internals with server session and shared CSRF request helper, no client token persistence.
- [ ] Login, settings/password rotation, admin users page, reviewer permissions and error states.
- [ ] Update tests and docs; run node tests, tsc and Linux build; preserve portals/theme.

## Task 3: cloud upgrade and verification
- [ ] Installer preflight lock, package integrity, database/code/config backup, stage build, migration, interactive first admin.
- [ ] Cutover backend + frontend with AUTH_ENABLED and HTTPS Origin; preserve HTTP challenge and certificate renewal, private encoder and worker.
- [ ] Trusted HTTPS/session/admin/role smoke; rollback on failure without deleting new account tables.
- [ ] Isolated PostgreSQL concurrency and persistence checks without fake production reviews; source archive no secrets.
- [ ] Independent review, full local suite and CI; precise commits, verified GitHub main, tar SHA256 and one Alibaba command.

Cloud installation and browser acceptance remain pending until operator output and independent HTTPS probes. Never print passwords or tokens.
