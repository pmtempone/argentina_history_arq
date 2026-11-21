# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-TEY-0005`
**Fecha de Generación (UTC):** `2026-11-14T15:14:57Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## ⭐ Conclusión Ejecutiva (respuesta directa)

❌ **NO — la anomalía corresponde a una geoforma natural**

**¿Qué es?** La forma del terreno responde a: Vaguada de escorrentía / cauce tributario natural en matriz de selva paranaense. La concavidad de ~200 m de ancho y ~2.4 m de profundidad relativa con perfil en V suave corresponde a drenaje natural, no a una zanja constructiva (una zanja jesuítica-guaraní sería de pocos metros de ancho con paredes definidas y fondo plano).
**Certeza del juicio:** `89%` · **Prioridad de investigación:** BAJA (descartado)

**Próximo paso:** ninguno — archivado como descarte (queda en `DESCARTES_VLM.json` y `INVENTARIO_GEOMORFOLOGICO.geojson` como dato geomorfológico).

| Parámetro | Valor |
| :--- | :--- |
| **Veredicto pericial** | **NATURAL** |


---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-TEY-0005` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `zanja_lineal` |
| **Índice de Confianza Algorítmica** | `0.769` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |
| **Bioma / Entorno** | `selva_paranaense` |
| **Contexto Arqueológico Esperado** | `Estructuras jesuítico-guaraníes ocultas bajo canopia, hornos y zanjas.` |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `2763.48 m²`
- **Índice de Rectangularidad:** `0.4909`
- **Índice de Circularidad Isoperimétrica:** `0.2012`
- **Sobre-elevación Local Media (SLRM):** `-1.49 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `/Users/pablotempone/argentina_history_arq/archaeo-lidar-mcp/data/processed/zona_22_teyu_cuare_ARQ-TEY-0005_composite.png`
- **Modelo 3D Isométrico Térmico/Infrarrojo (Blender EEVEE):** `N/D`
- **Gráfico de Corte Transversal (Cross-Section):** `N/D`


**Figura 1 — Lámina compuesta de 4 paneles** (1: Hillshade 1.5x · 2: SLRM · 3: Perfil 2D · 4: Render 3D Blender):

![Lámina compuesta de 4 paneles del candidato ARQ-TEY-0005](../processed/zona_22_teyu_cuare_ARQ-TEY-0005_composite.png)


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
| **Nivel de certeza** | `89%` |
| **Interpretación funcional** | Vaguada de escorrentía / cauce tributario natural en matriz de selva paranaense. La concavidad de ~200 m de ancho y ~2.4 m de profundidad relativa con perfil en V suave corresponde a drenaje natural, no a una zanja constructiva (una zanja jesuítica-guaraní sería de pocos metros de ancho con paredes definidas y fondo plano). |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `Agente anfitrión (OpenCode / GLM) — Juez Pericial sobre lámina compuesta 6 paneles` |

**Justificación geomorfológica:** Panel 3: perfil 2D monotónico en V abierta de ~200 m de ancho, sin piso plano ni paredes de excavación. Paneles 1-2: la ventana íntegra cae dentro de una concavidad de drenaje mayor (SLRM saturado en negativo < -0.4 m), sin bordes construidos ni anillo de escombro. Panel 4: corredor cóncavo elongado continuo sin estructura interna. Panel 5 RGB: el contorno cae en clarito con vegetación ribereña baja, sin arquitectura ni infraestructura moderna. Panel 6: NDVI medio 0.84 (canopia densa) con dNDVI -0.059 leve, compatible con vegetación herbácea de fondo de cauce; no es cropmark arquitectónico. Morfología lineal (aspect ratio 6.9, rectangularidad 0.49) y probabilidad ML 0.031.
