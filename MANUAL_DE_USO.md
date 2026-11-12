# 📖 Manual de Uso — ArchaeoLiDAR Prospector

**Para cualquier persona que quiera usar el sistema, sin ser programadora.**
Este manual explica qué hace el sistema, qué le pedís y dónde mirás el resultado.
Todo lo acá descrito lo puede ejecutar un asistente de IA (Antigravity / OpenCode)
con el skill `archaeo-lidar-prospector`, o vos mismo con los comandos indicados.

---

## 1. ¿Qué es esto, en una frase?

Es un sistema que **escanea automáticamente mapas de elevación del terreno en busca de
formas sospechosas de ser construcciones prehispánicas** (pircas, recintos, pozos,
terrazas, zanjas), descarta las que son geoformas naturales, y genera el expediente
legal (dossier) de cada candidato para el INAPL, bajo la Ley 25.743.

**Analogía:** es un detector de metales que barre un campo entero y te deja solo las
5-10 señales que vale la pena ir a revisar a pie, cada una con su informe listo.

---

## 2. Las 5 cosas que el sistema sabe hacer

| # | Qué hace | Cuándo lo usás |
| :---: | :--- | :--- |
| 1 | **Prospección de zona** | Querés buscar sitios arqueológicos en un área de Argentina |
| 2 | **Caza de alta resolución** | Querés encontrar y usar datos de dron/LiDAR < 1 m/px (detecta cosas chicas) |
| 3 | **Vigilancia de saqueo** | Querés detectar pozos de huaquero cerca de sitios ya conocidos |
| 4 | **Juicio pericial (VLM)** | El sistema te muestra la "foto" de cada candidato y vos (o el agente) dictaminás: antropica / natural / artefacto |
| 5 | **Inventario geomorfológico** | Querés usar los descartes como datos de geomorfología/hidrología (paleocauces = agua, médanos, morrenas...) |

---

## 3. Recetas: "Quiero..." — paso a paso

### 3.1 "Quiero buscar en una zona que YA está en el catálogo"

El catálogo tiene 29 zonas (Tastil, Yocavil, Tolombón, Tilcara, Aconquija, Valle Grande,
Sierra de Manchao, Delta del Paraná, Iberá, etc.). Cada una ya viene calibrada para su bioma.

**Qué le pedís al asistente:**
> "Prospectá la zona ZONA_23_DELTA_PARANA con 4 candidatos"

**Comando equivalente:**
```bash
cd archaeo-lidar-mcp
./venv/bin/python -m src.autonomous_prospector --target ZONA_23_DELTA_PARANA --max-candidates 4
```

**Qué va a pasar (5 fases, automático):**
1. Descarga el mapa de elevación real (Copernicus GLO-30) del área de la zona.
2. Lo divide en cuadrículas de 500 m con 15% de solapamiento (puede ser 1-15 min).
3. En cada cuadrícula busca formas del terreno sospechosas (positivas Y negativas).
4. Valida cada candidato contra mapas oficiales (IGN, OpenStreetMap), literatura
   académica y el catálogo de sitios conocidos.
5. Genera la "lámina" (foto técnica de 4 paneles) y el dossier de cada candidato.

**Dónde mirás el resultado:**
- La pantalla te muestra la tabla final de candidatos.
- `data/processed/zona_XX_..._ARQ-XXX-0001_composite.png` → la foto técnica de cada candidato.
- `data/reports/DOSSIER_INAPL_ARQ-XXX-0001.md` → el informe de cada uno.
- `data/reports/MAPA_PROSPECCION_ZONA_XX.geojson` → el mapa de la zona.

⚠️ **Tiempo y ruido:** una zona satelital dispara cientos de "sospechosos" que el sistema
reduce a pocos priorizados. Muchos van a ser naturales — es lo esperado (ver §6).

---

### 3.2 "Quiero buscar en una zona NUEVA que no está en el catálogo"

**Qué le pedís al asistente:**
> "Agregá la zona ZONA_29_SIERRA_DE_MANCHAO al catálogo: centro en (-66.4, -28.3),
> extensión ~7 km x ~7 km, bioma de sierra, y después prospectala"

