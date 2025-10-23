#!/bin/bash

# Synthetic Market Data API - Startup Script
# This script starts all services using Docker Compose

echo "================================================"
echo "  Starting Synthetic Market Data API"
echo "================================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running!"
    echo "Please start Docker Desktop and try again."
    exit 1
fi

# Check if docker-compose exists
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: docker-compose is not installed!"
    echo "Please install docker-compose and try again."
    exit 1
fi

echo "🔨 Building Docker images..."
docker-compose build

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo ""
echo "🚀 Starting services..."
docker-compose up -d

if [ $? -ne 0 ]; then
    echo "❌ Failed to start services!"
    exit 1
fi

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Initialize database schema
echo ""
echo "🗄️  Initializing database..."
docker-compose exec -T postgres psql -U postgres -d synthetic_market << 'EOF'
-- Create tickers table if not exists
CREATE TABLE IF NOT EXISTS tickers (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    sector VARCHAR(50),
    initial_price DECIMAL(10, 2),
    min_price DECIMAL(10, 2),
    max_price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create market_ticks table if not exists
CREATE TABLE IF NOT EXISTS market_ticks (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    time TIMESTAMP NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    volume BIGINT NOT NULL,
    bid DECIMAL(10, 2),
    ask DECIMAL(10, 2)
);

-- Create indexes if not exist
CREATE INDEX IF NOT EXISTS idx_market_ticks_ticker_time ON market_ticks(ticker, time);
CREATE INDEX IF NOT EXISTS idx_market_ticks_time ON market_ticks(time);

-- Insert default tickers if not exist
INSERT INTO tickers (ticker, name, sector, initial_price, min_price, max_price)
VALUES
    ('SYNTH', 'Synthetic Corp', 'Technology', 100.00, 50.00, 200.00),
    ('TECH', 'Tech Industries', 'Technology', 150.00, 75.00, 300.00),
    ('FINANCE', 'Finance Group', 'Finance', 80.00, 40.00, 160.00),
    ('ENERGY', 'Energy Solutions', 'Energy', 120.00, 60.00, 240.00),
    ('HEALTH', 'Health Systems', 'Healthcare', 90.00, 45.00, 180.00)
ON CONFLICT (ticker) DO NOTHING;
EOF

if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Database initialization may have failed"
else
    echo "✅ Database initialized successfully"
fi

echo ""
echo "================================================"
echo "✅ All services are starting up!"
echo "================================================"
echo ""
echo "📊 Services:"
echo "   - PostgreSQL:    localhost:5432"
echo "   - Kafka:         localhost:9092"
echo "   - API Server:    http://localhost:3000"
echo "   - WebSocket:     ws://localhost:3000/ws"
echo ""
echo "📝 Useful commands:"
echo "   - View logs:     docker-compose logs -f"
echo "   - Stop all:      ./stop.sh"
echo "   - Restart:       ./stop.sh && ./start.sh"
echo ""
echo "🔗 API Endpoints:"
echo "   - GET  http://localhost:3000/"
echo "   - GET  http://localhost:3000/api/v1/tickers"
echo "   - GET  http://localhost:3000/api/v1/quote/SYNTH"
echo "   - GET  http://localhost:3000/api/v1/history/SYNTH"
echo "   - GET  http://localhost:3000/api/v1/bars/SYNTH"
echo "   - GET  http://localhost:3000/api/v1/stats/SYNTH"
echo ""
