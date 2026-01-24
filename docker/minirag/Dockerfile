FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Install additional system dependencies for lxml and other packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libavif-dev pkg-config \
    libjpeg-dev \
    gcc unzip zip \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------------------------------------------
ARG INSTALL_TYPE=cpu

RUN if [ "$INSTALL_TYPE" = "cpu" ]; then \
        echo "Installing CPU-only PyTorch..." && \
        uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --system; \
    else \
        echo "Skipping CPU-only install. Standard GPU version will be installed from requirements.txt"; \
    fi
# ---------------------------------------------------------------------------------------------------------------


COPY src/requirements.txt .

RUN uv pip install -r requirements.txt --system

# Pre-download HuggingFace model during build
ARG EMBEDDING_MODEL_ID=intfloat/multilingual-e5-base
ENV EMBEDDING_MODEL_ID=${EMBEDDING_MODEL_ID}
COPY docker/minirag/download_model.py /tmp/download_model.py
RUN python3 /tmp/download_model.py && rm /tmp/download_model.py

COPY src/ .

# Create directory structure for Alembic
RUN mkdir -p /app/models/db_schemes/minirag/

COPY docker/minirag/alembic.ini /app/models/db_schemes/minirag/alembic.ini

COPY docker/minirag/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]