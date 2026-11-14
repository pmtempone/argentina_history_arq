# Plan Maestro de Validación Científica Progresiva — ArchaeoLiDAR-AR

**Horizonte:** Programa de investigación aplicada de **6 meses (24 semanas)**  
**Propósito:** Demostrar, mediante datos independientes, métricas espacialmente bloqueadas y revisión ciega de especialistas, que `ArchaeoLiDAR-AR` puede **identificar y priorizar anomalías microtopográficas compatibles con evidencias arqueológicas**, distinguiéndolas de geoformas naturales y estructuras antrópicas modernas.

> **Principio rector:** Validar que un algoritmo segmenta *anomalías del terreno* **no equivale** a validar que descubre *sitios arqueológicos*. Este plan mide ambas dimensiones por separado y exige puertas de aprobación verificables entre etapas.

---

## 1. Arquitectura de Etapas y Puertas de Aprobación

| Etapa | Semanas | Foco Principal | Estado en Código | Puerta de Aprobación (Criterio para Avanzar) |
| :--- | :---: | :--- | :---: | :--- |
| **0** | 1 | Congelar línea base, fuente única de verdad y esquema de estados | **Implementado** | Reconstrucción determinista de campaña a partir de config + datos + commit/tag Git (`CAMPAIGN_MANIFEST.json`) |
| **1** | 2–4 | Auditoría científica del motor (calidad DEM, SVF/Openness, evidencia observable, 8 tests) | **Implementado** | **8/8 tests** de auditoría física/geoespacial aprobados sin artefactos en bordes, NoData ni degradación multi-resolución |
| **2** | 5–8 | Diseño del Benchmark Nacional V1 (positivos + 10 clases de negativos difíciles + bloques espaciales) | **Implementado (`133` registros curados, `blind_test: 0`)** | Dataset curado multi-bioma particionado en bloques espaciales (`development` / `validation` / `blind_test`) con cero fuga ([`BENCHMARK_V1_DATASET.json`](../archaeo-lidar-mcp/data/reports/BENCHMARK_V1_DATASET.json)) |
| **3** | 9–12 | Calibración probabilística, regla de abstención (`INCONCLUSIVE`), métricas ML separadas y módulo de paquete ciego | **Implementado** | Abstención integrada en pipeline autónomo y MCP (`tool_run_full_pipeline`), paquete de láminas ciegas sin metadatos y cálculo de $\kappa$ operativos ([`src/core/blind_review.py`](../archaeo-lidar-mcp/src/core/blind_review.py)) |
| **4** | 13–16 | Evaluación comparativa sobre DEM/LiDAR/UAV de alta resolución reales (< 1–5 m/px vs. 30 m) en 2–3 biomas | Protocolo cerrado ([`PROTOCOLO_ETAPAS_4_Y_5.md`](PROTOCOLO_ETAPAS_4_Y_5.md)) | Contraste cuantificado apareado (30 m vs. 5 m / < 1 m) en ≥ 2–3 biomas con persistencia, recall estratificado e IoU |
| **5** | 17–20 | Evaluación ciega multi-especialista sobre láminas periciales anonimizadas | Protocolo cerrado ([`PROTOCOLO_ETAPAS_4_Y_5.md`](PROTOCOLO_ETAPAS_4_Y_5.md)) | Cumplimiento de condiciones pre-registradas de validez ($\kappa \ge 0.40$, $\kappa_{\text{cuad}} \ge 0.60$), concordancia reportada y auditoría de desacuerdos |
| **6** | 21–22 | Verificación en terreno autorizada (Ley N° 25.743, arts. 23–24) | Planificado | Inspección de campo dirigida por investigadores habilitados con transición formal a `FIELD_CONFIRMED` |
| **7** | 23–24 | Cierre reproducible V2.0 y publicación técnica | Planificado | Liberación de código y métricas agregadas con resguardo estricto de coordenadas sensibles |

---

## 2. Detalle Técnico por Etapa

### Etapa 0 — Congelar el estado actual y definir «validado» (Semana 1)

