---
name: archaeo-lidar-prospector
description: >-
  Prospección arqueológica autónoma sobre datos LiDAR, fotogrametría UAV y DEMs en Argentina.
  Usar para ejecutar prospecciones en las Zonas 1 a 29, cazar datasets LiDAR/UAV de alta resolución (< 1m),
  generar modelos de relieve local (SLRM/Pendiente) con detección de relieve positivo Y negativo
  (recintos, chenques, terrazas, casas-pozo, zanjas), validar contra el catálogo de sitios publicados,
  renderizar modelos 3D isométricos térmicos en Blender 4.2 LTS, auditar candidatos con el Juez Pericial
  VLM (CONICET/NOA), emitir dossiers INAPL (Ley 25.743) y gestionar descartes en DESCARTES_VLM.json
  para mantener cero falsas alarmas en MAPA_FINAL_PROSPECCION.geojson.
---

# ArchaeoLiDAR Prospector: Manual Operativo y Guía Pericial

Este skill guía la ejecución autónoma y supervisada del sistema **ArchaeoLiDAR-AR-MCP** para la prospección, detección y juicio pericial de sitios arqueológicos en todo el territorio de la República Argentina, bajo el marco de la **Ley Nacional N° 25.743** (Protección del Patrimonio Arqueológico y Paleontológico - INAPL).

> 📖 **Para usuarios no técnicos:** existe un manual por escenarios en el raíz del repositorio
> (`MANUAL_DE_USO.md`): qué le pide la persona, qué hace el sistema y dónde mira el resultado.
> Cuando el usuario pregunte "cómo hago X" sin vocabulario técnico, guiarlo con ese manual.

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

### D. Catálogo de Sitios Registrados (Validación `SITIO_REGISTRADO`)
```bash
# Regenerar el GeoPackage de sitios publicados desde el CSV curado
# (sitios de dominio público/turístico con coordenadas aproximadas a ±100 m)
./venv/bin/python scripts/build_known_sites_gpkg.py
```
Un candidato a menos de 200 m de un sitio del catálogo (`data/known_sites.gpkg`,
fuente: `data/known_sites_published.csv`) se clasifica `SITIO_REGISTRADO` y NO se
reporta como inédito. Si se agrega un sitio nuevo, editar el CSV y regenerar el GPKG.

---

## 3. Catálogo de Biomas y Parámetros Adaptativos (Zonas 1 a 28)

Cada bioma argentino exige una calibración microtopográfica específica para evitar sesgos. El detector opera en **doble pase de signo**: relieve positivo (recintos, chenques, terrazas, pircas) y relieve negativo (casas-pozo, patios hundidos, zanjas y canales), con umbral `dZ` en valor absoluto:

| Bioma | Zonas Representativas | Radio SLRM (m) | Área Mín/Máx ($m^2$) | \|dZ\| Mín (m) | Pendiente Máx (°) | Objetivo Morfológico |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Alta Montaña** | Chañi, Famatina, Llullaillaco | $12.0$ | $15 - 2000$ | $0.30$ | $32^\circ$ | Plataformas cimeras, kanchas, tambos y tramos del Qhapaq Ñan. |
| **Yungas y Ceja de Selva** | Valle Grande, Ciudacita | $15.0$ | $30 - 5000$ | $0.35$ | $35^\circ$ | Andenería prehispánica, pucarás en filos y calzadas empedradas. |
| **Sierras Centrales** | Pampa de Achala (Comechingones) | $10.0$ | $12 - 800$ | $0.20$ | $25^\circ$ | Casas-pozo semi-enterradas (relieve NEGATIVO), pircas y corrales líticos. |
| **Selva Paranaense** | Teyú Cuaré (Misiones) | $20.0$ | $50 - 6000$ | $0.30$ | $25^\circ$ | Estructuras jesuítico-guaraníes bajo canopia, zanjas (negativo) y plataformas. |
| **Humedales y Llanuras** | Delta del Paraná, Iberá, Ansenuza | $35.0 - 40.0$ | $150 - 9000$ | $0.25 - 0.35$ | $8^\circ - 10^\circ$ | Cerritos y túmulos artificiales de tierra (Goya-Malabrigo / Chaná-Timbú). |
| **Meseta Patagónica** | Lago Strobel, Piedra Parada, Somuncurá | $8.0$ | $6 - 500$ | $0.25$ | $20^\circ - 22^\circ$ | Parapetos circulares de caza de guanaco y chenques de piedra. |
| **Volcánico / Basáltico** | La Payunia (Mendoza) | $10.0$ | $10 - 600$ | $0.25$ | $25^\circ$ | Apostaderos y corrales líticos emplazados entre coladas basálticas. |
| **UAV Sub-métrico (<0.10m)** | Vuelos de Dron (Mendoza, San Juan) | $2.5 - 6.0$ | $1.0 - 300$ | $0.10$ | $35^\circ$ | Muros individuales, cimientos, trincheras (negativo) y pedestales a escala centimétrica. |

