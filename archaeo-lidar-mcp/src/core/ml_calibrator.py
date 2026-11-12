"""Calibrador ML supervisado para puntuar candidatos arqueológicos con probabilidad calibrada.

Reemplaza la confianza heurística de `_classify_contour_morphology` (fórmula lineal de
descriptores de forma) por un clasificador entrenado con:
- **Clase 0 (hard negatives):** candidatos reales ya auditados y descartados por el
  Juez Pericial VLM en `DESCARTES_VLM.json` (NATURAL / ARTEFACTO), con features
  completas recuperadas de los mapas por zona `MAPA_PROSPECCION_*.geojson`.
- **Clase 1 (positivos):** estructuras sintéticas plantadas con verdad de campo
  conocida (recintos, círculos, terrazas, pozos, zanjas a 0.5 y 30 m/px),
  recuperadas por `detect_anomalies` sobre el DTM plantado.

Vector de features (9): área, desviación SLRM media y absoluta, rectangularidad,
circularidad (compactness), razón de aspecto, y — cuando hay rasters maestros
disponibles — `dz_extreme` (|SLRM| extremo en ventana), `slope_mean` y `slrm_std`
muestreados alrededor del centroide. Los faltantes se imputan (SimpleImputer).

Salida: `data/processed/ml_calibrator.joblib` + reporte de métricas
`data/reports/ML_BENCHMARK_METRICS.md`.

Referencias metodológicas: Guyot et al. 2018 (Remote Sensing, Carnac);
Berganzo-Besga & Orengo et al. 2021 (Remote Sensing 13:4181, Galicia).
"""

import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import rasterio
from pyproj import CRS, Transformer

from src.config import settings

DEFAULT_MODEL_PATH: Path = Path("./data/processed/ml_calibrator.joblib")
BENCHMARK_REPORT_PATH: Path = Path("./data/reports/ML_BENCHMARK_METRICS.md")

# Features del vector de entrenamiento (orden fijo para persistencia y scoring)
FEATURE_NAMES: List[str] = [
    "area_m2",
    "dz_mean",
    "dz_abs",
    "rectangularity",
    "circularity",
    "aspect_ratio",
    "dz_extreme_window",
    "slope_mean_deg",
    "slrm_std_window",
    "dz_contrast_ratio",
    "ndvi_anomaly_delta",
]
WINDOW_RADIUS_M: float = 75.0


# ---------------------------------------------------------------------------
# Extracción de features
# ---------------------------------------------------------------------------

def _sample_window_stats(
    raster_path: Union[str, Path],
    lon: float,
    lat: float,
    radius_m: float = WINDOW_RADIUS_M,
) -> Optional[Dict[str, float]]:
    """Muestra estadísticas de una ventana cuadrada centrada en el candidato WGS84.

    Convierte (lon, lat) al CRS del raster, lee una ventana de `radius_m` metros
    alrededor y devuelve estadísticas robustas de la banda 1 (NoData -> NaN).
    """
    with rasterio.open(raster_path) as src:
        crs_epsg = src.crs.to_epsg() or 5345
        to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(crs_epsg), always_xy=True)
        cx, cy = to_metric.transform(lon, lat)
        res = float(abs(src.transform.a))
        half_px = max(2, int(round(radius_m / res)))
        row, col = src.index(cx, cy)
        r0 = max(0, row - half_px)
        r1 = min(src.height, row + half_px + 1)
        c0 = max(0, col - half_px)
        c1 = min(src.width, col + half_px + 1)
        if r1 <= r0 or c1 <= c0:
            return None
        data = src.read(1, window=rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float64)
    nodata_mask = np.isnan(data) | (data <= -9000.0) | np.isclose(data, -9999.0)
    vals = data[~nodata_mask]
    if vals.size < 5:
        return None
    return {
        "absmax": float(np.nanmax(np.abs(vals))),
        "std": float(np.nanstd(vals)),
        "mean": float(np.nanmean(vals)),
    }


