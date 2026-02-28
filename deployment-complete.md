# AWS Deployment Plan: Roco Kingdom Team Builder

**Domain:** `rkteambuilder.com` (already purchased)
**Region:** Singapore (`ap-southeast-1`)
**EC2:** t3.small (2 vCPU, 2 GB RAM)
**Email:** AWS SES
**Routing:** Path-based (single domain via CloudFront)

---

## How Docker, GitHub Actions, and AWS Connect

```
You (local dev)
  │
  │  git push to main
  ▼
GitHub Repository
  │
  │  triggers automatically
  ▼
GitHub Actions (CI/CD runner)
  ├── 1. Run tests (pytest, npm typecheck, npm lint)
  ├── 2. Build backend Docker image
  ├── 3. Push image → AWS ECR (private container registry)
  ├── 4. Build frontend (npm run build)
  ├── 5. Upload frontend dist/ → AWS S3
  ├── 6. Invalidate CloudFront cache
  └── 7. SSM command to EC2 → pull new Docker image → restart containers
```

**Docker** = packaging format. Wraps your backend code + Python 3.10 + all pip dependencies into a portable image. Same image runs identically on your laptop and on EC2. No more "works on my machine" issues.

**GitHub Actions** = automation runner. On every `git push` to `main`, it runs your CI/CD pipeline. Similar to the GitHub Pages `.yml` you've written before, but deploying to AWS instead. Authenticates to AWS via OIDC (no long-lived AWS keys stored in GitHub).

**AWS** = hosting infrastructure. ECR stores your Docker images (like Docker Hub but private). EC2 runs the containers. S3 hosts the frontend. CloudFront sits in front of everything.

### Architecture

```
Users → https://rkteambuilder.com
              │
              ▼
     ┌───────────────────────────────────────────────┐
     │           CloudFront CDN                      │
     │  • HTTPS termination (ACM certificate)        │
     │  • Security headers                           │
     │  • DDoS protection                            │
     │  • Edge caching (Singapore, HK, Tokyo, etc.)  │
     └──────┬──────────────────────────┬─────────────┘
            │                          │
  /api/* → EC2:                        │  /* (default) → S3
  (all API calls use /api/ prefix)     │
  Nginx strips /api before FastAPI     │
            │                          │
            ▼                          ▼
  ┌─────────────────────┐    ┌───────────────┐
  │  EC2 t3.small       │    │   S3 Bucket   │
  │  ap-southeast-1     │    │  (React SPA)  │
  │                     │    │ rktb-frontend │
  │  ┌───────────────┐  │    └───────────────┘
  │  │ Nginx :80     │  │
  │  │ (reverse      │  │
  │  │  proxy +      │  │
  │  │  origin check)│  │
  │  └───────┬───────┘  │
  │          │          │
  │  ┌───────▼───────┐  │
  │  │ Docker Compose│  │
  │  │               │  │
  │  │ ┌───────────┐ │  │
  │  │ │ FastAPI   │ │  │
  │  │ │ :8000     │ │  │
  │  │ └───────────┘ │  │
  │  │ ┌───────────┐ │  │
  │  │ │ Redis 7   │ │  │
  │  │ │ :6379     │ │  │
  │  │ └───────────┘ │  │
  │  └───────────────┘  │
  └──────────┬──────────┘
             │
             ▼
  ┌──────────────────────┐
  │  RDS PostgreSQL 16   │
  │  db.t3.micro         │
  │  (private subnet,    │
  │   not internet-      │
  │   accessible)        │
  └──────────────────────┘
```

**Path-based routing** means everything goes through `rkteambuilder.com`:
- `rkteambuilder.com/teams` → S3 (React SPA — browser navigation)
- `rkteambuilder.com/api/auth/login` → EC2 (FastAPI API call)
- `rkteambuilder.com/api/teams` → EC2 (FastAPI data fetch)

All API calls use the `/api/` prefix so CloudFront can distinguish them from SPA navigation (which uses the same path names but without the prefix). Nginx strips `/api` before FastAPI sees the request, so FastAPI routes remain unchanged.

This means cookies are on the same domain — no cross-domain issues, no COOKIE_DOMAIN config needed, SameSite=Lax works.

### Cost Estimate ($200 free credit + free tier)

| Service | Free Tier (12 mo) | After Free Tier |
|---------|-------------------|-----------------|
| EC2 t3.small | Not free tier eligible | ~$15/mo |
| RDS db.t3.micro | 750 hrs/mo FREE | ~$15/mo |
| S3 (5 GB) | FREE | ~$0.12/mo |
| CloudFront (1 TB) | FREE | ~$85/TB |
| ECR (500 MB) | FREE | ~$0.10/GB |
| Parameter Store | FREE (standard) | FREE |
| Cloudflare DNS | FREE forever | FREE |
| SES (from EC2) | 3,000/mo FREE | $0.10/1000 |
| WAF (optional) | Not free | ~$5/mo + $0.60/M requests |
| **Year 1 total** | | **~$15-25/mo** |

With your $200 credit, that covers roughly the first 8-12 months (depending on whether you enable WAF).

