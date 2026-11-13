FROM condaforge/miniforge3:latest

LABEL maintainer="ArchaeoLiDAR-AR-MCP"
LABEL description="FastMCP Server for autonomous archaeological multisatellite & LiDAR detection in Argentina"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    BLENDER_PATH=/usr/bin/blender

WORKDIR /app

# Instalar Blender headless y librerías gráficas mínimas para renderizado 3D EEVEE
RUN apt-get update && apt-get install -y --no-install-recommends \
    blender \
    libegl1 \
    libgl1 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias C++ nativas geoespaciales vía conda-forge
RUN conda install -y -c conda-forge \
    python=3.11 \
    gdal \
    pdal \
    python-pdal \
    rasterio \
    pyproj \
    shapely \
    scipy \
    numpy \
    matplotlib-base \
    && conda clean -afy

# Instalar dependencias Python alineadas con pyproject.toml
RUN pip install --no-cache-dir \
    "fastmcp>=0.4.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.2.0" \
    opencv-python-headless \
    httpx \
    geopandas \
    "pystac-client>=0.9.0" \
    "planetary-computer>=1.0.0" \
    "boto3>=1.34.0" \
    "scikit-learn>=1.4.0"

COPY pyproject.toml README.md .env.example ./
COPY src/ ./src/
COPY tests/ ./tests/

RUN pip install --no-cache-dir --no-deps -e . \
    && mkdir -p /app/data/raw /app/data/processed /app/data/reports

CMD ["python", "-m", "src.server"]