def extract_features(
    props: Dict[str, Any],
    slrm_path: Optional[Union[str, Path]] = None,
    slope_path: Optional[Union[str, Path]] = None,
    window_radius_m: float = WINDOW_RADIUS_M,
) -> Dict[str, float]:
    """Extrae el vector de features geomorfológicos de un candidato.

    Args:
        props: Propiedades del candidato (debe incluir `area_m2`, `mean_elevation_m`,
            y opcionalmente `rectangularity`, `circularity`, `aspect_ratio`).
        slrm_path: Raster SLRM maestro de la zona para el contexto de ventana (opcional).
        slope_path: Raster de pendiente maestro de la zona (opcional).
        window_radius_m: Radio de la ventana de contexto en metros.

    Returns:
        Diccionario con las 9 features (`np.nan` cuando el contexto raster no está disponible).
    """
    area_m2 = float(props.get("area_m2") or 0.0)
    dz_mean = float(props.get("mean_elevation_m") or 0.0)
    rect = props.get("rectangularity")
    circ = props.get("circularity")
    aspect = props.get("aspect_ratio")

    # Inferir descriptores de forma desde la tipología cuando el registro no los trae
    anomaly_type = str(props.get("anomaly_type", ""))
    if rect is None:
        rect = {"recinto_ortogonal": 0.85, "terraza_lineal": 0.75, "zanja_lineal": 0.75,
                "estructura_circular": 0.75, "estructura_hundida": 0.75}.get(anomaly_type, np.nan)
    if circ is None:
        circ = {"recinto_ortogonal": 0.75, "estructura_circular": 0.95, "estructura_hundida": 0.95,
                "terraza_lineal": 0.60, "zanja_lineal": 0.60}.get(anomaly_type, np.nan)
    if aspect is None:
        aspect = {"terraza_lineal": 4.0, "zanja_lineal": 4.0}.get(anomaly_type, 1.4)

    ndvi_delta = props.get("ndvi_anomaly_delta")
    feats: Dict[str, float] = {
        "area_m2": area_m2,
        "dz_mean": dz_mean,
        "dz_abs": abs(dz_mean),
        "rectangularity": float(rect),
        "circularity": float(circ),
        "aspect_ratio": float(aspect),
        "dz_extreme_window": np.nan,
        "slope_mean_deg": np.nan,
        "slrm_std_window": np.nan,
        "dz_contrast_ratio": np.nan,
        "ndvi_anomaly_delta": float(ndvi_delta) if ndvi_delta is not None else np.nan,
    }

    centroid = props.get("centroid_wgs84")
    if centroid and len(centroid) == 2:
        lon, lat = float(centroid[0]), float(centroid[1])
        if slrm_path and Path(slrm_path).exists():
            stats = _sample_window_stats(slrm_path, lon, lat, window_radius_m)
            if stats:
                feats["dz_extreme_window"] = stats["absmax"]
                feats["slrm_std_window"] = stats["std"]
                feats["dz_contrast_ratio"] = round(abs(dz_mean) / max(float(stats["std"]), 0.05), 4)
        if slope_path and Path(slope_path).exists():
            sstats = _sample_window_stats(slope_path, lon, lat, window_radius_m)
            if sstats:
                feats["slope_mean_deg"] = sstats["mean"]
    return feats


def _features_to_vector(feats: Dict[str, float], feature_names: Optional[List[str]] = None) -> List[float]:
    names = feature_names or FEATURE_NAMES
    return [float(feats.get(name, np.nan)) for name in names]


# ---------------------------------------------------------------------------
# Construcción del dataset: negativos reales auditados + positivos sintéticos
# ---------------------------------------------------------------------------

