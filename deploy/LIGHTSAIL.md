# Deploy ClearPay4U on AWS Lightsail (Mumbai) with the GoDaddy domain clearpay4u.com

The result: **https://clearpay4u.com** on one Lightsail server in Mumbai. Caddy provides HTTPS, and the
app runs with its own Postgres database. Email goes out through Amazon SES. Nightly backups are kept on
the server and in snapshots.

```
Browser ──HTTPS──> Caddy (80/443) ──> web (nginx + React) ──/api──> api (FastAPI) ──> db (Postgres)
                                                                       └──SMTP──> Amazon SES
```

Time needed: about 1 hour, plus waiting for DNS and for SES production access (up to a day).
Cost: Lightsail 2 GB plan about $12/month. SES costs a few cents per thousand emails.

---

## 1. Create the server (Lightsail console)

1. Sign in at https://lightsail.aws.amazon.com. Create an AWS account first if needed, and turn on MFA
   for the root user.
2. Click **Create instance**.
   - **Region:** Mumbai (`ap-south-1`), zone A.
   - **Platform:** Linux/Unix. **Blueprint:** *OS only* → **Ubuntu 24.04 LTS**.
   - **SSH key:** keep the default key, or upload your own. Download the default key if you want to use
     your own SSH client.
   - **Plan:** *Dual-stack*, **2 GB RAM, 2 vCPUs, 60 GB SSD**.
   - **Name:** `clearpay4u-prod`. Click **Create instance**.
3. **Static IP** (so the address never changes): open *Networking* → **Create static IP**, attach it to
   `clearpay4u-prod`, and name it `clearpay4u-ip`. It is free while attached. Write the IP down; this
   guide calls it `13.x.x.x`.
4. **Firewall:** open the instance → *Networking* → *IPv4 Firewall*. You need these rules:
   - SSH 22 (already there). Use **Restrict to IP address** to allow only your own IP if you can.
   - HTTP 80 (already there).
   - **Add rule → HTTPS 443**.
   - Add the same HTTP and HTTPS rules under *IPv6 Firewall*.
5. **Automatic snapshots:** open the instance → *Snapshots* → turn on **Automatic snapshots**. Lightsail
   then takes a daily copy of the whole server, kept for 7 days.

## 2. Point clearpay4u.com at the server (GoDaddy)

1. GoDaddy → *My Products* → **clearpay4u.com** → **DNS** (Manage DNS).
2. Edit or delete the existing **A** record named `@`. GoDaddy usually points it at a "Parked" page.
   Then set:

   | Type  | Name | Value         | TTL    |
   |-------|------|---------------|--------|
   | A     | @    | `13.x.x.x`    | 1 hour |
   | CNAME | www  | `@`           | 1 hour |

   If a `www` CNAME already exists, edit it instead of adding a new one. Remove any **Forwarding** set
   up for the domain.
3. Check from your laptop: `nslookup clearpay4u.com` should show `13.x.x.x`. This can take from a few
   minutes to an hour. **Wait for it before step 5**: Caddy can only get the HTTPS certificate once the
   name points at the server.

## 3. Set up the server

1. In Lightsail click **Connect using SSH**, which opens a terminal in the browser. Or use your own SSH
   client: `ssh -i LightsailDefaultKey-ap-south-1.pem ubuntu@13.x.x.x`.
2. Run the setup script. It installs Docker and adds swap, a firewall, security updates and fail2ban. It
   also clones the repo to `~/clearpay4u` and schedules nightly backups:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/AshokThokala/PayrollEngine-MVP/main/deploy/setup-server.sh | bash
   ```
3. **Log out and back in** (type `exit`, then connect again), so Docker works without `sudo`.

## 4. Fill in the secrets

```bash
cd ~/clearpay4u
openssl rand -base64 36    # run three times: POSTGRES_PASSWORD, SECRET_KEY, and once spare
docker run --rm python:3.12-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                           # -> FIELD_ENCRYPTION_KEY
nano deploy/.env
```

Fill in `DOMAIN=clearpay4u.com`, `ACME_EMAIL`, `POSTGRES_PASSWORD`, `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`,
`ADMIN_EMAIL` and `ADMIN_PASSWORD` (a strong one). Leave the SMTP lines for step 6. Save with Ctrl+O,
Enter, then exit with Ctrl+X.

> **Save `FIELD_ENCRYPTION_KEY` and `POSTGRES_PASSWORD` in your password manager now.** PAN and bank
> account numbers are encrypted with that key. If the key is lost, that data cannot be read again, even
> from a backup.

## 5. Start ClearPay4U

```bash
~/clearpay4u/deploy/deploy.sh
```

The first build takes 5–10 minutes on the 2 GB plan. When it prints `ClearPay4U is live at
https://clearpay4u.com`, open the site, log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`, and change the
password.