> ⚠️ **Pricing disclaimer:** AWS pricing and free tier eligibility change over time. Always verify current pricing at [aws.amazon.com/pricing](https://aws.amazon.com/pricing/) before making decisions. The estimates above are approximate and based on ap-southeast-1 region pricing as of early 2025.

**Note:** Using Cloudflare DNS (free) instead of Route 53 ($0.50/mo) saves about $6/year.

---

## Phase 1: AWS Console & CLI Setup (One-Time)

```
  What Phase 1 builds — every AWS resource and how they connect:

  ┌────────────────────────────────────────────────────────────────────┐
  │  VPC  vpc-0953d095418f1950f   10.0.0.0/16  (1.4)                   │
  │  Your private, isolated network in AWS. Nothing gets in or out     │
  │  unless you explicitly allow it.                                   │
  │                                                                    │
  │  ┌───────────────────────────────────┐  ┌───────────────────────┐  │
  │  │  Public Subnet  10.0.1.0/24  (1a) │  │ Private Subnet  (1a)  │  │
  │  │  Routes to Internet Gateway       │  │ Private Subnet  (1b)  │  │
  │  │                                   │  │ No internet route     │  │
  │  │  ┌─────────────────────────────┐  │  │                       │  │
  │  │  │  EC2  t3.micro  (1.8)       │  │  │  ┌─────────────────┐  │  │
  │  │  │  13.228.63.192 (Elastic IP) │  │  │  │ RDS PostgreSQL  │  │  │
  │  │  │  IAM role: rktb-ec2-role    │  │  │  │ db.t3.micro(1.6)│  │  │
  │  │  │  SG: rktb-ec2-sg            │  │  │  │ SG: rktb-rds-sg │  │  │
  │  │  └─────────────────────────────┘  │  │  └─────────────────┘  │  │
  │  └───────────────────────────────────┘  └───────────────────────┘  │
  └────────────────────────────────────────────────────────────────────┘

  Outside the VPC (global AWS services):
  ┌───────────────┐  ┌───────────────┐  ┌──────────────────────────────┐
  │  S3  (1.9)    │  │  ECR  (1.9)   │  │  Parameter Store  (1.11)     │
  │  rktb-frontend│  │  rktb-backend │  │  /rktb/prod/DATABASE_URL     │
  │  (React SPA)  │  │  (Docker imgs)│  │  /rktb/prod/SECRET_KEY       │
  └───────────────┘  └───────────────┘  │  /rktb/prod/DEEPSEEK_API_KEY │
                                        │  /rktb/prod/REDIS_PASSWORD   │
  ┌───────────────┐  ┌───────────────┐  │  /rktb/prod/ORIGIN_SECRET    │
  │  ACM Cert     │  │  IAM Role     │  │  /rktb/prod/S3_REFERER_SECRET│
  │  us-east-1    │  │  rktb-ec2-role│  │  /rktb/prod/FRONTEND_URL     │
  │  (1.3)        │  │  (1.7)        │  │  /rktb/prod/ADMIN_EMAILS     │
  └───────────────┘  └───────────────┘  └──────────────────────────────┘

  ──────────────────────────────────────────────────────────────────────

  1.3 — ACM Certificate: why us-east-1?

  CloudFront is a GLOBAL service. It only reads SSL certificates from
  us-east-1 (its "home" region), regardless of where your app lives.
  Your app is in ap-southeast-1, but the certificate MUST be in us-east-1.

  Certificate covers:
  ├── rkteambuilder.com        (root domain)
  └── *.rkteambuilder.com      (wildcard — covers origin-api, www, etc.)

  Validation: ACM gives you a CNAME record to prove you own the domain.
  You add it to Cloudflare DNS → ACM verifies → certificate "Issued".

  ──────────────────────────────────────────────────────────────────────

  1.4 — VPC Networking: why public vs private subnets?

  Internet
      │
      ▼
  Internet Gateway (attached to VPC)
      │
      ▼
  Route Table → 0.0.0.0/0 → IGW (only public subnet uses this)
      │
      ▼
  Public Subnet 10.0.1.0/24  ← EC2 lives here
      │ can reach internet (pull Docker images, call AWS APIs)
      │ internet can reach EC2 (on allowed ports only via SG)

  Private Subnets 10.0.10.0/24 + 10.0.11.0/24  ← RDS lives here
      │ NO route to internet gateway
      │ RDS can only be reached from within the VPC
      │ Even if someone guesses the RDS endpoint, they can't connect

  Why 2 private subnets?  RDS requires a "subnet group" spanning 2
  availability zones (1a + 1b) for high-availability readiness, even
  if Multi-AZ is not enabled yet.

  ──────────────────────────────────────────────────────────────────────

  1.5 — Security Groups: two firewalls, layered

  Internet
      │
      ├── Port 22  (SSH):  YOUR IP only → EC2
      ├── Port 80  (HTTP): CloudFront IPs only → EC2  (via managed prefix list)
      ├── Port 443: BLOCKED  (CloudFront→EC2 is HTTP, CloudFront handles TLS)
      ├── Port 8000: BLOCKED (FastAPI only reachable via Nginx internally)
      │
      ▼
  EC2  (rktb-ec2-sg: sg-0c2dc3e4f20452ddb)
      │
      │ Port 5432: only EC2 security group → RDS
      │ (RDS SG checks source SG, not IP — handles dynamic IPs)
      ▼
  RDS  (rktb-rds-sg: sg-0eedc536da3a8f6fa)

  Note: CloudFront prefix list alone doesn't prove it's YOUR CloudFront.
  Anyone can create a CloudFront distribution. That's why Nginx ALSO
  checks the X-Origin-Verify secret (Phase 3.2) — two independent layers.

  ──────────────────────────────────────────────────────────────────────

  1.7 — IAM Role: EC2's permission badge

  EC2 uses a role (not a stored username/password) to access AWS services.
  The role is attached at launch time. AWS rotates credentials automatically.

  rktb-ec2-role grants:
  ┌──────────────────────┬──────────────────────────────────────────────┐
  │ Permission           │ Why needed                                   │
  ├──────────────────────┼──────────────────────────────────────────────┤
  │ ssm:GetParameter     │ Read secrets from Parameter Store (deploy.sh)│
  │ kms:Decrypt          │ Decrypt SecureString parameters              │
  │ ecr:GetAuthToken     │ Log in to ECR to pull Docker images          │
  │ ecr:BatchGetImage    │ Pull Docker image layers from ECR            │
  │ ecr:GetDownload...   │ Download image layers from ECR               │
  │ logs:PutLogEvents    │ Send container logs to CloudWatch            │
  │ ssm:UpdateInstance.. │ SSM Agent heartbeat (lets SSM find this EC2) │
  │ ssmmessages:*        │ SSM session channel (for remote commands)    │
  │ s3:GetObject         │ Download docker-compose from S3 during deploy│
  └──────────────────────┴──────────────────────────────────────────────┘

  ──────────────────────────────────────────────────────────────────────

  1.8 — EC2: why Elastic IP?

  By default, EC2 gets a NEW public IP every time it restarts.
  Cloudflare DNS record "origin-api.rkteambuilder.com → 13.228.63.192"
  would break every time EC2 rebooted.

  Elastic IP = permanent IP address reserved to your account.
  Cost: FREE while attached to a running instance. ~$4/mo if unattached.

  ──────────────────────────────────────────────────────────────────────

  1.9 — S3: website hosting mode vs OAC

  Website hosting mode chosen because:
  ├── Built-in 404 → index.html at S3 level (needed for React Router SPA)
  └── Simple to configure

  If we used OAC (CloudFront Origin Access Control):
  ├── CloudFront custom error responses (403/404 → index.html) would be
  │   distribution-wide → API 404 errors would also return index.html
  └── Would break the frontend when API returns 404

  Protection: S3 bucket policy requires Referer: <S3_REFERER_SECRET>
  CloudFront sends this header automatically. Direct browser access blocked.

  ECR = private Docker image registry (like Docker Hub but in your AWS account)
  └── Images tagged with git commit SHA (e.g. :abc1234) for rollbacks
      and also :latest for convenience

  ──────────────────────────────────────────────────────────────────────

  1.10 — Cloudflare DNS records added in Phase 1

  ┌────────────┬────────────────┬───────────────────────────────┬───────┐
  │ Type       │ Name           │ Content                       │ Proxy │
  ├────────────┼────────────────┼───────────────────────────────┼───────┤
  │ CNAME      │ _acm-validate  │ (ACM validation value)        │ grey  │
  │ A          │ origin-api     │ 13.228.63.192                 │ grey  │
  └────────────┴────────────────┴───────────────────────────────┴───────┘
  (rkteambuilder.com → CloudFront CNAME added in Phase 4.4)

  Both MUST be grey cloud (DNS only). If proxied through Cloudflare,
  origin-api would hide EC2's real IP from CloudFront, breaking the
  connection. ACM validation would also fail if proxied.

  ──────────────────────────────────────────────────────────────────────

  1.11 — Parameter Store: why not just use .env files on EC2?

  .env files on disk:                Parameter Store:
  ├── Must be manually managed       ├── Centrally managed in AWS
  ├── Risk of being committed to git ├── Encrypted at rest (KMS)
  ├── Hard to rotate secrets         ├── Audit log of every read
  ├── No audit trail                 ├── Rotatable without SSH
  └── Anyone with SSH can read them  └── Only accessible via IAM role

  deploy.sh reads secrets at deploy time and injects them as env vars
  into Docker containers. Secrets never touch disk on EC2.

```

### 1.1 Install & Configure AWS CLI

```bash
# Install AWS CLI v2 (on your WSL2)
# TIP: Run from /tmp to avoid cluttering your project directory
cd /tmp
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Create an IAM user in AWS Console:
#   1. Go to IAM → Users → Create user
#   2. Attach the "AdministratorAccess" policy directly
#   3. Go to the user → Security credentials → Create access key
#   4. Choose "Command Line Interface (CLI)" as the use case
#   5. Copy the Access Key ID and Secret Access Key

# Configure the CLI with your IAM credentials
aws configure
# AWS Access Key ID: your-key
# AWS Secret Access Key: your-secret
# Default region: ap-southeast-1
# Default output format: json

# Verify
aws sts get-caller-identity
```

### 1.2 DNS Setup (Domain Registered at Cloudflare)

Since your domain is registered at Cloudflare, you have **two options**:

**Option A: Keep DNS at Cloudflare (Recommended - Simpler)**

You don't need Route 53. You'll add DNS records directly in the Cloudflare dashboard.

- No nameserver changes needed
- Cloudflare will manage your DNS records
- ACM certificate validation will require manual CNAME records in Cloudflare

**Option B: Use Route 53 for DNS**

If you prefer AWS-managed DNS (easier ACM validation, unified AWS management):

```bash
# Create hosted zone
aws route53 create-hosted-zone --name rkteambuilder.com \
  --caller-reference "$(date +%s)" --region us-east-1
```

Then in Cloudflare:
1. DNS → Settings → Nameservers → change to "Custom nameservers"
2. Enter the 4 NS records from Route 53 output
3. Wait for propagation (can be up to 24-48 hours)

**This plan assumes Option A (Cloudflare DNS)** — I'll indicate where to add records in Cloudflare instead of Route 53.

### 1.3 Request ACM Certificate

CloudFront requires the certificate to be in **us-east-1** regardless of your app's region:

```bash
aws acm request-certificate \
  --domain-name rkteambuilder.com \
  --subject-alternative-names "*.rkteambuilder.com" \
  --validation-method DNS \
  --region us-east-1
```

Note the `CertificateArn` from the output.

**Validate via Cloudflare DNS:**

1. AWS Console → Certificate Manager → **us-east-1 region** → click the pending certificate
2. Expand "Domains" section → note the CNAME Name and Value for each domain
3. Go to Cloudflare Dashboard → your domain → DNS → Add record:
   - Type: `CNAME`
   - Name: The CNAME Name from ACM (remove `.rkteambuilder.com` suffix if Cloudflare auto-appends)
   - Target: The CNAME Value from ACM
   - Proxy status: **DNS only (grey cloud)** — IMPORTANT! Must be unproxied for ACM validation
4. Repeat for the wildcard domain validation record if there's a separate one
5. Wait for ACM status → "Issued" (usually 5-30 minutes)

**Example:**
If ACM shows:
- Name: `_abc123.rkteambuilder.com`
- Value: `_xyz789.acm-validations.aws.`

In Cloudflare:
- Name: `_abc123`
- Target: `_xyz789.acm-validations.aws`
- Proxy: OFF (grey cloud)

### 1.4 Create VPC and Networking

```bash
# Create VPC
VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 --region ap-southeast-1 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=rktb-vpc}]' \
  --query 'Vpc.VpcId' --output text)
echo "VPC: $VPC_ID"

# Enable DNS hostnames (required for RDS endpoint resolution)
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames '{"Value":true}'
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-support '{"Value":true}'

# Create and attach Internet Gateway
IGW_ID=$(aws ec2 create-internet-gateway --region ap-southeast-1 \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=rktb-igw}]' \
  --query 'InternetGateway.InternetGatewayId' --output text)
aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID

# Create public subnet (for EC2) - ap-southeast-1a
PUB_SUBNET=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.1.0/24 \
  --availability-zone ap-southeast-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=rktb-public-1a}]' \
  --query 'Subnet.SubnetId' --output text)

# Create private subnets (for RDS - needs 2 AZs for subnet group)
PRIV_SUBNET_A=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.10.0/24 \
  --availability-zone ap-southeast-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=rktb-private-1a}]' \
  --query 'Subnet.SubnetId' --output text)

PRIV_SUBNET_B=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block 10.0.11.0/24 \
  --availability-zone ap-southeast-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=rktb-private-1b}]' \
  --query 'Subnet.SubnetId' --output text)

# Create route table for public subnet → Internet
RTB_ID=$(aws ec2 create-route-table --vpc-id $VPC_ID --region ap-southeast-1 \
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=rktb-public-rt}]' \
  --query 'RouteTable.RouteTableId' --output text)
aws ec2 create-route --route-table-id $RTB_ID --destination-cidr-block 0.0.0.0/0 \
  --gateway-id $IGW_ID
aws ec2 associate-route-table --route-table-id $RTB_ID --subnet-id $PUB_SUBNET

echo "Public subnet: $PUB_SUBNET"
echo "Private subnets: $PRIV_SUBNET_A, $PRIV_SUBNET_B"
```

### 1.5 Create Security Groups

> See overview diagram above (section 1.5) for how ports and rules connect.

```bash
# EC2 Security Group
EC2_SG=$(aws ec2 create-security-group --group-name rktb-ec2-sg \
  --description "RKTB Backend EC2" --vpc-id $VPC_ID --region ap-southeast-1 \
  --query 'GroupId' --output text)

# SSH: Only from your current IP (for manual access)
# NOTE: GitHub Actions deploys via AWS SSM, not SSH. See Phase 5 for details.
# HARDENING: Ubuntu 22.04 uses key-only auth by default. Verify with:
#   sudo grep "PasswordAuthentication" /etc/ssh/sshd_config
# Once you're comfortable with SSM, consider closing port 22 entirely.
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id $EC2_SG \
  --protocol tcp --port 22 --cidr "${MY_IP}/32"

# HTTP: Only from CloudFront IPs (using AWS managed prefix list)
# This blocks direct internet scans/noise from hitting your EC2.
# NOTE: Prefix list alone doesn't prove it's YOUR CloudFront distribution
# (anyone can create CloudFront), so we STILL need X-Origin-Verify header check in Nginx.
CF_PREFIX_LIST=$(aws ec2 describe-managed-prefix-lists \
  --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" \
  --query "PrefixLists[0].PrefixListId" --output text --region ap-southeast-1)

# Safety check: verify prefix list was found
if [[ -z "$CF_PREFIX_LIST" || "$CF_PREFIX_LIST" == "None" ]]; then
  echo "WARNING: CloudFront prefix list not found in ap-southeast-1, trying us-east-1..."
  CF_PREFIX_LIST=$(aws ec2 describe-managed-prefix-lists \
    --filters "Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing" \
    --query "PrefixLists[0].PrefixListId" --output text --region us-east-1)
fi

if [[ -z "$CF_PREFIX_LIST" || "$CF_PREFIX_LIST" == "None" ]]; then
  echo "ERROR: CloudFront prefix list not found. Using 0.0.0.0/0 fallback (less secure)."
  aws ec2 authorize-security-group-ingress --group-id $EC2_SG \
    --protocol tcp --port 80 --cidr 0.0.0.0/0
else
  echo "Using CloudFront prefix list: $CF_PREFIX_LIST"
  aws ec2 authorize-security-group-ingress --group-id $EC2_SG \
    --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=$CF_PREFIX_LIST}]"
fi

# NOTE: No port 443 (CloudFront → EC2 is HTTP only, CloudFront terminates TLS)
# NOTE: No port 8000 (FastAPI only accessible via Docker internal network → Nginx)

# RDS Security Group
RDS_SG=$(aws ec2 create-security-group --group-name rktb-rds-sg \
  --description "RKTB RDS PostgreSQL" --vpc-id $VPC_ID --region ap-southeast-1 \
  --query 'GroupId' --output text)

# PostgreSQL: Only from EC2 security group
aws ec2 authorize-security-group-ingress --group-id $RDS_SG \
  --protocol tcp --port 5432 --source-group $EC2_SG

echo "EC2 SG: $EC2_SG"
echo "RDS SG: $RDS_SG"
```

### 1.6 Create RDS PostgreSQL

```bash
# Create DB subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name rktb-db-subnets \
  --db-subnet-group-description "Private subnets for RKTB RDS" \
  --subnet-ids $PRIV_SUBNET_A $PRIV_SUBNET_B \
  --region ap-southeast-1

# Generate a strong DB password
DB_PASSWORD=$(openssl rand -base64 24)
echo "DB Password (save this!): $DB_PASSWORD"

# Create RDS instance (free tier eligible: db.t3.micro)
aws rds create-db-instance \
    --db-instance-identifier rktb-postgres \
    --db-instance-class db.t3.micro \
    --engine postgres \
    --engine-version 16 \
    --master-username rktb_admin \
    --master-user-password "$DB_PASSWORD" \
    --allocated-storage 20 \
    --db-name roco_kingdom \
    --vpc-security-group-ids $RDS_SG \
    --db-subnet-group-name rktb-db-subnets \
    --no-publicly-accessible \
    --storage-encrypted \
    --deletion-protection \
    --region ap-southeast-1

# NOTE on RDS options:
# - backup-retention-period is 1 by defualt at free tier: Automated daily backups kept for 1 days
# - deletion-protection: Prevents accidental deletion (must disable in console before dropping DB)
# - Multi-AZ NOT enabled: Adds ~$15/mo but provides automatic failover. Enable if uptime is critical.
#   To enable later: aws rds modify-db-instance --db-instance-identifier rktb-postgres --multi-az
```

Wait ~10 minutes for RDS to be available:
```bash
aws rds wait db-instance-available --db-instance-identifier rktb-postgres --region ap-southeast-1
RDS_ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier rktb-postgres \
  --query 'DBInstances[0].Endpoint.Address' --output text --region ap-southeast-1)
echo "RDS Endpoint: $RDS_ENDPOINT"
```

### 1.7 Create IAM Role for EC2

```bash
# Create trust policy file
cat > /tmp/ec2-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ec2.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

# Create the role
aws iam create-role --role-name rktb-ec2-role \
  --assume-role-policy-document file:///tmp/ec2-trust.json

# Create permissions policy file
cat > /tmp/ec2-perms.json << 'ENDOFPOLICY'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ParameterStore",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters"],
      "Resource": "arn:aws:ssm:ap-southeast-1:*:parameter/rktb/prod/*"
    },
    {
      "Sid": "KMSDecrypt",
      "Effect": "Allow",
      "Action": ["kms:Decrypt"],
      "Resource": "*"
    },
    {
      "Sid": "ECRPull",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchCheckLayerAvailability"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SSMCore",
      "Effect": "Allow",
      "Action": [
        "ssm:UpdateInstanceInformation",
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3DeployFiles",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::rktb-frontend/deploy/*"
    }
  ]
}
ENDOFPOLICY

aws iam put-role-policy --role-name rktb-ec2-role \
  --policy-name rktb-ec2-perms --policy-document file:///tmp/ec2-perms.json

# NOTE: KMSDecrypt uses Resource:"*" because SSM SecureString uses the default
# aws/ssm KMS key. This is acceptable for simplicity. To scope tighter, find the
# key ARN via: aws kms describe-key --key-id alias/aws/ssm --region ap-southeast-1

# Create instance profile and attach role
aws iam create-instance-profile --instance-profile-name rktb-ec2-role
aws iam add-role-to-instance-profile \
  --instance-profile-name rktb-ec2-role --role-name rktb-ec2-role

# Wait a few seconds for propagation
sleep 10
```

### 1.8 Launch EC2 Instance

```bash
# Create SSH key pair
aws ec2 create-key-pair --key-name rktb-key --region ap-southeast-1 \
  --query 'KeyMaterial' --output text > ~/.ssh/rktb-key.pem
chmod 400 ~/.ssh/rktb-key.pem

# Find current Ubuntu 22.04 LTS AMI for ap-southeast-1
AMI_ID=$(aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text \
  --region ap-southeast-1)
echo "AMI: $AMI_ID"

# Launch instance
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type t3.small \
  --key-name rktb-key \
  --security-group-ids $EC2_SG \
  --subnet-id $PUB_SUBNET \
  --associate-public-ip-address \
  --iam-instance-profile Name=rktb-ec2-role \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=rktb-backend}]' \
  --region ap-southeast-1 \
  --query 'Instances[0].InstanceId' --output text)
echo "Instance: $INSTANCE_ID"

# Allocate Elastic IP (so IP doesn't change on reboot)
EIP_ALLOC=$(aws ec2 allocate-address --region ap-southeast-1 \
  --query 'AllocationId' --output text)
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region ap-southeast-1
aws ec2 associate-address --instance-id $INSTANCE_ID --allocation-id $EIP_ALLOC

EC2_IP=$(aws ec2 describe-addresses --allocation-ids $EIP_ALLOC \
  --query 'Addresses[0].PublicIp' --output text --region ap-southeast-1)
echo "EC2 Elastic IP: $EC2_IP"
```

### 1.9 Create S3 Bucket and ECR Repository

```bash
# S3 bucket for frontend (website hosting mode for SPA routing)
aws s3 mb s3://rktb-frontend --region ap-southeast-1

# IMPORTANT: For website hosting with conditional bucket policy, we must
# DISABLE Block Public Access. The referer condition protects against
# unauthorized access, but AWS considers Principal:"*" as "public".
aws s3api put-public-access-block --bucket rktb-frontend \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false

# Enable static website hosting with error document for SPA routing
# This handles 404s at S3 level (returns index.html), so CloudFront
# custom error responses are NOT needed - API errors pass through unchanged
aws s3 website s3://rktb-frontend \
  --index-document index.html \
  --error-document index.html

# Generate a random referer secret for origin protection
REFERER_SECRET=$(openssl rand -hex 32)
echo "S3 Referer Secret (save this!): $REFERER_SECRET"

# Store in Parameter Store
aws ssm put-parameter --name /rktb/prod/S3_REFERER_SECRET \
  --value "$REFERER_SECRET" --type SecureString --region ap-southeast-1

# Bucket policy: Allow public read ONLY with correct Referer header
# CloudFront will send this header; direct access is blocked
aws s3api put-bucket-policy --bucket rktb-frontend --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Sid\": \"AllowCloudFrontReferer\",
    \"Effect\": \"Allow\",
    \"Principal\": \"*\",
    \"Action\": \"s3:GetObject\",
    \"Resource\": \"arn:aws:s3:::rktb-frontend/*\",
    \"Condition\": {
      \"StringEquals\": {
        \"aws:Referer\": \"$REFERER_SECRET\"
      }
    }
  }]
}"

# ECR repository for backend Docker images
ECR_URI=$(aws ecr create-repository --repository-name rktb-backend \
  --region ap-southeast-1 --image-scanning-configuration scanOnPush=true \
  --query 'repository.repositoryUri' --output text)
echo "ECR URI: $ECR_URI"
```

> **Why website hosting instead of OAC?**
>
> S3 website hosting has a built-in error document feature: when a file doesn't exist, S3 returns `index.html` (for SPA routing). This happens at the S3 level, so we don't need CloudFront custom error responses.
>
> If we used OAC with CloudFront custom error responses (403/404 → index.html), those responses would be **distribution-wide** and would also affect API errors - breaking the frontend when the API returns 403/404.
>
> **Security tradeoff:** Referer headers can be spoofed by non-browser clients (curl, scripts), so this is weaker than OAC. However, the frontend is just static HTML/JS/CSS - not sensitive data. The API remains protected by the origin secret header. For most applications, this tradeoff is acceptable.
>
> **Higher-security alternative:** Use S3 REST endpoint + OAC, and add Lambda@Edge on origin-response to rewrite S3 403/404 → index.html for the S3 origin only. This adds complexity (~$0.60/million requests) but provides cryptographic origin protection.

### 1.10 Create DNS Records (in Cloudflare)

Go to **Cloudflare Dashboard → rkteambuilder.com → DNS**

**Add record for API origin:**
| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| A | `origin-api` | `(your EC2 Elastic IP)` | DNS only (grey cloud) | Auto |

**Important:** The `origin-api` subdomain MUST be **DNS only (grey cloud)**, not proxied through Cloudflare. CloudFront needs to connect directly to your EC2.

The main `rkteambuilder.com` CNAME to CloudFront will be added after CloudFront is set up (Phase 4).

### 1.11 Store Secrets in Parameter Store

```bash
# Generate secrets
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
REDIS_PASSWORD=$(openssl rand -hex 24)
ORIGIN_SECRET=$(openssl rand -hex 32)

echo "Save these somewhere safe:"
echo "SECRET_KEY: $SECRET_KEY"
echo "REDIS_PASSWORD: $REDIS_PASSWORD"
echo "ORIGIN_SECRET: $ORIGIN_SECRET"

# Store in Parameter Store (standard tier = FREE)
aws ssm put-parameter --name /rktb/prod/DATABASE_URL \
  --value "postgresql://rktb_admin:${DB_PASSWORD}@${RDS_ENDPOINT}:5432/roco_kingdom" \
  --type SecureString --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/SECRET_KEY \
  --value "$SECRET_KEY" --type SecureString --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/GEMINI_API_KEY \
  --value "YOUR_GEMINI_KEY_HERE" --type SecureString --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/DEEPSEEK_API_KEY \
    --value "YOUR_DEEPSEEK_KEY_HERE" --type SecureString --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/REDIS_PASSWORD \
  --value "$REDIS_PASSWORD" --type SecureString --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/ORIGIN_SECRET \
  --value "$ORIGIN_SECRET" --type SecureString --region ap-southeast-1

# NOTE: COOKIE_DOMAIN is intentionally NOT set for path-based routing.
# When unset, cookies default to exact origin (rkteambuilder.com), which is correct.
# Do NOT set COOKIE_DOMAIN=.rkteambuilder.com — that's for subdomain-based routing only.

aws ssm put-parameter --name /rktb/prod/FRONTEND_URL \
  --value "https://rkteambuilder.com" --type String --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/ADMIN_EMAILS \
  --value "your-admin@email.com" --type String --region ap-southeast-1
```

---------------------------------------------------------------
Everything checks out for Phase 1:

  === VPC ===
  vpc-0953d095418f1950f      available

  === Subnets ===
  rktb-private-1a    subnet-0d45a0f978e9960e2        available
  rktb-private-1b    subnet-02b203de9836c46f6        available
  rktb-public-1a     subnet-0a9dc3d622aff9cf7        available

  === Security Groups ===
  rktb-rds-sg        sg-0eedc536da3a8f6fa
  rktb-ec2-sg        sg-0c2dc3e4f20452ddb

  === RDS ===
  available  rktb-postgres.cnwseow4y66l.ap-southeast-1.rds.amazonaws.com
  sg-0eedc536da3a8f6fa

  === EC2 ===
  i-08477110ddb42c54d        running 13.228.63.192   arn:aws:iam::273130558025:instance-profile/rktb-ec2-role

  === IAM Role ===
  rktb-ec2-role

  === ACM Certificate ===
  ISSUED

  === S3 Bucket ===
  {
      "BucketArn": "arn:aws:s3:::rktb-frontend",
      "BucketRegion": "ap-southeast-1",
      "AccessPointAlias": false
  }
  rktb-frontend exists

  === ECR ===
  273130558025.dkr.ecr.ap-southeast-1.amazonaws.com/rktb-backend

  === Parameter Store ===
  Status: All 9 secrets stored 
  /rktb/prod/ADMIN_EMAILS, /rktb/prod/DATABASE_URL, /rktb/prod/DEEPSEEK_API_KEY, 
  /rktb/prod/FRONTEND_URL, /rktb/prod/GEMINI_API_KEY, /rktb/prod/ORIGIN_SECRET, 
  /rktb/prod/REDIS_PASSWORD, /rktb/prod/S3_REFERER_SECRET, /rktb/prod/SECRET_KEY
  
  === Cloudflare DNS ===
  Status: origin-api.rkteambuilder.com → EC2 IP (configured manually)
  
  === Cloudflare DNS ===
  Status: ACM validation CNAME (configured manually)


---

## Phase 2: Docker Configuration (Files to Create in Repo)

```
  Phase 2 creates 4 files in your repo. No AWS resources are created here —
  these files are used later by Phase 3 (EC2 setup) and Phase 5 (CI/CD).

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Your Git Repository                                                │
  │                                                                     │
  │  backend/Dockerfile          .dockerignore                          │
  │  ─────────────────────       ────────────                           │
  │  Recipe for building the     Tells Docker what to SKIP              │
  │  Docker image:               when building the image:               │
  │                              ├── .git/                              │
  │  FROM python:3.10-slim       ├── .github/                           │
  │  RUN apt-get install gcc     ├── frontend/      (not needed)        │
  │      libpq-dev               ├── *.md           (not needed)        │
  │  COPY requirements.txt       ├── .env / .env.*  (secrets!)          │
  │  RUN pip install -r ...      ├── backend/tests/ (not needed)        │
  │  COPY backend/ backend/      └── venv/ / .venv/ (reinstalled fresh) │
  │  EXPOSE 8000                                                        │
  │  CMD uvicorn backend.main    Keeps image small, no secrets baked in │
  │      --host 0.0.0.0          ─────────────────────────────────────  │
  │      --port 8000             Why 0.0.0.0 in CMD?                    │
  │      --workers 2             Inside Docker, binding to 127.0.0.1    │
  │                              would only be reachable from within    │
  │                              the container. 0.0.0.0 lets Docker     │
  │                              forward traffic in from the host.      │
  │                              docker-compose.prod.yml then maps it   │
  │                              to 127.0.0.1:8000 on EC2 (Nginx only)  │
  │                                                                     │
  │  docker-compose.prod.yml              docker-compose.yml            │
  │  ───────────────────────              ──────────────────            │
  │  Used on EC2 by deploy.sh             Local dev only.               │
  │  Defines two containers:             Mirrors prod structure but     │
  │                                       uses local .env file.         │
  │  backend:                            Not used in production at all. │
  │    image: <ECR>:${IMAGE_TAG}                                        │
  │    ports: 127.0.0.1:8000:8000                                       │
  │    env: DATABASE_URL, SECRET_KEY                                    │
  │         DEEPSEEK_API_KEY, ...                                       │
  │         (injected by deploy.sh                                      │
  │          from Parameter Store)                                      │
  │    depends_on: redis                                                │
  │                                                                     │
  │  redis:                                                             │
  │    image: redis:7-alpine                                            │
  │    command: redis-server                                            │
  │             --requirepass ${REDIS_PASSWORD}                         │
  │    ports: 127.0.0.1:6379:6379 (not exposed externally)              │
  └─────────────────────────────────────────────────────────────────────┘

  ──────────────────────────────────────────────────────────────────────

  How Phase 2 files connect to other phases:

  Dockerfile  ──────────────────────────────────► Phase 5 (GitHub Actions)
                                                   docker build -f backend/Dockerfile
                                                   docker push → ECR (Phase 1.9)
                                                        │
                                                        ▼
  .dockerignore ──────────────────────────────────► (read automatically during
                                                    docker build — keeps image
                                                    lean, no secrets included)
                                                        │
                                                        ▼
  docker-compose.prod.yml ──────────────────────► Phase 3 (deploy.sh on EC2)
                                                   GitHub Actions copies it to S3
                                                   deploy.sh downloads it from S3
                                                   docker compose -f docker-compose.prod.yml up
                                                        │
                                                        ▼
                                                   Containers run with secrets
                                                   from Parameter Store (Phase 1.11)

  docker-compose.yml ────────────────────────────► Local development only
                                                   (npm run dev / local testing)

  ──────────────────────────────────────────────────────────────────────

  Why does docker-compose.prod.yml come from S3 during deploy?

  GitHub Actions SSM command can only send a short shell command to EC2.
  The docker-compose.prod.yml file is too large to embed in a command.

  Solution:
  ① GitHub Actions uploads docker-compose.prod.yml → S3 (rktb-frontend/deploy/)
  ② SSM command tells EC2: "download it from S3, then run deploy.sh"
  ③ EC2 IAM role (1.7) has s3:GetObject on rktb-frontend/deploy/* — so it can

  This means EC2 always runs the LATEST docker-compose.prod.yml from the repo,
  not a stale version that was manually copied there earlier.
```

### 2.1 Backend Dockerfile

Create **`backend/Dockerfile`**:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for psycopg2 and general build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy entire project (needed because backend imports use "backend." prefix)
COPY backend/ backend/

# Expose port
EXPOSE 8000

# Run FastAPI - bind to 0.0.0.0 inside container (Docker networking isolates it)
# docker-compose.prod.yml maps this to 127.0.0.1:8000 on the host
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### 2.2 .dockerignore

Create **`.dockerignore`** at project root:

```
.git
.github
frontend/
*.md
*.pyc
__pycache__
.env
.env.*
backend/tests/
venv/
.venv/
.mypy_cache/
.pytest_cache/
```

### 2.3 Production Docker Compose

Create **`docker-compose.prod.yml`** at project root:

```yaml
services:
  backend:
    image: ${ECR_URI}:${IMAGE_TAG:-latest}
    restart: always
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=${DATABASE_URL}
      - SECRET_KEY=${SECRET_KEY}
      - LLM_PROVIDER=deepseek
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      # Cookie settings for path-based routing (same domain for frontend + API)
      # COOKIE_DOMAIN not set = defaults to exact origin (rkteambuilder.com), correct for same-site
      - COOKIE_SAMESITE=lax
      - COOKIE_SECURE=true
      - FRONTEND_URL=${FRONTEND_URL}  # CRITICAL: Used for email links, must be public URL
      - ALLOWED_ORIGINS=${FRONTEND_URL}
      - RATE_LIMIT_ENABLED=true
      - ANALYSIS_RATE_LIMIT=1/2minutes
      # NOTE: Backend rate limiter MUST extract client IP from CloudFront-Viewer-Address header
      # (not from REMOTE_ADDR which will be CloudFront's IP). See backend/rate_limiter.py.
      - SMTP_HOST=${SMTP_HOST:-}
      - SMTP_PORT=${SMTP_PORT:-587}
      - SMTP_USER=${SMTP_USER:-}
      - SMTP_PASSWORD=${SMTP_PASSWORD:-}
      - SMTP_FROM_EMAIL=noreply@rkteambuilder.com
      - SMTP_FROM_NAME=RK Team Builder
      - ADMIN_EMAILS=${ADMIN_EMAILS:-}
    depends_on:
      redis:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    restart: always
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --bind 0.0.0.0
      --save 900 1
      --save 300 10
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  redis-data:
```

### 2.4 Local Development Docker Compose (Optional)

Create **`docker-compose.yml`** at project root:

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - backend/.env
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
      - db

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: roco_kingdom
      POSTGRES_USER: rktb_admin
      POSTGRES_PASSWORD: localdev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

## Phase 3: EC2 Server Setup

```
  What Phase 3 builds — software stack inside EC2:

  ┌────────────────────────────────────────────────────────────┐
  │  EC2 t3.micro  (13.228.63.192)                             │
  │                                                            │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │ Nginx  (port 80)                          [3.2]     │   │
  │  │ • reverse proxy to FastAPI                          │   │
  │  │ • verifies X-Origin-Verify header                   │   │
  │  │ • passes real client IP via CloudFront-Viewer-      │   │
  │  │   Address header to FastAPI for rate limiting       │   │
  │  └───────────────────────┬─────────────────────────────┘   │
  │                          │ proxy_pass 127.0.0.1:8000       │
  │  ┌───────────────────────▼─────────────────────────────┐   │
  │  │ Docker Compose                            [3.3]     │   │
  │  │                                                     │   │
  │  │  ┌──────────────────────┐  ┌───────────────────┐    │   │
  │  │  │ FastAPI :8000        │  │ Redis :6379       │    │   │
  │  │  │ (rktb-backend image  │  │ (redis:7-alpine   │    │   │
  │  │  │  from ECR)           │  │  password-        │    │   │
  │  │  │                      │  │  protected)       │    │   │
  │  │  │ reads env vars from  │  │                   │    │   │
  │  │  │ deploy.sh (secrets   │  │ used for LLM      │    │   │
  │  │  │ from Parameter Store)│  │ response cache    │    │   │
  │  │  └──────────────────────┘  └───────────────────┘    │   │
  │  └─────────────────────────────────────────────────────┘   │
  │                                                            │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │ SSM Agent                                 [3.1]     │   │
  │  │ • receives deploy commands from GitHub Actions      │   │
  │  │ • no SSH or open port needed                        │   │
  │  │ • uses EC2 IAM role (1.7) to authenticate to AWS    │   │
  │  └─────────────────────────────────────────────────────┘   │
  │                                                            │
  │  ┌─────────────────────────────────────────────────────┐   │
  │  │ AWS CLI + deploy.sh                       [3.3]     │   │
  │  │ • fetches secrets from Parameter Store (1.11)       │   │
  │  │ • logs into ECR (1.9) to pull Docker images         │   │
  │  │ • runs Alembic migrations against RDS (1.6)         │   │
  │  │ • starts containers via docker-compose.prod.yml     │   │
  │  └─────────────────────────────────────────────────────┘   │
  └────────────────────────────────────────────────────────────┘

  ──────────────────────────────────────────────────────────────

  3.1 — What each installed piece does and connects to:

  ┌──────────────┬────────────────────────────────────────────────┐
  │ Software     │ Connects to / Why                              │
  ├──────────────┼────────────────────────────────────────────────┤
  │ Docker       │ Pulls images from ECR (1.9) via IAM role (1.7) │
  │              │ Runs FastAPI + Redis as isolated containers    │
  ├──────────────┼────────────────────────────────────────────────┤
  │ Nginx        │ Port 80 open to CloudFront IPs (EC2 SG, 1.5)   │
  │              │ Checks ORIGIN_SECRET from Parameter Store(1.11)│
  │              │ Proxies valid requests to FastAPI :8000        │
  ├──────────────┼────────────────────────────────────────────────┤
  │ SSM Agent    │ EC2 IAM role (1.7) has AmazonSSMManagedInstance│
  │              │ CorePolicy → AWS SSM can send shell commands   │
  │              │ to this EC2 without any open SSH port          │
  ├──────────────┼────────────────────────────────────────────────┤
  │ AWS CLI      │ Uses EC2 IAM role (1.7) automatically — no     │
  │              │ credentials stored on disk. Can read Parameter │
  │              │ Store, push/pull ECR, call STS                 │
  └──────────────┴────────────────────────────────────────────────┘

  ──────────────────────────────────────────────────────────────

  3.2 — Nginx: two-layer security for the EC2 origin

  Incoming request to port 80:

  Layer 1 — Security Group (1.5):
  ┌──────────────────────────────────────────────────────────┐
  │ Only AWS CloudFront IP ranges are allowed on port 80     │
  │ Direct browser/attacker → EC2:80  =  DROPPED at network  │
  └────────────────────────────┬─────────────────────────────┘
                               │ (only CloudFront gets through)
                               ▼
  Layer 2 — Nginx origin secret check:
  ┌──────────────────────────────────────────────────────────┐
  │ CloudFront adds header: X-Origin-Verify: <ORIGIN_SECRET> │
  │                                                          │
  │ Nginx checks: does $http_x_origin_verify match?          │
  │   No  → return 403 (attacker spoofing CloudFront IPs)    │
  │   Yes → proxy_pass to 127.0.0.1:8000                     │
  └────────────────────────────┬─────────────────────────────┘
                               │ only YOUR CloudFront can pass both layers
                               ▼
  FastAPI receives the request with these headers:
  ├── Host                       (original domain)
  ├── X-Forwarded-Proto: https   (so FastAPI knows it's HTTPS)
  ├── X-Real-IP / X-Forwarded-For (CloudFront's IP — not useful)
  └── CloudFront-Viewer-Address   (REAL user IP — used for rate limiting)

  Why CloudFront-Viewer-Address matters:
    Without it, all requests look like they come from CloudFront's IP.
    Your rate limiter would see ONE IP for ALL users → rate limiting breaks.
    CloudFront-Viewer-Address carries the actual end-user IP through.

  ──────────────────────────────────────────────────────────────

  3.3 — deploy.sh: what runs every time you deploy

  GitHub Actions SSM command → EC2 runs deploy.sh <git-sha>
       │
       ▼
  ① Fetch secrets from Parameter Store (using IAM role — no creds on disk)
       ├── DATABASE_URL, SECRET_KEY, DEEPSEEK_API_KEY
       ├── REDIS_PASSWORD, FRONTEND_URL, ADMIN_EMAILS
       └── SMTP_* (optional, skipped if not set yet)
       │
       ▼
  ② ECR login (using IAM role)
       aws ecr get-login-password | docker login
       │
       ▼
  ③ Pull new Docker image from ECR
       docker pull <ECR_URI>:<git-sha>
       │
       ▼
  ④ Start Redis first (other containers depend on it)
       docker compose up -d redis
       sleep 3
       │
       ▼
  ⑤ Run Alembic migrations (schema changes before new code starts)
       docker run --rm --network host \
         -e DATABASE_URL \
         <image> python -m alembic upgrade head
       │
       ▼
  ⑥ Start/restart all containers with new image
       docker compose up -d --remove-orphans
       │
       ▼
  ⑦ Health check
       docker compose ps  (shows running containers)

  Resources used by deploy.sh:
  ├── Parameter Store (1.11) → secrets injected as env vars
  ├── ECR (1.9)              → Docker image source
  ├── RDS (1.6)              → migrations target (private subnet)
  ├── docker-compose.prod.yml (Phase 2) → container config
  └── IAM role (1.7)         → permission to do all of the above

  ──────────────────────────────────────────────────────────────

  Big picture after Phase 3:

  EC2 is now a fully configured server:
  ├── Nginx        running, origin-verified, proxying to :8000
  ├── Docker       installed, authenticated to ECR
  ├── SSM Agent    running, ready for remote deploy commands
  ├── AWS CLI      working via IAM role (no stored credentials)
  └── deploy.sh    ready at /home/ubuntu/rktb/deploy.sh

  But no containers are running yet — FastAPI and Redis start
  in Phase 7 (first deployment) when deploy.sh runs for the
  first time via GitHub Actions (Phase 5).
```

### 3.1 SSH In and Install Docker + Nginx

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Install Nginx + AWS CLI
sudo apt install nginx awscli -y

# Install SSM Agent (enables remote commands from GitHub Actions without SSH)
# Ubuntu 22.04 AMIs often have it pre-installed. Check first:
if systemctl status amazon-ssm-agent &>/dev/null || systemctl status snap.amazon-ssm-agent.amazon-ssm-agent &>/dev/null; then
  echo "SSM Agent already installed and running"
else
  echo "Installing SSM Agent..."
  # Option 1: Via snap (simpler)
  sudo snap install amazon-ssm-agent --classic
  sudo systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent.service
  sudo systemctl start snap.amazon-ssm-agent.amazon-ssm-agent.service

  # Option 2: Via .deb (alternative if snap doesn't work)
  # wget https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/debian_amd64/amazon-ssm-agent.deb
  # sudo dpkg -i amazon-ssm-agent.deb
  # sudo systemctl enable amazon-ssm-agent
  # sudo systemctl start amazon-ssm-agent
fi

# Verify SSM Agent is running
systemctl status amazon-ssm-agent 2>/dev/null || systemctl status snap.amazon-ssm-agent.amazon-ssm-agent

# IMPORTANT: Log out and back in for docker group to take effect
exit
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192

# Verify installations
docker --version
docker compose version
nginx -v
aws sts get-caller-identity  # Should work via instance role
```

### 3.2 Configure Nginx

Fetch the origin secret from Parameter Store:
```bash
ORIGIN_SECRET=$(aws ssm get-parameter --name /rktb/prod/ORIGIN_SECRET \
  --with-decryption --region ap-southeast-1 --query Parameter.Value --output text)
echo "Origin secret: $ORIGIN_SECRET"
```

Create `/etc/nginx/sites-available/rktb`:

```bash
sudo tee /etc/nginx/sites-available/rktb << 'NGINX_CONF'
server {
    listen 80;
    server_name origin-api.rkteambuilder.com;

    # Verify requests come from CloudFront (not direct access)
    # This check is CRITICAL for trusting CloudFront-Viewer-Address header.
    # Without it, attackers could spoof the viewer IP by sending direct requests.
    set $origin_secret "REPLACE_WITH_ORIGIN_SECRET";

    if ($http_x_origin_verify != $origin_secret) {
        return 403;
    }

    # SECURITY: CloudFront-Viewer-Address is trustworthy ONLY because we verified
    # the X-Origin-Verify header above. Direct requests (which could spoof this
    # header) are rejected with 403.

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    location /api/ {
        # Strip /api prefix before forwarding to FastAPI
        # e.g. /api/teams → /teams, /api/auth/login → /auth/login
        rewrite ^/api(/.*)$ $1 break;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        # IMPORTANT: CloudFront-Viewer-Address contains the REAL client IP
        # $remote_addr will be CloudFront's IP, which is useless for rate limiting
        # Backend MUST use CloudFront-Viewer-Address for rate limiting and logging
        proxy_set_header CloudFront-Viewer-Address $http_cloudfront_viewer_address;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # DeepSeek analysis takes ~86s; set well above that
        proxy_read_timeout 210s;
        proxy_connect_timeout 10s;
    }
}
NGINX_CONF
```

Then replace the placeholder and enable:
```bash
# Replace placeholder with actual secret
sudo sed -i "s/REPLACE_WITH_ORIGIN_SECRET/$ORIGIN_SECRET/" /etc/nginx/sites-available/rktb

# Enable site, disable default
sudo ln -sf /etc/nginx/sites-available/rktb /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

### 3.3 Create Deploy Script

Create `/home/ubuntu/rktb/deploy.sh`:

```bash
mkdir -p /home/ubuntu/rktb
cat > /home/ubuntu/rktb/deploy.sh << 'DEPLOY_SCRIPT'
#!/bin/bash
set -e

REGION="ap-southeast-1"
IMAGE_TAG="${1:-latest}"

echo "=== Fetching configuration ==="
export DATABASE_URL=$(aws ssm get-parameter --name /rktb/prod/DATABASE_URL --with-decryption --region $REGION --query Parameter.Value --output text)
export SECRET_KEY=$(aws ssm get-parameter --name /rktb/prod/SECRET_KEY --with-decryption --region $REGION --query Parameter.Value --output text)
export DEEPSEEK_API_KEY=$(aws ssm get-parameter --name /rktb/prod/DEEPSEEK_API_KEY --with-decryption --region $REGION --query Parameter.Value --output text)
export REDIS_PASSWORD=$(aws ssm get-parameter --name /rktb/prod/REDIS_PASSWORD --with-decryption --region $REGION --query Parameter.Value --output text)
export FRONTEND_URL=$(aws ssm get-parameter --name /rktb/prod/FRONTEND_URL --region $REGION --query Parameter.Value --output text)
export ADMIN_EMAILS=$(aws ssm get-parameter --name /rktb/prod/ADMIN_EMAILS --region $REGION --query Parameter.Value --output text)

# SMTP (optional, may not exist yet)
export SMTP_HOST=$(aws ssm get-parameter --name /rktb/prod/SMTP_HOST --region $REGION --query Parameter.Value --output text 2>/dev/null || echo "")
export SMTP_PORT="587"
export SMTP_USER=$(aws ssm get-parameter --name /rktb/prod/SMTP_USER --with-decryption --region $REGION --query Parameter.Value --output text 2>/dev/null || echo "")
export SMTP_PASSWORD=$(aws ssm get-parameter --name /rktb/prod/SMTP_PASSWORD --with-decryption --region $REGION --query Parameter.Value --output text 2>/dev/null || echo "")

# ECR login
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/rktb-backend"
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "=== Pulling image: ${ECR_URI}:${IMAGE_TAG} ==="
docker pull "${ECR_URI}:${IMAGE_TAG}"
export IMAGE_TAG

echo "=== Starting services (creates network and starts Redis first) ==="
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml up -d redis
sleep 3  # Wait for Redis to be ready

echo "=== Running database migrations ==="
# Alembic migrations only need DATABASE_URL.
# Using --network host to connect directly to RDS endpoint.
# Minimal env vars to reduce coupling (migrations shouldn't need runtime secrets).
docker run --rm --network host \
  -e DATABASE_URL="$DATABASE_URL" \
  "${ECR_URI}:${IMAGE_TAG}" \
  python -m alembic -c backend/alembic.ini upgrade head

echo "=== Starting services ==="
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml up -d --remove-orphans

echo "=== Waiting for health check ==="
sleep 5
docker compose -f docker-compose.prod.yml ps

echo "=== Deployment complete ==="
DEPLOY_SCRIPT

chmod +x /home/ubuntu/rktb/deploy.sh
```

---

## Phase 4: CloudFront Distribution

```
  What Phase 4 builds:

  User types https://rkteambuilder.com
       │
       ▼
  ┌──────────────────────────────────────────────────────────┐
  │  Cloudflare DNS (4.4)                                    │
  │  rkteambuilder.com CNAME → d12qs0zigkefaz.cloudfront.net │
  │  (DNS only, grey cloud — no Cloudflare proxying)         │
  └────────────────────────┬─────────────────────────────────┘
                           │ resolves to CloudFront edge node
                           ▼
  ┌──────────────────────────────────────────────────────────┐
  │  CloudFront Distribution (4.1)                           │
  │  domain: d12qs0zigkefaz.cloudfront.net                   │
  │  cert:   ACM rkteambuilder.com (from 1.10, us-east-1)    │
  │  default root object: index.html                         │
  │  security headers: SecurityHeadersPolicy (all behaviors) │
  │                                                          │
  │  Behavior matching (2 rules, first match wins):          │
  │                                                          │
  │  /api/*  (ALL HTTP methods)                              │
  │  CachingDisabled                          ──────────────►│──► EC2 origin
  │  AllViewerExceptHostHeader                │    origin-api.
  │  Nginx rewrites /api/foo → /foo           │    rkteambuilder
  │  before FastAPI sees the request          │    .com
  │                                           │    (port 80,
  │                                           │    HTTP only)
  │                                                          │
  │  /* (default, everything else)            ──────────────►│──► S3 origin
  │  (GET, HEAD only, CachingOptimized)                      │    rktb-frontend
  └──────────────────────────────────────────────────────────┘    .s3.amazonaws
                           │                                       .com
          ┌────────────────┴────────────────┐
          │                                 │
          ▼                                 ▼
  ┌───────────────────┐           ┌───────────────────┐
  │  EC2 (API)        │           │  S3 (Frontend)    │
  │                   │           │                   │
  │  CloudFront sends │           │  CloudFront sends │
  │  X-Origin-Verify  │           │  Referer header   │
  │  header with      │           │  with secret      │
  │  secret           │           │  (from 1.9)       │
  │  (from 1.11)      │           │                   │
  │                   │           │  S3 bucket policy │
  │  Nginx checks it: │           │  (4.2) rejects    │
  │  wrong → 403      │           │  requests without │
  │  correct → proxy  │           │  correct Referer  │
  │  to FastAPI :8000 │           │                   │
  └───────────────────┘           └───────────────────┘

  ──────────────────────────────────────────────────────────

  4.1 — Two origins, two secrets

  Origin 1: EC2 API                  Origin 2: S3 Frontend
  ┌──────────────────────┐           ┌──────────────────────┐
  │ origin-api.          │           │ rktb-frontend.s3.    │
  │ rkteambuilder.com    │           │ amazonaws.com        │
  │                      │           │                      │
  │ CloudFront adds:     │           │ CloudFront adds:     │
  │ X-Origin-Verify:     │           │ Referer:             │
  │ <ORIGIN_SECRET>      │           │ <S3_REFERER_SECRET>  │
  │ (stored in Parameter │           │ (stored in Parameter │
  │  Store 1.11)         │           │  Store 1.11)         │
  │                      │           │                      │
  │ Nginx verifies it    │           │ S3 bucket policy     │
  │ (Phase 3.2)          │           │ verifies it (4.2)    │
  └──────────────────────┘           └──────────────────────┘

  Both secrets prevent users from bypassing CloudFront
  and hitting your origins directly.

  ──────────────────────────────────────────────────────────

  4.1 — Cache & Origin Request Policies (why each one matters)

  All API behaviors:
  ┌─────────────────────────────────────────────────────────┐
  │ Cache policy: CachingDisabled                           │
  │   → CloudFront never stores API responses               │
  │   → Every request goes through to EC2                   │
  │   → Critical: auth cookies, user data must be fresh     │
  │                                                         │
  │ Origin request policy: AllViewerExceptHostHeader        │
  │   → Forwards cookies (JWT auth cookies)                 │
  │   → Forwards Authorization header                       │
  │   → Forwards query strings (?limit=10&offset=0)         │
  │   → Skips Host header (prevents EC2 confusion)          │
  │                                                         │
  │ Response headers policy: SecurityHeadersPolicy          │
  │   → Adds HSTS (force HTTPS even if user types http://)  │
  │   → X-Frame-Options: DENY (no iframe embedding)         │
  │   → X-Content-Type-Options: nosniff                     │
  │   → Referrer-Policy (limits URL leakage)                │
  └─────────────────────────────────────────────────────────┘

  S3 default behavior:
  ┌─────────────────────────────────────────────────────────┐
  │ Cache policy: CachingOptimized                          │
  │   → CloudFront caches static files at edge nodes        │
  │   → Users in Tokyo/HK get files from nearby edge,       │
  │     not Singapore S3 → faster loads                     │
  │   → Cache cleared on deploy via CloudFront invalidation │
  └─────────────────────────────────────────────────────────┘

  ──────────────────────────────────────────────────────────

  4.4 — Why Cloudflare DNS only, not proxied

  DNS only (grey cloud) ✅          Proxied (orange cloud) ❌
  User → CloudFront → EC2/S3        User → Cloudflare → CloudFront → EC2/S3

  ✅ CloudFront sees real user IP    ❌ CloudFront sees Cloudflare IP
  ✅ Rate limiting works correctly   ❌ Rate limiting broken (all same IP)
  ✅ CloudFront SSL cert used        ❌ SSL chain gets complicated
  ✅ One CDN layer (faster)          ❌ Two CDN layers (slower, redundant)
```

This is best done via the **AWS Console** due to the number of settings.

### 4.1 Create CloudFront Distribution

**AWS Console → CloudFront → Create Distribution**

**Origins:**

| # | Origin Domain | Protocol Policy | Custom Headers |
|---|--------------|-----------------|----------------|
| 1 | `rktb-frontend.s3-website-ap-southeast-1.amazonaws.com` | HTTP only | `Referer`: `YOUR_S3_REFERER_SECRET` |
| 2 | `origin-api.rkteambuilder.com` | HTTP only (port 80) | `X-Origin-Verify`: `YOUR_ORIGIN_SECRET` |

**Important for Origin 1 (S3 Website):**
- Use the **website endpoint** (`s3-website-ap-southeast-1`), NOT the REST endpoint (`s3.ap-southeast-1`)
- Do NOT use OAC - we're using referer header protection instead
- Origin Protocol Policy: **HTTP only** (S3 website hosting doesn't support HTTPS)
- Add custom header `Referer` with the secret from Parameter Store

**For Origin 2 (EC2 API):**
- Origin Protocol Policy: **HTTP only**
- Add custom header `X-Origin-Verify` with the secret from Parameter Store
- **Origin timeout settings** (click "Additional settings"):
  - Connection timeout: **10 seconds** (default)
  - Response timeout: **120 seconds** (LLM analysis typically takes ~90s, 120s provides safe buffer)
  - Keep-alive timeout: **5 seconds** (default)

> **Note:** CloudFront allows response timeout up to 120 seconds without AWS Support approval. 120 seconds is chosen to provide comfortable buffer for DeepSeek LLM analysis calls (~90s typical).

**Cache Behaviors (order matters - specific paths first, default last):**

| Priority | Path Pattern | Origin | Viewer Protocol | Allowed Methods | Cache Policy | Origin Request Policy |
|----------|-------------|--------|-----------------|-----------------|-------------|----------------------|
| 1 | `/api/*` | EC2-API | Redirect HTTPS | ALL | CachingDisabled | AllViewerExceptHostHeader |
| Default | `*` | S3-Frontend | Redirect HTTPS | GET, HEAD | CachingOptimized | None (not needed) |

**Why only two rules?** All API calls from the frontend use the `/api/` prefix (e.g., `GET /api/teams`, `POST /api/auth/login`). A single `/api/*` behavior routes them all to EC2. Everything else — including browser navigation to `/teams`, `/monsters`, `/build` — falls through to the S3 default and gets `index.html`, allowing React Router to handle the URL client-side.

**Why not individual rules per API path?** The old approach had 19 separate CloudFront behaviors (one per API path). The fatal flaw: browser navigation and API calls shared the same URL namespace. For example, `GET /teams` could be either a React Router page load (should return `index.html`) or an API data fetch (should return JSON). CloudFront can't distinguish them, so refreshing `/teams` in the browser returned raw JSON instead of the app. The `/api/` prefix eliminates this namespace collision.

**Adding new API routes:** Just add the endpoint in `backend/main.py`. No CloudFront changes needed — the single `/api/*` behavior covers all current and future API routes automatically.

**Note on Origin Request Policy:** "AllViewerExceptHostHeader" forwards all headers, cookies, and query strings to EC2. This is required for auth cookies and Authorization headers to reach FastAPI. The S3 default behavior needs no origin request policy.

**Distribution Settings:**
- Alternate domain names (CNAMEs): `rkteambuilder.com`
- Custom SSL certificate: select the ACM cert from us-east-1
- Default root object: `index.html`
- Price class: "Use only North America, Europe, Asia, Middle East, and Africa" (cheaper than all edge locations)

**Custom Error Responses:**
- **DO NOT configure any custom error responses!**
- S3 website hosting handles SPA routing via its error document feature
- If you add 403/404 → index.html here, it would also intercept API errors (breaking the frontend)

**Response Headers Policy:**
Create a custom policy or use the managed "SecurityHeadersPolicy" with:
- Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: strict-origin-when-cross-origin

**Note:** Nginx also sets X-Content-Type-Options and X-Frame-Options. CloudFront will add these headers if missing, and duplicates are harmless. For cleaner responses, you can remove the Nginx headers and rely solely on CloudFront's response headers policy.

### 4.2 Verify S3 Bucket Policy

The S3 bucket policy was already configured in step 1.9 with referer header protection. No additional configuration needed.

To verify the policy is correct:
```bash
aws s3api get-bucket-policy --bucket rktb-frontend --query Policy --output text
```

The policy should show `aws:Referer` condition matching your secret.

### 4.3 Edge-Level Abuse Protection (Optional but Recommended)

For expensive endpoints like `/analysis/*` (LLM calls), consider adding AWS WAF to block abuse at the edge before requests reach EC2:

**AWS Console → WAF & Shield → Create Web ACL:**

1. **Scope:** CloudFront distributions
2. **Associated resources:** Select your CloudFront distribution
3. **Add rules:**

**Rule 1: Rate limit analysis endpoint**
- Rule type: Rate-based rule
- Rate limit: 10 requests per 5 minutes (adjust based on your tier limits)
- Scope: Only requests matching `/analysis/*` path
- Action: Block

**Rule 2: Geographic restriction (optional)**
- If your users are primarily in specific regions, block traffic from others

**Rule 3: AWS Managed Rules (optional)**
- Add "AWSManagedRulesCommonRuleSet" for basic protection against common attacks

**Cost:** ~$5/month base + $0.60 per million requests. Worth it for LLM cost protection.

> **Why edge-level protection matters:**
> - Backend rate limiting still processes the request (EC2 CPU, network)
> - With WAF, blocked requests never reach EC2 at all
> - LLM costs are the biggest risk - even rate-limited requests that timeout can trigger partial LLM usage

### 4.4 Create DNS Record for Root Domain (in Cloudflare)

Point `rkteambuilder.com` to CloudFront:

Go to **Cloudflare Dashboard → rkteambuilder.com → DNS**

**Add CNAME record for root domain:**
| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| CNAME | `@` | `dXXXXXXXXXX.cloudfront.net` | DNS only (grey cloud) | Auto |

Replace `dXXXXXXXXXX.cloudfront.net` with your actual CloudFront distribution domain (visible in CloudFront console → Distribution → Domain name).

**Important:** The root domain MUST be **DNS only (grey cloud)**, not proxied through Cloudflare. If you proxy through Cloudflare, the connection would be:

`User → Cloudflare → CloudFront → EC2/S3`

This adds latency and can cause issues with:
- CloudFront-Viewer-Address header (IP detection)
- SSL certificate chain
- Cache-related headers

By setting it to DNS only, the connection is:

`User → CloudFront → EC2/S3` (direct, faster, simpler)

**Optional: Add www redirect**
| Type | Name | Content | Proxy |
|------|------|---------|-------|
| CNAME | `www` | `dXXXXXXXXXX.cloudfront.net` | DNS only |

Then add `www.rkteambuilder.com` to CloudFront's alternate domain names and update the ACM certificate to include it (or use the wildcard cert).

---

## Phase 5: GitHub Actions CI/CD

```
  5.1 — OIDC: How GitHub gets AWS credentials (no stored keys)

  Old way (bad):                        Phase 5 way (OIDC):
  ┌─────────────────┐                   ┌─────────────────┐
  │ GitHub Secrets  │                   │ GitHub Actions  │
  │ AWS_ACCESS_KEY  │                   │ runner          │
  │ AWS_SECRET_KEY  │                   └────────┬────────┘
  │ (permanent,     │                            │ "I am GitHub, running
  │  if leaked =    │                            │  repo HaotingShen/roco-
  │  catastrophe)   │                            │  kingdom-team-builder"
  └─────────────────┘                            ▼
                                        ┌─────────────────┐
                                        │ AWS IAM (OIDC)  │
                                        │ Identity        │
                                        │ Provider        │
                                        │ (registered in  │
                                        │  5.1 console)   │
                                        └────────┬────────┘
                                                 │ verifies identity,
                                                 │ checks trust policy:
                                                 │ "is it the right repo?"
                                                 ▼
                                        ┌─────────────────┐
                                        │ github-actions- │
                                        │ rktb IAM Role   │
                                        │ (created 5.1)   │
                                        │                 │
                                        │ grants 15-min   │
                                        │ temp credentials│
                                        └────────┬────────┘
                                                 │ can now access:
                                                 ├── ECR (push images)
                                                 ├── S3 (upload frontend)
                                                 ├── CloudFront (invalidate)
                                                 └── SSM (send deploy cmd to EC2)

  ──────────────────────────────────────────────────────────────────

  5.2 — GitHub Secrets (what the workflow reads at runtime)

  GitHub repo → Settings → Secrets:

  AWS_ROLE_ARN               → which IAM role to assume (from 5.1)
  ECR_REPOSITORY             → where to push Docker image (from 1.9)
  S3_BUCKET                  → where to upload frontend (from 1.9)
  CLOUDFRONT_DISTRIBUTION_ID → which distribution to invalidate (from 4.1)
  EC2_INSTANCE_ID            → which EC2 to send SSM command to (from 1.8)

  ──────────────────────────────────────────────────────────────────

  5.3 — deploy.yml: What happens on every git push to main

  git push to main
       │
       ▼
  GitHub Actions triggers 4 parallel jobs:

  ┌─────────────────────────┐    ┌─────────────────────────┐
  │    test-backend         │    │    test-frontend        │
  │                         │    │                         │
  │  spins up:              │    │  runs:                  │
  │  • postgres:16          │    │  • npm ci               │
  │  • redis:7-alpine       │    │  • npm run typecheck    │
  │                         │    │  • npm run lint         │
  │  runs: pytest -v        │    │                         │
  └────────────┬────────────┘    └────────────┬────────────┘
               │ must pass                    │ must pass
               ▼                              ▼
  ┌─────────────────────────┐    ┌─────────────────────────┐
  │    build-backend        │    │    deploy-frontend      │
  │                         │    │                         │
  │  OIDC → IAM role        │    │  OIDC → IAM role        │
  │  ECR login              │    │  npm run build          │
  │  docker build           │    │  (VITE_API_BASE_URL=    │
  │    -f backend/Dockerfile│    │   https://rkteambuilder │
  │  docker push to ECR     │    │   .com/api)             │
  │    :latest              │    │                         │
  │    :<git-sha>           │    │  s3 sync dist/ →        │
  │                         │    │   rktb-frontend         │
  │  Uses: ECR (1.9)        │    │                         │
  │        Dockerfile (2)   │    │  cloudfront invalidate  │
  └────────────┬────────────┘    │   "/*" (clears cache)   │
               │ must pass       │                         │
               ▼                 │  Uses: S3 (1.9)         │
  ┌─────────────────────────┐    │        CloudFront (4.1) │
  │    deploy-backend       │    └─────────────────────────┘
  │                         │
  │  OIDC → IAM role        │
  │                         │
  │  copies docker-compose  │
  │  .prod.yml → S3         │
  │                         │
  │  SSM send-command to EC2│
  │  → EC2 runs deploy.sh:  │
  │     • fetch secrets from│
  │       Parameter Store   │
  │     • pull new image    │
  │       from ECR          │
  │     • run migrations    │
  │     • restart containers│
  │                         │
  │  polls SSM until done   │
  │  (up to 5 min)          │
  │  fails CI if deploy     │
  │  fails on EC2           │
  │                         │
  │  Uses: SSM (1.7 role)   │
  │        ECR (1.9)        │
  │        deploy.sh (3.3)  │
  │        docker-compose   │
  │        .prod.yml (2)    │
  └─────────────────────────┘

  End result after every push:
  ├── Backend: new Docker image running on EC2 with zero-downtime swap
  ├── Frontend: new files in S3, CloudFront cache cleared worldwide
  └── Database: migrations applied automatically before containers start
```

### 5.1 Set Up OIDC (GitHub → AWS, no stored AWS keys)

> **Prerequisite:** Complete Phase 4 first to get the CloudFront distribution ID needed for the IAM policy below.

**AWS Console → IAM → Identity Providers → Add Provider:**
1. Provider type: OpenID Connect
2. Provider URL: `https://token.actions.githubusercontent.com`
3. Audience: `sts.amazonaws.com`
4. Click "Add provider"

**Create IAM Role for GitHub Actions:**

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Trust policy
# IMPORTANT: Replace YOUR_GITHUB_USERNAME with your actual GitHub username
cat > /tmp/gh-trust.json << ENDTRUST
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/roco-kingdom-team-builder:ref:refs/heads/main"
      }
    }
  }]
}
ENDTRUST