**Qué hace el asistente (o vos a mano, 10 minutos):**
1. Abre `archaeo-lidar-mcp/src/core/data_fetcher.py` y copia el bloque de otra zona
   dentro de `TARGET_ZONES`.
2. Completa los campos clave:

| Campo | Qué es | Cómo lo elijo |
| :--- | :--- | :--- |
| `bbox` | Caja del área: `[lon_min, lat_min, lon_max, lat_max]` | Centro de tu interés ± ~0.035° por lado (~4 km). **Verificá que incluya lo que conocés del área** (error típico: quedarse corto — en La Ciudacita el bbox original dejaba fuera el sitio 2.7 km) |
| `epsg` | Faja POSGAR según la longitud | Longitud -76..-70.5 → 5343 · -70.5..-67.5 → 5344 · -67.5..-64.5 → 5345 · -64.5..-61.5 → 5346 · -61.5..-58.5 → 5347 · -58.5..-55.5 → 5348 · -55.5..-52 → 5349 |
| `biome` | Ambiente del área | alta_montaña / yungas / humedal / patagonia / sierras / selva / basalto... |
| `slrm_radius_m`, `min_area_m2`, `max_area_m2`, `min_dz_m` | Calibración | **Copia los valores de la tabla de biomas del README** que mejor se parezcan a tu zona |
| `archaeo_context` | Qué se espera encontrar ahí | Descripción en una frase (ej: "corrales de piedra y parapetos de caza") |

3. Corre la prospección como en §3.1 con `--target ZONA_29_...`.

⚠️ **Expectativa de resolución:** con imágenes satelitales públicas (30 m/píxel) solo se
pueden detectar estructuras grandes (≥ ~1.800 m², tipo plaza o corral mayor). Para
estructuras chicas (recintos de 10 m) se necesita dron/LiDAR → §3.3.

---

### 3.3 "Quiero datos de dron/LiDAR de alta resolución (para detectar cosas chicas)"

**Qué le pedís al asistente:**
> "Buscá datasets de alta resolución en Argentina y prospectá el mejor"
> — o, si ya sabés cuál:
> "Prospectá el dataset ZENODO:3383227"

**Comandos:**
```bash
./venv/bin/python -m src.autonomous_prospector --hunt-highres --max-candidates 4
./venv/bin/python -m src.autonomous_prospector --highres-id ZENODO:3383227 --max-candidates 4
```

**Qué va a pasar:** busca en catálogos científicos (OpenTopography, Zenodo, IGN), elige
el mejor dataset de Argentina (< 5 m/px), lo descarga, lo proyecta y prospecciona
preservando su resolución nativa (detecta muros finos, zanjas, pedestales).

### 3.4 "Tengo MI PROPIO vuelo de dron (.las/.laz)"

**Qué le pedís al asistente:**
> "Procesá mi nube de puntos data/raw/mi_vuelo.laz y prospectala"

**Comando:**
```bash
./venv/bin/python scripts/process_real_lidar.py data/raw/mi_vuelo.laz --resolution 0.5 --radius 10.0
```

**Qué va a pasar:** filtra la vegetación (SMRF), genera el modelo del suelo y corre el
pipeline completo (SLRM → detección → validación → dossier).

---

### 3.5 "El sistema me muestra candidatos — ¿cómo los AUDITO (hago de juez)?"

Cada candidato tiene una lámina de 4 paneles (`..._composite.png`). Mirala en este orden:

| Panel | Qué mirás | Qué te dice |
| :---: | :--- | :--- |
| 1. Hillshade | ¿Hay líneas rectas, esquinas, muros? | La arquitectura ES geométrica: líneas rectas, círculos perfectos |
| 2. SLRM | ¿La forma es un solo bulto liso o tiene estructura interna? | Bulto liso simétrico = natural casi siempre |
| 3. Perfil 2D | ¿El "bordado"? Recinto = piso plano + bordes altos; lomada = media pelota | Media pelota lisa = natural |
| 4. Render 3D | Verificación visual final | — |

