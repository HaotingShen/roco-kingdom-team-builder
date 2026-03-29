# Plan: Integrate Umami Analytics

**Context:** Add self-hosted Umami analytics to track Chinese + global visitors, deployable to existing EC2 infrastructure, with a shareable public stats URL for advertisers.

---

## Architecture

```
analytics.rkteambuilder.com (Cloudflare DNS A → 13.228.63.192, grey cloud)
    → EC2 nginx :443 (Let's Encrypt cert via certbot)
    → Docker Umami :3000 (127.0.0.1 only, not exposed to host network)
    → RDS PostgreSQL (new `umami` database on existing RDS instance)

rkteambuilder.com (React SPA, hosted on S3/CloudFront)
    → <script defer src="https://analytics.rkteambuilder.com/script.js">
    → pageview events sent directly to Umami (not blocked in China)
```

Umami runs as an additional Docker service alongside backend + redis on the same EC2.
Completely independent of CloudFront path-based routing — no existing behaviors change.

**No conflicts with existing features:**
- Port 3000 is unused (backend=8000, redis=6379)
- nginx config added as a new separate file `/etc/nginx/sites-available/umami`, does not touch the existing `/etc/nginx/sites-available/rktb` (which handles `origin-api.rkteambuilder.com`)
- The analytics script tag uses `defer` — zero impact on page load, SEO, or rendering
- `docker compose up -d --remove-orphans` in deploy.sh naturally picks up the new service

---

## Files to Modify

- `docker-compose.prod.yml` — add Umami service (code change, auto-deployed via CI/CD)
- `frontend/index.html` — add tracking script tag (second commit, after WEBSITE_ID is known)
- `/home/ubuntu/rktb/deploy.sh` on EC2 (manual SSH edit, not in git) — add UMAMI env var exports

> **Critical sequencing:** The deploy.sh on EC2 MUST be updated (Phase 1.8) BEFORE the git push in Phase 2. If the git push runs first, docker-compose will receive empty UMAMI_DATABASE_URL/UMAMI_APP_SECRET and the Umami container will crash-loop on startup.

---

## Phase 1: Pre-deploy Setup (All Manual)

### 1.1 Open ports 80 and 443 on EC2 security group
AWS Console → EC2 → Security Groups → `sg-0c2dc3e4f20452ddb` → Inbound rules:
- Add rule: Type=HTTP, Port=80, Source=`0.0.0.0/0`
- Add rule: Type=HTTPS, Port=443, Source=`0.0.0.0/0`

> **Why port 80 too?** Port 80 currently only allows CloudFront IPs (managed prefix list). Let's Encrypt's ACME HTTP-01 challenge comes from Let's Encrypt's servers — not CloudFront — so certbot will fail without opening port 80 to all. Also needed every 90 days for automatic cert renewal.
>
> **Security impact of opening port 80:** The existing API nginx block (`origin-api.rkteambuilder.com`) still checks the X-Origin-Verify secret and returns 403 on all direct requests. Opening the port doesn't expose the API — nginx rejects anything that doesn't come from CloudFront.

### 1.2 Add Cloudflare DNS record
Cloudflare DNS dashboard for rkteambuilder.com → Add record:
- Type: A, Name: `analytics`, IPv4: `13.228.63.192`, Proxy status: **OFF (grey cloud, DNS only)**

> Grey cloud is required so Let's Encrypt's ACME HTTP-01 challenge reaches EC2 directly. Wait ~1-2 minutes for DNS to propagate before running certbot in step 1.5.

### 1.3 Create `umami` database on RDS
SSH into EC2, then run:
```bash
DB_URL=$(aws ssm get-parameter --name /rktb/prod/DATABASE_URL --with-decryption --query Parameter.Value --output text --region ap-southeast-1)
psql "${DB_URL/postgresql+psycopg2/postgresql}" -c "CREATE DATABASE umami;"
```