def _load_negative_samples(
    reports_dir: Optional[Union[str, Path]] = None,
) -> Tuple[List[Dict[str, float]], List[Dict[str, Any]]]:
    """Recupera los hard negatives del archivo de descartes y los mapas por zona.

    Cruza cada candidato descartado por el Juez Pericial (`DESCARTES_VLM.json`) con sus
    props completas en `MAPA_PROSPECCION_*.geojson` y muestrea el contexto raster de
    los maestros `data/processed/{zona}_master_{slrm,slope}.tif` cuando existen.
    """
    rep_dir = Path(reports_dir) if reports_dir else settings.reports_dir
    disc_path = rep_dir / "DESCARTES_VLM.json"
    if not disc_path.exists():
        return [], []

    desc = json.loads(disc_path.read_text(encoding="utf-8")).get("discarded", {})

    # Índice: id de candidato -> (props completas, rutas maestras de su zona)
    zone_map_dir = rep_dir.parent / "processed"
    id_index: Dict[str, Tuple[Dict[str, Any], Path]] = {}
    for map_path in sorted(rep_dir.glob("MAPA_PROSPECCION_*.geojson")):
        try:
            fc = json.loads(map_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        zone_key = map_path.stem.replace("MAPA_PROSPECCION_", "").lower()
        masters = (zone_map_dir / f"{zone_key}_master_slrm.tif",
                   zone_map_dir / f"{zone_key}_master_slope.tif")
        for feat in fc.get("features", []):
            fid = feat.get("id") or feat.get("properties", {}).get("id")
            if fid:
                id_index[fid] = (feat.get("properties", {}), zone_key, masters)

    # Registros sin mapa por zona (campaña Tastil ARQ-000X / highres HR-*): props mínimas
    # del propio descarte + contexto raster de la zona Tastil / highres Zenodo.
    fallback_masters = (
        zone_map_dir / "zona_1_tastil_master_slrm.tif",
        zone_map_dir / "zona_1_tastil_master_slope.tif",
    )
    fallback_hr = (
        zone_map_dir / "highres_zenodo_3383227_master_slrm.tif",
        zone_map_dir / "highres_zenodo_3383227_master_slope.tif",
    )

    samples: List[Dict[str, float]] = []
    meta: List[Dict[str, Any]] = []
    for cid, entry in desc.items():
        if cid in id_index:
            props, zone_key_item, masters = id_index[cid]
            group_id = f"NEG_{zone_key_item}"
        else:
            prefix = cid.replace("ARQ-", "").split("-")[0]
            props = {k: entry.get(k) for k in ("area_m2", "mean_elevation_m", "anomaly_type")}
            masters = fallback_hr if prefix in {"HR", "HRM"} else fallback_masters
            group_id = f"NEG_{prefix}"
        feats = extract_features(props, slrm_path=masters[0], slope_path=masters[1])
        feats["label"] = 0
        samples.append(feats)
        meta.append({
            "id": cid,
            "source": "descarte_vlm_audited",
            "anomaly_type": entry.get("anomaly_type"),
            "group": group_id,
        })
    return samples, meta


def _generate_synthetic_positive_samples(
    working_dir: Optional[Union[str, Path]] = None,
    seed: int = 42,
    configs_limit: Optional[int] = None,
) -> Tuple[List[Dict[str, float]], List[Dict[str, Any]]]:
    """Genera positivos sintéticos con verdad de campo conocida (estructuras plantadas).

    Replica el generador de `tests/conftest.py` a dos escalas (0.5 m/px y 30 m/px)
    con variaciones de tamaño y dZ, ejecuta el detector y conserva solo las detecciones
    cuyo centroide cae dentro de una estructura plantada (evita contaminar con fantasmas).
    """
    from src.core.anomaly_detector import detect_anomalies
    from src.core.relief_models import compute_slope, compute_slrm

    work = Path(working_dir) if working_dir else Path(tempfile.mkdtemp(prefix="ml_positives_"))
    work.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    configs: List[Dict[str, Any]] = []
    # Escala 0.5 m/px (LiDAR/UAV, tile de 200 m): recintos, círculos, terrazas, pozos y
    # zanjas, con separación suficiente para que la clausura morfológica no los fusione.
    for i in range(4):
        configs.append(
            {
                "res": 0.5, "size_px": 400, "slrm_radius_m": 15.0 + i * 2.0,
                "min_area": 6.0, "max_area": 9000.0, "min_dz": 0.15,
                "structures": [
                    {"kind": "rect", "center": (60.0, 60.0 + i * 8.0), "w": 12.0 + i * 2.0, "h": 7.0, "dz": 0.45 + i * 0.15, "rot": np.radians(20.0 + i * 15.0)},
                    {"kind": "circle", "center": (150.0, 85.0 + i * 10.0), "r": 4.0 + i * 0.8, "dz": 0.45 + i * 0.12},
                    {"kind": "pit", "center": (172.0, 158.0 + i * 3.0), "r": 5.0 + i * 0.7, "dz": -(0.45 + i * 0.12)},
                    {"kind": "trench", "center": (60.0, 175.0 + i * 2.0), "w": 4.0 + i * 0.6, "length": 45.0 + i * 6.0, "dz": -(0.45 + i * 0.1)},
                    {"kind": "terrace", "center": (110.0, 160.0), "w": 6.0 + i, "length": 60.0 + i * 8.0, "dz": 0.5 + i * 0.1},
                ],
            }
        )
    # Escala 30 m/px (GLO-30): plaza grande y corral grande (recall test)
    configs.append(
        {
            "res": 30.0, "size_px": 64, "slrm_radius_m": 240.0,
            "min_area": 12.0, "max_area": 60000.0, "min_dz": 0.15,
            "structures": [
                {"kind": "rect", "center": (720.0, 720.0), "w": 150.0, "h": 90.0, "dz": 0.60, "rot": 0.0},
                {"kind": "circle", "center": (1200.0, 840.0), "r": 105.0, "dz": 0.60},
            ],
        }
    )

    samples: List[Dict[str, float]] = []
    meta: List[Dict[str, Any]] = []

    def _plant(kind: str, xx: np.ndarray, yy: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
        if kind == "rect":
            th = cfg.get("rot", 0.0)
            dx, dy = xx - cfg["center"][0], yy - cfg["center"][1]
            x_rot = dx * np.cos(th) + dy * np.sin(th)
            y_rot = -dx * np.sin(th) + dy * np.cos(th)
            return (np.abs(x_rot) <= cfg["w"] / 2.0) & (np.abs(y_rot) <= cfg["h"] / 2.0)
        if kind in {"circle", "pit"}:
            return np.hypot(xx - cfg["center"][0], yy - cfg["center"][1]) <= cfg["r"]
        # terrace / trench: franja alineada E-W (o rotada leve)
        th = np.radians(rng.uniform(-30, 30))
        dx, dy = xx - cfg["center"][0], yy - cfg["center"][1]
        x_rot = dx * np.cos(th) + dy * np.sin(th)
        y_rot = -dx * np.sin(th) + dy * np.cos(th)
        return (np.abs(x_rot) <= cfg["length"] / 2.0) & (np.abs(y_rot) <= cfg["w"] / 2.0)

    for ci, cfg in enumerate(configs if configs_limit is None else configs[:configs_limit]):
        res = cfg["res"]
        width = height = cfg["size_px"]
        cols = (np.arange(width, dtype=np.float64) + 0.5) * res
        rows = (np.arange(height, dtype=np.float64) + 0.5) * res
        xx, yy = np.meshgrid(cols, rows)
        # Rampa de pendiente realista (2-22 grados en dirección aleatoria): el terreno sintético
        # debe solapar la distribución de pendiente de los negativos reales (GLO-30 montañoso)
        # para que el modelo aprenda MORFOLOGÍA y no "terreno plano vs montañoso".
        theta_deg = rng.uniform(2.0, 22.0)
        dir_th = rng.uniform(0.0, 2.0 * np.pi)
        # Rugosidad colinar suave (~±0.25 m) para solapar la distribución de slrm_std real
        from scipy.ndimage import gaussian_filter
        roughness = gaussian_filter(rng.normal(0.0, 0.25, size=(height, width)), sigma=6.0)
        z = 2000.0 + np.tan(np.radians(theta_deg)) * (
            xx * np.cos(dir_th) + yy * np.sin(dir_th)
        ) + roughness + 1.0 * np.sin(xx / 300.0) + 1.0 * np.cos(yy / 300.0)
        planted: List[Tuple[np.ndarray, float]] = []  # (centro, radio de tolerancia)
        for s in cfg["structures"]:
            mask = _plant(s["kind"], xx, yy, s)
            z[mask] += s["dz"]
            if s["kind"] in {"circle", "pit"}:
                tol = s["r"] + 4.0
            elif s["kind"] == "rect":
                tol = max(s["w"], s["h"]) / 2.0 + 4.0
            else:
                tol = s["length"] / 2.0 + 4.0
            planted.append((s["center"], tol, s["kind"], s["dz"]))

        from rasterio.transform import from_origin
        dtm_path = work / f"pos_dtm_{ci}.tif"
        profile = {
            "driver": "GTiff", "height": height, "width": width, "count": 1,
            "dtype": "float32", "crs": rasterio.crs.CRS.from_epsg(5344),
            "transform": from_origin(2500000.0, 7000200.0, res, res), "nodata": -9999.0,
        }
        with rasterio.open(dtm_path, "w", **profile) as dst:
            dst.write(z.astype(np.float32), 1)

        slrm_path = compute_slrm(dtm_path, work / f"pos_slrm_{ci}.tif", radius_m=cfg["slrm_radius_m"])
        slope_path = compute_slope(dtm_path, work / f"pos_slope_{ci}.tif")
        fc = detect_anomalies(
            slrm_path, slope_path,
            min_area=cfg["min_area"], max_area=cfg["max_area"], min_dz=cfg["min_dz"],
            border_margin_px=max(2, int(round(cfg["slrm_radius_m"] / res))),
        )
        to_metric = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(5344), always_xy=True)
        for feat in fc.get("features", []):
            props = feat["properties"]
            lon, lat = props["centroid_wgs84"]
            cx, cy = to_metric.transform(lon, lat)
            local = (cx - 2500000.0, 7000200.0 - cy)
            # Recuperar solo detecciones dentro del radio de tolerancia de una estructura plantada
            matched = None
            for (pcenter, tol, kind, dz) in planted:
                d = math.hypot(local[0] - pcenter[0], local[1] - pcenter[1])
                if d <= tol:
                    matched = (kind, dz)
                    break
            if matched is None:
                continue
            # Coherencia de signo: el dZ detectado debe corresponder al tipo plantado
            kind_planted, dz_planted = matched
            sign_ok = (props["mean_elevation_m"] < 0) == (dz_planted < 0)
            if not sign_ok:
                continue
            feats = extract_features(props, slrm_path=slrm_path, slope_path=slope_path)
            feats["label"] = 1
            samples.append(feats)
            meta.append({
                "id": f"SYN-{ci}-{len(meta):03d}",
                "source": "sintetico_plantado",
                "anomaly_type": props.get("anomaly_type"),
                "group": f"SYN_CFG_{ci}",
            })
    return samples, meta


def build_dataset(
    reports_dir: Optional[Union[str, Path]] = None,
    positive_workdir: Optional[Union[str, Path]] = None,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """Construye la matriz de features (X) y etiquetas (y) del calibrador.

    Returns:
        `(X, y, meta)` con meta describiendo el origen de cada fila.
    """
    neg, neg_meta = _load_negative_samples(reports_dir)
    pos, pos_meta = _generate_synthetic_positive_samples(positive_workdir, seed=seed)
    rows = neg + pos
    X = np.array([_features_to_vector(s) for s in rows], dtype=np.float64)
    y = np.array([int(s["label"]) for s in rows], dtype=np.int64)
    meta = neg_meta + pos_meta
    return X, y, meta


# ---------------------------------------------------------------------------
# Entrenamiento, evaluación y scoring
# ---------------------------------------------------------------------------

def _build_pipeline(seed: int = 42, min_class_count: int = 5):
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    base = GradientBoostingClassifier(
        n_estimators=150, max_depth=3, learning_rate=0.08, random_state=seed
    )
    # La calibración isotónica requiere >= cv ejemplos por clase EN CADA fold de entrenamiento.
    # Con datasets muy chicos (< 4 ejemplos por clase) cualquier partición deja un fold sin
    # suficientes ejemplos: se omite la capa de calibración (predict_proba del GBM sin calibrar)
    # y se documenta en el reporte. Con el dataset real (> 80 negativos) la calibración está activa.
    if min_class_count >= 4:
        n_cal_folds = max(2, min(3, min_class_count - 1))
        final_clf = CalibratedClassifierCV(base, method="isotonic", cv=n_cal_folds)
    else:
        final_clf = base
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", final_clf),
    ])