**Veredictos posibles:**
- `ANTROPICA` → es estructura humana → queda en el mapa final.
- `NATURAL` → geoforma (lomada, médano, filo, vaguada...) → descartado.
- `ARTEFACTO` → error técnico del mapa (costura de tiles, borde del raster) → descartado.

**Qué le pedís al asistente:**
> "Inspeccioná el candidato ARQ-CIU-0001 y registrá tu dictamen pericial"

El agente (con el skill) abre la lámina, aplica los criterios del Juez Pericial
(CONICET/NOA) y registra el veredicto. Si hay sospecha de excavación ilegal cerca de un
sitio conocido, se activa el protocolo de saqueo (§3.6).

---

### 3.6 "Sospecho SAQUEO (huaqueo) cerca de un sitio"

**Cómo funciona:** el sistema marca automáticamente con `ALERTA_SAQUEO` todo hundimiento
**circular de 5 a 25 m de diámetro** con la boca hacia abajo (pozo) que esté a **menos de
1 km de un sitio arqueológico registrado** (catálogo, OSM `historic=*` o IGN).

**Qué aparece:** en la consola un 🚨, en el dossier una sección de denuncia con la vía
legal (Ley 25.743, art. 20 y 23), y el sitio más cercano con su distancia.

**Qué hacés si aparece una alerta:**
1. No es una prospección más: es prioridad patrimonial.
2. Se comunica de inmediato a la Delegación regional del INAPL y a la dirección
   provincial de patrimonio.
3. Las coordenadas exactas están solo en el `ANEXO_CONFIDENCIAL_COORDENADAS.json`
   (para el personal autorizado).

**Para que las alertas funcionen, el catálogo de sitios debe estar actualizado:**
```bash
./venv/bin/python scripts/build_known_sites_gpkg.py   # tras editar data/known_sites_published.csv
```

---

### 3.7 "Quiero ENTRENAR / recalibrar el modelo de puntuación"

El sistema puntúa cada candidato con una probabilidad de ser antropico. Ese modelo se
alimenta de los descartes que vos (como juez) fuiste auditando: **cada dictamen tuyo lo
hace más inteligente**.

**Qué le pedís al asistente:**
> "Re-entrená el calibrador ML y mostrame las métricas"

```bash
./venv/bin/python -c "from src.core.ml_calibrator import train_calibrator; print(train_calibrator())"
```

**Dónde mirás las métricas:** `data/reports/ML_BENCHMARK_METRICS.md`
(precision/recall/F1 y qué features pesan más en la decisión).

**Regla:** después de cada campaña con dictámenes nuevos, re-entrenar. Si un hallazgo se
confirma en campo, es la mejora más valiosa posible del modelo.

⚠️ **Por ahora el modelo puntúa "modo consejero"** (`--ml-mode advisory`, el default): su
puntaje se guarda en cada candidato para priorizar, pero no bloquea nada — el filtro sigue
siendo el score morfológico y la compuerta final es el Juez Pericial. Motivo: el modelo se
entrenó sin hallazgos confirmados reales, así que hoy tiende a puntuar bajo a TODO lo que
viene de imágenes satelitales. Cuando haya hallazgos confirmados en campo, se re-entrena y
podrá pasarse al modo estricto (`--ml-mode filter`).

---

### 3.8 "Quiero usar los descartes para OTRA ciencia (agua, erosión, clima)"

Todo lo que el juez descarta como `NATURAL` queda guardado como dato útil:
`data/reports/INVENTARIO_GEOMORFOLOGICO.geojson`, con subtipo etiquetado:
- `paleocauce` → **prospección de agua subterránea**
- `medano_fosil`, `cono_aluvial` → geología superficial
- `morrena`, `canchal` → monitoreo periglacial/climático
- `escarpa`, `domo_volcanico` → geología estructural

**Qué le pedís al asistente:**
> "Filtrá el inventario geomorfológico por paleocauces y pasame el archivo"

---

## 4. ¿Dónde está cada resultado? (diccionario de archivos)