### 1.4 Generate secrets and store in SSM Parameter Store
```bash
# On EC2: generate a random 32-byte secret
openssl rand -hex 32
# Save the output — this is your UMAMI_APP_SECRET

# Store both secrets in Parameter Store:
aws ssm put-parameter \
  --name /rktb/prod/UMAMI_APP_SECRET \
  --value "<output from openssl above>" \
  --type SecureString --region ap-southeast-1

# Build the Umami DATABASE_URL:
# Same RDS host + credentials as main app, just change the database name to `umami`
# Format: postgresql://rktb_admin:<PASSWORD>@rktb-postgres.cnwseow4y66l.ap-southeast-1.rds.amazonaws.com:5432/umami
# The <PASSWORD> is: 26c50b538a8a5444ff7458424d9b9d2209d773e0c592370e

aws ssm put-parameter \
  --name /rktb/prod/UMAMI_DATABASE_URL \
  --value "postgresql://rktb_admin:26c50b538a8a5444ff7458424d9b9d2209d773e0c592370e@rktb-postgres.cnwseow4y66l.ap-southeast-1.rds.amazonaws.com:5432/umami?sslmode=require" \
  --type SecureString --region ap-southeast-1
```

> **IAM note:** The EC2 instance role `rktb-ec2-role` already has `ssm:GetParameter` on `/rktb/prod/*` (since it fetches all existing secrets). The new `/rktb/prod/UMAMI_*` keys are covered by the same wildcard — no IAM changes needed.

### 1.5 Add nginx server block for analytics subdomain
Create the nginx config file on EC2 **before** running certbot (certbot needs the server block to exist):
```bash
sudo tee /etc/nginx/sites-available/umami << 'NGINX_CONF'
server {
    listen 80;
    server_name analytics.rkteambuilder.com;

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX_CONF

sudo ln -sf /etc/nginx/sites-available/umami /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 1.6 Install certbot and get SSL certificate
```bash
sudo apt update && sudo apt install certbot python3-certbot-nginx -y

# Run certbot once — it reads the existing server block, gets the cert,
# and rewrites /etc/nginx/sites-available/umami to add SSL + HTTP→HTTPS redirect automatically
sudo certbot --nginx -d analytics.rkteambuilder.com
# Prompts: enter email, agree to ToS, select option 2 (redirect HTTP to HTTPS)
```

After certbot completes, verify the config and check security headers survived the rewrite:
```bash
sudo nginx -t
sudo systemctl reload nginx

# Confirm security headers are in the HTTPS server block (not just HTTP block)
grep -A2 "X-Content-Type" /etc/nginx/sites-available/umami
```
If the headers are missing from the `listen 443` block, add them manually before the `location /` line.

> certbot also installs a systemd timer for auto-renewal every 90 days. Port 80 must remain open to 0.0.0.0/0 permanently, otherwise renewal will fail.

### 1.7 Verify nginx is serving Umami (before Umami container exists)
```bash
# Should return 502 Bad Gateway (nginx is up, but Umami container not yet running — expected)
curl -I https://analytics.rkteambuilder.com
```
A 502 confirms nginx + SSL is working correctly. The 200 will come after Phase 2 deploys Umami.

### 1.8 Update deploy.sh on EC2 to export Umami secrets

> **This step MUST be completed before the git push in Phase 2.**

```bash
# On EC2
nano /home/ubuntu/rktb/deploy.sh
```

Add these two lines immediately after the `export SMTP_PASSWORD=...` line (around line 27):
```bash
export UMAMI_DATABASE_URL=$(aws ssm get-parameter --name /rktb/prod/UMAMI_DATABASE_URL --with-decryption --region $REGION --query Parameter.Value --output text)
export UMAMI_APP_SECRET=$(aws ssm get-parameter --name /rktb/prod/UMAMI_APP_SECRET --with-decryption --region $REGION --query Parameter.Value --output text)
```

---

## Phase 2: Code Changes (git push → auto-deploy)

### Change 1: docker-compose.prod.yml — add Umami service

Add the `umami` service after the `redis` service block, immediately before the `volumes:` line at the bottom:

```yaml
  umami:
    image: ghcr.io/umami-software/umami:postgresql-latest
    restart: always
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      - DATABASE_URL=${UMAMI_DATABASE_URL}
      - APP_SECRET=${UMAMI_APP_SECRET}
      - NODE_TLS_REJECT_UNAUTHORIZED=0
