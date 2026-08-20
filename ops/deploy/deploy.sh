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

docker image prune -a -f
echo "=== Deployment complete ==="