aws iam create-role --role-name github-actions-rktb \
  --assume-role-policy-document file:///tmp/gh-trust.json

# Permissions policy
# IMPORTANT: Replace these placeholders with actual values before running
DIST_ID="YOUR_CLOUDFRONT_DISTRIBUTION_ID"  # From Phase 4.1 (e.g., E1ABC2DEF3GHIJ)
EC2_INSTANCE_ID="YOUR_EC2_INSTANCE_ID"     # From Phase 1.8 (e.g., i-0abc123def456789)
cat > /tmp/gh-perms.json << ENDPERMS
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECR",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket", "s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::rktb-frontend",
        "arn:aws:s3:::rktb-frontend/*"
      ]
    },
    {
      "Sid": "CloudFront",
      "Effect": "Allow",
      "Action": "cloudfront:CreateInvalidation",
      "Resource": "arn:aws:cloudfront::${ACCOUNT_ID}:distribution/${DIST_ID}"
    },
    {
      "Sid": "SSMSendCommand",
      "Effect": "Allow",
      "Action": ["ssm:SendCommand"],
      "Resource": [
        "arn:aws:ssm:ap-southeast-1::document/AWS-RunShellScript",
        "arn:aws:ec2:ap-southeast-1:${ACCOUNT_ID}:instance/${EC2_INSTANCE_ID}"
      ]
    },
    {
      "Sid": "SSMGetCommandInvocation",
      "Effect": "Allow",
      "Action": ["ssm:GetCommandInvocation"],
      "Resource": "*"
    }
  ]
}
ENDPERMS

