# Informe de Línea de Base Reproducible — ArchaeoLiDAR-AR

*Generado (UTC):* `2026-11-13T23:15:44Z` | *Commit Git:* `31593ac` | *Tag:* `untagged`

## 1. Resumen Único de Campaña (Fuente Única de Verdad)

- **Zonas en catálogo:** 30
- **Candidatos activos en `MAPA_FINAL_PROSPECCION.geojson`:** 0
- **Descartes archivados (`DESCARTES_VLM.json`):** 126
- **Geoformas catalogadas (`INVENTARIO_GEOMORFOLOGICO.geojson`):** 86

### Conteo por Estado Formal de Evidencia

| Estado | Significado | Cantidad |
| :--- | :--- | :---: |
| `ALGORITHMIC_DETECTION` | Anomalía topográfica detectada por algoritmo | 0 |
| `AI_PREASSESSMENT` | Evaluación preliminar ML / VLM | 0 |
| `EXPERT_REVIEWED` | Revisado por especialista humano | 0 |
| `FIELD_CONFIRMED` | Verificado en campo con autorización | 0 |
| `REJECTED_NATURAL` | Descartado como geoforma natural | 103 |
| `REJECTED_MODERN` | Descartado como infraestructura moderna o artefacto | 23 |
| `INCONCLUSIVE` | Evidencia insuficiente a la resolución disponible | 0 |

## 2. Registro de Afirmaciones (Alcance Científico Honesto)

### Lo que el proyecto SÍ puede afirmar actualmente
- Ingesta geodésica reproducible por bloques HTTP Range Request y reproyección automática a POSGAR 2007 (EPSG:5343–5349).
- Detección algorítmica de anomalías microtopográficas positivas y negativas mediante SLRM NaN-safe, Pendiente, SVF/Openness y segmentación morfométrica con piso físico de 2 píxeles nativos.
- Filtrado multifuente contra catastro público (IGN WFS, OpenStreetMap Overpass) y catálogo de sitios publicados (±100 m).
- Inspección visual multimodal de hasta 6 paneles (DTM/SLRM/Perfil/Blender 3D + Sentinel-2 RGB/NDVI) y trazabilidad forense de descartes e inventario geomorfológico.
- Resguardo estricto de coordenadas sensibles conforme a la Ley Nacional N° 25.743 (ANEXO confidencial y exclusión GeoJSON en Git).

### Lo que el proyecto NO afirma sin validación externa
- Descubrimiento automático o confirmación de sitios arqueológicos sin inspección de campo autorizada y dictamen de especialista.
- Detección de muros finos, casas-pozo o micro-estructuras (< ~1800 m²) sobre DEM satelitales globales de 30 m/px.
- Interpretación directa del score morfológico o ML como probabilidad arqueológica calibrada sin benchmark real independiente ni evaluación en terreno.
- Detección automática de saqueo (huaqueo) como acusación legal autónoma sin verificación técnica e institucional competente.

---
*Manifiesto JSON estructurado:* `data/reports/CAMPAIGN_MANIFEST.json`