```

`--remove-orphans` in deploy.sh naturally picks this up. No changes to deploy.sh CI/CD flow.

> **Why `NODE_TLS_REJECT_UNAUTHORIZED=0`?** AWS RDS uses a certificate signed by AWS's own CA, which Node.js does not trust by default. Without this, Prisma (used internally by Umami) throws `Error opening a TLS connection: self-signed certificate in certificate chain` and crashes on startup. This env var tells Node.js to skip CA chain verification while still using SSL encryption. The alternative (mounting the AWS RDS CA bundle into the container) is significantly more complex.

> **Why `?sslmode=require` in UMAMI_DATABASE_URL?** RDS requires SSL connections. Without it the error is `no pg_hba.conf entry for host..., no encryption`. The `sslmode=require` enforces SSL at the PostgreSQL protocol level; `NODE_TLS_REJECT_UNAUTHORIZED=0` handles the Node.js certificate trust issue on top.


---

## Phase 3: Post-deploy Setup (Manual, after git push deploys)

### 3.1 First-time Umami login and website registration
1. Go to `https://analytics.rkteambuilder.com`
2. Default credentials: username `admin`, password `umami`
3. **Change password immediately** (Settings → Profile) — `admin/umami` is publicly known, do this before anything else
4. Settings → Websites → Add website
   - Name: `RK Team Builder`
   - Domain: `rkteambuilder.com`
5. Copy the generated **Website ID** (a UUID like `a1b2c3d4-...`)

### 3.2 Enable public stats sharing (for advertiser)
Settings → Websites → your site → Share URL toggle → copy the public URL → send to advertiser.

### Change 2: frontend/index.html — add tracking script

Add the following as the **last line before `</head>`** (between `</style>` on line 95 and `</head>` on line 96):
```html
    <script defer src="https://analytics.rkteambuilder.com/script.js" data-website-id="PASTE_WEBSITE_ID_HERE"></script>
```

Replace `PASTE_WEBSITE_ID_HERE` with the UUID from step 3.1.

Push to main → GitHub Actions builds frontend → deploys to S3 → invalidates CloudFront. No SEO impact (`defer` doesn't block rendering or parsing).

---

## Verification

```bash
# On EC2: all three containers should show healthy/running
docker compose -f docker-compose.prod.yml ps

# Umami dashboard reachable
curl -I https://analytics.rkteambuilder.com
# Expected: HTTP/2 200

# Tracking script served (confirms script.js endpoint works)
curl -I https://analytics.rkteambuilder.com/script.js
# Expected: HTTP/2 200 with content-type: application/javascript
```

---

## Post-deploy: Connection Pool Cap (added 2026-03-29)

Umami shares the same RDS instance as the backend. Its Prisma connection pool defaults to 9 connections (CPU cores × 2 + 1), which silently consumes slots from the shared `max_connections=80` limit.

**Fix:** append `&connection_limit=5` to `UMAMI_DATABASE_URL` in SSM, then restart umami.

```bash
# Run from local machine (EC2 role lacks ssm:PutParameter)
aws ssm put-parameter --name /rktb/prod/UMAMI_DATABASE_URL \
  --value "postgresql://...?sslmode=require&connection_limit=5" \
  --type SecureString --overwrite --region ap-southeast-1

# Then on EC2
export UMAMI_DATABASE_URL=$(aws ssm get-parameter --name /rktb/prod/UMAMI_DATABASE_URL \
  --with-decryption --query Parameter.Value --output text --region ap-southeast-1)
docker compose -f docker-compose.prod.yml up -d umami
```

5 connections is sufficient — Umami is a single Node.js process and rarely needs more than 2 concurrent DB connections.