Se consolidó la línea de base reproducible en [`src/core/baseline_manifest.py`](../archaeo-lidar-mcp/src/core/baseline_manifest.py) y el generador CLI [`scripts/build_campaign_manifest.py`](../archaeo-lidar-mcp/scripts/build_campaign_manifest.py):

- **Fuente única de verdad:** Todo conteo operativo se genera programáticamente en [`CAMPAIGN_MANIFEST.json`](../archaeo-lidar-mcp/data/reports/CAMPAIGN_MANIFEST.json) y [`BASELINE_REPORT_V1.md`](../archaeo-lidar-mcp/data/reports/BASELINE_REPORT_V1.md), eliminando cifras discrepantes mantenidas a mano en distintos documentos.
- **Esquema formal de estados (`CandidateLifecycleState` en `src/schemas.py`):**
  1. `ALGORITHMIC_DETECTION`: El algoritmo detectó una anomalía topográfica.
  2. `AI_PREASSESSMENT`: Un modelo de IA (calibrador ML o juez VLM) realizó una evaluación preliminar. **Nunca** se promueve automáticamente a revisión experta ni a confirmación de campo.
  3. `EXPERT_REVIEWED`: Un especialista humano acreditado auditó la lámina pericial y sus metadatos.
  4. `FIELD_CONFIRMED`: Evidencia verificada presencialmente en terreno con autorización legal competente.
  5. `REJECTED_NATURAL`: Descartado como geoforma natural.
  6. `REJECTED_MODERN`: Descartado como infraestructura moderna o artefacto digital.
  7. `INCONCLUSIVE`: La resolución disponible o la ambigüedad impiden decidir (abstención formal).
- **Familias de anomalías (`AnomalyFamilyLiteral`):** `POTENTIAL_ANTHROPOGENIC`, `GEOMORPHOLOGICAL`, `MODERN`.
- **Registro explícito de alcance (`CLAIMS_REGISTRY`):** Listado auditado de afirmaciones permitidas vs. afirmaciones que requieren evidencia de campo externa.

**Estado actual observado en `BASELINE_REPORT_V1.md`:** 30 entradas en catálogo, 126 descartes registrados (`103` `REJECTED_NATURAL`, `23` `REJECTED_MODERN`), 86 geoformas en `INVENTARIO_GEOMORFOLOGICO.geojson` y 0 candidatos confirmados en `MAPA_FINAL_PROSPECCION.geojson`.

---

### Etapa 1 — Auditoría científica y geoespacial del motor (Semanas 2–4)

#### 1.1 Perfil de calidad y aptitud de escala (`src/core/dem_quality.py`)
`audit_dem_quality()` inspecciona cada GeoTIFF generando un `DEMQualityProfile` que registra:
- Tipo de modelo (`DSM`, `DTM`, `DEM`), código EPSG (POSGAR 2007), resolución de grilla vs. **resolución nativa real**, precisión vertical estimada, cobertura válida, fracción de vacíos (`void_fraction`), vacíos perimetrales (`border_nodata_fraction`) y etiqueta `SYNTHETIC_FALLBACK`.
- **Restricción física explícita (MDE-Ar v2.1 / GLO-30):** Un modelo de 30 m/px (como MDE-Ar v2.1 del IGN, ~2 m de error vertical nominal, o Copernicus GLO-30) **no es apto para microtopografía** (`suitable_for_microtopography=False`): con el piso físico mínimo de 2 píxeles nativos ($2 \times 30^2 = 1800\text{ m}^2$), sirve para macro-geoformas y complejos extensos (> 0.2 ha), jamás para muros angostos o casas-pozo pequeñas.

