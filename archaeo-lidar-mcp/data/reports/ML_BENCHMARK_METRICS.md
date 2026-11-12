# Benchmark del Calibrador ML (probabilidad calibrada vs score heurístico)

*Generado (UTC):* 2026-11-12T03:36:13Z

## 1. Composición del dataset

- **Clase 0 (hard negatives reales):** 110 candidatos descartados por el Juez Pericial VLM
  (`DESCARTES_VLM.json`, NATURAL/ARTEFACTO) con features completas de los mapas por zona.
- **Clase 1 (positivos sintéticos plantados):** 20 detecciones sobre estructuras con
  verdad de campo conocida (recintos, círculos, terrazas, pozos, zanjas; 0.5 m/px y 30 m/px).
- **Vector de features (9):** `area_m2`, `dz_mean`, `dz_abs`, `rectangularity`, `circularity`, `aspect_ratio`, `dz_extreme_window`, `slope_mean_deg`, `slrm_std_window`

## 2. Métricas (validación cruzada estratificada, 5 folds, predicción out-of-fold)

| Clase | Precision | Recall | F1 |
| :--- | :---: | :---: | :---: |
| **0 — NATURAL/ARTEFACTO** | 0.972 | 0.964 | 0.968 |
| **1 — ANTROPICA (positivo)** | 0.810 | 0.850 | 0.829 |
| **Macro-promedio** | 0.891 | 0.907 | 0.899 |

## 3. Importancia de features (GradientBoosting, promedio de folds)

| Feature | Importancia |
| :--- | :---: |
| `rectangularity` | 0.2784 |
| `slrm_std_window` | 0.2221 |
| `aspect_ratio` | 0.2124 |
| `slope_mean_deg` | 0.1246 |
| `dz_abs` | 0.0788 |
| `area_m2` | 0.0583 |
| `dz_extreme_window` | 0.0253 |
| `dz_mean` | 0.0000 |
| `circularity` | 0.0000 |

## 4. Limitaciones declaradas (transparencia metodológica)

- La clase positiva es **sintética**: mide separabilidad de los features, no recall en campo real.
- Los positivos provienen de DTM plantados a 0.5 m/px y 30 m/px; existe sesgo de resolución
  respecto a los negativos (GLO-30 supermuestreado a 2 m/px).
- No hay positivos reales auditados aún (`MAPA_FINAL` vacío): al confirmarse hallazgos en campo,
  re-entrenar con `train_calibrator()` para incluirlos.

Modelo persistido: `data/processed/ml_calibrator.joblib`
