# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-VAL-0004`
**Fecha de Generación (UTC):** `2026-11-12T23:30:06Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## ⭐ Conclusión Ejecutiva (respuesta directa)

❌ **NO — la anomalía corresponde a una geoforma natural**

**¿Qué es?** La forma del terreno responde a: Confluencia natural de dos quebradas / vaguadas de escorrentía en ladera.
**Certeza del juicio:** `92%` · **Prioridad de investigación:** BAJA (descartado)

**Próximo paso:** ninguno — archivado como descarte (queda en `DESCARTES_VLM.json` y `INVENTARIO_GEOMORFOLOGICO.geojson` como dato geomorfológico).

| Parámetro | Valor |
| :--- | :--- |
| **Veredicto pericial** | **NATURAL** |


---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-VAL-0004` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `estructura_hundida` |
| **Índice de Confianza Algorítmica** | `0.882` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |
| **Bioma / Entorno** | `sierras_centrales` |
| **Contexto Arqueológico Esperado** | `Unidades domésticas circulares de la cultura Tafí, montículos ceremoniales, andenes agrícolas y corrales pircados en valle intermontano.` |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `411.6 m²`
- **Índice de Rectangularidad:** `0.6814`
- **Índice de Circularidad Isoperimétrica:** `0.905`
- **Sobre-elevación Local Media (SLRM):** `-1.316 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `/Users/pablotempone/argentina_history_arq/archaeo-lidar-mcp/data/processed/zona_32_tafi_del_valle_ARQ-VAL-0004_composite.png`
- **Modelo 3D Isométrico Térmico/Infrarrojo (Blender EEVEE):** `N/D`
- **Gráfico de Corte Transversal (Cross-Section):** `N/D`


**Figura 1 — Lámina compuesta de 4 paneles** (1: Hillshade 1.5x · 2: SLRM · 3: Perfil 2D · 4: Render 3D Blender):

![Lámina compuesta de 4 paneles del candidato ARQ-VAL-0004](../processed/zona_32_tafi_del_valle_ARQ-VAL-0004_composite.png)


---

## 4. Anexo Reservado de Coordenadas

Las coordenadas exactas de replanteo para inspección en campo por personal autorizado del **INAPL** o
direcciones provinciales de patrimonio se encuentran en:
- Archivo: `ANEXO_CONFIDENCIAL_COORDENADAS.json`

---

## 5. Juicio Pericial de Inteligencia Artificial Multimodal

| Campo | Dictamen |
| :--- | :--- |
| **Veredicto final** | **NATURAL** |
| **Nivel de certeza** | `92%` |
| **Interpretación funcional** | Confluencia natural de dos quebradas / vaguadas de escorrentía en ladera. |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `antigravity_vlm_6panel` |

**Justificación geomorfológica:** Depresión en V abierta (-1.32 m) en perfil 2D y Panel 4 3D; el Panel 5 (RGB) evidencia dos cauces tributarios convergiendo en el contorno sin muros ni bordes construidos (NDVI=0.2954, dNDVI=-0.0045).