aws iam put-role-policy --role-name github-actions-rktb \
  --policy-name github-actions-perms --policy-document file:///tmp/gh-perms.json
```

> **Note on SSM permissions:** `ssm:GetCommandInvocation` requires `Resource: "*"` because it doesn't support resource-level permissions well. Scoping it to specific command/instance ARNs often causes "Access Denied" errors. `ssm:SendCommand` can be scoped to specific documents and instances.

### 5.2 Add GitHub Repository Secrets

Go to your GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret Name | Value | Notes |
|-------------|-------|-------|
| `AWS_ROLE_ARN` | `arn:aws:iam::ACCOUNT_ID:role/github-actions-rktb` | From step 5.1 |
| `ECR_REPOSITORY` | `rktb-backend` | ECR repo name |
| `S3_BUCKET` | `rktb-frontend` | S3 bucket name |
| `CLOUDFRONT_DISTRIBUTION_ID` | `EXXXXXXXXXX` | From CloudFront console |
| `EC2_INSTANCE_ID` | `i-xxxxxxxxxxxxxxxxx` | From step 1.8 (not the IP, the instance ID) |

> **Note:** No SSH key needed! We use AWS SSM instead of SSH for deployments. This is more secure (no keys stored in GitHub) and works regardless of security group rules.

### 5.3 Create GitHub Actions Workflow

Create **`.github/workflows/deploy.yml`**:

```yaml
name: Build & Deploy

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: ap-southeast-1

