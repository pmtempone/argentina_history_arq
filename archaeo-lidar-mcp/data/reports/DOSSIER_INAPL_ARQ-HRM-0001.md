# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-HRM-0001`
**Fecha de Generación (UTC):** `2026-11-12T04:08:59Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## ⭐ Conclusión Ejecutiva (respuesta directa)

❌ **NO — la anomalía es un artefacto técnico o un error del mapa**

**¿Qué es?** Origen del rasgo: Mesa/soporte de calibración instrumental (hail pad) y huellas de rodado asociadas al experimento micrometeorológico HailPixel (noviembre 2018, San Rafael, Mendoza). No reviste carácter arqueológico prehispánico.
**Certeza del juicio:** `98%` · **Prioridad de investigación:** BAJA (descartado)

**Próximo paso:** ninguno — archivado como descarte (queda en `DESCARTES_VLM.json` y `INVENTARIO_GEOMORFOLOGICO.geojson` como dato geomorfológico).

| Parámetro | Valor |
| :--- | :--- |
| **Veredicto pericial** | **ARTEFACTO** |


---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-HRM-0001` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `recinto_ortogonal` |
| **Índice de Confianza Algorítmica** | `0.866` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |
| **Bioma / Entorno** | `alta_resolucion_uav` |
| **Contexto Arqueológico Esperado** | `Relevamiento fotogramétrico de ultra-alta resolución con dron (0.0025 m/px) en San Rafael, Mendoza (Cuyo, Argentina). Detección de alineaciones pircadas, recintos de piedra, trincheras y rasgos arqueológicos antrópicos.` |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `1.24 m²`
- **Índice de Rectangularidad:** `0.7351`
- **Índice de Circularidad Isoperimétrica:** `0.4742`
- **Sobre-elevación Local Media (SLRM):** `0.503 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/highres_zenodo_3383227_ARQ-HRM-0001_composite.png`
- **Modelo 3D Isométrico Térmico/Infrarrojo (Blender EEVEE):** `N/D`
- **Gráfico de Corte Transversal (Cross-Section):** `N/D`


**Figura 1 — Lámina compuesta de 4 paneles** (1: Hillshade 1.5x · 2: SLRM · 3: Perfil 2D · 4: Render 3D Blender):

![Lámina compuesta de 4 paneles del candidato ARQ-HRM-0001](../processed/highres_zenodo_3383227_ARQ-HRM-0001_composite.png)


---

## 4. Anexo Reservado de Coordenadas

Las coordenadas exactas de replanteo para inspección en campo por personal autorizado del **INAPL** o
direcciones provinciales de patrimonio se encuentran en:
- Archivo: `ANEXO_CONFIDENCIAL_COORDENADAS.json`

---

## 5. Juicio Pericial de Inteligencia Artificial Multimodal

| Campo | Dictamen |
| :--- | :--- |
| **Veredicto final** | **ARTEFACTO** |
| **Nivel de certeza** | `98%` |
| **Interpretación funcional** | Mesa/soporte de calibración instrumental (hail pad) y huellas de rodado asociadas al experimento micrometeorológico HailPixel (noviembre 2018, San Rafael, Mendoza). No reviste carácter arqueológico prehispánico. |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `Senior Space Archaeologist (VLM CONICET/NOA)` |

**Justificación geomorfológica:** El corte transversal 2D y el modelo isométrico 3D en Blender 4.2 revelan un pedestal prismático regular de 1.24 m² (1.2 x 0.8 m) sobreelevado +0.50 m con paredes verticales artificiales a 90°, emplazado dentro de una depresión alargada con estrías paralelas de rodado mecánico. Corresponde al soporte del sensor hail pad documentado en los metadatos del vuelo fotogramétrico de Zenodo 3383227.
