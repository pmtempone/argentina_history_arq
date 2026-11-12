FROM condaforge/miniforge3:latest

LABEL maintainer="ArchaeoLiDAR-AR-MCP"
LABEL description="FastMCP Server for autonomous archaeological LiDAR detection in Argentina"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

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

# Instalar dependencias Python adicionales vía pip
RUN pip install --no-cache-dir \
    "fastmcp>=0.4.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.2.0" \
    opencv-python-headless \
    httpx \
    geopandas \
    pytest \
    pytest-asyncio

COPY pyproject.toml README.md .env.example ./
COPY src/ ./src/
COPY tests/ ./tests/

RUN mkdir -p /app/data/raw /app/data/processed /app/data/reports

CMD ["python", "-m", "src.server"]
