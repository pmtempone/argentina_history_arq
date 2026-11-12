# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-MAN-0003`
**Fecha de Generación (UTC):** `2026-11-12T03:59:36Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-MAN-0003` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `estructura_hundida` |
| **Índice de Confianza Algorítmica** | `0.92` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |
| **Bioma / Entorno** | `sierras_centrales` |
| **Contexto Arqueológico Esperado** | `Casas-pozo comechingonas semi-enterradas (relieve negativo), corrales pircados, morteros y aleros en las laderas occidentales.` |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `49.66 m²`
- **Índice de Rectangularidad:** `0.7759`
- **Índice de Circularidad Isoperimétrica:** `1.2`
- **Sobre-elevación Local Media (SLRM):** `-0.228 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/zona_29_sierra_de_manchao_ARQ-MAN-0003_composite.png`
- **Modelo 3D Isométrico Térmico/Infrarrojo (Blender EEVEE):** `N/D`
- **Gráfico de Corte Transversal (Cross-Section):** `N/D`

---

## 4. Anexo Reservado de Coordenadas

Las coordenadas exactas de replanteo para inspección en campo por personal autorizado del **INAPL** o
direcciones provinciales de patrimonio se encuentran en:
- Archivo: `data/reports/ANEXO_CONFIDENCIAL_COORDENADAS.json`

---

## 5. Juicio Pericial de Inteligencia Artificial Multimodal

| Campo | Dictamen |
| :--- | :--- |
| **Veredicto final** | **NATURAL** |
| **Nivel de certeza** | `87%` |
| **Interpretación funcional** | Microconcavidad de ladera (~15 m de núcleo, profundidad 0.24 m), no compatible con pozo. |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `agente pericial in situ (modo mcp_host, Juez Senior CONICET/NOA)` |

**Justificación geomorfológica:** Panel 1: gradiente de ladera sin paredes de excavación, sin anillo de escombro ni traza de deposición. Panel 2: SLRM uniforme, la concavidad no se distingue del fondo. Panel 3: parábola lisa de -0.24 m sobre ~35 m con núcleo de ~15 m: una casa-pozo comechingona (5-8 m, bordes netos, fondo plano) o un pozo de huaquero (paredes verticales + escombro perimetral) mostraría gradiente abrupto en el perfil; aquí la pendiente es continua. Panel 4: cuenca suave. Profundidad en el ruido del DEM supermuestreado (dZ umbral 0.20 m).
