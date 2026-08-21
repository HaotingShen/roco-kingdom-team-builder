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
export POSTGRES_PASSWORD=$(aws ssm get-parameter --name /rktb/prod/POSTGRES_PASSWORD --with-decryption --region $REGION --query Parameter.Value --output text)

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

echo "=== Starting datastores (creates network; Postgres must be healthy before migrations) ==="
cd /home/ubuntu/rktb
docker compose -f docker-compose.prod.yml up -d redis postgres

echo "=== Waiting for Postgres healthcheck ==="
for i in $(seq 1 30); do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' rktb-postgres-1 2>/dev/null)" = "healthy" ]; then
    echo "Postgres healthy after ${i}0s"; break
  fi
  if [ "$i" -eq 30 ]; then echo "ERROR: Postgres did not become healthy in 300s"; exit 1; fi
  sleep 10
done

echo "=== Running database migrations ==="
# Alembic migrations only need DATABASE_URL.
# Postgres now runs as a compose service, so the migration container must join the
# compose network -- "--network host" only worked when the DB was an external RDS
# endpoint and would NOT resolve the "postgres" hostname.
# Network name is derived from the running redis container rather than hardcoded.
COMPOSE_NET=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' rktb-redis-1)
echo "Using compose network: ${COMPOSE_NET}"
# Minimal env vars to reduce coupling (migrations shouldn't need runtime secrets).
docker run --rm --network "${COMPOSE_NET}" \
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
