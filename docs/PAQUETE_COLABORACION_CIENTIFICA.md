# Paquete de Colaboración Científica Interinstitucional — ArchaeoLiDAR-AR

**Destinatarios propuestos:**  
- **INAPL** — Instituto Nacional de Antropología y Pensamiento Latinoamericano (Autoridad Nacional de Aplicación — Ley N° 25.743 / RENYCOA)  
- **FFyL-UBA** — Instituto de Arqueología, Facultad de Filosofía y Letras (Universidad de Buenos Aires)  
- **IMHICIHU-CONICET** — Instituto Multidisciplinario de Historia y Ciencias Humanas (CONICET)  
- **IGN** — Instituto Geográfico Nacional  
- **AAPRA** — Asociación de Arqueólogos Profesionales de la República Argentina (marco ético-metodológico de evaluación profesional)

---

## 1. Resumen Ejecutivo Técnico

`ArchaeoLiDAR-AR` es un entorno de software abierto diseñado como **herramienta de apoyo técnico para priorización topográfica y teledetección arqueológica** sobre territorio argentino (proyección oficial **POSGAR 2007**, Fajas 1–7, `EPSG:5343–5349`).

### Qué SÍ es y qué NO pretende ser
- **SÍ es:** Un motor reproducible de procesamiento geodésico y morfométrico (SLRM NaN-safe, Pendiente, SVF, Openness positivo/negativo, clustering espacial, contexto espectral Sentinel-2 NDVI/NDWI y láminas periciales multi-panel) con trazabilidad completa de descartes.
- **NO es (ni afirma ser sin validación externa):** Un descubridor automático autónomo de sitios arqueológicos, un sustituto del criterio arqueológico especialista ni un sistema habilitado para realizar campañas o difundir localizaciones precisas al margen de la normativa patrimonial vigente.

Actualmente el proyecto completó la **Etapa 0** (manifiesto único reproducible y 7 estados formales de evidencia) y la **Etapa 1** (auditoría geoespacial, perfil de calidad de sensores y suite de 8 pruebas deterministas), y ofrece el **esquema del Benchmark Nacional V1** para construir su evaluación empírica junto a equipos académicos y organismos públicos.

---

## 2. Esquema de Colaboración y Roles Propuestos

| Institución | Contribución Técnica / Científica Propuesta | Retorno / Beneficio Directo |
| :--- | :--- | :--- |
| **INAPL** | Lineamientos de gobernanza conforme Ley N° 25.743; criterios de anonimización/desfasaje de coordenadas y revisión del formato de dossiers técnicos | Herramienta estandarizada de cribado y priorización previa para evaluación patrimonial sin exposición pública de yacimientos |
| **FFyL-UBA & IMHICIHU-CONICET** | Co-curaduría de sitios de referencia y **negativos difíciles** regionales (geoformas naturales y obras modernas); participación de especialistas en el **panel ciego (Etapa 5)** y dirección científica de eventual contraste en terreno (Etapa 6) | Automatización reproducible de láminas (Hillshade/SLRM/SVF/NDVI), benchmark nacional publicable conjuntamente (coautoría científica) y ahorro de horas de gabinete |
| **IGN** | Articulación técnica para uso acotado de **MDE 5 m (WCS / vuelos aerofotogramétricos)** en áreas piloto y comparación sistemática frente a **MDE-Ar v2.1 (30 m, ~2 m vertical)** | Validación cuantitativa de aptitud microtopográfica de productos geodésicos nacionales en distintos biomas argentinos |
| **AAPRA** | Revisión de protocolo ético-profesional para publicación responsable de resultados, evaluación ciega e historial de trazabilidad | Estándar de buenas prácticas para IA aplicada a patrimonio cultural en Argentina |

---

## 3. Protocolo de Evaluación Ciega con Especialistas (Etapa 5)

Inspirado en las recomendaciones de **Casana (2021)** y **Vinci et al. (2024)**, ningún especialista evaluador recibirá inicialmente el score ni la etiqueta sugerida por el módulo ML/VLM, evitando el sesgo de confirmación:

1. **Muestra mixta anonimizada:** Se prepara un lote balanceado por bioma con:
   - Anomalías provenientes de sitios arqueológicos reales conocidos (a escala compatible con el sensor: `sensor_detectable=True`).
   - **Negativos difíciles** seleccionados (5 tipos naturales: `cauce_seco`, `carcava`, `terraza_fluvial`, `cono_deyeccion`, `afloramiento_rocoso`; 5 tipos modernos: `cantera`, `terraplen_moderno`, `camino_rural`, `obra_hidraulica`, `terraza_agricola_reciente`).
   - Candidatos inéditos preseleccionados en bloques de test ciego (`blind_test`).
2. **Material entregado por ítem (ID opaco `BLIND-XXXX`):**
   - Lámina visual multi-panel (Hillshade multi-direccional, SLRM, Perfil topográfico 2D, Vista 3D/Pendiente, Chip RGB satelital y Mapa NDVI/NDWI) **sin coordenadas geográficas visibles en la imagen** ni scores de IA.
   - Metadatos físicos neutros: resolución nativa real (`DEMQualityProfile`), dimensiones métricas estimadas, relieve relativo (Δz) y bioma general.
