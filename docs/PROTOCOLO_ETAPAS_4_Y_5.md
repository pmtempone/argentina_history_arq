# Protocolo Científico Pre-registrado — Etapas 4 y 5 (Validación Multi-Resolución y Evaluación Ciega)

**Estado del protocolo:** Cerrado y pre-registrado previo al envío de láminas a especialistas externos  
**Rama de referencia técnica:** `feat/national-benchmark-v1` (módulos base: [`src/core/dem_quality.py`](../archaeo-lidar-mcp/src/core/dem_quality.py), [`src/core/benchmark_v1.py`](../archaeo-lidar-mcp/src/core/benchmark_v1.py) y [`src/core/blind_review.py`](../archaeo-lidar-mcp/src/core/blind_review.py))  
**Documentos relacionados:** [Plan Maestro de Validación](PLAN_MAESTRO_VALIDACION.md) · [Paquete de Colaboración Científica](PAQUETE_COLABORACION_CIENTIFICA.md)

> **Regla fundamental de separación epistémica:** Las etapas 0 a 3 constituyen infraestructura de software y curaduría interna (`133` registros en `BENCHMARK_V1_DATASET.json`, con **`blind_test: 0`**). Este protocolo rige la producción de **evidencia externa e independiente** en las Etapas 4 y 5. Ninguna corrida interna, descarte de IA ni referencia bibliográfica aproximada ($\pm 100\text{ m}$) será tratada como prueba ciega ni como confirmación arqueológica.

---

## 1. Principio de Pre-registro: Lote Piloto de Instrumento vs. Evaluación Ciega Confirmatoria

Para evitar el *data leakage*, la circularidad o la reinterpretación *post-hoc* de una revisión exploratoria como prueba representativa, todo material exportado mediante [`scripts/build_blind_review_pack.py`](../archaeo-lidar-mcp/scripts/build_blind_review_pack.py) se clasifica estrictamente en una de dos instancias no intercambiables:

| Instancia | Origen permitido de los ítems | `blind_test` en Dataset | Finalidad permitida | Uso explícitamente prohibido |
| :--- | :--- | :---: | :--- | :--- |
| **Lote Piloto de Calibración de Instrumento (Exploratorio)** | `development` / `validation` (ej. el paquete piloto de `12` láminas `BLIND-0001`..`BLIND-0012`) | `0` (no elegible) | Verificar anonimización PNG/EXIF, legibilidad de ejes métricos locales (`0..W m`, `0..H m`), claridad de `EVALUATOR_INSTRUCTIONS.md` y consistencia operativa de la planilla CSV | **Prohibido** reportar sus tasas de acierto, recall o precisión como desempeño arqueológico independiente del detector |
| **Lote de Evaluación Ciega Independiente (Confirmatorio)** | Exclusivamente bloques espaciales (`region_block_id`) congelados en `blind_test` y controles curados bajo convenio institucional previo al test | Congelado antes de la entrega (`blind_test > 0`) | Medir concordancia inter-evaluador, especificidad frente a negativos difíciles y tasa de priorización útil con hipótesis cerradas | **Prohibido** re-etiquetar, ajustar umbrales ML/detector o excluir casos después de abrir `CONFIDENTIAL_BLIND_KEY.json` |

Antes de remitir cualquier lote confirmatorio a los especialistas, se registra el resumen criptográfico (`manifest_sha256` y `csv_template_sha256` emitidos en `BLIND_REVIEW_PACK_MANIFEST.json` y `CONFIDENTIAL_BLIND_KEY.json`) y se congela el parámetro `--seed`.

---

## 2. Etapa 4 — Protocolo de Comparación Multi-Resolución en 2–3 Biomas Contrastantes

### 2.1 Diseño apareado multi-escala
Se evaluarán ventanas geográficas estrictamente apareadas (idéntico polígono envolvente proyectado en **POSGAR 2007**, `EPSG:5343–5349`) comparando de forma sistemática tres escalas de resolución espacial nativa:

1. **Grilla gruesa nacional/global (`30 m/px`):** Copernicus GLO-30 / MDE-Ar v2.1 (IGN, error vertical nominal ~2 m).
2. **Grilla intermedia oficial (`5 m/px`):** MDE fotogramétricos del IGN u homólogos provinciales verificados.
3. **Alta resolución sub-métrica (`0.05 – 1.0 m/px`):** Vuelos LiDAR aerotransportados o fotogrametría UAV de repositorios abiertos/institucionales (ej. precordillera cuyana / valles del NOA).

La comparación deberá ejecutarse en al menos **2 a 3 biomas contrastantes** contemplados en `BenchmarkV1` (por ejemplo: `puna_alta_montana` / `noa_quebradas_valles` con cobertura vegetal escasa, `cuyo_precordillera` con piedemonte aluvial, y `yungas_selva` o `humedal_llanura` con cobertura arbórea o relieve fluvial complejo), prohibiendo promediar resultados entre biomas sin desglose explícito (`by_biome`).

### 2.2 Criterios de inclusión, exclusión y abstención de rasters (`DEMQualityProfile`)
Cada raster candidato será auditado previamente con `audit_dem_quality()` (`src/core/dem_quality.py`):

- **Criterios de inclusión:**
  - Proyección métrica verificada en POSGAR 2007 (`EPSG:5343–5349`) o reproyección sin distorsión de escala superior al `2 %`.
  - Procedencia documentada (producto `DTM`, `DSM` o `DEM`, fecha de adquisición, sensor, fuente institucional/DOI).
  - Resolución nativa real verificada en metadatos (se prohíbe computar suelo físico sobre un DEM de 30 m remuestreado artificialmente a 2 m sin preservar `dem_native_resolution_m = 30.0`).
  - Fracción de vacíos dentro de la región útil `void_fraction <= 0.25`.
- **Criterios de exclusión o abstención obligatoria (`should_abstain_prediction` -> `INCONCLUSIVE`):**
  - Rasters marcados como `SYNTHETIC_FALLBACK`.
  - Cobertura con `void_fraction > 0.25` o artefactos severos en bordes (`border_nodata_fraction`).
  - Rasgos o sitios objetivo cuya área esperada sea inferior al piso físico mínimo del sensor:

$$A_{\min} = 2 \cdot \text{GSD}_{\text{nativo}}^2$$

  Es decir: $1800\text{ m}^2$ para `30 m/px`, $50\text{ m}^2$ para `5 m/px` y $0.5\text{–}2.0\text{ m}^2$ para `0.5–1.0 m/px`. Toda anomalía incompatible con $A_{\min}$ se marca como `sensor_detectable = False` o `INCONCLUSIVE`, nunca como falso negativo del algoritmo ni como evidencia negativa de campo.

### 2.3 Métricas cuantitativas de estabilidad y detectabilidad
En cada ventana apareada se medirán cuatro indicadores:

1. **Tasa de persistencia y verificación inter-escala:** proporción de anomalías segmentadas en `30 m` que corresponden a geoformas o estructuras topográficas reales identificables en `< 1–5 m` frente a artefactos de interpolación de grilla gruesa.
2. **Ganancia de detectabilidad microtopográfica (`Recall` estratificado por área):** sensibilidad con IC del 95 % de Wilson en cuatro rangos de superficie ($< 50\text{ m}^2$, $50\text{–}500\text{ m}^2$, $500\text{–}1800\text{ m}^2$, $\ge 1800\text{ m}^2$) sobre controles detectables.
3. **Estabilidad geométrica entre escalas:** desplazamiento medio de centroides $\Delta c$ (m) e índice de solapamiento espacial ($\text{IoU}$) entre polígonos detectados a `5 m` / `< 1 m` y a `30 m`.
4. **Carga operativa de falsas alarmas ($\text{FP/km}^2$):** densidad de anomalías espurias por $\text{km}^2$ antes y después de aplicar la regla de abstención (`should_abstain_prediction`).

---

## 3. Etapa 5 — Diseño Muestral y Estratificación del Panel Ciego

