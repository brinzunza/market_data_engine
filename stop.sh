#!/bin/bash

# Synthetic Market Data API - Shutdown Script
# This script stops all services using Docker Compose

echo "================================================"
echo "  Stopping Synthetic Market Data API"
echo "================================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "⚠️  Warning: Docker is not running!"
    echo "Services may already be stopped."
    exit 0
fi

# Check if docker-compose exists
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: docker-compose is not installed!"
    exit 1
fi

echo "🛑 Stopping all services..."
docker-compose down

if [ $? -ne 0 ]; then
    echo "❌ Failed to stop services!"
    exit 1
fi

echo ""
echo "================================================"
echo "✅ All services stopped successfully!"
echo "================================================"
echo ""
echo "📝 Next steps:"
echo "   - Start again:        ./start.sh"
echo "   - Remove all data:    docker-compose down -v"
echo "   - View containers:    docker ps -a"
echo ""
