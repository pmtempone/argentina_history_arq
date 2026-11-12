# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `ARQ-TIN-0007`
**Fecha de Generación (UTC):** `2026-11-11T14:17:30Z`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `ARQ-TIN-0007` |
| **Clasificación Preliminar** | **CANDIDATO_INEDITO** |
| **Tipología Morfológica** | `terraza_lineal` |
| **Índice de Confianza Algorítmica** | `0.9` |
| **Faja Métrica de Cálculo** | `EPSG:5344` (POSGAR 2007) |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `77.66 m²`
- **Índice de Rectangularidad:** `0.8825`
- **Índice de Circularidad Isoperimétrica:** `0.5624`
- **Sobre-elevación Local Media (SLRM):** `0.235 m`
- **Distancia al Curso de Agua más Próximo (IGN):** `No determinado (sin datos IGN)`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `N/D pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `N/D`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `data/processed/zona_3_tinogasta_ARQ-TIN-0007_composite.png`
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
| **Nivel de certeza** | `92%` |
| **Interpretación funcional** | Ondulación superficial del terreno / microrrelieve de llanura aluvial |
| **¿Inspección terrestre / dron?** | **NO** |
| **Backend evaluador** | `mcp_host:ArchaeoSeniorCONICET` |

**Justificación geomorfológica:** Rango de reflectancia ínfimo (0.713 a 0.719) en Hillshade. El corte 2D muestra que en el centroide exacto la sobreelevación es de apenas +0.05 m, sin pendiente ni contención de andén.
