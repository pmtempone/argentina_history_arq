# Kit de Publicación para ResearchGate — ArchaeoLiDAR-AR

Esta guía contiene todos los campos listos para copiar y pegar al subir el manuscrito [`ArchaeoLiDAR_AR_ResearchGate_Preprint.pdf`](ArchaeoLiDAR_AR_ResearchGate_Preprint.pdf) a **ResearchGate**, junto con la verificación final de confidencialidad conforme a la **Ley Nacional N° 25.743**.

---

## 1. Tipo de Publicación Recomendado en ResearchGate

* **Publication Type:** `Preprint` *(permite asignar un **DOI gratuito de ResearchGate** de forma inmediata si el trabajo aún no fue enviado a una revista con referato, o vincular un **DOI de Zenodo** al archivar el release del repositorio)*.
* **Alternativa si preferís no usar Preprint:** `Technical Report` o `Methodological Paper / Working Paper`.
* **Archivo a subir:** `docs/paper/ArchaeoLiDAR_AR_ResearchGate_Preprint.pdf` (Full-text PDF, acceso público).
* **Fecha de publicación:** `November 2026`
* **Idioma:** `Spanish (with Bilingual English Abstract)`

---

## 2. Título (Copiar y Pegar)

### Título Principal (Español — recomendado para el campo Title si tu audiencia principal es Argentina/CONICET/INAPL)
```text
ArchaeoLiDAR-AR: Plataforma Autónoma Multisatélite con Calibración Epistémica, Protocolo Ciego y Resguardo Geodésico (Ley N° 25.743) para Prospección Arqueológica en Argentina
```

### Título en Inglés (para subtítulo, versión internacional o metadata alternativa)
```text
ArchaeoLiDAR-AR: An Autonomous Multi-Satellite Platform with Epistemic Calibration, Blind Review Protocol, and Geodetic Safeguards (Argentine Law No. 25,743) for Archaeological Prospection
```

---

## 3. Abstract (Copiar y Pegar en ResearchGate)

> ResearchGate recomienda cargar el **Abstract en inglés** (o bilingüe) para maximizar la indexación internacional y las citas cruzadas. Podés pegar directamente cualquiera de las dos versiones (o ambas separadas por `---`).

### Versión Bilingüe Recomendada (Inglés + Español)
```text
Archaeological remote sensing across Argentina faces three structural constraints: (i) the lack of uniform national airborne LiDAR coverage, requiring integration of global 30 m/px satellite Digital Elevation Models (DEMs) with sparse sub-metric UAV/LiDAR surveys; (ii) extreme physiographic diversity spanning eight macro-biomes (from High Andean sanctuaries above 4,600 m a.s.l. to Yungas montane forests, Paranaense rainforest, Paraná/Iberá wetlands, and the Patagonian steppe); and (iii) the legal and ethical mandate to safeguard precise site coordinates against looting (guaqueo) under Argentine National Law No. 25,743. This paper introduces ArchaeoLiDAR-AR (archaeo-lidar-mcp), an open-source reproducible platform exposed as a 13-tool FastMCP server and CLI pipeline for multi-resolution topographic prioritization. The architecture combines partial HTTP Range Request streaming (/vsicurl/) over Copernicus GLO-30, FABDEM V1-2, ALOS AW3D30, IGN MDE-Ar, and SMRF-filtered .las/.laz point clouds; automated projection into the seven official POSGAR 2007 Gauss-Krüger metric belts (EPSG:5343–5349); NaN-safe relief modeling (SLRM, Slope, 16-azimuth Sky-View Factor, and 8-azimuth Positive/Negative Openness); dual-sign OpenCV segmentation constrained by a mandatory two-pixel physical floor (A_min,eff = max(A_min,biome, 2 * GSD_native^2)); multi-source cadastral filtering (IGN WFS, OpenStreetMap Overpass, curated public sites ±100 m, OpenAlex/Semantic Scholar); selective Sentinel-2 L2A spectral context (NDVI/NDWI/dNDVI); headless Blender 4.2 EEVEE 3D rendering; ALERTA_SAQUEO looting-pit surveillance; isotonic-calibrated GradientBoostingClassifier scoring (5-fold StratifiedGroupKFold, macro F1 = 0.867 in advisory mode); and a formal INCONCLUSIVE abstention gate coupled to a preregistered double-blind multi-specialist evaluation protocol. Deterministic engine verification passes 8/8 physical-geospatial audit checks (64/64 total unit/integration tests). Across the consolidated 30-zone plus UAV campaign, the provenance-audited corpus (N = 121 evaluated anomalies; frozen snapshot baseline-v1.0: N = 126) isolated 81.0% (n = 98) natural landforms and 19.0% (n = 23) modern features or raster artifacts, achieving 0 false alarms forwarded to fieldwork while compiling an 81-feature secondary geomorphological inventory and 121 confidentiality-compliant INAPL technical dossiers.

---

Resumen (ES): La teledetección arqueológica en la República Argentina enfrenta cobertura LiDAR heterogénea, extrema diversidad entre ocho macro-biomas y la exigencia de resguardo geodésico frente al saqueo bajo la Ley Nacional N° 25.743. ArchaeoLiDAR-AR implementa un pipeline autónomo reproducible (servidor FastMCP de 13 herramientas + CLI) con lectura parcial por HTTP Range Requests, reproyección POSGAR 2007 (EPSG:5343–5349), modelado SLRM/SVF/Openness NaN-safe, segmentación en doble signo, calibración ML supervisada con validación espacial agrupada, vigilancia ALERTA_SAQUEO, regla formal de abstención (INCONCLUSIVE) y protocolo pre-registrado de evaluación ciega multi-especialista. La auditoría del motor supera 64/64 pruebas automáticas (8/8 auditorías físico-geoespaciales) y la campaña depurada por procedencia (N = 121 anomalías) alcanzó 0 falsas alarmas derivadas a terreno con 81 geoformas catalogadas en un inventario geomorfológico secundario.
```

