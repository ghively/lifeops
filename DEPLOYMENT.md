# Deployment Guide

Production deployment instructions for Knowledge OS.

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [AWS Deployment](#aws-deployment)
3. [Docker Deployment](#docker-deployment)
4. [Kubernetes](#kubernetes)
5. [Database Setup](#database-setup)
6. [SSL/HTTPS](#ssltls)
7. [Monitoring](#monitoring)
8. [Scaling](#scaling)
9. [Backup & Recovery](#backup--recovery)
10. [Troubleshooting](#troubleshooting)

---

## Pre-Deployment Checklist

- [ ] All tests passing (`pytest`, `npm test`)
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] SSL certificates obtained
- [ ] Backups configured
- [ ] Monitoring set up
- [ ] Load testing completed
- [ ] Security audit done
- [ ] Documentation updated
- [ ] Team trained on deployment

---

## AWS Deployment

### Architecture

```
┌─────────────────────────────────────┐
│         CloudFront (CDN)            │
└──────────────────┬──────────────────┘
                   │
┌──────────────────▼──────────────────┐
│  Application Load Balancer (ALB)    │
│  (SSL termination)                  │
└──────────────────┬──────────────────┘
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
┌────────┐   ┌────────┐   ┌────────┐
│ ECS    │   │ ECS    │   │ ECS    │
│ Backend│   │Backend │   │Backend │
└────┬───┘   └────┬───┘   └────┬───┘
     │            │            │
     └────────────┼────────────┘
                  ▼
         ┌────────────────┐
         │  RDS Database  │
         │  (PostgreSQL)  │
         └────────────────┘
         
         ┌────────────────┐
         │  ElastiCache   │
         │  (Redis)       │
         └────────────────┘
         
         ┌────────────────┐
         │  S3 Bucket     │
         │  (Backups)     │
         └────────────────┘
```

### Step 1: Create ECR Repository

```bash
# Create image repository
aws ecr create-repository --repository-name knowledge-os-backend

# Get login token
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com
```

### Step 2: Build and Push Docker Image

```bash
# Build image
docker build -t knowledge-os-backend:latest backend/

# Tag for ECR
docker tag knowledge-os-backend:latest \
  123456789.dkr.ecr.us-east-1.amazonaws.com/knowledge-os-backend:latest

# Push to ECR
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/knowledge-os-backend:latest
```

### Step 3: Create ECS Task Definition

```json
{
  "family": "knowledge-os-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/knowledge-os-backend:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "DATABASE_URL",
          "value": "postgresql://user:pass@rds-host:5432/knowledge_os"
        },
        {
          "name": "REDIS_URL",
          "value": "redis://cache-host:6379"
        },
        {
          "name": "SECRET_KEY",
          "value": "your-secret-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/knowledge-os",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

### Step 4: Create ECS Cluster and Service

```bash
# Create cluster
aws ecs create-cluster --cluster-name knowledge-os

# Create service
aws ecs create-service \
  --cluster knowledge-os \
  --service-name backend \
  --task-definition knowledge-os-backend \
  --desired-count 3 \
  --launch-type FARGATE \
  --load-balancers \
    targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=backend,containerPort=8000 \
  --network-configuration \
    awsvpcConfiguration='{subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=ENABLED}'
```

### Step 5: Configure ALB

```bash
# Create target group
aws elbv2 create-target-group \
  --name knowledge-os-backend \
  --protocol HTTP \
  --port 8000 \
  --vpc-id vpc-xxx

# Register targets (automated by ECS)

# Create load balancer
aws elbv2 create-load-balancer \
  --name knowledge-os-alb \
  --subnets subnet-xxx subnet-yyy \
  --security-groups sg-xxx \
  --scheme internet-facing
```

---

## Docker Deployment

### Single Container

```bash
# Build image
docker build -t knowledge-os:latest .

# Run container
docker run -d \
  --name knowledge-os \
  -p 8000:8000 \
  -e DATABASE_URL=sqlite:///knowledge_os.db \
  -e SECRET_KEY=your-secret \
  -v /data:/app/data \
  knowledge-os:latest
```

### Docker Compose (Production)

`docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  backend:
    image: knowledge-os-backend:latest
    environment:
      DATABASE_URL: postgresql://user:pass@postgres:5432/knowledge_os
      REDIS_URL: redis://redis:6379
      SECRET_KEY: ${SECRET_KEY}
      DEBUG: "false"
    depends_on:
      - postgres
      - redis
      - qdrant
    restart: always
    networks:
      - main

  frontend:
    image: knowledge-os-frontend:latest
    environment:
      VITE_API_URL: https://api.example.com
    restart: always
    networks:
      - main

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: knowledge_os
      POSTGRES_USER: knowledge
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: always
    networks:
      - main

  redis:
    image: redis:7-alpine
    restart: always
    networks:
      - main

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_data:/qdrant/storage
    restart: always
    networks:
      - main

  nginx:
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - backend
      - frontend
    restart: always
    networks:
      - main

volumes:
  postgres_data:
  qdrant_data:

networks:
  main:
```

Deploy:

```bash
# Build images
docker-compose -f docker-compose.prod.yml build

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose logs -f backend
```

---

## Kubernetes

### Deployment Manifest

`k8s/backend-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: knowledge-os-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: knowledge-os-backend
  template:
    metadata:
      labels:
        app: knowledge-os-backend
    spec:
      containers:
      - name: backend
        image: gcr.io/project-id/knowledge-os-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: secret
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Service

`k8s/backend-service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: knowledge-os-backend
spec:
  selector:
    app: knowledge-os-backend
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Deploy

```bash
# Create secrets
kubectl create secret generic db-credentials \
  --from-literal=url="postgresql://..."

# Apply manifests
kubectl apply -f k8s/

# Check status
kubectl get deployments
kubectl get services

# View logs
kubectl logs -l app=knowledge-os-backend
```

---

## Database Setup

### PostgreSQL Production

```bash
# Create database and user
createdb knowledge_os
createuser knowledge -P

# Grant privileges
psql -c "GRANT ALL PRIVILEGES ON DATABASE knowledge_os TO knowledge"

# Run migrations
alembic upgrade head

# Verify
psql -U knowledge knowledge_os -c "\dt"
```

### Qdrant Production

Run as separate service:

```bash
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest
```

Or managed service (Qdrant Cloud).

---

## SSL/TLS

### Let's Encrypt with Certbot

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --standalone \
  -d api.example.com \
  -d example.com

# Configure nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    
    location / {
        proxy_pass http://backend:8000;
    }
}

# Auto-renew
sudo certbot renew --dry-run
```

### Nginx Configuration

```nginx
upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name api.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;
    
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    client_max_body_size 100M;
    
    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Monitoring

### Prometheus

`prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'knowledge-os'
    static_configs:
      - targets: ['localhost:8000']
```

### Grafana

```bash
docker run -d \
  --name grafana \
  -p 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin \
  grafana/grafana
```

### Health Check

```bash
# Check backend
curl https://api.example.com/health

# Check status
curl https://api.example.com/api/v1/system/status

# Check smoke test
curl https://api.example.com/api/v1/system/smoke-test
```

---

## Scaling

### Horizontal Scaling

```bash
# Scale backend to 5 instances
aws ecs update-service \
  --cluster knowledge-os \
  --service backend \
  --desired-count 5
```

### Auto-Scaling

```bash
# Create auto-scaling group
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name knowledge-os-asg \
  --launch-configuration-name knowledge-os-lc \
  --min-size 2 \
  --max-size 10 \
  --desired-capacity 3

# Scale on CPU utilization
aws autoscaling put-scaling-policy \
  --auto-scaling-group-name knowledge-os-asg \
  --policy-name scale-up \
  --policy-type TargetTrackingScaling \
  --target-tracking-configuration file://target-tracking.json
```

---

## Backup & Recovery

### Automated Backups

**Database:**
```bash
# Daily backup
0 2 * * * pg_dump knowledge_os > /backups/db-$(date +\%Y\%m\%d).sql

# Upload to S3
aws s3 sync /backups/ s3://knowledge-os-backups/
```

**Qdrant Snapshots:**
```bash
curl -X POST http://localhost:6333/snapshots
aws s3 sync /qdrant/snapshots/ s3://knowledge-os-backups/snapshots/
```

### Point-in-Time Recovery

```bash
# Restore from backup
psql knowledge_os < /backups/db-20260101.sql

# Or use WAL archive
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker logs backend

# Check environment variables
docker inspect backend | grep -i env

# Test database connection
psql $DATABASE_URL -c "SELECT 1"
```

### High Memory Usage

```bash
# Monitor memory
docker stats

# Reduce worker processes
# Increase cache TTL
# Enable caching layer (Redis)
```

### Slow Response Times

```bash
# Check database queries
# Enable query logging
# Add indexes
# Scale horizontally

# Use APM tool
docker run -d --name dd-agent datadog/agent
```

### Database Lock

```bash
# Kill blocking queries
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE state = 'active' AND query LIKE '%lock%';
```

---

## Rollback

### Immediate Rollback

```bash
# Revert to previous image
aws ecs update-service \
  --cluster knowledge-os \
  --service backend \
  --force-new-deployment \
  --task-definition knowledge-os-backend:previous

# Or
docker pull knowledge-os:previous
docker-compose up -d
```

### Database Rollback

```bash
alembic downgrade -1
```

---

## Production Checklist

- [ ] Secrets stored in secrets manager
- [ ] Database backups automated
- [ ] Monitoring and alerting configured
- [ ] Auto-scaling enabled
- [ ] SSL/HTTPS enforced
- [ ] Rate limiting enabled
- [ ] CORS configured
- [ ] Logging centralized
- [ ] Disaster recovery plan documented
- [ ] Team trained on operations

---

**See also:**
- [INSTALLATION.md](INSTALLATION.md) - Setup
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical details