### 3.1 Unidad muestral y población que representan las láminas
Cada ítem del paquete (`BLIND-XXXX`) representa **una ventana topográfica local centrada en una anomalía microtopográfica discreta segmentada por el motor**, acompañada de su entorno inmediato (buffer configurable, mínimo 12 píxeles de radio), no un mapa arqueológico completo ni un inventario de sitios al azar. La inferencia estadística de Etapa 5 mide **la validez de discriminación morfológica entre anomalías candidatas, geoformas naturales y estructuras modernas sobre el producto DEM evaluado**.

### 3.2 Composición muestral y proporciones pre-definidas
Para la evaluación ciega confirmatoria se establece un tamaño objetivo de **$N \ge 60$ láminas por campaña multi-bioma** (o un mínimo aceptable de **$N = 30$ láminas** en acuerdos piloto acotados, estratificado de forma uniforme por bloque espacial no visto en desarrollo):

| Estrato muestral | Proporción objetivo | Criterio estricto de elegibilidad |
| :--- | :---: | :--- |
| **Controles Positivos de Referencia (`sensor_detectable = True`)** | **25 %** | Estructuras arqueológicas documentadas con geometría precisa conocida (`coordinate_precision_m < 15 m`) y huella microtopográfica $\ge 2 \cdot \text{GSD}_{\text{nativo}}^2$ en el raster evaluado. Se excluyen citas de `known_sites_published.csv` con incertidumbre $\pm 100\text{ m}$ no ancladas con exactitud al DEM. |
| **Controles Negativos Difíciles — Geoformas Naturales** | **25 %** | Casos curados en las 5 subcategorías naturales de `HardNegativeCategory`: `cauce_seco`, `carcava`, `terraza_fluvial`, `cono_deyeccion`, `afloramiento_rocoso`. |
| **Controles Negativos Difíciles — Antrópico Moderno / Artefactos** | **25 %** | Casos curados en las 5 subcategorías modernas/técnicas: `cantera`, `terraplen_moderno`, `camino_rural`, `obra_hidraulica`, `terraza_agricola_reciente` (más artefactos digitales verificados). |
| **Candidatos Algorítmicos Inéditos (`ALGORITHMIC_DETECTION`)** | **25 %** | Anomalías detectadas por el motor en bloques espaciales reservados (`blind_test`) sin dictamen previo de VLM ni evaluación humana previa expuesta. |

**Regla de balance:** La generación mediante `export_blind_review_pack()` mezcla aleatoriamente todos los estratos con semilla pre-registrada y garantiza que ninguna categoría represente más del `85 %` del lote, previniendo la paradoja de prevalencia del estadístico $\kappa$.

### 3.3 Condiciones técnicas de cegamiento y custodia de la clave
1. **Generación de láminas (`render_blind_candidate_lamina`):** Todas las imágenes deben renderizarse directamente desde GeoTIFF (`rendered_from_geotiff = true`), exhibiendo tres paneles sincrónicos:
   - *Hillshade multidireccional 1.5x* (4 acimuts: `315°`, `45°`, `135°`, `225°`).
   - *Modelo de Relieve Local (SLRM)* en escala divergente centrada en `0`.
   - *Perfil transversal E–O* expresado en **relieve relativo $\Delta z$ [m]** (centrado en la mediana para impedir deducir la cota absoluta sobre el nivel del mar, evitando identificar si la ventana pertenece a la Puna o al Delta).
2. **Supresión absoluta de identificadores y fuga espacial:**
   - Ejes expresados exclusivamente en metros locales relativos (`0..W m`, `0..H m`), sin coordenadas POSGAR 2007 ni WGS84.
   - Sin nombres de zona, departamentos, códigos `ARQ-*`, veredictos previos ni probabilidades del calibrador ML.
   - Ejecución obligatoria de `strip_png_metadata_and_verify()` verificando cero etiquetas EXIF y cero chunks PNG `tEXt`, `iTXt`, `zTXt`, `eXIf` y `tIME`.