---

## 4. Disciplines, Skills & Keywords (Etiquetas de ResearchGate)

* **Primary Disciplines:**
  * `Archaeology`
  * `Remote Sensing`
  * `Geomatics / Geographic Information Systems (GIS)`
  * `Geomorphology`
  * `Machine Learning`
* **Keywords / Skills (copiar separadas por coma):**
  `Archaeological Remote Sensing, LiDAR, Digital Elevation Models, Local Relief Model (SLRM), Sky-View Factor, Openness, POSGAR 2007, Argentina, Cultural Heritage Protection, Law 25743, Blind Evaluation, Machine Learning Calibration, FastMCP, Geomorphological Inventory, Looting Surveillance`

---

## 5. Código y Disponibilidad de Datos (Project / Supplementary Links)

* **Source Code Repository (MIT License):** `https://github.com/pmtempone/argentina_history_arq`
* **Supplementary Data Availability Statement (para pegar en ResearchGate):**
  > Source code, 64 automated unit/integration tests, `benchmark_v1_schema.json`, aggregated campaign manifests (`CAMPAIGN_MANIFEST.json`, `ML_BENCHMARK_METRICS.md`), preregistered validation protocols (Stages 4–5), and the reproducible figure generator (`docs/paper/generate_figures.py`) are publicly archived under the MIT License at https://github.com/pmtempone/argentina_history_arq. In strict compliance with Argentine National Law No. 25,743 (arts. 20, 23–24), precise coordinates of unpublished anomalies (`*ANEXO_CONFIDENCIAL_COORDENADAS.json`, `*CONFIDENTIAL_BLIND_KEY.json`, and zone GeoJSONs) are excluded from the public repository and shared exclusively under institutional agreements with INAPL, CONICET, IGN, and accredited university teams.

---

## 6. Cita BibTeX Lista

```bibtex
@unpublished{Tempone2026ArchaeoLiDAR,
  author = {Tempone, Pablo},
  title  = {{ArchaeoLiDAR-AR}: Plataforma Aut\'onoma Multisat\'elite con Calibraci\'on Epist\'emica, Protocolo Ciego y Resguardo Geod\'esico ({Ley N\textsuperscript{o}~25.743}) para Prospecci\'on Arqueol\'ogica en Argentina},
  year   = {2026},
  month  = {nov},
  note   = {ResearchGate Preprint / Technical Paper. Code available at \url{https://github.com/pmtempone/argentina_history_arq}},
  url    = {https://github.com/pmtempone/argentina_history_arq}
}
```

---

## 7. Checklist Pre-Subida de Confidencialidad (Ley Nacional N° 25.743)

- [x] **Cero coordenadas de candidatos inéditos:** ni el texto ni las Figuras 1–7 revelan coordenadas puntuales WGS84 ni POSGAR 2007 de anomalías no publicadas.
- [x] **Mapa Nacional (Figura 2):** grafica exclusivamente centroides regionales generalizados de las 30 zonas de `TARGET_ZONES`, el relevamiento meteorológico público UAV de San Rafael (`ZENODO:3383227`, Soderholm 2019) y los 9 sitios turísticos publicados ($\pm 100\,\mathrm{m}$) de `known_sites_published.csv`.
- [x] **Casos de Estudio (Figuras 5 y 6):** muestran únicamente 3 anomalías explícitamente auditadas y **descartadas** como no patrimoniales (`ARQ-TEY-0005` `NATURAL` 89 %, `ARQ-MAN-0004` `NATURAL`, `ARQ-HRM-0001` `ARTEFACTO` 98 %).
- [x] **Paquete Ciego (Figura 7):** las láminas `BLIND-0001` y `BLIND-0002` operan en ejes métricos locales (`0..W m`, `0..H m`) y relieve relativo $\Delta z$ centrado en la mediana, con verificación `strip_png_metadata_and_verify()`.
- [x] **Integridad científica:** se reconcilian explícitamente `baseline-v1.0` (`N = 126`) y el corpus depurado tras la purga de `ZENODO:18023344` (`N = 121`), declarando `FIELD_CONFIRMED = 0` y modo ML `advisory`.
