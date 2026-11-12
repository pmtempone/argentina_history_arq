# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-0025`
**Fecha de Generación (UTC):** `2026-11-12T10:22:00Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## ⭐ Conclusión Ejecutiva (respuesta directa)

⏳ **PENDIENTE — el candidato aún no fue auditado visualmente**

**¿Qué es?** Se detectó una forma sospechosa pero falta el juicio pericial (lámina compuesta disponible).
**Certeza del juicio:** `0%` · **Prioridad de investigación:** MEDIA (pendiente de auditoría)

**Próximo paso:** juicio pericial sobre la lámina compuesta (sección 3).

| Parámetro | Valor |
| :--- | :--- |
| **Veredicto pericial** | **PENDIENTE_REVISION** |

> ℹ️ **Cómo completar el dictamen:** el Juez Pericial (agente o VLM) debe inspeccionar la
> lámina compuesta (sección 3) y registrar el veredicto con
> `src.core.vlm_judge.record_vlm_verdict(candidate_id=..., verdict_data=...)`. Este
> documento se regenerará automáticamente con la conclusión definitiva.


---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-0025` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `estructura_circular` |
| **Índice de Confianza Algorítmica** | `0.968` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |
| **Bioma / Entorno** | `N/D` |
| **Contexto Arqueológico Esperado** | `N/D` |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `73.99 m²`
- **Índice de Rectangularidad:** `0.7916`
- **Índice de Circularidad Isoperimétrica:** `0.9694`
- **Sobre-elevación Local Media (SLRM):** `0.491 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/synthetic_posgar_faja2_dtm_ARQ-0025_composite.png`
- **Modelo 3D Isométrico Térmico/Infrarrojo (Blender EEVEE):** `N/D`
- **Gráfico de Corte Transversal (Cross-Section):** `N/D`


**Figura 1 — Lámina compuesta de 4 paneles** (1: Hillshade 1.5x · 2: SLRM · 3: Perfil 2D · 4: Render 3D Blender):

![Lámina compuesta de 4 paneles del candidato ARQ-0025](../processed/synthetic_posgar_faja2_dtm_ARQ-0025_composite.png)


---

## 4. Anexo Reservado de Coordenadas

Las coordenadas exactas de replanteo para inspección en campo por personal autorizado del **INAPL** o
direcciones provinciales de patrimonio se encuentran en:
- Archivo: `ANEXO_CONFIDENCIAL_COORDENADAS.json`