| Archivo / carpeta | Qué es | Para quién |
| :--- | :--- | :--- |
| `data/reports/MAPA_FINAL_PROSPECCION.geojson` | **El mapa final** de hallazgos confirmados (ANTROPICA) | Todos |
| `data/reports/DOSSIER_INAPL_*.md` | Informe legal de cada candidato (sin coordenadas) | INAPL / autoridades |
| `data/reports/ANEXO_CONFIDENCIAL_COORDENADAS.json` | Coordenadas exactas (protegidas) | Solo personal autorizado |
| `data/reports/DESCARTES_VLM.json` | Archivo forense de todo lo descartado y por qué | Auditoría científica |
| `data/reports/INVENTARIO_GEOMORFOLOGICO.geojson` | Las geoformas naturales con subtipo | Geomorfología / hidro |
| `data/reports/MAPA_PROSPECCION_ZONA_*.geojson` | Mapa por zona con todos los candidatos | Trabajo interno |
| `data/reports/ML_BENCHMARK_METRICS.md` | Métricas del modelo de puntuación | Transparencia |
| `data/processed/*_composite.png` | La "foto técnica" de 4 paneles de cada candidato | El juez (vos o el agente) |
| `data/known_sites_published.csv` | Catálogo de sitios públicos conocidos | Para actualizar (±100 m) |

---

## 5. Cómo pedirle cosas al asistente (ejemplos de prompts)

Con el skill `archaeo-lidar-prospector` cargado, frases que funcionan:

- *"Prospectá la ZONA_19_ACHALA con 4 candidatos y después auditá los láminas vos como juez"*
- *"Agregá una zona nueva para el valle de X, centro (-65.2, -26.0), bioma yungas, y corréla"*
- *"¿Hubo alguna ALERTA_SAQUEO en la última corrida? Pasame el sitio y la distancia"*
- *"Re-entrená el calibrador ML y contame si mejoró el F1"*
- *"Pasame los paleocauces del inventario geomorfológico de Catamarca"*
- *"¿Qué tan grande es el área que se analizó en la última zona? ¿Cuánto tardó?"*

---

## 6. Reglas de oro (léelas una vez)

1. **El sistema produce CANDIDATOS, no hallazgos.** Solo la verificación en campo por
   personal autorizado confirma un sitio. Nadie excavó nada por ver una lámina bonita.
2. **Las coordenadas exactas no se comparten.** Los `MAPA_PROSPECCION_*.geojson` y el
   ANEXO confidencial quedan adentro del entorno de trabajo. Solo circulan los dossiers.
3. **0 falsas alarmas > muchos hallazgos.** Si el juez duda → `NATURAL` o
   `PENDIENTE_REVISION`. Un falso positivo derivado a campo cuesta caro; un candidato
   extra revisado no.
4. **Satelital ≠ dron.** Con Copernicus GLO-30 solo se ven estructuras grandes. Para lo
   chico, datos de dron/LiDAR (§3.3-3.4). No pidas peras al olmo satelital.
5. **Cada dictamen humano mejora el sistema** (§3.7). El descarte no es pérdida: es
   entrenamiento y también dato geomorfológico (§3.8).

---

## 7. Glosario mínimo

| Término | Qué es, en criollo |
| :--- | :--- |
| **DTM** | El mapa de la altura del terreno (donde no hay vegetación) |
| **SLRM** | "Lupa de relieve": le saca las montañas grandes para que se vean los bultos chicos (Hesse 2010) |
| **dZ** | Cuánto sobresale (o se hunde) una forma respecto del terreno de alrededor |
| **POSGAR 2007** | El sistema de coordenadas métricas oficial de Argentina (fajas EPSG:5343-5349) |
| **Candidato / anomalía** | Una forma del terreno sospechosa de ser construcción |
| **Descarte** | Candidato que el juez dictaminó natural o artefacto |
| **Hard negative** | Un descarte real usado para "enseñarle" al modelo qué NO es arqueología |
| **Tiling / celda** | El área se corta en cuadrículas de 500 m con 15% de solapamiento para escanearla |
| **GLO-30 / UAV** | Mapas de elevación satelitales (30 m/píxel) vs vuelos de dron (centímetros/píxel) |

---

*Referencias científicas por técnica: ver la sección "📚 Referencias Metodológicas" del
[README del subproyecto](archaeo-lidar-mcp/README.md).*
