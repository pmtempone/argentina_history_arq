"""Tests unitarios y de integración para el renderizador 3D isométrico infrarrojo en Blender (bpy)."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.core.relief_models import compute_slrm
from src.core.visual_inspector import (
    export_normalized_heightmap,
    find_blender_binary,
    render_blender_3d_candidate,
    render_candidate_composite,
)


def test_find_blender_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verifica la detección de Blender en el sistema o vía variable BLENDER_PATH."""
    blender_bin = find_blender_binary()
    if blender_bin is not None:
        assert Path(blender_bin).exists()
        return

    # Fallback para entornos mínimos sin Blender preinstalado: valida detección vía BLENDER_PATH
    fake_blender = tmp_path / "blender"
    fake_blender.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_blender.chmod(0o755)
    monkeypatch.setenv("BLENDER_PATH", str(fake_blender))
    assert find_blender_binary() == str(fake_blender)


def test_export_normalized_heightmap(tmp_path: Path) -> None:
    """Verifica la exportación de un recorte de microrelieve a PNG de 16 bits."""
    arr = np.zeros((64, 64), dtype=np.float64)
    arr[16:48, 16:48] = 0.65
    arr[20:44, 20:44] = 0.05  # recinto hueco (pirca perimetral)

    out_png = tmp_path / "test_hm.png"
    res_path = export_normalized_heightmap(arr, out_png)
    assert res_path.exists()

    img_u16 = cv2.imread(str(res_path), cv2.IMREAD_UNCHANGED)
    assert img_u16 is not None
    assert img_u16.dtype == np.uint16
    assert img_u16.shape == (64, 64)
    assert int(img_u16.max()) > 50000
    assert int(img_u16.min()) == 0


def test_blender_render_cli_execution(tmp_path: Path) -> None:
    """Ejecuta el renderizado 3D headless en Blender 4.2 con EEVEE-Next y valida la imagen térmica resultante."""
    if not find_blender_binary():
        pytest.skip("Blender no está instalado en este entorno.")

    arr = np.zeros((80, 80), dtype=np.float64)
    # Simular muros ortogonales pircados (+0.60 m)
    arr[20:60, 20:60] = 0.60
    arr[24:56, 24:56] = 0.02

    out_3d = tmp_path / "ARQ-TEST_3d_thermal.png"
    rendered = render_blender_3d_candidate(
        candidate_id="ARQ-TEST",
        slrm_crop_path=arr,
        out_png_path=out_3d,
        width_m=40.0,
        length_m=40.0,
        exaggeration=1.8,
        res_x=1280,
        res_y=720,
    )
    assert rendered is not None
    assert out_3d.exists()

    img = cv2.imread(str(out_3d), cv2.IMREAD_COLOR)
    assert img is not None
    assert img.shape[0] == 720
    assert img.shape[1] == 1280
    # Debe tener variación cromática entre el fondo oscuro y los muros amarillos/blancos térmicos
    assert float(img.std()) > 10.0


def test_composite_4_panels_with_blender(synthetic_posgar_dtm: Path, tmp_path: Path) -> None:
    """Verifica que render_candidate_composite genere la lámina 2x2 de 4 paneles cuando include_3d_render=True."""
    if not find_blender_binary():
        pytest.skip("Blender no está instalado en este entorno.")

    slrm_tif = tmp_path / "slrm.tif"
    compute_slrm(synthetic_posgar_dtm, slrm_tif, radius_m=15.0)

    comp_png = tmp_path / "ARQ-0026_composite.png"
    res = render_candidate_composite(
        dtm_path=synthetic_posgar_dtm,
        slrm_path=slrm_tif,
        bbox_posgar=[2500055.0, 7000127.0, 2500075.0, 7000143.0],
        out_png_path=comp_png,
        centroid_posgar=[2500065.0, 7000135.0],
        buffer_m=15.0,
        candidate_id="ARQ-0026",
        include_3d_render=True,
    )
    assert Path(res).exists()
    thermal_3d = tmp_path / "ARQ-0026_3d_thermal.png"
    assert thermal_3d.exists()
