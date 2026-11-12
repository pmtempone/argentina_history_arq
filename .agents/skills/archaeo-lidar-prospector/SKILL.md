---
name: archaeo-lidar-prospector
description: >-
  Prospección arqueológica autónoma sobre datos LiDAR, fotogrametría UAV y DEMs en Argentina.
  Usar para ejecutar prospecciones en las Zonas 1 a 28, cazar datasets LiDAR/UAV de alta resolución (< 1m),
  generar modelos de relieve local (SLRM/Pendiente), renderizar modelos 3D isométricos térmicos en Blender 4.2 LTS,
  auditar candidatos con el Juez Pericial VLM (CONICET/NOA), emitir dossiers INAPL (Ley 25.743) y gestionar
  descartes en DESCARTES_VLM.json para mantener cero falsas alarmas en MAPA_FINAL_PROSPECCION.geojson.
---

# ArchaeoLiDAR Prospector: Manual Operativo y Guía Pericial

Este skill guía la ejecución autónoma y supervisada del sistema **ArchaeoLiDAR-AR-MCP** para la prospección, detección y juicio pericial de sitios arqueológicos en todo el territorio de la República Argentina, bajo el marco de la **Ley Nacional N° 25.743** (Protección del Patrimonio Arqueológico y Paleontológico - INAPL).

---

## 1. Entorno de Ejecución y Dependencias

* **Directorio Raíz del Proyecto:** `/Users/pablotempone/argentina_history_arq/archaeo-lidar-mcp`
* **Entorno Virtual Python:** `./venv/bin/python`
* **Motor 3D Headless:** Blender 4.2 LTS (instalado en `/Applications/Blender.app/Contents/MacOS/Blender`)
* **Sistema Geodésico Obligatorio:** **POSGAR 2007** (Fajas 1 a 7, `EPSG:5343` a `EPSG:5349`). Nunca operar métricas en grados geográficos WGS84.

---

## 2. Comandos CLI Principales

### A. Prospección de Zonas Específicas
```bash
cd /Users/pablotempone/argentina_history_arq/archaeo-lidar-mcp

# Prospectar una zona individual (ej. Humedal del Delta del Paraná)
./venv/bin/python -m src.autonomous_prospector --target ZONA_23_DELTA_PARANA --max-candidates 4

# Prospectar Santuario Incaico de Alta Montaña (Volcán Chañi)
./venv/bin/python -m src.autonomous_prospector --target ZONA_17_CHANI --max-candidates 4

# Correr sobre todas las zonas nuevas (ZONA_4 a ZONA_28)
./venv/bin/python -m src.autonomous_prospector --new-zones-only --max-candidates 5

# Correr la campaña nacional completa (Zonas 1 a 28)
./venv/bin/python -m src.autonomous_prospector --all-zones --max-candidates 5
```

### B. Prospección de Alta Resolución UAV / LiDAR (< 1.0 m/px)
```bash
# Búsqueda y descarga automática del mejor dataset disponible en Argentina
./venv/bin/python -m src.autonomous_prospector --hunt-highres --max-candidates 4

# Prospección de un dataset específico por ID (ej. San Rafael, Mendoza a 5 cm/px)
./venv/bin/python -m src.autonomous_prospector --highres-id ZENODO:3383227 --max-candidates 4

# Prospección de dron en Precordillera de San Juan (0.25 m/px)
./venv/bin/python -m src.autonomous_prospector --highres-id ZENODO:18023344 --max-candidates 4
```

### C. Procesamiento de Nubes de Puntos Crudas Locales (.las / .laz)
```bash
# Procesar vuelo de dron local con filtrado SMRF y generación de DTM
./venv/bin/python scripts/process_real_lidar.py data/raw/mi_vuelo.laz --resolution 0.5 --radius 10.0
```

---

## 3. Catálogo de Biomas y Parámetros Adaptativos (Zonas 1 a 28)

Cada bioma argentino exige una calibración microtopográfica específica para evitar sesgos:

| Bioma | Zonas Representativas | Radio SLRM (m) | Área Mín/Máx ($m^2$) | dZ Mín (m) | Pendiente Máx (°) | Objetivo Morfológico |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Alta Montaña** | Chañi, Famatina, Llullaillaco | $12.0$ | $15 - 2000$ | $+0.30$ | $32^\circ$ | Plataformas cimeras, kanchas, tambos y tramos del Qhapaq Ñan. |
| **Yungas y Ceja de Selva** | Valle Grande, Ciudacita | $15.0$ | $30 - 5000$ | $+0.35$ | $35^\circ$ | Andenería prehispánica, pucarás en filos y calzadas empedradas. |
| **Sierras Centrales** | Pampa de Achala (Comechingones) | $10.0$ | $12 - 800$ | $+0.20$ | $25^\circ$ | Casas-pozo semi-enterradas, pircas y corrales líticos. |
| **Selva Paranaense** | Teyú Cuaré (Misiones) | $20.0$ | $50 - 6000$ | $+0.30$ | $25^\circ$ | Estructuras jesuítico-guaraníes bajo canopia, zanjas y plataformas. |
| **Humedales y Llanuras** | Delta del Paraná, Iberá, Ansenuza | $35.0 - 40.0$ | $150 - 9000$ | $+0.25 - +0.35$ | $8^\circ - 10^\circ$ | Cerritos y túmulos artificiales de tierra (Goya-Malabrigo / Chaná-Timbú). |
| **Meseta Patagónica** | Lago Strobel, Piedra Parada, Somuncurá | $8.0$ | $6 - 500$ | $+0.25$ | $20^\circ - 22^\circ$ | Parapetos circulares de caza de guanaco y chenques de piedra. |
| **Volcánico / Basáltico** | La Payunia (Mendoza) | $10.0$ | $10 - 600$ | $+0.25$ | $25^\circ$ | Apostaderos y corrales líticos emplazados entre coladas basálticas. |
| **UAV Sub-métrico (<0.10m)** | Vuelos de Dron (Mendoza, San Juan) | $2.5 - 6.0$ | $1.0 - 300$ | $+0.10$ | $35^\circ$ | Muros individuales, cimientos, trincheras y pedestales a escala centimétrica. |

---

## 4. Herramientas MCP Disponibles (Servidor FastMCP)

El servidor expone herramientas nativas para invocar desde agentes o clientes MCP:
* `tool_autonomous_prospect`: Ejecuta el barrido autónomo por celdas con overlap del 15% sobre cualquier zona.
* `tool_hunt_highres_lidar_argentina`: Consulta en tiempo real las APIs de OpenTopography, Zenodo y el IGN.
* `tool_vlm_judge_candidate`: Construye el prompt pericial estructurado con las métricas cuantitativas y la lámina compuesta.
* `tool_record_vlm_verdict`: Registra el veredicto oficial, archiva descartes en `DESCARTES_VLM.json` y regenera el dossier INAPL.
* `tool_inspect_candidate`: Genera la lámina compuesta de 4 paneles (2x2) con el modelo 3D de Blender.
* `tool_process_lidar_dtm`: Filtra la nube de puntos con SMRF (ASPRS Clase 2) y proyecta a GeoTIFF POSGAR 2007.

---

## 5. Protocolo de Evaluación del Juez Pericial VLM

Para mantener la regla estricta de **0 falsos positivos**, todo candidato debe ser clasificado en una de las 4 categorías:

1. **`ANTROPICA`**: Estructura arqueológica confirmada (recinto ortogonal, muro pircado, cerrito con evidencia inequívoca, etc.). Se preserva en `MAPA_FINAL_PROSPECCION.geojson`.
2. **`NATURAL`**: Geoforma geomorfológica natural (albardón aluvial, cresta de erosión, espolón periglacial, médano eólico, gendarme de cumbre, bloque ignimbrítico). Se archiva en `DESCARTES_VLM.json`.
3. **`ARTEFACTO`**: Rasgo antrópico moderno (mesa de sensor científico / *hail pad*, canal de riego actual, terraplén vial, corte de maquinaria) o anomalía de interpolación del raster (efecto de borde / costura de tile). Se archiva en `DESCARTES_VLM.json`.
4. **`PENDIENTE_REVISION`**: Estado transitorio antes del juicio visual multimodal.

### Registro de Veredicto en Python:
```python
from src.core.vlm_judge import record_vlm_verdict

verdict_dict = {
    "verdict": "ARTEFACTO",  # o NATURAL / ANTROPICA
    "certainty_pct": 98,
    "functional_interpretation": "Descripción pericial detallada",
    "geomorphological_justification": "Justificación técnica sobre corte 2D y modelo 3D Blender",
    "field_inspection_recommended": False,
    "backend": "Senior Space Archaeologist (VLM CONICET/NOA)",
}

record_vlm_verdict(candidate_id="ARQ-HRM-0001", verdict_data=verdict_dict)
```

---

## 6. Documentación Patrimonial y Entregables (Ley 25.743)

Al finalizar la prospección, el sistema actualiza automáticamente:
1. `data/reports/MAPA_FINAL_PROSPECCION.geojson`: FeatureCollection consolidada de hallazgos confirmados (debe mantener 0 falsos positivos).
2. `data/reports/DESCARTES_VLM.json`: Archivo forense con todas las anomalías descartadas y su justificación.
3. `data/reports/DOSSIER_INAPL_{CANDIDATO_ID}.md`: Informe técnico legal individual para presentación ante el INAPL.
4. `data/reports/ANEXO_CONFIDENCIAL_COORDENADAS.json`: Almacén protegido de coordenadas geodésicas de replanteo para prevenir saqueo (*guaqueo*).
