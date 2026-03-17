# FFmpeg Worker with NVIDIA GPU Hardware Acceleration
# Supports NVENC (encoding) and NVDEC (decoding)

FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Configure Chinese mirror sources for apt
RUN sed -i 's|http://archive.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com|https://mirrors.aliyun.com|g' /etc/apt/sources.list

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    python3 \
    python3-pip \
    python3-dev \
    # FFmpeg dependencies
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    libx264-dev \
    libx265-dev \
    libnuma-dev \
    libvpx-dev \
    libmp3lame-dev \
    libopus-dev \
    yasm \
    nasm \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install NVIDIA Video Codec SDK headers (from local package)
COPY package/nv-codec-headers-n12.1.14.0.tar.gz /tmp/
RUN cd /tmp && \
    tar xzf nv-codec-headers-n12.1.14.0.tar.gz && \
    cd nv-codec-headers-n12.1.14.0 && \
    make && \
    make install && \
    cd /tmp && \
    rm -rf nv-codec-headers-n12.1.14.0 nv-codec-headers-n12.1.14.0.tar.gz

# Build FFmpeg with NVIDIA NVENC/NVDEC support (from local package)
COPY package/FFmpeg-n6.1.tar.gz /tmp/
RUN cd /tmp && \
    tar xzf FFmpeg-n6.1.tar.gz && \
    cd FFmpeg-n6.1 && \
    ./configure \
        --enable-gpl \
        --enable-nonfree \
        --enable-libx264 \
        --enable-libx265 \
        --enable-libvpx \
        --enable-libmp3lame \
        --enable-libopus \
        --enable-nvenc \
        --enable-nvdec \
        --enable-cuda \
        --enable-cuvid \
        --enable-ffnvcodec \
        --enable-filter=scale_cuda \
        --enable-filter=hwupload_cuda \
        --extra-cflags="-I/usr/local/cuda/include -I/usr/local/include" \
        --extra-ldflags="-L/usr/local/cuda/lib64 -L/usr/local/lib" \
        --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd /tmp && \
    rm -rf FFmpeg-n6.1 FFmpeg-n6.1.tar.gz

# Install Python dependencies (using Chinese mirror)
RUN pip3 install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    fastapi \
    uvicorn \
    redis \
    numpy \
    opencv-python-headless

# Copy worker code
COPY ffmpeg/worker.py .

# Create non-root user
RUN useradd -m -u 1000 worker && chown -R worker:worker /app
USER worker

EXPOSE 8080

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8080"]
