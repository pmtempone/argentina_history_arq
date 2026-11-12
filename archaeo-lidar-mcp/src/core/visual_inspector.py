"""Inspección visual multimodal: láminas compuestas (Hillshade 1.5x + SLRM + Perfil + Render 3D Blender) y cortes de nube cruda."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import matplotlib
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from scipy.ndimage import map_coordinates

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from src.schemas import CrossSectionResult  # noqa: E402

try:
    import pdal

    HAS_PDAL = True
except ImportError:
    pdal = None  # type: ignore[assignment]
    HAS_PDAL = False


def _compute_multidirectional_hillshade(
    dtm: np.ndarray,
    res_x: float,
    res_y: float,
    z_factor: float = 1.5,
) -> np.ndarray:
    """Calcula un Hillshade multidireccional combinando 4 acimuts (315°, 45°, 135°, 225°) con exageración 1.5x."""
    valid_mask = ~np.isnan(dtm)
    filled = np.where(valid_mask, dtm, np.nanmedian(dtm) if np.any(valid_mask) else 0.0)

    dy, dx = np.gradient(filled * z_factor, res_y, res_x)
    slope = np.pi / 2.0 - np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)

    altitudes_deg = [45.0, 45.0, 45.0, 45.0]
    azimuths_deg = [315.0, 45.0, 135.0, 225.0]
    weights = [0.40, 0.25, 0.15, 0.20]

    hillshade = np.zeros_like(filled, dtype=np.float64)
    for alt_deg, az_deg, w in zip(altitudes_deg, azimuths_deg, weights):
        zenith_rad = np.radians(90.0 - alt_deg)
        azimuth_rad = np.radians((360.0 - az_deg + 90.0) % 360.0)
        shaded = np.sin(zenith_rad) * np.sin(slope) + (
            np.cos(zenith_rad) * np.cos(slope) * np.cos(azimuth_rad - aspect)
        )
        hillshade += w * np.clip(shaded, 0.0, 1.0)

    hillshade[~valid_mask] = np.nan
    return hillshade


def find_blender_binary() -> Optional[str]:
    """Detecta la ruta del ejecutable de Blender en macOS o en el PATH del sistema."""
    env_bin = os.environ.get("BLENDER_BIN")
    if env_bin and Path(env_bin).exists():
        return str(Path(env_bin).resolve())

    macos_candidates = [
        Path("/Applications/Blender.app/Contents/MacOS/Blender"),
        Path.home() / ".local" / "bin" / "blender",
    ]
    for candidate in macos_candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

    which_bin = shutil.which("blender") or shutil.which("Blender")
    if which_bin:
        return str(which_bin)

    return None


def export_normalized_heightmap(
    crop_array: np.ndarray,
    out_png_path: Union[str, Path],
) -> Path:
    """Exporta un recorte 2D de elevación/SLRM como imagen PNG de 16 bits normalizada [0, 65535]."""
    dst_path = Path(out_png_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    arr = np.nan_to_num(np.asarray(crop_array, dtype=np.float64), nan=0.0)
    vmin = float(np.percentile(arr, 2.0))
    vmax = float(np.max(arr))
    span = vmax - vmin
    if span <= 1e-6:
        norm = np.zeros_like(arr, dtype=np.float64)
    else:
        norm = np.clip((arr - vmin) / span, 0.0, 1.0)

    # Suavizado gaussiano ligero (3x3) para evitar dientes de sierra de píxel en la malla desplazada
    norm_u16 = (norm * 65535.0).astype(np.uint16)
    norm_u16 = cv2.GaussianBlur(norm_u16, (3, 3), 0)
    cv2.imwrite(str(dst_path), norm_u16)
    return dst_path


def render_blender_3d_candidate(
    candidate_id: str,
    slrm_crop_path: Union[str, Path, np.ndarray],
    out_png_path: Union[str, Path],
    width_m: float = 50.0,
    length_m: float = 50.0,
    exaggeration: float = 1.8,
    res_x: int = 1280,
    res_y: int = 720,
) -> Optional[str]:
    """Ejecuta Blender en modo headless para renderizar el terreno 3D isométrico en falso color térmico.

    Args:
        candidate_id: Identificador del candidato (ej. `ARQ-0026`).
        slrm_crop_path: Ruta a un GeoTIFF/PNG del recorte SLRM o matriz `np.ndarray` de elevación local.
        out_png_path: Ruta de destino para el render 3D (`<candidate_id>_3d_thermal.png`).
        width_m: Ancho métrico del recorte en eje Este (m).
        length_m: Largo métrico del recorte en eje Norte (m).
        exaggeration: Exageración vertical del modificador Displace (por defecto 1.8x).
        res_x: Ancho del render en píxeles (por defecto 1280).
        res_y: Alto del render en píxeles (por defecto 720).

    Returns:
        Ruta como string al PNG renderizado, o `None` si Blender no está disponible.
    """
    blender_bin = find_blender_binary()
    if not blender_bin:
        return None

    dst_png = Path(out_png_path).resolve()
    dst_png.parent.mkdir(parents=True, exist_ok=True)
    hm_png = dst_png.parent / f"{candidate_id}_heightmap_16bit.png"

    if isinstance(slrm_crop_path, np.ndarray):
        export_normalized_heightmap(slrm_crop_path, hm_png)
    else:
        src_p = Path(slrm_crop_path)
        if src_p.suffix.lower() in {".tif", ".tiff"}:
            with rasterio.open(src_p) as src_ds:
                arr = src_ds.read(1).astype(np.float64)
                if src_ds.nodata is not None:
                    arr[np.isclose(arr, float(src_ds.nodata)) | (arr <= -9000.0)] = np.nan
            export_normalized_heightmap(arr, hm_png)
        else:
            hm_png = src_p.resolve()

    script_path = Path(__file__).resolve().parent.parent / "utils" / "blender_render.py"
    cmd = [
        blender_bin,
        "-b",
        "-P",
        str(script_path),
        "--",
        "--heightmap",
        str(hm_png),
        "--output",
        str(dst_png),
        "--width-m",
        str(max(5.0, float(width_m))),
        "--length-m",
        str(max(5.0, float(length_m))),
        "--exaggeration",
        str(float(exaggeration)),
        "--res-x",
        str(int(res_x)),
        "--res-y",
        str(int(res_y)),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if proc.returncode == 0 and dst_png.exists():
            return str(dst_png)
    except Exception:
        return None

    return None


def render_candidate_composite(
    dtm_path: Union[str, Path],
    slrm_path: Union[str, Path],
    bbox_posgar: Sequence[float],
    out_png_path: Union[str, Path],
    centroid_posgar: Optional[Sequence[float]] = None,
    buffer_m: float = 15.0,
    candidate_id: Optional[str] = None,
    include_3d_render: Optional[bool] = None,
) -> str:
    """Genera una lámina compuesta (3 o 4 paneles) para inspección visual multimodal por LLM/Arqueólogo.

    Panel 1: Hillshade multidireccional con exageración vertical 1.5x y traza que cruza el centroide.
    Panel 2: Modelo de Relieve Local (SLRM) con mapa de color de alto contraste (`viridis`).
    Panel 3: Perfil topográfico 2D (sobreelevación SLRM) atravesando dinámicamente el centroide
             del candidato hacia los extremos del bounding box extendido en 15 metros.
    Panel 4 (si Blender 3D está activo): Render 3D isométrico volumétrico en falso color térmico/infrarrojo.

    Args:
        dtm_path: Ruta al archivo GeoTIFF del DTM en POSGAR 2007.
        slrm_path: Ruta al archivo GeoTIFF del SLRM en POSGAR 2007.
        bbox_posgar: Secuencia `[minx, miny, maxx, maxy]` en coordenadas métricas POSGAR 2007.
        out_png_path: Ruta de salida para la imagen PNG compuesta.
        centroid_posgar: Tupla o lista opcional `[cx, cy]` en POSGAR 2007 del candidato arqueológico.
                         Si no se provee, se calcula como el centroide geométrico de `bbox_posgar`.
        buffer_m: Margen de extensión métrica del bounding box en metros (por defecto 15.0 m).
        candidate_id: Identificador opcional del candidato para nombrar el render 3D térmico.
        include_3d_render: Si es `True`, genera e incrusta el 4to panel 3D con Blender. Si es `None`,
                           se activa automáticamente fuera de corridas de tests unitarios rápidos.

    Returns:
        Ruta como string a la imagen PNG generada.
    """
    if len(bbox_posgar) != 4:
        raise ValueError("bbox_posgar debe contener exactamente 4 valores: [minx, miny, maxx, maxy].")

    minx, miny, maxx, maxy = [float(v) for v in bbox_posgar]
    dst_png = Path(out_png_path)
    dst_png.parent.mkdir(parents=True, exist_ok=True)

    # Determinar centroide métrico específico del candidato
    if centroid_posgar is not None and len(centroid_posgar) >= 2:
        cx, cy = float(centroid_posgar[0]), float(centroid_posgar[1])
    else:
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    # Extender el bounding box en buffer_m metros (por defecto 15 m)
    ext_minx = minx - float(buffer_m)
    ext_maxx = maxx + float(buffer_m)
    ext_miny = miny - float(buffer_m)
    ext_maxy = maxy + float(buffer_m)

    with rasterio.open(dtm_path) as dtm_src, rasterio.open(slrm_path) as slrm_src:
        window = from_bounds(ext_minx, ext_miny, ext_maxx, ext_maxy, transform=dtm_src.transform)
        # Si la ventana cae fuera o es muy pequeña, leer todo el raster como respaldo seguro
        if window.width < 4 or window.height < 4:
            dtm_crop = dtm_src.read(1).astype(np.float64)
            slrm_crop = slrm_src.read(1).astype(np.float64)
            bounds_ext = (dtm_src.bounds.left, dtm_src.bounds.right, dtm_src.bounds.bottom, dtm_src.bounds.top)
            crop_transform = dtm_src.transform
        else:
            dtm_crop = dtm_src.read(1, window=window, boundless=True, fill_value=np.nan).astype(np.float64)
            slrm_crop = slrm_src.read(1, window=window, boundless=True, fill_value=np.nan).astype(np.float64)
            bounds_ext = (ext_minx, ext_maxx, ext_miny, ext_maxy)
            crop_transform = rasterio.windows.transform(window, dtm_src.transform)

        if dtm_src.nodata is not None:
            dtm_crop[np.isclose(dtm_crop, float(dtm_src.nodata)) | (dtm_crop <= -9000.0)] = np.nan
        if slrm_src.nodata is not None:
            slrm_crop[np.isclose(slrm_crop, float(slrm_src.nodata)) | (slrm_crop <= -9000.0)] = np.nan

        res_x = float(abs(dtm_src.transform.a))
        res_y = float(abs(dtm_src.transform.e))

    hillshade = _compute_multidirectional_hillshade(dtm_crop, res_x=res_x, res_y=res_y, z_factor=1.5)

    # Definir traza dinámica A-A' que atraviesa el centroide exacto (cx, cy)
    p1_x = bounds_ext[0]
    p2_x = bounds_ext[1]
    profile_len_m = max(1e-3, abs(p2_x - p1_x))
    length_y_m = max(1e-3, abs(bounds_ext[3] - bounds_ext[2]))
    num_pts = max(40, int(np.ceil(profile_len_m / min(res_x, res_y))))

    x_samples = np.linspace(p1_x, p2_x, num_pts)
    y_samples = np.full(num_pts, cy)
    dist_m = np.linspace(0.0, profile_len_m, num_pts)

    # Extraer perfil continuo mediante interpolación bilinear de coordenadas
    inv_t = ~crop_transform
    col_f = inv_t.a * x_samples + inv_t.b * y_samples + inv_t.c
    row_f = inv_t.d * x_samples + inv_t.e * y_samples + inv_t.f
    profile_slrm = map_coordinates(
        np.nan_to_num(slrm_crop, nan=0.0),
        [row_f, col_f],
        order=1,
        mode="nearest",
    )

    if include_3d_render is None:
        should_render_3d = "PYTEST_CURRENT_TEST" not in os.environ
    else:
        should_render_3d = bool(include_3d_render)

    cand_tag = candidate_id or dst_png.stem.replace("_composite", "")
    thermal_3d_png_path: Optional[str] = None
    if should_render_3d:
        out_3d = dst_png.parent / f"{cand_tag}_3d_thermal.png"
        thermal_3d_png_path = render_blender_3d_candidate(
            candidate_id=cand_tag,
            slrm_crop_path=slrm_crop,
            out_png_path=out_3d,
            width_m=profile_len_m,
            length_m=length_y_m,
            exaggeration=1.8,
        )

    if thermal_3d_png_path and Path(thermal_3d_png_path).exists():
        fig, axes_grid = plt.subplots(2, 2, figsize=(15, 11), dpi=150)
        ax0 = axes_grid[0, 0]
        ax1 = axes_grid[0, 1]
        ax2 = axes_grid[1, 0]
        ax3 = axes_grid[1, 1]
    else:
        fig, axes_row = plt.subplots(1, 3, figsize=(16, 5), dpi=150)
        ax0 = axes_row[0]
        ax1 = axes_row[1]
        ax2 = axes_row[2]
        ax3 = None

    # Panel 1: Hillshade 1.5x con traza y centroide
    im0 = ax0.imshow(hillshade, cmap="gray", extent=bounds_ext, origin="upper")
    ax0.plot(
        [p1_x, p2_x],
        [cy, cy],
        color="crimson",
        linestyle="--",
        linewidth=1.4,
        label="Traza A-A' (Centroide)",
    )
    ax0.plot(
        cx,
        cy,
        marker="o",
        color="yellow",
        markersize=6,
        markeredgecolor="red",
        label=f"Centroide ({cx:.1f}, {cy:.1f})",
    )
    ax0.set_title("1. Hillshade Multidireccional (Exag. 1.5x)")
    ax0.set_xlabel("Este POSGAR (m)")
    ax0.set_ylabel("Norte POSGAR (m)")
    ax0.legend(loc="lower right", fontsize=8)
    plt.colorbar(im0, ax=ax0, fraction=0.046, pad=0.04, label="Reflectancia")

    # Panel 2: SLRM (viridis) con traza y centroide
    im1 = ax1.imshow(slrm_crop, cmap="viridis", vmin=-0.5, vmax=1.0, extent=bounds_ext, origin="upper")
    ax1.plot([p1_x, p2_x], [cy, cy], color="white", linestyle="--", linewidth=1.4)
    ax1.plot(cx, cy, marker="o", color="yellow", markersize=6, markeredgecolor="black")
    ax1.set_title("2. Simple Local Relief Model (SLRM)")
    ax1.set_xlabel("Este POSGAR (m)")
    ax1.set_ylabel("Norte POSGAR (m)")
    plt.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04, label="Δ Elevación Local (m)")

    # Panel 3: Perfil Topográfico 2D sobre la traza del centroide
    ax2.plot(dist_m, profile_slrm, color="#1f77b4", linewidth=2.0, label="Micro-relieve SLRM (m)")
    ax2.axhline(0.0, color="gray", linestyle=":", linewidth=1.0)
    ax2.fill_between(
        dist_m,
        0.0,
        np.nan_to_num(profile_slrm, nan=0.0),
        where=(np.nan_to_num(profile_slrm, nan=0.0) >= 0.15),
        color="#ff7f0e",
        alpha=0.45,
        label="Anomalía Positiva (>= 0.15 m)",
    )
    centroid_dist_on_trace = cx - p1_x
    ax2.axvline(
        centroid_dist_on_trace,
        color="crimson",
        linestyle=":",
        linewidth=1.5,
        label="Eje del Centroide",
    )
    ax2.set_title("3. Perfil Topográfico 2D sobre Centroide")
    ax2.set_xlabel("Distancia Horizontal en Traza (m)")
    ax2.set_ylabel("Sobre-elevación SLRM (m)")
    ax2.grid(True, linestyle="--", alpha=0.4)
    ax2.legend(loc="upper right", fontsize=8)

    # Panel 4: Render 3D Volumétrico Isométrico Estilo Infrarrojo (Blender)
    if ax3 is not None and thermal_3d_png_path is not None:
        img_3d = mpimg.imread(thermal_3d_png_path)
        ax3.imshow(img_3d)
        ax3.set_title("4. Modelo 3D Isométrico Infrarrojo (Blender EEVEE - Exag. 1.8x)")
        ax3.axis("off")

    fig.tight_layout()
    fig.savefig(dst_png, bbox_inches="tight")
    plt.close(fig)

    return str(dst_png)


def _load_pointcloud_arrays(las_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Carga vectores X, Y, Z y Classification de un archivo .las/.laz o respaldo .npz/.tif."""
    if las_path.suffix.lower() == ".npz":
        data = np.load(las_path)
        return (
            data["X"].astype(np.float64),
            data["Y"].astype(np.float64),
            data["Z"].astype(np.float64),
            data["Classification"].astype(np.int32),
        )

    if HAS_PDAL and las_path.suffix.lower() in {".las", ".laz"}:
        pipeline = pdal.Pipeline(json.dumps([{"type": "readers.las", "filename": str(las_path)}]))
        pipeline.execute()
        arr = pipeline.arrays[0]
        return (
            arr["X"].astype(np.float64),
            arr["Y"].astype(np.float64),
            arr["Z"].astype(np.float64),
            arr["Classification"].astype(np.int32),
        )

    if las_path.suffix.lower() in {".tif", ".tiff"}:
        with rasterio.open(las_path) as src:
            band = src.read(1).astype(np.float64)
            rows, cols = np.where(~np.isnan(band) & (band > -9000.0))
            xs, ys = rasterio.transform.xy(src.transform, rows, cols)
            zs = band[rows, cols]
            cls = np.full_like(zs, 2, dtype=np.int32)
            return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64), zs, cls

    raise RuntimeError(f"No es posible leer la nube de puntos '{las_path}' sin soporte PDAL activo.")