def train_calibrator(
    reports_dir: Optional[Union[str, Path]] = None,
    model_path: Optional[Union[str, Path]] = None,
    report_path: Optional[Union[str, Path]] = None,
    seed: int = 42,
    positive_workdir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Entrena el calibrador, evalúa con validación cruzada estratificada y persiste el modelo.

    Escribe el modelo en `data/processed/ml_calibrator.joblib` y el reporte de métricas
    (precision, recall, F1, feature importances) en `data/reports/ML_BENCHMARK_METRICS.md`.
    """
    from sklearn.metrics import precision_recall_fscore_support
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold, cross_val_predict

    X, y, meta = build_dataset(reports_dir, positive_workdir=positive_workdir, seed=seed)
    if len(set(y.tolist())) < 2:
        raise ValueError("El dataset debe contener ambas clases para entrenar.")

    groups = np.array([str(m.get("group") or m.get("id") or idx) for idx, m in enumerate(meta)])
    neg_groups = len(set(groups[y == 0].tolist()))
    pos_groups = len(set(groups[y == 1].tolist()))
    min_groups = min(neg_groups, pos_groups)

    pipeline = _build_pipeline(seed=seed, min_class_count=int(np.bincount(y).min()))
    n_splits = max(2, min(5, int(np.bincount(y).min()) - 1))
    if min_groups >= 2:
        n_group_splits = min(n_splits, min_groups)
        sgkf = StratifiedGroupKFold(n_splits=n_group_splits, shuffle=True, random_state=seed)
        y_pred_cv = cross_val_predict(pipeline, X, y, groups=groups, cv=sgkf, method="predict")
        cv_label = f"validación cruzada espacial agrupada (StratifiedGroupKFold, {n_group_splits} folds)"
    else:
        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        y_pred_cv = cross_val_predict(pipeline, X, y, cv=skf, method="predict")
        cv_label = f"validación cruzada estratificada ({n_splits} folds)"
    prec, rec, f1, _ = precision_recall_fscore_support(y, y_pred_cv, labels=[0, 1], zero_division=0)
    macro = {"precision": float(prec.mean()), "recall": float(rec.mean()), "f1": float(f1.mean())}

    # Ajuste final sobre el dataset completo y persistencia
    pipeline.fit(X, y)
    out_model = Path(model_path) if model_path else (Path(settings.processed_dir) / "ml_calibrator.joblib")
    out_model.parent.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump(
        {"pipeline": pipeline, "feature_names": FEATURE_NAMES, "trained_at_utc": datetime.now(timezone.utc).isoformat()},
        out_model,
    )

    # Importancias de features (promedio sobre los folds internos del calibrador)
    clf = pipeline.named_steps["clf"]
    if hasattr(clf, "calibrated_classifiers_"):
        importances = np.mean(
            [
                getattr(est, "estimator", est).feature_importances_
                for est in clf.calibrated_classifiers_
            ],
            axis=0,
        )
    else:
        importances = clf.feature_importances_
    pairs = sorted(zip(FEATURE_NAMES, importances), key=lambda t: -t[1])

    n_neg = int((y == 0).sum())
    n_pos = int((y == 1).sum())
    report_lines = [
        "# Benchmark del Calibrador ML (probabilidad calibrada vs score heurístico)",
        "",
        f"*Generado (UTC):* {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "## 1. Composición del dataset",
        "",
        f"- **Clase 0 (hard negatives reales):** {n_neg} candidatos descartados por el Juez Pericial VLM",
        "  (`DESCARTES_VLM.json`, NATURAL/ARTEFACTO) con features completas de los mapas por zona.",
        f"- **Clase 1 (positivos sintéticos plantados):** {n_pos} detecciones sobre estructuras con",
        "  verdad de campo conocida (recintos, círculos, terrazas, pozos, zanjas; 0.5 m/px y 30 m/px).",
        f"- **Vector de features ({len(FEATURE_NAMES)}):** " + ", ".join(f"`{f}`" for f in FEATURE_NAMES),
        "",
        f"## 2. Métricas ({cv_label}, predicción out-of-fold)",
        "",
        "| Clase | Precision | Recall | F1 |",
        "| :--- | :---: | :---: | :---: |",
        f"| **0 — NATURAL/ARTEFACTO** | {prec[0]:.3f} | {rec[0]:.3f} | {f1[0]:.3f} |",
        f"| **1 — ANTROPICA (positivo)** | {prec[1]:.3f} | {rec[1]:.3f} | {f1[1]:.3f} |",
        f"| **Macro-promedio** | {macro['precision']:.3f} | {macro['recall']:.3f} | {macro['f1']:.3f} |",
        "",
        "## 3. Importancia de features (GradientBoosting, promedio de folds)",
        "",
        "| Feature | Importancia |",
        "| :--- | :---: |",
    ]
    for name, imp in pairs:
        report_lines.append(f"| `{name}` | {float(imp):.4f} |")
    report_lines += [
        "",
        "## 4. Limitaciones declaradas (transparencia metodológica)",
        "",
        "- La clase positiva es **sintética**: mide separabilidad de los features, no recall en campo real.",
        "- Los positivos provienen de DTM plantados a 0.5 m/px y 30 m/px; existe sesgo de resolución",
        "  respecto a los negativos (GLO-30 supermuestreado a 2 m/px).",
        "- No hay positivos reales auditados aún (`MAPA_FINAL` vacío): al confirmarse hallazgos en campo,",
        "  re-entrenar con `train_calibrator()` para incluirlos.",
        "",
        f"Modelo persistido: `{out_model}`",
        "",
    ]
    out_report = Path(report_path) if report_path else BENCHMARK_REPORT_PATH
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "model_path": str(out_model),
        "report_path": str(out_report),
        "n_samples": int(len(y)),
        "n_negatives": n_neg,
        "n_positives": n_pos,
        "cv_metrics": {
            "precision_class0": float(prec[0]), "recall_class0": float(rec[0]), "f1_class0": float(f1[0]),
            "precision_class1": float(prec[1]), "recall_class1": float(rec[1]), "f1_class1": float(f1[1]),
            "macro": macro,
        },
        "feature_importances": {name: float(imp) for name, imp in pairs},
    }


def load_calibrator(model_path: Optional[Union[str, Path]] = None) -> Optional[Dict[str, Any]]:
    """Carga el modelo persistido (None si no existe: modo degradado a score heurístico)."""
    import joblib
    path = Path(model_path) if model_path else (Path(settings.processed_dir) / "ml_calibrator.joblib")
    if not path.exists():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


def score_candidate(
    props: Dict[str, Any],
    slrm_path: Optional[Union[str, Path]] = None,
    slope_path: Optional[Union[str, Path]] = None,
    model_path: Optional[Union[str, Path]] = None,
    model: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """Puntúa un candidato con la probabilidad calibrada del modelo (None si no hay modelo)."""
    bundle = model if model is not None else load_calibrator(model_path)
    if bundle is None:
        return None
    feats = extract_features(props, slrm_path=slrm_path, slope_path=slope_path)
    expected_names = bundle.get("feature_names", FEATURE_NAMES)
    X = np.array([_features_to_vector(feats, expected_names)], dtype=np.float64)
    prob = float(bundle["pipeline"].predict_proba(X)[0, 1])
    return round(prob, 4)