#### 1.2 Modelos de relieve y trazabilidad (`src/core/relief_models.py`)
Además de **SLRM NaN-safe** y **Pendiente**, se incorporaron:
- **Sky-View Factor (SVF)** multi-direccional (16 acimutes, horizonte por ventana métrica configurable) sin *wrap-around* en bordes ni propagación espuria de NoData, siguiendo **Kokalj & Hesse (2017)** y **Kokalj et al. (2025)**.
- **Positive Openness (PO)** y **Negative Openness (NO)** para resaltar crestas, recintos amurallados, zanjas y estructuras negativas independientemente de la dirección de iluminación.
- **Sidecar de parámetros (`*_relief_params.json`):** Persiste radio SLRM, algoritmo, percentiles de contraste, parámetros SVF/Openness y perfil de calidad junto a cada corrida.

#### 1.3 Separación entre saliencia topográfica y probabilidad arqueológica (`src/core/anomaly_detector.py`)
Cada feature de `detect_anomalies()` incluye un bloque `observable_evidence` con descriptores geométricos medibles (`rectangularity`, `circularity`, `aspect_ratio`, `dimensions_m2`, `relative_relief_m`, `min_area_effective_m2`, `physical_floor_applied`, `pixel_area_m2`) y la etiqueta explícita `score_interpretation = "geometric_topographic_salience_not_archaeological_probability"`.

#### 1.4 Suite de 8 pruebas técnicas obligatorias (`tests/test_engine_scientific_audit.py`)
1. Raster sintético conocido (recuperación positiva y negativa + esquema de evidencia).
2. Raster plano y rampa planar uniforme (0 anomalías espurias).
3. Vacíos internos `NoData` y bordes incompletos (sin falsos anillos en SLRM, SVF ni OpenCV).
4. Degradación multi-resolución (1 m vs. 30 m con bloqueo físico a 1800 m²).
5. Consistencia métrica entre fajas POSGAR 2007 (`EPSG:5344` vs. `EPSG:5345`, tolerancia < 2 %).
6. Invariancia rotacional de SLRM/SVF/Openness frente a rotación de `90°` y anisotropía controlada de hillshade.
7. Robustez frente a ruido gaussiano y erosión gaussiana moderada.
8. Determinismo bit-a-bit bajo ejecuciones idénticas repetidas.

---

### Etapa 2 — Diseño del Benchmark Nacional V1 (Semanas 5–8)

Implementado estructuralmente en [`src/core/benchmark_v1.py`](../archaeo-lidar-mcp/src/core/benchmark_v1.py), [`data/benchmark_v1_schema.json`](../archaeo-lidar-mcp/data/benchmark_v1_schema.json) y validado por [`tests/test_benchmark_v1.py`](../archaeo-lidar-mcp/tests/test_benchmark_v1.py):

- **Sitios positivos con control de escala:** `BenchmarkEntry` calcula o verifica `sensor_detectable = (expected_feature_area_m2 >= 2 * dem_resolution_m^2)`. Sitios arqueológicos pequeños evaluados sobre 30 m se registran como `sensor_detectable=False` y **se excluyen del denominador computable** (`excluded_undetectable_sites`) para no exigir milagros físicos ni penalizar falsamente métricas de detección.
- **Taxonomía obligatoria de 10 clases de negativos difíciles (`HardNegativeCategory`):**
  - *5 geoformas naturales:* `cauce_seco`, `carcava`, `terraza_fluvial`, `cono_deyeccion`, `afloramiento_rocoso`.
  - *5 estructuras modernas:* `cantera`, `terraplen_moderno`, `camino_rural`, `obra_hidraulica`, `terraza_agricola_reciente`.
- **Partición espacial bloqueada (`assign_spatial_block_splits`):** Siguiendo **Roberts et al. (2017)**, la asignación a `development` (60 %), `validation` (20 %) y `blind_test` (20 %) opera por `region_block_id` completo, garantizando cero fuga por autocorrelación espacial (en línea con las alertas de **Vinci et al. 2024** y **Weak Supervision LiDAR 2026**).

---

### Etapa 3 — Calibración, abstención formal y métricas de campaña (Semanas 9–12)

- **Regla formal de abstención (`should_abstain_prediction`):** El sistema debe abstenerse (`INCONCLUSIVE`) ante cualquiera de 4 condiciones objetivas:
  1. DEM derivado de `SYNTHETIC_FALLBACK`.
  2. Fracción de vacíos `NoData > 25 %`.
  3. Área objetivo menor que el piso físico del sensor (`min_detectable_area_m2`).
  4. Probabilidad calibrada dentro de la banda operativa de incertidumbre (`[0.35, 0.65]`).
