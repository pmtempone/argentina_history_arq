# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-VGR-0003`
**Fecha de Generación (UTC):** `2026-11-12T10:41:37Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## ⭐ Conclusión Ejecutiva (respuesta directa)

❌ **NO — la anomalía corresponde a una geoforma natural**

**¿Qué es?** La forma del terreno responde a: Hombro/dorso de ladera de una forma mayor (ventana saturada: toda la celda SLRM > 1.0 m).
**Certeza del juicio:** `85%` · **Prioridad de investigación:** BAJA (descartado)

**Próximo paso:** ninguno — archivado como descarte (queda en `DESCARTES_VLM.json` y `INVENTARIO_GEOMORFOLOGICO.geojson` como dato geomorfológico).

| Parámetro | Valor |
| :--- | :--- |
| **Veredicto pericial** | **NATURAL** |


---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-VGR-0003` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `terraza_lineal` |
| **Índice de Confianza Algorítmica** | `0.882` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |
| **Bioma / Entorno** | `yungas_selva` |
| **Contexto Arqueológico Esperado** | `Andenería agrícola prehispánica, calzadas empedradas y recintos bajo monte.` |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `131.46 m²`
- **Índice de Rectangularidad:** `0.3758`
- **Índice de Circularidad Isoperimétrica:** `0.1739`
- **Sobre-elevación Local Media (SLRM):** `1.3 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/zona_20_valle_grande_ARQ-VGR-0003_composite.png`
- **Modelo 3D Isométrico Térmico/Infrarrojo (Blender EEVEE):** `N/D`
- **Gráfico de Corte Transversal (Cross-Section):** `N/D`


**Figura 1 — Lámina compuesta de 4 paneles** (1: Hillshade 1.5x · 2: SLRM · 3: Perfil 2D · 4: Render 3D Blender):

![Lámina compuesta de 4 paneles del candidato ARQ-VGR-0003](../processed/zona_20_valle_grande_ARQ-VGR-0003_composite.png)


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
| **Nivel de certeza** | `85%` |
| **Interpretación funcional** | Hombro/dorso de ladera de una forma mayor (ventana saturada: toda la celda SLRM > 1.0 m). |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `agente pericial in situ (modo mcp_host, Juez Senior CONICET/NOA)` |

**Justificación geomorfológica:** Panel 1: gradiente plano sin andenes transversales, muros de contención ni escalones de plataforma (rasgos definitorios de andenería). Panel 2: SLRM integralmente saturado en amarillo (>1.0 m): la ventana de 35 m cae dentro de una forma mayor y no captura su contexto; el candidato es el flanco de una loma, no una terraza delimitada. Panel 3: lomo desdibujado de 1.7 a 0.8 m sobre 70 m, sin quiebres de andén. Panel 4: ladera continua. Un andén agrícola prehispánico tiene 2-4 m de ancho de banqueta y muro frontal: debajo de la resolución nativa de GLO-30; este rasgo es el hombro natural de la ladera.
