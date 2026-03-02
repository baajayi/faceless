FROM python:3.11-slim

# System deps: ffmpeg for audio/video, imagemagick for moviepy text
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    libmagickwand-dev \
    fonts-liberation \
    wget \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Download Nunito-Bold font
RUN mkdir -p /app/assets/fonts && \
    wget -q "https://github.com/googlefonts/nunito/raw/main/fonts/ttf/Nunito-Bold.ttf" \
    -O /app/assets/fonts/Nunito-Bold.ttf || \
    cp /usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf \
    /app/assets/fonts/Nunito-Bold.ttf

# ImageMagick policy — allow PDF/text operations needed by moviepy
RUN sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' \
    /etc/ImageMagick-6/policy.xml 2>/dev/null || true && \
    sed -i 's/<policy domain="path" rights="none" pattern="@\*"\/>/<policy domain="path" rights="read|write" pattern="@*"\/>/' \
    /etc/ImageMagick-6/policy.xml 2>/dev/null || true

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy project
COPY . .

# Create output directory
RUN mkdir -p /app/output

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
