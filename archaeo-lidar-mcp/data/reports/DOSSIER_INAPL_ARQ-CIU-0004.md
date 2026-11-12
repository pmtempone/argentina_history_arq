# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-CIU-0004`
**Fecha de Generación (UTC):** `2026-11-12T03:04:08Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-CIU-0004` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `estructura_hundida` |
| **Índice de Confianza Algorítmica** | `0.92` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |
| **Bioma / Entorno** | `yungas_montana` |
| **Contexto Arqueológico Esperado** | `Pucarás en filos de montaña, plazas amuralladas (kanchas) y recintos satélites.` |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `54.49 m²`
- **Índice de Rectangularidad:** `0.6811`
- **Índice de Circularidad Isoperimétrica:** `1.142`
- **Sobre-elevación Local Media (SLRM):** `-2.672 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/zona_21_ciudacita_ARQ-CIU-0004_composite.png`
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
| **Nivel de certeza** | `88%` |
| **Interpretación funcional** | Concavidad natural (nicho de nivación / cauce de cabecera) de ~35 m de ancho y ~2.5 m de profundidad relativa. |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `agente pericial in situ (modo mcp_host, Juez Senior CONICET/NOA)` |

**Justificación geomorfológica:** Panel 1: concavidad suave en ladera con zona brillante SE (piso de cauce/nicho), sin bordes elevados construidos. Panel 2: tile íntegramente fuera de rango de color (SLRM << -0.4 m en toda la celda), indicador de que la ventana cae dentro de una vaguada profunda; el tile SLRM es inválido como referencia local. Panel 3: perfil en U continuo de -1.1 a -3.5 m, sin piso plano, sin bordes perimetrales elevados, sin muros: un pozo/casa-pozo construida exigiría bordes netos y fondo plano. Panel 4: cuenca lisa. Área reportada (54 m²) es solo el núcleo más profundo del hueco; no hay arquitectura.
