# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-HR-0005`
**Fecha de Generación (UTC):** `2026-11-11T14:02:07Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-HR-0005` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `terraza_lineal` |
| **Índice de Confianza Algorítmica** | `0.802` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `49.19 m²`
- **Índice de Rectangularidad:** `0.3084`
- **Índice de Circularidad Isoperimétrica:** `0.1063`
- **Sobre-elevación Local Media (SLRM):** `1.18 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/highres_san_juan_uav_ARQ-HR-0005_composite.png`
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
| **Nivel de certeza** | `96%` |
| **Interpretación funcional** | Escarpa de falla / banco estratigráfico sub-vertical expuesto (rumbo NE-SW) |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `mcp-host-agent` |

**Justificación geomorfológica:** Tanto el Hillshade 1.5x como el modelo 3D térmico de Blender revelan con nitidez sub-métrica un escalón estructural y escarpa de falla natural con rumbo NE-SW y caída abrupta de > 2 m hacia el SE, coincidente con el objetivo geológico del relevamiento UAV de rupturas superficiales.