- **Métricas de campo (`compute_benchmark_metrics`):**
  - *Recuperación operable:* Recall por sitio computable + intervalo de confianza del 95 % de Wilson.
  - *Carga operativa de gabinete/campo:* `precision_at_k` (`@5`, `@10`) y `false_positives_per_km2`.
  - *Fidelidad geométrica:* Distancia media de centroide (m) e IoU espacial sobre verdaderos positivos.
  - *Calibración probabilística:* `pr_auc`, `brier_score` y `calibration_bins` (**ML Best Practices 2026**).
  - *Desglose por bioma (`by_biome`):* Prohíbe promediar silenciosamente biomas áridos abiertos (ej. Puna/Prepuna) con biomas arbóreos complejos (ej. Yungas/Selva Paranaense).

---

### Etapas 4 a 7 — Validación empírica, evaluación ciega y terreno (Semanas 13–24)

Las **Etapas 4 a 7** dependen de insumos externos e institucionales descritos en detalle en el [Paquete de Colaboración Científica](PAQUETE_COLABORACION_CIENTIFICA.md):
- **Etapa 4:** Pruebas piloto apareadas con rasters reales de alta resolución (< 1 m UAV/LiDAR y 5 m IGN) contrastados frente a GLO-30 / MDE-Ar v2.1 en 2–3 biomas según criterios de inclusión/exclusión del [Protocolo Pre-registrado Etapas 4 y 5](PROTOCOLO_ETAPAS_4_Y_5.md).
- **Etapa 5:** Estudio ciego multi-especialista inspirado en **Casana (2021)** y regido íntegramente por el [Protocolo Pre-registrado Etapas 4 y 5](PROTOCOLO_ETAPAS_4_Y_5.md) (distinguiendo el piloto exploratorio de `12` láminas del lote confirmatorio sobre `blind_test`, con planilla `evaluator_sheet_template.csv` y umbrales explícitos de validez).
- **Etapa 6:** Contrastación en terreno exclusivamente bajo permisos vigentes (Ley N° 25.743, arts. 23–24) y dirección arqueológica acreditada.
- **Etapa 7:** Publicación de informe técnico v2.0 con resultados por bioma, curva costo-beneficio para priorización de campaña y preservación estricta de la confidencialidad espacial.

---

## 3. Referencias Bibliográficas y Normativas Operativas

- **Casana, J. (2021).** *Rethinking the Role of Machine Learning and Automated Detection in Archaeological Remote Sensing* (evaluación ciega, carga real de falsos positivos y sesgo de confirmación).
- **Kokalj, Ž., & Hesse, R. (2017).** *Airborne Laser Scanning Raster Data Visualization: A Guide to Good Practice.* Založba ZRC, Ljubljana. (SLRM, Sky-View Factor, Openness positivo/negativo, hillshade multi-direccional).
- **Kokalj, Ž., et al. (2025).** Buenas prácticas actualizadas de visualización de relieve ALS y trazabilidad de parámetros en arqueología del paisaje.
- **Roberts, D. R., et al. (2017).** *Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure.* Ecography, 40(8), 913–929. (Partición por bloques espaciales anti-fuga).
- **Vinci, G., et al. (2024).** Sesgos de escala, curaduría de negativos difíciles y brechas de generalización regional en detección remota arqueológica sobre LiDAR/DEM.
- **Weak Supervision LiDAR (2026) & ML Best Practices (2026).** Calibración con N pequeño, control estricto de fuga espacial y rechazo/abstención en modelos de teledetección.
- **Ley Nacional N° 25.743 (Argentina).** Protección del Patrimonio Arqueológico y Paleontológico (y Decreto Reglamentario 1022/2004), particularmente **artículos 23 y 24** sobre concesiones, autorizaciones de prospección y resguardo de localización de yacimientos.