**Notas de calibración (críticas para interpretar resultados):**

1. **Piso físico de área por resolución:** el detector eleva automáticamente `min_area` al valor de 2 píxeles del raster nativo (`MIN_AREA_PIXEL_FACTOR = 2`). En zonas satelitales (Copernicus GLO-30, 30 m/px ⇒ píxel de 900 m²) un `min_area` de 6–15 m² es físicamente irrecuperable y se eleva a ~1800 m²; el ajuste se registra en `metadata` (`min_area_floor_applied`). Al reportar resultados, citar el `min_area_effective_m2` real, no el solicitado.
2. **Signo del relieve (`mean_elevation_m`):** con signo. Positivo = sobreelevación (recinto, cerrito, pirca); negativo = hundimiento (casa-pozo, patio hundido, zanja). Tipologías de relieve negativo: `estructura_hundida` y `zanja_lineal`.
3. **Hundimientos cerrados:** un contorno negativo que toca el borde del tile se descarta (vaguadas, cauces naturales que lo atraviesan). Solo se aceptan depresiones completamente contenidas en la celda.
4. **Margen de borde del tile:** la tendencia SLRM está sesgada cerca del borde del raster (residual espurio hasta ±0.25 m en terreno colinar); los contornos que tocan el borde se descartan en ambos pases. La cobertura de esa franja la garantiza el overlap del 15% del tiling: una estructura cerca de un borde se detecta desde la celda vecina.

---

## 4. Herramientas MCP Disponibles (Servidor FastMCP)

El servidor expone herramientas nativas para invocar desde agentes o clientes MCP:
* `tool_autonomous_prospect`: Ejecuta el barrido autónomo por celdas con overlap del 15% sobre cualquier zona (relieve positivo y negativo, puntuación ML calibrada, validación IGN/OSM + catálogo de sitios registrados).
* `tool_hunt_highres_lidar_argentina`: Consulta en tiempo real las APIs de OpenTopography, Zenodo y el IGN.
* `tool_vlm_judge_candidate`: Construye el prompt pericial estructurado con las métricas cuantitativas y la lámina compuesta.
* `tool_record_vlm_verdict`: Registra el veredicto oficial, archiva descartes en `DESCARTES_VLM.json` + `INVENTARIO_GEOMORFOLOGICO.geojson` y regenera el dossier INAPL.
* `tool_inspect_candidate`: Genera la lámina compuesta de 4 paneles (2x2) con el modelo 3D de Blender.
* `tool_process_lidar_dtm`: Filtra la nube de puntos con SMRF (ASPRS Clase 2) y proyecta a GeoTIFF POSGAR 2007.

---

## 4b. Calibrador ML Supervisado (probabilidad calibrada)

El score heurístico morfológico se reemplaza por una **probabilidad calibrada** (`ml_probability`) cuando existe el modelo entrenado en `data/processed/ml_calibrator.joblib`:

```bash
# Entrenar/re-entrenar el calibrador y regenerar el benchmark de métricas
./venv/bin/python -c "from src.core.ml_calibrator import train_calibrator; print(train_calibrator())"
```

