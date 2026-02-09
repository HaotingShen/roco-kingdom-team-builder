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
     ┌─────────────────────────────────────────────┐
     │           CloudFront CDN                      │
     │  • HTTPS termination (ACM certificate)        │
     │  • Security headers                           │
     │  • DDoS protection                            │
     │  • Edge caching (Singapore, HK, Tokyo, etc.)  │
     └──────┬──────────────────────────┬─────────────┘
            │                          │
  API paths → EC2:                     │  /* (default) → S3
  /auth/* /teams/* /team/*             │
  /monsters/* /moves/* /types          │
  /traits /personalities /species      │
  /magic_items /game_terms /config/*   │
  /admin/* /cache/* /analysis/*        │
  /health                              │
            │                          │
            ▼                          ▼
  ┌─────────────────────┐    ┌───────────────┐
  │  EC2 t3.small       │    │   S3 Bucket   │
  │  ap-southeast-1     │    │  (React SPA)  │
  │                     │    │  rktb-frontend │
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
- `rkteambuilder.com/build` → S3 (React SPA)
- `rkteambuilder.com/auth/login` → EC2 (FastAPI API)
- `rkteambuilder.com/teams` → EC2 (FastAPI API)

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

### 1.1 Install & Configure AWS CLI

```bash
# Install AWS CLI v2 (on your WSL2)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure with your IAM user credentials
# SECURITY OPTIONS (choose one):
#   1. BEST: Use AWS IAM Identity Center (SSO) → `aws configure sso`
#   2. GOOD: Create IAM user with scoped policy (see below), delete keys after setup
#   3. ACCEPTABLE: Create IAM user with AdministratorAccess, delete keys after setup
#
# For option 2, create a policy with only these services:
#   EC2, RDS, S3, CloudFront, ECR, IAM, SSM, ACM, SES, CloudWatch, SNS, WAF
#   (see AWS docs for specific actions needed)
#
# After initial setup, you can delete the access keys and use SSO/role assumption.
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
  --backup-retention-period 7 \
  --storage-encrypted \
  --deletion-protection \
  --region ap-southeast-1

# NOTE on RDS options:
# - backup-retention-period 7: Automated daily backups kept for 7 days (recoverable to any point-in-time)
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

---

## Phase 2: Docker Configuration (Files to Create in Repo)

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
      - GEMINI_API_KEY=${GEMINI_API_KEY}
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

### 3.1 SSH In and Install Docker + Nginx

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@$EC2_IP

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
ssh -i ~/.ssh/rktb-key.pem ubuntu@$EC2_IP

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

    location / {
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

        # LLM analysis can take 30+ seconds
        proxy_read_timeout 120s;
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
export GEMINI_API_KEY=$(aws ssm get-parameter --name /rktb/prod/GEMINI_API_KEY --with-decryption --region $REGION --query Parameter.Value --output text)
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
  - Response timeout: **60 seconds** (time to first byte)
  - Keep-alive timeout: **5 seconds** (default)
  - Read timeout: **60 seconds** (time to receive full response after first byte)

> **Why 60 seconds?** This is CloudFront's maximum without AWS Support approval. To determine if it's enough:
> 1. Test locally: `time curl -X POST http://localhost:8000/team/analyze -d '...'`
> 2. If your p95 analysis time is under 50s, 60s timeout is fine
> 3. If analyses regularly exceed 60s, either request a timeout increase (up to 180s via AWS Support) or implement async: `POST /analysis/submit` → poll → `GET /analysis/{id}/result`

**Cache Behaviors (order matters - specific paths first, default last):**

| Priority | Path Pattern | Origin | Viewer Protocol | Allowed Methods | Cache Policy | Origin Request Policy |
|----------|-------------|--------|-----------------|-----------------|-------------|----------------------|
| 1 | `/auth/*` | EC2-API | Redirect HTTPS | ALL (incl. DELETE) | CachingDisabled | AllViewerExceptHostHeader |
| 2 | `/teams` | EC2-API | Redirect HTTPS | ALL | CachingDisabled | AllViewerExceptHostHeader |
| 3 | `/teams/*` | EC2-API | Redirect HTTPS | ALL | CachingDisabled | AllViewerExceptHostHeader |
| 4 | `/team/*` | EC2-API | Redirect HTTPS | ALL | CachingDisabled | AllViewerExceptHostHeader |
| 5 | `/monsters` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 6 | `/monsters/*` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 7 | `/moves` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 8 | `/moves/*` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 9 | `/types` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 10 | `/traits` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 11 | `/personalities` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 12 | `/magic_items` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 13 | `/game_terms` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 14 | `/species` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 15 | `/admin/*` | EC2-API | Redirect HTTPS | ALL | CachingDisabled | AllViewerExceptHostHeader |
| 16 | `/cache/*` | EC2-API | Redirect HTTPS | ALL | CachingDisabled | AllViewerExceptHostHeader |
| 17 | `/analysis/*` | EC2-API | Redirect HTTPS | ALL | CachingDisabled | AllViewerExceptHostHeader |
| 18 | `/config/*` | EC2-API | Redirect HTTPS | GET, HEAD, OPTIONS | CachingDisabled | AllViewerExceptHostHeader |
| 19 | `/health` | EC2-API | Redirect HTTPS | GET, HEAD | CachingDisabled | AllViewerExceptHostHeader |
| Default | `*` | S3-Frontend | Redirect HTTPS | GET, HEAD | CachingOptimized | None (not needed) |

**Note on Origin Request Policy:** "AllViewerExceptHostHeader" is required for API behaviors to forward cookies, Authorization headers, and query strings. For the S3 default behavior, no origin request policy is needed since static files don't require these headers.

**Note:** CloudFront behaviors are matched in order. `/teams` and `/teams/*` need separate rules because CloudFront's `/teams/*` does NOT match the exact path `/teams` (only paths with content after the slash). Same for `/monsters` and `/monsters/*`, `/moves` and `/moves/*`.

**Future-proofing note:** Routes like `/types`, `/traits`, `/personalities`, `/magic_items`, `/game_terms`, `/species` currently only have list endpoints (no `/{id}` subpaths). If you ever add detail routes (e.g., `/types/fire`, `/traits/123`), you MUST add corresponding `/*` behaviors, or those requests will silently route to S3 and return HTML instead of JSON.

**Important: For all API behaviors**, you MUST forward cookies and the Authorization header. Use the managed origin request policy "AllViewerExceptHostHeader" which forwards all headers, cookies, and query strings. Use managed cache policy "CachingDisabled" so API responses are never cached by CloudFront.

> ⚠️ **MAINTENANCE REQUIREMENT: Keep CloudFront behaviors in sync with API routes**
>
> When you add a new API endpoint (e.g., `/search/*`, `/v2/*`, `/webhooks/*`), you MUST add a corresponding CloudFront behavior. Otherwise:
> 1. CloudFront routes the request to S3 (default behavior)
> 2. S3 returns `index.html` (the SPA error document)
> 3. Your frontend receives HTML instead of JSON - silent failure!
>
> **Checklist when adding new API routes:**
> 1. Add endpoint in `backend/main.py`
> 2. Add CloudFront behavior in AWS Console (or via CLI/Terraform)
> 3. Test that the endpoint returns JSON, not HTML
>
> **Alternative:** Prefix all API routes with `/api/*` and use a single CloudFront behavior. This requires refactoring the backend routes but eliminates maintenance burden.

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
aws s3api get-bucket-policy --bucket rktb-frontend --query Policy --output text | jq .
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
          VITE_API_BASE_URL=https://rkteambuilder.com npm run build

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
ssh -i ~/.ssh/rktb-key.pem ubuntu@$EC2_IP "cd /home/ubuntu/rktb && bash deploy.sh latest"

# Option 2: Via SSM (works from anywhere)
aws ssm start-session --target $INSTANCE_ID --region ap-southeast-1
# Then inside the session: cd /home/ubuntu/rktb && bash deploy.sh latest
```

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
ssh -i ~/.ssh/rktb-key.pem ubuntu@$EC2_IP

# Get the running backend container ID
CONTAINER_ID=$(docker ps --filter "name=backend" --format "{{.ID}}")

# Run the data import inside the container
docker exec $CONTAINER_ID python3 -m backend.scripts.importers.reset_and_reimport
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

# 1. Health check
curl https://rkteambuilder.com/health
# Expected: {"status":"ok"}

# 2. Frontend loads
curl -I https://rkteambuilder.com
# Expected: 200 OK, security headers present

# 3. API endpoints work
curl "https://rkteambuilder.com/monsters?limit=1"
# Expected: JSON response with monster data

# 4. Auth works
curl -X POST https://rkteambuilder.com/auth/guest \
  -H "Content-Type: application/json"
# Expected: 200 with access_token

# 5. Direct EC2 access blocked
curl http://$EC2_IP/health
# Expected: 403 Forbidden (nginx rejects non-CloudFront requests)

curl http://$EC2_IP:8000/health
# Expected: Connection refused (port 8000 not exposed)

# 6. HTTPS redirect
curl -I http://rkteambuilder.com
# Expected: 301 → https://rkteambuilder.com

# 7. Redis not accessible externally
redis-cli -h $EC2_IP ping
# Expected: Connection refused
```

---

## Phase 9: Observability & Monitoring

### 9.1 Configure CloudWatch Log Streaming

**Nginx access logs → CloudWatch:**

```bash
ssh -i ~/.ssh/rktb-key.pem ubuntu@$EC2_IP

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

## Phase 10: Backend Config Change for Path-Based Routing

Since the frontend and API are on the same domain (`rkteambuilder.com`), you need to update `VITE_API_BASE_URL`:

**File: `frontend/src/lib/api.ts`** — verify that the axios base URL handles same-origin correctly. With `VITE_API_BASE_URL=https://rkteambuilder.com`, requests to `/auth/login` will go to `https://rkteambuilder.com/auth/login`, which CloudFront routes to EC2. This should work without changes.

**File: `backend/config.py`** — no COOKIE_DOMAIN needed. When cookies are set without an explicit domain, they default to the exact origin domain, which is `rkteambuilder.com`. Since both frontend and API are on this domain, cookies flow correctly.

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
| **Add new API route** | **1. Add in main.py → 2. Add CloudFront behavior → 3. Test returns JSON** |

**Switching LLM Provider (e.g., Gemini → DeepSeek):**

The backend uses `GEMINI_API_KEY` for LLM analysis. To switch providers:

1. **If using compatible API (OpenAI-compatible like DeepSeek):**
   - Update `backend/llm_service.py` to use the new SDK/endpoint
   - Add new parameter: `aws ssm put-parameter --name /rktb/prod/DEEPSEEK_API_KEY --value "..." --type SecureString`
   - Update `docker-compose.prod.yml` to pass the new env var
   - Update `deploy.sh` to fetch the new parameter
   - Redeploy

2. **Update rate limits:** DeepSeek may have different rate limits than Gemini. Adjust:
   - `ANALYSIS_RATE_LIMIT` in docker-compose.prod.yml
   - WAF rate-based rules (if configured)
   - Backend rate limiter thresholds

3. **Test thoroughly:** Different models may produce different JSON structures or response quality.

---

## Files to Create (Summary)

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Backend container image definition |
| `.dockerignore` | Exclude unnecessary files from Docker build context |
| `docker-compose.prod.yml` | Production compose file (runs on EC2) |
| `docker-compose.yml` | Local development compose file (optional) |
| `.github/workflows/deploy.yml` | CI/CD pipeline: test → build → deploy |
