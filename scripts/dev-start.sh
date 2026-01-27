#!/bin/bash
# Development startup script

set -e

echo "=========================================="
echo "ModelSquare - Development Environment"
echo "=========================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Error: Docker Compose is not installed"
    exit 1
fi

echo ""
echo "Starting infrastructure services (PostgreSQL, Redis, MinIO, SRS)..."
docker compose up -d postgres redis minio srs

echo ""
echo "Waiting for services to be healthy..."
sleep 10

echo ""
echo "Services started successfully!"
echo ""
echo "=========================================="
echo "Service URLs:"
echo "=========================================="
echo "PostgreSQL: localhost:5432"
echo "Redis:      localhost:6379"
echo "MinIO:      http://localhost:9000 (Console: http://localhost:9001)"
echo "SRS:        rtmp://localhost:1935 (HTTP: http://localhost:8080)"
echo ""
echo "=========================================="
echo "To start the backend API:"
echo "=========================================="
echo "  cd backend"
echo "  pip install -r requirements.txt"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "API Docs: http://localhost:8000/api/v1/docs"
echo ""
echo "=========================================="
echo "To start the frontend:"
echo "=========================================="
echo "  cd frontend"
echo "  npm install"
echo "  npm run dev"
echo ""
echo "Frontend: http://localhost:5173"
echo ""
echo "=========================================="
echo "To stop all services:"
echo "=========================================="
echo "  docker compose down"
echo ""
