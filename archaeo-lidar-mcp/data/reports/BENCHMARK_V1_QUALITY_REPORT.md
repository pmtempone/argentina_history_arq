# Informe de Curaduría y Calidad — BENCHMARK_V1_DATASET

*Generado (UTC):* `2026-11-13T23:30:31Z`

> **Advertencia Epistémica:** Este benchmark piloto consolida controles negativos generados por el Juez VLM (`AI_REJECTED_CANDIDATE`) y referencias publicadas aproximadas ±100 m (`PUBLISHED_SITE_REFERENCE`). **No equivale** a ground truth arqueológico de campo ni habilita aún un `blind_test` independiente.

## 1. Integridad y No-Duplicación de Fuentes

- **Descartes VLM de entrada (`DESCARTES_VLM.json`):** 126
- **Inventario Geomorfológico (`INVENTARIO_GEOMORFOLOGICO.geojson`):** 86 registros — subconjunto estricto de descartes: `True` (fusionados como atributos en 86 entradas sin duplicar observaciones).
- **Registros sintéticos excluidos:** 2 (ARQ-0025, ARQ-0026)
- **Referencias publicadas (`known_sites_published.csv`):** 9 (±100 m, excluidas de `blind_test`)
- **Total activo en `BENCHMARK_V1_DATASET.json`:** **133 entradas**

## 2. Hashes SHA-256 de Procedencia

| Fuente | SHA-256 | Tamaño (bytes) |
| :--- | :--- | :---: |
| `descartes_vlm` | `5fd678a1294fd983d19f632b0e8afb73971b4eeb256d27ec50d2090de48b9573` | 111643 |
| `inventario_geomorfologico` | `decf0b4d557663c0a4b6c29d3b838b6a86dd3d8544f77815640aa83dd560b448` | 70085 |
| `known_sites_published` | `f6109cdd30caa603f99c6c9e2815bd19834b4ade1a20b954b93ab3f2a850353d` | 2493 |

## 3. Distribución por Nivel de Evidencia y Partición Espacial

| Nivel de Evidencia | Cantidad | `archaeo_confirmed` | Elegible `blind_test` |
| :--- | :---: | :---: | :---: |
| `AI_REJECTED_CANDIDATE` | 124 | `False` | `False` |
| `PUBLISHED_SITE_REFERENCE` | 9 | `False` | `False` |
| `EXPERT_REVIEWED` | 0 | `True` (cuando aplique) | `True` |
| `FIELD_CONFIRMED` | 0 | `True` | `True` |

### Partición por Bloques Espaciales (Roberts et al. 2017)
- `development`: **99**
- `validation`: **34**
- `blind_test`: **0** (reservado exclusivamente para muestras independientes futuras con `eligible_for_blind_test=True`)

### Categorías Conservadoras de Negativos

- `afloramiento_rocoso`: 27
- `artefacto_dem_interpolacion`: 21
- `cauce_seco`: 8
- `cono_deyeccion`: 8
- `geoforma_no_especificada`: 49
- `terraza_fluvial`: 11