jobs:
  # ── Run Backend Tests ─────────────────────────────────
  test-backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_roco
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
          cache: pip
          cache-dependency-path: backend/requirements.txt

      - name: Install dependencies
        run: pip install -r backend/requirements.txt

      - name: Run pytest
        run: cd backend && pytest -v
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_roco
          REDIS_URL: redis://localhost:6379/0
          GEMINI_API_KEY: test-key-not-used-in-tests
          DEEPSEEK_API_KEY: test-key-not-used-in-tests
          SECRET_KEY: test-secret-key-minimum-thirty-two-characters-long
          ENVIRONMENT: testing

  # ── Run Frontend Checks ───────────────────────────────
  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - run: cd frontend && npm ci
      - run: cd frontend && npm run typecheck
      - run: cd frontend && npm run lint

  # ── Build & Push Backend Docker Image ─────────────────
  build-backend:
    needs: [test-backend]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.ecr-login.outputs.registry }}
          ECR_REPOSITORY: ${{ secrets.ECR_REPOSITORY }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG \
                        -t $ECR_REGISTRY/$ECR_REPOSITORY:latest \
                        -f backend/Dockerfile .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

  # ── Deploy Frontend to S3 + CloudFront ────────────────
  deploy-frontend:
    needs: [test-frontend]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Build frontend
        run: |
          cd frontend
          npm ci
          VITE_API_BASE_URL=https://rkteambuilder.com/api npm run build

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Deploy to S3
        run: aws s3 sync frontend/dist/ s3://${{ secrets.S3_BUCKET }}/ --delete

      - name: Invalidate CloudFront cache
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} \
            --paths "/*"

  # ── Deploy Backend to EC2 via SSM ─────────────────────
  # NOTE: We use SSM instead of SSH because:
  # 1. No SSH keys stored in GitHub secrets
  # 2. Works regardless of EC2 security group rules (no port 22 from GitHub IPs needed)
  # 3. Commands are audited in CloudTrail
  deploy-backend:
    needs: [build-backend]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Upload docker-compose to S3
        run: |
          aws s3 cp docker-compose.prod.yml s3://${{ secrets.S3_BUCKET }}/deploy/docker-compose.prod.yml

      - name: Deploy via SSM
        run: |
          # Send command to EC2 via SSM (no SSH needed)
          COMMAND_ID=$(aws ssm send-command \
            --instance-ids "${{ secrets.EC2_INSTANCE_ID }}" \
            --document-name "AWS-RunShellScript" \
            --parameters commands='["cd /home/ubuntu/rktb && aws s3 cp s3://${{ secrets.S3_BUCKET }}/deploy/docker-compose.prod.yml . && bash deploy.sh ${{ github.sha }}"]' \
            --timeout-seconds 300 \
            --query 'Command.CommandId' \
            --output text)

          echo "Command ID: $COMMAND_ID"

          # Poll for command completion (aws ssm wait command-executed doesn't exist)
          for i in {1..60}; do
            STATUS=$(aws ssm get-command-invocation \
              --command-id "$COMMAND_ID" \
              --instance-id "${{ secrets.EC2_INSTANCE_ID }}" \
              --query 'Status' --output text 2>/dev/null || echo "Pending")
            echo "Attempt $i: Status = $STATUS"
            if [[ "$STATUS" == "Success" || "$STATUS" == "Failed" || "$STATUS" == "Cancelled" || "$STATUS" == "TimedOut" ]]; then
              break
            fi
            sleep 5
          done

          # Get final command output
          aws ssm get-command-invocation \
            --command-id "$COMMAND_ID" \
            --instance-id "${{ secrets.EC2_INSTANCE_ID }}" \
            --query '[Status, StandardOutputContent, StandardErrorContent]' \
            --output text

          # Fail the job if command didn't succeed
          if [[ "$STATUS" != "Success" ]]; then
            echo "SSM command failed with status: $STATUS"
            exit 1
          fi
