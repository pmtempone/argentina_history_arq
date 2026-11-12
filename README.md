# Prospección Arqueológica con LiDAR y Teledetección en Argentina

Repositorio central del proyecto de teledetección satelital, LiDAR y fotogrametría aérea con dron para el descubrimiento y preservación del patrimonio arqueológico en la República Argentina, bajo el marco de la **Ley Nacional N° 25.743 (INAPL)**.

---

## 📁 Estructura del Repositorio

* **`archaeo-lidar-mcp/`**: Servidor FastMCP y motor autónomo de prospección en Python:
  * `src/autonomous_prospector.py`: Pipeline principal de prospección por ventanas deslizantes (tiling).
  * `src/core/highres_hunter.py`: Cazador autónomo de datasets LiDAR y UAV (< 1.0 m/px) en OpenTopography, Zenodo y el IGN.
  * `src/utils/blender_render.py`: Renderizador 3D volumétrico isométrico térmico en Blender 4.2 LTS headless (EEVEE).
  * `src/core/vlm_judge.py`: Juez pericial multimodal VLM (LLM-as-Judge, Zheng et al. 2023) con criterios arqueológicos CONICET/NOA y gestión de falsas alarmas.
  * `src/core/ml_calibrator.py`: Calibrador ML supervisado (GradientBoosting calibrado con hard negatives de descartes periciales; metodología Guyot 2018 / Berganzo-Besga & Orengo 2021). Métricas: `data/reports/ML_BENCHMARK_METRICS.md`.
  * `src/core/looting_monitor.py`: Vigilancia patrimonial `ALERTA_SAQUEO` (metodología Parcak et al. 2016).
  * `src/core/geoform_inventory.py`: Inventario geomorfológico secundario derivado de los descartes NATURAL.
  * `src/core/data_fetcher.py`: Catálogo de 28 zonas arqueológicas con calibración adaptativa por bioma.
  * `src/core/known_sites.py` + `scripts/build_known_sites_gpkg.py`: Catálogo de sitios arqueológicos publicados (coordenadas aproximadas ±100 m) para clasificar candidatos `SITIO_REGISTRADO`.
  * `data/reports/`: Entregables patrimoniales (`MAPA_FINAL_PROSPECCION.geojson`, `DESCARTES_VLM.json`, `INVENTARIO_GEOMORFOLOGICO.geojson`, dossiers INAPL y anexo confidencial de coordenadas).
* **`.agents/skills/archaeo-lidar-prospector/SKILL.md`**: Skill oficial para el asistente **Antigravity** (AGY) para operar autónomamente el software, ejecutar prospecciones y registrar dictámenes periciales.

---

## ⚡ Ejecución Rápida

```bash
cd archaeo-lidar-mcp
source venv/bin/activate

# Prospección autónoma en el Delta del Paraná (Cerritos de indios / Humedal)
python -m src.autonomous_prospector --target ZONA_23_DELTA_PARANA --max-candidates 4

# Caza y procesamiento de datasets de dron de ultra alta resolución (ej. San Rafael a 5 cm/px)
python -m src.autonomous_prospector --highres-id ZENODO:3383227 --max-candidates 4
```

## 🚀 Empezá por acá

👉 **[Manual de Uso (para cualquier persona)](MANUAL_DE_USO.md)** — qué hace el sistema,
qué le pedís, dónde mirás el resultado, por escenarios ("quiero prospectar una zona
nueva", "quiero detectar saqueo", "cómo audito un candidato").

Para documentación técnica detallada, consulta el [**README de ArchaeoLiDAR-AR-MCP**](archaeo-lidar-mcp/README.md) y el skill en [`.agents/skills/archaeo-lidar-prospector/SKILL.md`](.agents/skills/archaeo-lidar-prospector/SKILL.md).
