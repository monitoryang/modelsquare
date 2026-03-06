FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including FFmpeg for video processing, Chinese fonts, and Docker CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    fonts-wqy-zenhei \
    ca-certificates \
    gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && for i in 1 2 3 4 5; do \
         curl -fsSL --retry 3 --retry-delay 5 https://mirrors.aliyun.com/docker-ce/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && break || sleep 10; \
       done \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000

# Run with uvicorn (as root for docker socket access)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