If it says it is not answering yet:
```bash
cd ~/clearpay4u
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env ps
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env logs --tail=80 caddy api
```
A Caddy line about the certificate (`challenge failed`, `NXDOMAIN`) means DNS isn't pointing at the
server yet: wait, then run `deploy.sh` again.

## 6. Email through Amazon SES

1. AWS console → **Amazon SES**, in region **Asia Pacific (Mumbai)**.
2. **Identities → Create identity → Domain** → `clearpay4u.com`. Keep **Easy DKIM** on (RSA 2048) and
   create the identity.
3. SES shows **3 CNAME records**. Add each one in GoDaddy DNS (Add → CNAME). GoDaddy adds the domain
   itself, so in **Name** enter only the part *before* `.clearpay4u.com`, e.g. `abc123._domainkey`.
4. Also in GoDaddy, add or edit these records:

   | Type | Name     | Value                                                      |
   |------|----------|------------------------------------------------------------|
   | TXT  | @        | `v=spf1 include:amazonses.com ~all` (if an SPF TXT exists, add `include:amazonses.com` to it instead) |
   | TXT  | _dmarc   | `v=DMARC1; p=quarantine; rua=mailto:you@example.com`       |

5. Wait for the identity to show **Verified**, usually under an hour.
6. **Get production access:** SES → *Account dashboard* → **Request production access**. Choose
   *Transactional*, use case "employee invites and payroll notifications for client companies", website
   `https://clearpay4u.com`. Until AWS approves it (often within a day), SES only delivers to addresses
   you have verified yourself.
7. **SMTP credentials:** SES → *SMTP settings* → **Create SMTP credentials**. Copy the SMTP user name and
   password; they are shown only once.
8. On the server, put them in `deploy/.env`:
   ```
   SMTP_HOST=email-smtp.ap-south-1.amazonaws.com
   SMTP_PORT=587
   SMTP_SECURITY=starttls
   SMTP_USER=<SMTP user name>
   SMTP_PASSWORD=<SMTP password>
   SMTP_FROM=ClearPay4U <no-reply@clearpay4u.com>
   ```
   Then run `~/clearpay4u/deploy/deploy.sh`. Test it by inviting yourself as an employee on the
   *Employee onboarding* page.

## 7. Updating the site

Merge PRs on GitHub as usual, then on the server run:
```bash
~/clearpay4u/deploy/deploy.sh            # latest main (backs up the database first)
~/clearpay4u/deploy/deploy.sh <commit>   # roll back to an earlier version
```

## 8. Backups and restore

- **Nightly:** `~/backups/clearpay4u-YYYY-MM-DD-HHMM.sql.gz`, kept for 14 days (`BACKUP_KEEP_DAYS`).
  There is also one before every deploy. The log is in `~/backup.log`.
- **Daily snapshots** of the whole server, from step 1.5.
- **Off the server:** from time to time, copy a backup to your laptop. Keep it private: it contains
  salaries, and PAN and account numbers in encrypted form.
  ```bash
  scp -i LightsailDefaultKey-ap-south-1.pem ubuntu@13.x.x.x:backups/clearpay4u-*.sql.gz .
  ```
- **Restore:** `~/clearpay4u/deploy/restore.sh ~/backups/clearpay4u-<date>.sql.gz` (type `RESTORE` to
  confirm). The same `FIELD_ENCRYPTION_KEY` must be in `deploy/.env`.

## 9. Checklist before real clients

- [ ] Admin password changed, MFA on the AWS root account, SSH restricted to your IP.
- [ ] `FIELD_ENCRYPTION_KEY`, `SECRET_KEY` and `POSTGRES_PASSWORD` stored in a password manager.
- [ ] SES production access granted, and a test invite received in a Gmail inbox (not spam).
- [ ] Automatic snapshots on, and a restore tried once on a test server.
- [ ] A billing alarm in AWS Budgets (e.g. $25/month).
- [ ] A privacy policy and terms on the site, since you store employees' personal and financial data
      (India's DPDP Act).

## When you outgrow one server

- **4 GB plan:** take a snapshot, create a new instance from it on the bigger plan, then move the static
  IP to it. There is no DNS change.
- **Managed database:** create a Lightsail PostgreSQL database in Mumbai, restore a backup into it,
  remove the `db` service, and set `DATABASE_URL` to the managed database. This gives automatic
  backups and point-in-time restore.