- **Clase 0 (hard negatives):** descartes reales auditados por el Juez Pericial (`DESCARTES_VLM.json`).
- **Clase 1 (positivos):** estructuras sintéticas plantadas con verdad de campo conocida.
- Métricas (precision/recall/F1 por clase, macro) e importancias de features en
  `data/reports/ML_BENCHMARK_METRICS.md`. **Re-entrenar** cada vez que se agreguen
  candidatos auditados o se confirme un hallazgo en campo.
- Si el modelo no existe, el sistema degrada al score heurístico (los resultados de esa
  corrida deben etiquetarse como no calibrados).
- **Modo de uso (`--ml-mode`):**
  - `advisory` (default): el ML puntúa cada candidato (`ml_probability` en props y contexto
    del Juez VLM) pero el filtro de entrada usa el score heurístico. Motivo: el calibrador
    actual presenta sesgo de resolución (positivos sintéticos 0.5 m/px vs negativos GLO-30)
    y en modo `filter` anula la totalidad de candidatos de zonas satelitales nuevas.
  - `filter`: la probabilidad ML es el umbral de entrada. Usar solo cuando el modelo esté
    re-entrenado con positivos reales de la misma resolución.

---

## 4c. Vigilancia Patrimonial: Protocolo `ALERTA_SAQUEO` (Ley 25.743)

Cuando un hundimiento cerrado **circular de 5–25 m de diámetro** con dZ negativo aparece a
**< 1000 m** de un sitio del catálogo (`known_sites.gpkg`), con contexto `historic=*` en OSM
o asentamiento/infraestructura IGN, el candidato recibe `patrimonial_priority: ALERTA_SAQUEO`:

1. El prompt del Juez VLM incluye la instrucción de analizar evidencia de excavación ilegal
   (bordes netos, escombro perimetral, fondo irregular) y notificar al INAPL.
2. El Dossier INAPL del candidato se emite con sección de denuncia prioritaria (art. 20 y 23).
3. La distancia al sitio, diámetro y contexto quedan registrados en props y anexo confidencial.
4. Este es un flujo de **denuncia urgente**, no de prospección ordinaria: nunca esperar al
   lote de descartes; registrar y comunicar de inmediato.

---

## 4d. Inventario Geomorfológico Secundario

Cada descarte `NATURAL` alimenta `data/reports/INVENTARIO_GEOMORFOLOGICO.geojson` con su
subtipo etiquetado (paleocauce, médano fósil, morrena, escarpa, cono aluvial, roca
fracturada, domo volcánico, canchal, albardón, lomada). Al informar resultados a terceros
(hidrogeología, geomorfología, gestión de riesgo), citar este inventario como subproducto
científico del descarte pericial. Regenerarlo completo:

```bash
./venv/bin/python -c "from src.core.geoform_inventory import backfill_inventory_from_descartes; print(backfill_inventory_from_descartes('./data/reports'))"
```

---

## 5. Protocolo de Evaluación del Juez Pericial VLM

Para mantener la regla estricta de **0 falsos positivos**, todo candidato debe ser clasificado en una de las 4 categorías:

1. **`ANTROPICA`**: Estructura arqueológica confirmada (recinto ortogonal, muro pircado, casa-pozo, cerrito con evidencia inequívoca, etc.). Se preserva en `MAPA_FINAL_PROSPECCION.geojson`.
2. **`NATURAL`**: Geoforma geomorfológica natural (albardón aluvial, cresta de erosión, espolón periglacial, médano eólico, gendarme de cumbre, bloque ignimbrítico, vaguada/cauce). Se archiva en `DESCARTES_VLM.json`.
3. **`ARTEFACTO`**: Rasgo antrópico moderno (mesa de sensor científico / *hail pad*, canal de riego actual, terraplén vial, corte de maquinaria) o anomalía de interpolación del raster (efecto de borde / costura de tile). Se archiva en `DESCARTES_VLM.json`.
4. **`PENDIENTE_REVISION`**: Estado transitorio antes del juicio visual multimodal.

