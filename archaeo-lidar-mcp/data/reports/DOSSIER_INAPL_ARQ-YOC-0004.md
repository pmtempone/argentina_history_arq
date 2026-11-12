# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-YOC-0004`
**Fecha de Generación (UTC):** `2026-11-11T14:14:44Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-YOC-0004` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `estructura_circular` |
| **Índice de Confianza Algorítmica** | `0.98` |
| **Faja Métrica de Cálculo** | `EPSG:5345` (POSGAR 2007) |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `34.49 m²`
- **Índice de Rectangularidad:** `0.5388`
- **Índice de Circularidad Isoperimétrica:** `1.0327`
- **Sobre-elevación Local Media (SLRM):** `2.191 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/zona_2_yocavil_ARQ-YOC-0004_composite.png`
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
| **Veredicto final** | **ARTEFACTO** |
| **Nivel de certeza** | `96%` |
| **Interpretación funcional** | Costura de píxel / salto de bloque de remuestreo en celda GLO-30 |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `mcp_host:ArchaeoSeniorCONICET` |

**Justificación geomorfológica:** En el Hillshade 1.5x se evidencian marcadas líneas de costura ortogonal en la grilla ráster a lo largo de Este 3495428. El perfil transversal describe una rampa escalonada abrupta en el límite de bloque sobre un área minúscula de 34 m².