```

---

## Phase 6: AWS SES Email Setup

### 6.1 Verify Domain in SES

```bash
# Verify domain
aws sesv2 create-email-identity --email-identity rkteambuilder.com --region ap-southeast-1

# Get DKIM tokens
aws sesv2 get-email-identity --email-identity rkteambuilder.com --region ap-southeast-1 \
  --query 'DkimAttributes.Tokens'
```

The output will be 3 tokens like `["abc123...", "def456...", "ghi789..."]`.

**Add DKIM CNAME records in Cloudflare:**

Go to **Cloudflare Dashboard → rkteambuilder.com → DNS → Add record** (3 times):

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| CNAME | `TOKEN1._domainkey` | `TOKEN1.dkim.amazonses.com` | DNS only (grey cloud) |
| CNAME | `TOKEN2._domainkey` | `TOKEN2.dkim.amazonses.com` | DNS only (grey cloud) |
| CNAME | `TOKEN3._domainkey` | `TOKEN3.dkim.amazonses.com` | DNS only (grey cloud) |

Replace `TOKEN1`, `TOKEN2`, `TOKEN3` with your actual tokens from the AWS CLI output.

**Important:** DKIM records MUST be **DNS only (grey cloud)**, not proxied.

Wait a few minutes, then verify in AWS Console → SES → Identities → rkteambuilder.com → DKIM status should show "Verified".

### 6.2 Request SES Production Access

SES starts in sandbox mode (can only send to verified emails). Request production:

1. AWS Console → SES → Account Dashboard → Request Production Access
2. Use case: "Transactional emails - email verification and password reset for web application users"
3. Usually approved within 24 hours

### 6.3 Create SMTP Credentials

> ⚠️ **IMPORTANT: Email Link Generation**
>
> The backend generates email links (verification, password reset) using `FRONTEND_URL` from config, **NOT** the request Host header. This is critical because:
>
> - CloudFront uses `AllViewerExceptHostHeader` policy (doesn't forward viewer's Host)
> - The origin receives `origin-api.rkteambuilder.com` as Host, not `rkteambuilder.com`
> - If code used request Host, email links would point to the wrong domain
>
> **Rule:** All externally-facing URLs must use `FRONTEND_URL`. Never rely on request Host headers.
>
> The current backend (`email_service.py`) already follows this pattern correctly.

1. AWS Console → SES → SMTP Settings → Create SMTP Credentials
2. Note the SMTP username and password
3. Store in Parameter Store:

```bash
aws ssm put-parameter --name /rktb/prod/SMTP_HOST \
  --value "email-smtp.ap-southeast-1.amazonaws.com" \
  --type String --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/SMTP_USER \
  --value "SMTP_USERNAME_FROM_SES" \
  --type SecureString --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/SMTP_PASSWORD \
  --value "SMTP_PASSWORD_FROM_SES" \
  --type SecureString --region ap-southeast-1