3. **Custodia física de `CONFIDENTIAL_BLIND_KEY.json`:**
   - El archivo `*CONFIDENTIAL_BLIND_KEY.json` está bloqueado en `.gitignore` y **no se incluye en la carpeta compartida con los evaluadores** ni se abre antes del cierre de recepción.
   - Sólo al recibirse todas las planillas completadas se coteja la integridad SHA-256 de cada imagen y se ejecuta `evaluate_blind_evaluator_sheets()`.

---

## 4. Formulario Estandarizado para Especialistas (`evaluator_sheet_template.csv`)

Cada especialista recibe únicamente la carpeta de imágenes `images/BLIND-XXXX.png`, `EVALUATOR_INSTRUCTIONS.md` y una copia limpia de `evaluator_sheet_template.csv` con el esquema fijo `BLIND_EVALUATOR_COLUMNS` definido en [`src/core/blind_review.py`](../archaeo-lidar-mcp/src/core/blind_review.py):

### 4.1 Columnas de contexto físico neutro (pre-completadas, solo lectura)
- `blind_id`: Identificador opaco secuencial (`BLIND-0001`, ...).
- `dem_native_resolution_m`: Resolución espacial nativa efectiva del modelo de elevación (en metros).
- `anomaly_area_m2`: Superficie poligonal delimitada por el detector (en $\text{m}^2$).
- `relative_relief_m`: Amplitud vertical relativa observada en la ventana ($\text{m}$).
- `relief_sign`: Polaridad morfológica dominante (`positivo`, `negativo`, `mixto_o_plano`).
- `general_biome`: Macro-ambiente ecológico regional sin topónimos locales (`Arido_Altoandino`, `noa_quebradas_valles`, `cuyo_precordillera`, `Selva_Pedemontana`, `meseta_patagonica`, `Humedal_Aluvial`, etc.).

### 4.2 Campos de dictamen independiente (completados por cada especialista)
- `reviewer_id`: Código anónimo asignado al evaluador (ej. `ESP-NOA-01`), manteniendo confidencial su identidad durante el análisis estadístico.
- `decision` *(lista cerrada obligatoria)*:
  - `ARCHAEOLOGICAL_PLAUSIBLE`: Geometría y contexto compatibles con estructura antrópica prehistórica o histórica (recinto ortogonal, canchón, terraza agrícola antigua, casa-pozo, estructura defensiva o monticular antrópica).
  - `NATURAL_GEOFORM`: Geoforma natural o artefacto de interpolación/ruido del DEM sin indicios constructivos antrópicos.
  - `MODERN_INFRASTRUCTURE`: Alambrado, huella vehicular, cantera, obra hidráulica o infraestructura contemporánea.
  - `INCONCLUSIVE`: La resolución o contraste topográfico de la lámina impide una discriminación morfológica responsable.
- `severity_ordinal_1_to_4` *(escala ordinal obligatoria para ponderación de desacuerdos)*:
  - `1`: Descartado / claramente natural o moderno.
  - `2`: Improbable / señal muy débil o ambigua.
  - `3`: Plausible / amerita revisión documental adicional y contexto multitemporal.
  - `4`: Altamente plausible / prioridad de verificación en campo bajo permiso vigente.
- `confidence_1_to_5`: Nivel de certeza del dictamen en escala Likert (`1` = mínima, `5` = máxima).
- `diagnostic_notes`: Descripción sucinta de los rasgos morfológicos diagnósticos observados (alineamientos rectilíneos, ángulos rectos, rupturas de pendiente, continuidad con red de drenaje, etc.).

---

## 5. Plan de Análisis Estadístico y Condiciones de Validez Experimental

El cálculo de cierre se ejecuta de forma reproducible mediante `compute_inter_rater_agreement()`, `evaluate_blind_evaluator_sheets()` (`src/core/blind_review.py`) y `compute_benchmark_metrics()` (`src/core/benchmark_v1.py`).

### 5.1 Métricas de concordancia inter-evaluador y desempeño
1. **Concordancia nominal sobre `decision`:**
   - Acuerdo porcentual por pares (`percent_agreement`) y tasa de unanimidad exacta (`exact_unanimous_rate`) con intervalo de confianza del **95 % de Wilson**.
   - **$\kappa$ de Cohen** (entre pares de 2 evaluadores) y **$\kappa$ de Fleiss** (para $\ge 3$ evaluadores simultáneos).
