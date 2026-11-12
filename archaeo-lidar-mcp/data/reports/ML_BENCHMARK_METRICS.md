# Benchmark del Calibrador ML (probabilidad calibrada vs score heurístico)

*Generado (UTC):* 2026-11-12T23:30:17Z

## 1. Composición del dataset

- **Clase 0 (hard negatives reales):** 126 candidatos descartados por el Juez Pericial VLM
  (`DESCARTES_VLM.json`, NATURAL/ARTEFACTO) con features completas de los mapas por zona.
- **Clase 1 (positivos sintéticos plantados):** 20 detecciones sobre estructuras con
  verdad de campo conocida (recintos, círculos, terrazas, pozos, zanjas; 0.5 m/px y 30 m/px).
- **Vector de features (11):** `area_m2`, `dz_mean`, `dz_abs`, `rectangularity`, `circularity`, `aspect_ratio`, `dz_extreme_window`, `slope_mean_deg`, `slrm_std_window`, `dz_contrast_ratio`, `ndvi_anomaly_delta`

## 2. Métricas (validación cruzada espacial agrupada (StratifiedGroupKFold, 5 folds), predicción out-of-fold)

| Clase | Precision | Recall | F1 |
| :--- | :---: | :---: | :---: |
| **0 — NATURAL/ARTEFACTO** | 0.947 | 0.992 | 0.969 |
| **1 — ANTROPICA (positivo)** | 0.929 | 0.650 | 0.765 |
| **Macro-promedio** | 0.938 | 0.821 | 0.867 |

## 3. Importancia de features (GradientBoosting, promedio de folds)

| Feature | Importancia |
| :--- | :---: |
| `rectangularity` | 0.2985 |
| `slrm_std_window` | 0.1830 |
| `area_m2` | 0.1470 |
| `aspect_ratio` | 0.1444 |
| `slope_mean_deg` | 0.0940 |
| `dz_extreme_window` | 0.0678 |
| `dz_abs` | 0.0411 |
| `dz_contrast_ratio` | 0.0118 |
| `circularity` | 0.0064 |
| `dz_mean` | 0.0061 |

## 4. Limitaciones declaradas (transparencia metodológica)

- La clase positiva es **sintética**: mide separabilidad de los features, no recall en campo real.
- Los positivos provienen de DTM plantados a 0.5 m/px y 30 m/px; existe sesgo de resolución
  respecto a los negativos (GLO-30 supermuestreado a 2 m/px).
- No hay positivos reales auditados aún (`MAPA_FINAL` vacío): al confirmarse hallazgos en campo,
  re-entrenar con `train_calibrator()` para incluirlos.

Modelo persistido: `/Users/pablotempone/argentina_history_arq/archaeo-lidar-mcp/data/processed/ml_calibrator.joblib`