```

Then redeploy backend to pick up the new env vars:
```bash
# Option 1: Via SSH (if your IP is whitelisted)
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192 "cd /home/ubuntu/rktb && bash deploy.sh latest"

# Option 2: Via SSM (works from anywhere)
aws ssm start-session --target $INSTANCE_ID --region ap-southeast-1
# Then inside the session: cd /home/ubuntu/rktb && bash deploy.sh latest
```

### 6.4 Resend (Active Email Provider — SES Alternative)

AWS SES production access was denied twice by Trust and Safety. Resend is used instead — it has no approval process, a 3,000 emails/month free tier, and uses standard SMTP so zero code changes were needed.

> **Note:** Resend is built on AWS infrastructure internally — the MX bounce record points to `amazonses.com`. It is essentially a developer-friendly wrapper around SES with pre-approved sending reputation.

#### 6.4.1 Domain Setup

1. Sign up at **resend.com**
2. Resend Dashboard → Domains → Add domain → `rkteambuilder.com`, Region: any (US East is fine)
3. Resend shows DNS records to add — add all of them in **Cloudflare → rkteambuilder.com → DNS**:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| TXT | `resend._domainkey` | *(DKIM value from Resend)* | DNS only |
| MX | `send` | *(bounce endpoint from Resend, priority 10)* | DNS only |
| TXT | `send` | *(SPF value from Resend)* | DNS only |
| TXT | `_dmarc` | `v=DMARC1; p=none;` | DNS only |

4. Click **Verify Records** in Resend — wait for green status

#### 6.4.2 Create API Key

Resend Dashboard → API Keys → Create API key:
- Name: `rktb-prod`
- Permission: **Sending access**
- Domain: **rkteambuilder.com**

Copy the key immediately (shown only once, starts with `re_`).

#### 6.4.3 Store Credentials in Parameter Store

```bash
aws ssm put-parameter --name /rktb/prod/SMTP_HOST \
  --value "smtp.resend.com" --type String --overwrite \
  --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/SMTP_USER \
  --value "resend" --type String --overwrite \
  --region ap-southeast-1