**Contexto de validación previa al juicio:** el prospector ya clasifica cada candidato con `_classify_validation_outcome` (IGN WFS + Overpass OSM + catálogo de sitios registrados):
- `SITIO_REGISTRADO` → coincide con un sitio publicado del catálogo o etiquetado `historic=archaeological_site|ruins` en OSM (no es inédito).
- `FALSO_POSITIVO_MODERNO` → infraestructura moderna cercana (edificios, alambrados en OSM, asentamientos IGN a ≤ 150 m con geometría medible).
- `CANDIDATO_INEDITO` → sin coincidencias: es el único caso que requiere el juicio VLM completo.

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
5. `data/known_sites.gpkg`: GeoPackage de sitios arqueológicos publicados (fuente curada: `data/known_sites_published.csv`, coordenadas aproximadas ±100 m) usado para clasificar `SITIO_REGISTRADO`. Regenerar con `scripts/build_known_sites_gpkg.py` tras editar el CSV.

> **Recordatorio de confidencialidad (Ley 25.743):** los dossiers públicos omiten coordenadas exactas;
> los GeoJSON de resultados por zona contienen geometría precisa y NO deben publicarse ni difundirse
> fuera del entorno de trabajo autorizado.

---

## 7. Referencias Metodológicas (papers por técnica)

Cada técnica del pipeline tiene precedente científico publicado; este proyecto agrega el empaquetado
autónomo, la calibración por bioma y el marco legal argentino:

| Técnica | Módulo | Referencia |
| :--- | :--- | :--- |
| SLRM (modelo de relieve local) | `relief_models.py` | Hesse, R. (2010). *LiDAR-derived Local Relief Models – a new tool for archaeological prospection*. Archaeological Prospection, 17(2), 67–72. |
| Visualizaciones de relieve (hillshade, pendiente) | `visual_inspector.py` | Kokalj, Ž. & Hesse, R. (2019). *Relief Visualisation Toolbox (RVT)*, ZRC SAZU; Zakšek, Oštir & Kokalj (2011), *Remote Sensing* 3(2). |
| Detección morfométrica sobre modelos de relieve | `anomaly_detector.py` | Guyot, A. et al. (2018). *Remote Sensing*, 10(2), 225 (Random Forest multi-escala, Carnac). |
| ML sobre LiDAR para rasgos arqueológicos | `anomaly_detector.py` | Verschoof-van der Vaart & Lambers (2019), *J. Comp. Apps. Archaeology* 2(1); Trier et al. (2020), *Int. J. Applied Earth Obs. Geoinformation* (Faster R-CNN, Noruega). |
| Calibrador ML con hard negatives a mega-escala | `ml_calibrator.py` | Berganzo-Besga, Orengo et al. (2021), *Remote Sensing* 13(20), 4181 (Galicia, 30.000 km²); ADAF (2026), *J. Archaeological Science: Reports*; Orengo et al. (2020), *PNAS* 117(33). |
| Juez pericial multimodal | `vlm_judge.py` | Zheng, L. et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. NeurIPS 36. |
| Vigilancia de saqueo por teledetección | `looting_monitor.py` | Parcak, S. et al. (2016). *Satellite evidence of archaeological site looting in Egypt: 2002–2013*. Antiquity, 90(350). |
| LiDAR y ocupación prehispánica sudamericana | contexto | Canuto et al. (2018), *Science* 361 (PACUNAM, Petén); Prümers et al. (2022), *Nature* (Casarabe, Llanos de Mojos). |

**Posicionamiento:** el estado del arte entrena redes (YOLO/R-CNN/U-Net) con datos etiquetados de
alta resolución; este sistema opera de forma autónoma sobre DEM satelitales públicos con calibración
por bioma, calibrador ML alimentado por descartes reales y salida documental legal. El
`ML_BENCHMARK_METRICS.md` declara sus limitaciones explícitamente.