def render_pointcloud_cross_section(
    las_path: Union[str, Path],
    p1_xy: Sequence[float],
    p2_xy: Sequence[float],
    swath_width_m: float = 2.0,
    out_png_path: Union[str, Path] = "cross_section.png",
) -> CrossSectionResult:
    """Extrae una franja (swath) de la nube de puntos cruda y renderiza su corte transversal 2D.

    Distingue retornos de vegetación (ASPRS Clases 3, 4 y 5 en verde semitransparente) de los
    retornos de suelo firme (ASPRS Clase 2 en marrón sólido), calculando la densidad efectiva
    de puntos de suelo por metro cuadrado (`ground_density_pts_m2`) y la integridad del perfil.

    Args:
        las_path: Ruta al archivo `.las/.laz` (o `.npz`/`.tif` en tests sintéticos).
        p1_xy: Punto inicial `[x1, y1]` del corte en coordenadas métricas POSGAR 2007.
        p2_xy: Punto final `[x2, y2]` del corte en coordenadas métricas POSGAR 2007.
        swath_width_m: Ancho total de la franja de muestreo en metros (por defecto 2.0 m).
        out_png_path: Ruta de salida para el gráfico PNG del corte transversal.

    Returns:
        Instancia de `CrossSectionResult` con las métricas cuantitativas y ruta al gráfico.
    """
    src_path = Path(las_path)
    dst_png = Path(out_png_path)
    dst_png.parent.mkdir(parents=True, exist_ok=True)

    x1, y1 = float(p1_xy[0]), float(p1_xy[1])
    x2, y2 = float(p2_xy[0]), float(p2_xy[1])
    dx = x2 - x1
    dy = y2 - y1
    profile_length_m = float(np.hypot(dx, dy))
    if profile_length_m <= 1e-6:
        raise ValueError("Los puntos p1_xy y p2_xy del corte transversal no pueden ser idénticos.")

    ux = dx / profile_length_m
    uy = dy / profile_length_m

    xs, ys, zs, classifications = _load_pointcloud_arrays(src_path)

    # Proyección ortogonal sobre el vector p1 -> p2
    rel_x = xs - x1
    rel_y = ys - y1
    along_dist = rel_x * ux + rel_y * uy
    perp_dist = np.abs(-rel_x * uy + rel_y * ux)

    half_swath = float(swath_width_m) / 2.0
    in_swath = (along_dist >= 0.0) & (along_dist <= profile_length_m) & (perp_dist <= half_swath)

    swath_d = along_dist[in_swath]
    swath_z = zs[in_swath]
    swath_c = classifications[in_swath]

    ground_mask = swath_c == 2
    veg_mask = np.isin(swath_c, [3, 4, 5])

    ground_count = int(np.sum(ground_mask))
    veg_count = int(np.sum(veg_mask))

    swath_area_m2 = max(1e-6, profile_length_m * float(swath_width_m))
    ground_density = float(ground_count / swath_area_m2)

    # Calcular cobertura longitudinal del suelo en bins de 1 m para estimar integridad del perfil
    num_bins = max(1, int(np.ceil(profile_length_m)))
    if ground_count > 0:
        hist, _ = np.histogram(swath_d[ground_mask], bins=num_bins, range=(0.0, profile_length_m))
        occupied_ratio = float(np.mean(hist > 0))
        density_factor = min(1.0, ground_density / 2.0)
        integrity_score = round(0.6 * occupied_ratio + 0.4 * density_factor, 4)
    else:
        integrity_score = 0.0

    # Renderizado del scatter plot 2D
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)
    if veg_count > 0:
        ax.scatter(
            swath_d[veg_mask],
            swath_z[veg_mask],
            c="#2ca02c",
            alpha=0.45,
            s=14,
            label=f"Vegetación ASPRS 3-5 ({veg_count} pts)",
        )
    if ground_count > 0:
        ax.scatter(
            swath_d[ground_mask],
            swath_z[ground_mask],
            c="#8c564b",
            alpha=0.95,
            s=18,
            label=f"Suelo ASPRS 2 ({ground_count} pts)",
        )
        # Línea de tendencia suave del suelo si hay suficientes puntos
        order = np.argsort(swath_d[ground_mask])
        ax.plot(
            swath_d[ground_mask][order],
            swath_z[ground_mask][order],
            color="#5c3228",
            linewidth=1.0,
            alpha=0.6,
        )

    ax.set_title(
        f"Corte Transversal de Nube Cruda (Ancho={swath_width_m:.1f} m | "
        f"Densidad Suelo={ground_density:.2f} pts/m²)"
    )
    ax.set_xlabel("Distancia Horizontal sobre la Traza (m)")
    ax.set_ylabel("Cota Z (m s.n.m.)")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper right")

    fig.tight_layout()
    fig.savefig(dst_png, bbox_inches="tight")
    plt.close(fig)

    return CrossSectionResult(
        plot_image_path=str(dst_png),
        ground_points_count=ground_count,
        vegetation_points_count=veg_count,
        ground_density_pts_m2=round(ground_density, 4),
        profile_integrity_score=float(np.clip(integrity_score, 0.0, 1.0)),
    )
