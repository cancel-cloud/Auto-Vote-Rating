FROM python:3.11-slim

# Install system dependencies including Chromium for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application code
COPY worker/ ./worker/
COPY dashboard/ ./dashboard/
COPY start.sh .

# Create data directory for persistent storage
RUN mkdir -p /app/data

# Create Playwright profile directory for persistent browser contexts
RUN mkdir -p /app/data/playwright-profile && \
    chmod 755 /app/data/playwright-profile

# Make startup script executable
RUN chmod +x start.sh

# Expose port for dashboard
EXPOSE 8080

# Run the application
CMD ["./start.sh"]