aws ssm put-parameter --name /rktb/prod/SMTP_PASSWORD \
  --value "re_YOUR_API_KEY" --type SecureString --overwrite \
  --region ap-southeast-1
```

`SMTP_PORT=587` and `SMTP_USE_TLS=true` remain unchanged — Resend uses identical settings to SES.
`SMTP_FROM_EMAIL=noreply@rkteambuilder.com` is hardcoded in `docker-compose.prod.yml` and unchanged.

#### 6.4.4 Redeploy Backend

> **Note:** Steps 6.4.1–6.4.3 can be completed before Phase 7. If you do so, skip this step — the Phase 7 initial deployment will already pick up the credentials from Parameter Store automatically. Only run this if you configured Resend after the backend was already deployed.

`deploy.sh` reads SMTP credentials fresh from Parameter Store on every run:

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192
cd /home/ubuntu/rktb && bash deploy.sh latest
```

#### 6.4.5 Verify Email Delivery

Register a new account on `https://rkteambuilder.com` and confirm the verification email arrives in the inbox.

---

## Phase 7: First Deployment & Data Import

### 7.1 Initial Deploy

After all AWS resources are created and GitHub Actions is configured:

```bash
# Push to main to trigger the first deployment
git add backend/Dockerfile .dockerignore docker-compose.prod.yml docker-compose.yml .github/workflows/deploy.yml
git commit -m "Add Docker and CI/CD configuration for AWS deployment"
git push origin main
```

Watch the GitHub Actions run in your repo's "Actions" tab.

### 7.2 Import Game Data

After the first deployment succeeds and the backend container is running:

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192

# Get the running backend container ID
CONTAINER_ID=$(docker ps --filter "name=backend" --format "{{.ID}}")

# Run the data import inside the container
# NOTE: pipe "yes" via -i flag to answer the confirmation prompt non-interactively
echo "yes" | docker exec -i $CONTAINER_ID python3 -m backend.scripts.importers.reset_and_reimport
```

### 7.3 Run Alembic Migrations (if not auto-run by deploy.sh)

```bash
docker exec $CONTAINER_ID python -m alembic -c backend/alembic.ini upgrade head
```

---

## Phase 8: Post-Deployment Verification

```bash
# Set your EC2 IP if not already in environment (from Phase 1.8)
# EC2_IP=<your-elastic-ip-here>

# 1. Health check (API prefix required — /health alone goes to S3)
curl https://rkteambuilder.com/api/health
# Expected: {"status":"ok"}

# 2. Frontend loads
curl -I https://rkteambuilder.com
# Expected: 200 OK, security headers present

# 3. SPA routing works (browser refresh on /teams should return index.html, not JSON)
curl -I https://rkteambuilder.com/teams
# Expected: 200 OK with Content-Type: text/html (served by S3)

# 4. API endpoints work
curl "https://rkteambuilder.com/api/monsters?limit=1"
# Expected: JSON response with monster data

# 5. Auth works
curl -X POST https://rkteambuilder.com/api/auth/guest \
  -H "Content-Type: application/json"
# Expected: 200 with access_token

# 5. Direct EC2 access blocked
curl http://13.228.63.192/health
# Expected: 403 Forbidden (nginx rejects non-CloudFront requests)

curl http://13.228.63.192:8000/health
# Expected: Connection refused (port 8000 not exposed)

# 6. HTTPS redirect
curl -I http://rkteambuilder.com
# Expected: 301 → https://rkteambuilder.com

# 7. Redis not accessible externally
redis-cli -h 13.228.63.192 ping
# Expected: Connection refused
```

---

## Phase 9: Observability & Monitoring

### 9.1 Configure CloudWatch Log Streaming

**Nginx access logs → CloudWatch:**

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@13.228.63.192

# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Create config
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'EOF'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/nginx/access.log",
            "log_group_name": "/rktb/nginx/access",
            "log_stream_name": "{instance_id}"
          },
          {
            "file_path": "/var/log/nginx/error.log",
            "log_group_name": "/rktb/nginx/error",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
EOF

# Start agent
sudo systemctl enable amazon-cloudwatch-agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s
```

**Docker container logs (optional CloudWatch integration):**

The backend container logs to stdout/stderr. By default, use `docker logs` to view them on EC2. For centralized logging in CloudWatch, add the following to the `backend` service in `docker-compose.prod.yml`:

```yaml
    logging:
      driver: awslogs
      options:
        awslogs-region: ap-southeast-1
        awslogs-group: /rktb/backend
        awslogs-stream: backend
        awslogs-create-group: "true"
```

> **Tradeoff:** CloudWatch Logs adds ~$0.50/GB ingestion + $0.03/GB storage. For low-traffic apps, `docker logs` on EC2 is sufficient. Enable CloudWatch logging if you need log retention beyond EC2 instance lifecycle, cross-service log correlation, or alerting based on log patterns.

**If NOT using `awslogs-create-group: "true"`**, create the log group manually first:
```bash
aws logs create-log-group --log-group-name /rktb/backend --region ap-southeast-1
```

### 9.2 Create Basic CloudWatch Alarms

**First, set required variables and create the SNS topic for alerts:**
```bash
# Get account ID and instance ID (if not already set)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=rktb-backend" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text --region ap-southeast-1)

# Create SNS topic (must exist before alarms reference it)
aws sns create-topic --name rktb-alerts --region ap-southeast-1
aws sns subscribe --topic-arn arn:aws:sns:ap-southeast-1:$ACCOUNT_ID:rktb-alerts \
  --protocol email --notification-endpoint your-email@example.com --region ap-southeast-1
# IMPORTANT: Check your email and confirm the subscription before proceeding
```

**Then create the alarms:**

```bash
# High CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "rktb-ec2-high-cpu" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:ap-southeast-1:$ACCOUNT_ID:rktb-alerts \
  --region ap-southeast-1

# RDS high CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "rktb-rds-high-cpu" \
  --metric-name CPUUtilization \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=DBInstanceIdentifier,Value=rktb-postgres \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:ap-southeast-1:$ACCOUNT_ID:rktb-alerts \
  --region ap-southeast-1

# RDS low storage alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "rktb-rds-low-storage" \
  --metric-name FreeStorageSpace \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 2147483648 \
  --comparison-operator LessThanThreshold \
  --dimensions Name=DBInstanceIdentifier,Value=rktb-postgres \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:ap-southeast-1:$ACCOUNT_ID:rktb-alerts \
  --region ap-southeast-1
```

### 9.3 View Logs

| Log Type | Location |
|----------|----------|
| Nginx access | CloudWatch → `/rktb/nginx/access` |
| Nginx error | CloudWatch → `/rktb/nginx/error` |
| Backend app | CloudWatch → `/rktb/backend` OR `ssh EC2 && docker logs rktb-backend-1` |
| Docker events | `ssh EC2 && docker events` |

---

## Phase 10: Frontend API Prefix and SPA Routing

**The `/api` prefix is critical — here's why:**

React SPA routes (like `/teams`, `/monsters`, `/auth/login`) and FastAPI routes share the same URL namespace. Without a prefix, a browser refresh on `/teams` causes CloudFront to route the request to EC2, which returns JSON instead of `index.html`. The React app never loads.

The fix: all frontend API calls use `VITE_API_BASE_URL=https://rkteambuilder.com/api`, so they hit `/api/*`. CloudFront routes `/api/*` to EC2. All other paths — including browser navigation to `/teams`, `/monsters`, etc. — fall through to the S3 default behavior and return `index.html`, letting React Router handle the URL client-side.

Nginx on EC2 strips the `/api` prefix (`rewrite ^/api(/.*)$ $1 break`) before passing to FastAPI, so FastAPI routes remain unchanged.

**File: `frontend/src/lib/api.ts`** — the axios base URL is set from `VITE_API_BASE_URL` at build time. No code changes needed; only the environment variable (set in `deploy.yml`) matters.

**File: `backend/config.py`** — no COOKIE_DOMAIN needed. When cookies are set without an explicit domain, they default to the exact origin domain (`rkteambuilder.com`). Since both frontend and API are on this domain, cookies flow correctly.

---

## Ongoing Operations Reference

> **SSH vs SSM:** SSH is available for manual admin work (port 22 locked to your IP). CI/CD uses SSM (no SSH keys in GitHub). You can also use SSM for manual work if your IP changes frequently.
>
> **SSH shortcut:** Add to `~/.ssh/config` for convenience:
> ```
> Host rktb
>   HostName <your-ec2-elastic-ip>
>   User ubuntu
>   IdentityFile ~/.ssh/rktb-key.pem
> ```
> Then use `ssh rktb` instead of the full command.

| Task | Command |
|------|---------|
| View logs | `ssh rktb` then `cd rktb && docker compose -f docker-compose.prod.yml logs -f backend` |
| Restart backend | `ssh rktb` then `cd rktb && docker compose -f docker-compose.prod.yml restart backend` |
| Redeploy | `git push origin main` (triggers GitHub Actions) |
| Manual redeploy (SSH) | `ssh rktb` then `cd rktb && bash deploy.sh latest` |
| Manual redeploy (SSM) | `aws ssm start-session --target $INSTANCE_ID --region ap-southeast-1` then run deploy.sh |
| RDS snapshot | `aws rds create-db-snapshot --db-instance-identifier rktb-postgres --db-snapshot-identifier backup-$(date +%Y%m%d) --region ap-southeast-1` |
| Update SSH IP | Update EC2 security group port 22 source CIDR via AWS Console or `aws ec2 modify-security-group-rules` |
| Switch LLM provider | Update SSM parameter + redeploy (see note below) |
| Check costs | `aws ce get-cost-and-usage --time-period Start=$(date +%Y-%m-01),End=$(date +%Y-%m-%d) --granularity MONTHLY --metrics BlendedCost` |
| Scale up EC2 | Stop instance → Change type → Start (or launch new, swap Elastic IP) |
| View CloudWatch logs | AWS Console → CloudWatch → Log groups → `/rktb/*` |
| **Add new API route** | **Add in main.py only — no CloudFront changes needed (all routes covered by `/api/*` behavior)** |

**Switching LLM Provider (currently using DeepSeek):**

The backend uses DeepSeek (`LLM_PROVIDER=deepseek`) for LLM analysis in production. To switch to Gemini or another provider:

1. Update `LLM_PROVIDER` in `docker-compose.prod.yml` (e.g., `LLM_PROVIDER=gemini`)
2. Ensure the API key is in Parameter Store (Gemini key is already stored)
3. Update `docker-compose.prod.yml` to pass the correct env var
4. Update `deploy.sh` to fetch the correct parameter
5. Redeploy

**Note:** Different models may produce different response quality. Test thoroughly after switching.

---

## Files to Create (Summary)

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Backend container image definition |
| `.dockerignore` | Exclude unnecessary files from Docker build context |
| `docker-compose.prod.yml` | Production compose file (runs on EC2) |
| `docker-compose.yml` | Local development compose file (optional) |
| `.github/workflows/deploy.yml` | CI/CD pipeline: test → build → deploy |
