# Pochtamt — a self-hosted mail server with an admin panel

[Русский](README.md) · [Docs (Russian)](docs/README.md) · [License: GPL-3.0](LICENSE)

Pochtamt (Russian for "main post office") is a complete mail server for a small organisation on a single
Debian 13 host: Postfix + Dovecot + Rspamd + ClamAV, PostgreSQL as the single source of truth, a FastAPI REST
backend and a Vue 3 administration panel. Everything comes from Debian packages and is updated by `apt`;
Docker is used only for the optional SOGo groupware. Users and passwords are local or, optionally, from Active Directory.

The core design rule: **the panel has no access to the host.** The backend writes only to PostgreSQL and Redis.
Postfix and Dovecot read the database through views under read-only roles. The only window to the host is a tiny
agent whose commands are whitelisted in sudoers. A compromised panel does not give a shell on the mail server.

## Features

- Virtual domains, mailboxes, aliases and forwards, catch-all, domain aliases, mailing lists.
- Mailbox modes (normal, receive-only, send-only, internal-only), quotas, autoreply, forward with copy, BCC,
  per-user Sieve rules; a self-service user cabinet.
- Sender/login enforcement, SASL via Dovecot, TLS 1.2+, DANE for outbound (local DNSSEC resolver), optional
  smarthost and per-destination TLS policies.
- Rspamd (SPF/DKIM/DMARC/ARC, bayes, greylisting, per-user rate limits) and ClamAV (reject at SMTP).
- DKIM keys generated and stored by the panel (working copy in Redis); ready-to-paste DNS records.
- Admin panel: dashboards, DNS checks per domain, Postfix queue, host metrics with history, server settings via
  a validated whitelist, spam-filter tuning, audit log, superadmin and per-domain admin roles.
- Optional Active Directory: admin login with domain accounts, mailbox passwords verified by LDAPS bind,
  hourly sync of users with a `mail` attribute and of groups into lists.
- One idempotent install script for a clean Debian 13, deployment over SSH from a workstation, Let's Encrypt via
  certbot, nftables, fail2ban, systemd sandboxing, login throttling.
- Optional SOGo (Docker, same host): CalDAV/CardDAV with invitations and free/busy, shared calendars and
  address books, its own webmail, ActiveSync for Outlook and phones.
- Migration tooling from iRedMail (domains, mailboxes with password hashes, forwards, Maildirs, DKIM keys).

## Layout

| Folder | Contents |
|---|---|
| `db/` | PostgreSQL schema: tables, views for Postfix/Dovecot, roles |
| `postfix/`, `dovecot/`, `rspamd/` | configuration templates (`@KEY@` placeholders filled from `install/.env`) |
| `backend/` | FastAPI backend and CLI (`python -m app.cli`) |
| `frontend/` | Vue 3 + PrimeVue admin panel and user cabinet |
| `agent/` | host agent (Postfix queue, Dovecot quotas, whitelisted service parameters) |
| `sogo/` | optional SOGo in Docker (image built from Debian packages, config, compose) |
| `install/` | `install.sh`, `deploy.sh`, systemd units, nginx, fail2ban, nftables, migration helpers |
| `docs/` | documentation (Russian) |
| `tools/` | pre-commit secret check, LDAPS certificate script for a domain controller |

## Quick start

Requirements: a clean Debian 13 (2 vCPU, 4 GB RAM, a disk for `/var/vmail`), a public IP with a PTR record,
inbound ports 25, 465, 587, 993 and 80 (for Let's Encrypt).

```bash
git clone https://github.com/nsneo-iv/pochtamt.git /opt/mail && cd /opt/mail
cp install/.env.example install/.env && cp backend/.env.example backend/.env && cp agent/.env.example agent/.env
# fill in the three .env files (hostnames, networks, passwords: openssl rand -hex 24; secrets: openssl rand -hex 32)
bash install/install.sh
cd backend && sudo -u mailapp .venv/bin/python -m app.cli admin-add admin superadmin --password
```

Then open `https://<ADMIN_HOSTNAME>/` from an allowed network, create a domain, generate DKIM, publish the DNS
records shown on the domain dashboard and add mailboxes. See `docs/install.md` for the full guide.

## Language

The admin panel UI and the documentation are in Russian. Code, API, configuration keys and comments in
configuration templates follow the usual English conventions of the underlying software. Contributions of
translations are welcome (the frontend keeps its strings in the components; the PrimeVue locale lives in
`frontend/src/locale/`).

## License

GNU General Public License v3.0 or later. See [`LICENSE`](LICENSE).