3. **Dictamen individual independiente (≥ 2–3 especialistas por lote):** Cada evaluador clasifica el ítem en una de las categorías formales (`EXPERT_REVIEWED` compatible con rasgo antrópico antiguo / `REJECTED_NATURAL` / `REJECTED_MODERN` / `INCONCLUSIVE`) indicando rasgos diagnósticos y confianza (1–5).
4. **Cierre estadístico:** Se computa concordancia inter-evaluador ($\kappa$ de Fleiss/Cohen), recall operable sobre sitios detectables con IC 95 % de Wilson, falsos positivos por $\text{km}^2$ y matriz de confusión por tipo de negativo difícil.
5. **Auditoría de desacuerdos:** Análisis cualitativo conjunto de casos donde el algoritmo falló o superó la inspección inicial, retroalimentando la Etapa 6 (terreno) y la Etapa 7 (versión V2.0).

---

## 4. Seguridad Geodésica y Resguardo Patrimonial (Ley N° 25.743)

El software incorpora salvaguardas técnicas alineadas con la **Ley Nacional N° 25.743** (especialmente **artículos 23 y 24**, relativos a la autorización de prospecciones, registro obligatorio ante la autoridad de aplicación y prevención de destrucción o tráfico ilícito):

- **Aislamiento de coordenadas precisas:** Ningún archivo con polígonos exactos (`*ANEXO_CONFIDENCIAL_COORDENADAS.json`, `*MAPA_PROSPECCION_*.geojson`, `*MAPA_FINAL_PROSPECCION.geojson`) se versiona en el repositorio público (bloqueo explícito en `.gitignore`).
- **Purga automática de descartes:** Al marcarse una anomalía como `NATURAL` o `ARTEFACTO`, `record_vlm_verdict()` elimina sus geometrías precisas de los mapas activos, conservando únicamente trazabilidad de auditoría y metadatos agregados.
- **Separación estricta de estados:** Todo reporte o visualización de una anomalía detectada por software lleva el rótulo explícito `ALGORITHMIC_DETECTION` o `AI_PREASSESSMENT`, prohibiendo presentarla como hallazgo arqueológico confirmado.
- **Regla de acceso diferenciado:**
  - *Abierto (Licencia MIT):* código fuente, perfiles sintéticos de prueba, esquema JSON del benchmark y métricas agregadas sin coordenadas.
  - *Restringido bajo convenio institucional:* rasters de alta resolución aportados por socios, shapefiles/GeoPackage de sitios reales y anexos de coordenadas de prospección.

---

## 5. Cronograma de Trabajo Conjunto (6 Meses)

- **Mes 1 (Etapas 0–1 completadas + contacto inicial):** Presentación del paquete técnico, firma de acuerdos de confidencialidad/uso de datos y selección de 2–3 áreas piloto de biomas contrastantes (ej. NOA prepuneño, Yungas/selva montana y estepa patagónica).
- **Mes 2 (Etapa 2):** Curaduría conjunta de bloques espaciales (`region_block_id`) e integración de las 10 categorías de negativos difíciles sin fuga espacial (`Roberts et al. 2017`).
- **Mes 3 (Etapa 3):** Calibración probabilística sobre partición de desarrollo/validación, fijación de umbrales de abstención (`should_abstain_prediction`) y congelamiento del conjunto `blind_test`.
- **Mes 4 (Etapa 4):** Corridas comparativas sobre vuelos LiDAR/UAV (< 1 m) y MDE 5 m del IGN frente a cobertura nacional de 30 m.
- **Mes 5 (Etapa 5):** Sesión de evaluación ciega con especialistas de UBA/CONICET/INAPL y análisis inter-evaluador.
- **Mes 6 (Etapas 6–7):** Contraste acotado en terreno (bajo permiso vigente art. 23–24 Ley 25.743) en la o las localidades viables, cierre de métricas V2.0 y redacción de manuscrito científico conjunto.

---

## 6. Plantilla de Nota de Presentación Institucional

> **Asunto:** Propuesta de colaboración científico-técnica: validación interdisciplinaria de software abierto para priorización topográfica arqueológica (`ArchaeoLiDAR-AR`)
>
> Estimadas autoridades y equipos de investigación de [INAPL / Instituto de Arqueología FFyL-UBA / IMHICIHU-CONICET / IGN]:
>
> Nos dirigimos a ustedes con el objetivo de proponer una línea de trabajo colaborativo en torno a `ArchaeoLiDAR-AR`, una herramienta de software abierto orientada a asistir la detección y priorización de anomalías microtopográficas potencialmente compatibles con estructuras arqueológicas en territorio argentino.
>
> Lejos de plantear una automatización acrítica del registro arqueológico, el proyecto parte de una premisa metodológica estricta: una detección algorítmica sobre un modelo de elevación requiere auditoría física de escala, calibración frente a geoformas naturales e infraestructuras modernas, evaluación ciega por especialistas y contraste autorizado en terreno conforme a la Ley Nacional N° 25.743.
>
> Actualmente contamos con una línea base congelada, auditoría geoespacial automatizada (POSGAR 2007, SLRM, SVF, Openness y control físico de resolución) y la estructura inicial de un Benchmark Nacional por bloques espaciales. Buscamos conformar un grupo piloto para: (1) definir los protocolos de resguardo geodésico de coordenadas, (2) curar un conjunto representativo de sitios detectables y negativos difíciles en 2–3 biomas argentinos sobre datos de alta resolución (< 5 m y < 1 m), y (3) ejecutar una evaluación ciega con arqueólogos/as especialistas.
>
> Adjuntamos el dossier técnico completo y el Plan Maestro de Validación de 6 meses, quedando a plena disposición para coordinar una reunión introductoria y acordar condiciones institucionales de acceso restringido a datos de referencia.
>
> Saludan atentamente,  
> [Equipo / Responsable ArchaeoLiDAR-AR]