2. **Concordancia ordinal sobre `severity_ordinal_1_to_4`:**
   - **$\kappa$ ponderado lineal** (`weighted_kappa_linear`) y **$\kappa$ ponderado cuadrático** (`weighted_kappa_quadratic`) para penalizar proporcionalmente desacuerdos severos (`1` vs. `4`) frente a discrepancias adyacentes (`3` vs. `4`).
3. **Evaluación frente al estándar externo (solo tras desbloquear `CONFIDENTIAL_BLIND_KEY.json`):**
   - Matriz de confusión del detector y de la IA previa frente al consenso experto y frente a los controles positivos detectables (`sensor_detectable = True`).
   - Recall operable con IC Wilson 95 %, especificidad por subcategoría de `HardNegativeCategory`, `precision@5`, `precision@10` y $\text{FP/km}^2$ desglosados por bioma y resolución.
   - Auditoría cualitativa obligatoria de todos los desacuerdos (`ESP` vs. `ESP` y `consenso experto` vs. `modelo`).

### 5.2 Criterios explícitos para declarar VÁLIDO el experimento (Puerta Etapa 5 $\rightarrow$ Etapa 6)
El experimento ciego se considerará metodológicamente **válido** únicamente si satisface de manera conjunta las cinco condiciones siguientes:

1. **Integridad documental y de cegamiento del 100 %:** Todos los ítems verifican `metadata_stripped_verified == true`, `rendered_from_geotiff == true` y coincidencia bit-a-bit de `sha256` entre las láminas enviadas y `CONFIDENTIAL_BLIND_KEY.json`.
2. **Participación mínima independiente:** Al menos **2 especialistas acreditados independientes por bioma** (óptimo **3** sin comunicación mutua durante la carga) con tasa de respuesta $\ge 90\%$ sobre las láminas asignadas.
3. **Concordancia mínima interpretable:** Sobre las láminas evaluables (`not INCONCLUSIVE`), alcanzar al menos:
   - $\kappa_{\text{Fleiss/Cohen}} \ge 0.40$ (nivel *Moderado* en escala de Landis & Koch) en `decision`, **y**
   - $\kappa_{\text{ponderado cuadrático}} \ge 0.60$ (*Sustancial*) en la escala ordinal `severity_ordinal_1_to_4`.
4. **Ausencia de degeneración marginal:** `degenerate_single_class == false` y prevalencia máxima observada por clase $\le 85\%$ en los controles incluidos.
5. **Regla explícita de promoción a `EXPERT_REVIEWED`:** Un candidato inédito del bloque ciego transita formalmente al estado `EXPERT_REVIEWED` (elegible para tramitar inspección de terreno en Etapa 6 conforme **Ley N° 25.743, arts. 23–24**) solo si obtiene:
   - `decision == "ARCHAEOLOGICAL_PLAUSIBLE"` en al menos **$2/3$ de los evaluadores** (o unanimidad $2/2$ en paneles de dos evaluadores),
   - `severity_ordinal_1_to_4 >= 3` en el consenso, y
   - ningún voto de `MODERN_INFRASTRUCTURE` con `confidence_1_to_5 >= 4`.

### 5.3 Condiciones de invalidez o resultado no concluyente por escala/bioma
- Si en un sensor o bioma específico $\kappa_{\text{Fleiss/Cohen}} < 0.20$ o la proporción de dictámenes humanos `INCONCLUSIVE` supera el **50 %** del lote evaluado, **el experimento declara a esa combinación sensor/bioma como morfológicamente no resoluble**, bloqueando la emisión de afirmaciones arqueológicas sobre esa fuente de datos y restringiendo el despliegue futuro a sensores de mayor resolución en Etapa 4/6.
- Todo resultado, positivo o nulo, deberá informarse íntegramente incluyendo métricas no favorables e intervalos de confianza completos, sin ocultar corridas descartadas ni eliminar *outliers* luego de conocer la clave secreta.
