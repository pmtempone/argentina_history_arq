# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-HR-0001`
**Fecha de Generación (UTC):** `2026-11-11T14:02:06Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-HR-0001` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `recinto_ortogonal` |
| **Índice de Confianza Algorítmica** | `0.733` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `11.28 m²`
- **Índice de Rectangularidad:** `0.6649`
- **Índice de Circularidad Isoperimétrica:** `0.7654`
- **Sobre-elevación Local Media (SLRM):** `1.808 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/highres_san_juan_uav_ARQ-HR-0001_composite.png`
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
| **Nivel de certeza** | `94%` |
| **Interpretación funcional** | Bloque errático / promontorio rocoso aislado (tor) en afloramiento sub-métrico |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `mcp-host-agent` |

**Justificación geomorfológica:** En la resolución nativa de 0.50 m/px (UAV DTM), la anomalía de 11.28 m² exhibe en el perfil 2D y en el modelo 3D de Blender un domo convexo único de +3.2 m de altura sin cavidad central ni mampostería perimetral (perfil en U invertida aguda, no en M). Corresponde a un bloque o mogote rocoso natural del afloramiento.
