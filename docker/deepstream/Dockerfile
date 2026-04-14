FROM nvcr.io/nvidia/deepstream:8.0-triton-multiarch

# Use the new nvstreammux which preserves source resolution instead of
# forcing a fixed width/height.  This way the output video matches the
# original RTMP stream resolution.
ENV USE_NEW_NVSTREAMMUX=yes

# Install CJK font for Chinese text rendering in nvdsosd overlays
RUN apt-get update && apt-get install -y --no-install-recommends fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/* && fc-cache -fv

# Install Python dependencies for the pipeline manager FastAPI service
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

WORKDIR /app

# Compile YOLOv8 custom output parser for nvinferserver
COPY custom_yolo_parser/ ./custom_yolo_parser/
RUN cd /app/custom_yolo_parser && make CUDA_VER=12.8

# Copy application code
COPY pipeline_manager.py metadata_extractor.py owl_probe.py ./
COPY config/ ./config/

EXPOSE 8080

CMD ["python3", "pipeline_manager.py"]
