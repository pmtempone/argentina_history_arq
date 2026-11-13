"""Tests para generación de láminas ciegas, limpieza de metadatos PNG/EXIF y concordancia inter-evaluador."""

from __future__ import annotations

import csv
import json
import re
import struct
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image, PngImagePlugin
from rasterio.transform import from_origin

from src.core.blind_review import (
    BLIND_EVALUATOR_COLUMNS,
    FORBIDDEN_PNG_CHUNKS,
    compute_inter_rater_agreement,
    evaluate_blind_evaluator_sheets,
    export_blind_review_pack,
    render_blind_candidate_lamina,
    strip_png_metadata_and_verify,
)


def _read_chunk_types(png_path: Path) -> set[bytes]:
    raw = png_path.read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    pos = 8
    chunks: set[bytes] = set()
    while pos + 8 <= len(raw):
        length = struct.unpack(">I", raw[pos : pos + 4])[0]
        ctype = raw[pos + 4 : pos + 8]
        chunks.add(ctype)
        pos += 12 + length
        if ctype == b"IEND":
            break
    return chunks


def _create_synthetic_posgar_dtm_and_slrm(tmp_path: Path) -> tuple[Path, Path]:
    dtm_path = tmp_path / "synth_dtm.tif"
    slrm_path = tmp_path / "synth_slrm.tif"

    rows, cols = 60, 60
    res = 1.0
    origin_x, origin_y = 3500000.0, 6800000.0
    transform = from_origin(origin_x, origin_y, res, res)

    y_idx, x_idx = np.indices((rows, cols), dtype=np.float64)
    base_slope = 1200.0 + 0.05 * x_idx - 0.03 * y_idx
    mound = np.exp(-((x_idx - 30.0) ** 2 + (y_idx - 30.0) ** 2) / (2.0 * 4.5**2)) * 1.4
    dtm = base_slope + mound
    slrm = mound - np.mean(mound)

    profile = {
        "driver": "GTiff",
        "height": rows,
        "width": cols,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:5345",
        "transform": transform,
        "nodata": -9999.0,
    }
    with rasterio.open(dtm_path, "w", **profile) as dst:
        dst.write(dtm.astype(np.float32), 1)
    with rasterio.open(slrm_path, "w", **profile) as dst:
        dst.write(slrm.astype(np.float32), 1)

    return dtm_path, slrm_path


def test_strip_png_metadata_removes_text_exif_and_software_chunks(tmp_path: Path) -> None:
    dirty_png = tmp_path / "dirty.png"
    clean_png = tmp_path / "clean.png"

    arr = np.full((32, 32, 3), 120, dtype=np.uint8)
    img = Image.fromarray(arr, mode="RGB")

    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Software", "ArchaeoLiDAR-VLM-Secret")
    pnginfo.add_text("Description", "ARQ-0001 zona_1_tastil POSGAR 3500000,6800000")
    pnginfo.add_itxt("Comment", "confidence=0.98 verdict=NATURAL")

    exif = img.getexif()
    exif[0x010E] = "Secret ImageDescription EXIF"
    exif[0x0131] = "ArchaeoSoftware"

    img.save(dirty_png, format="PNG", pnginfo=pnginfo, exif=exif.tobytes())

    dirty_chunks = _read_chunk_types(dirty_png)
    assert dirty_chunks & FORBIDDEN_PNG_CHUNKS

    res = strip_png_metadata_and_verify(dirty_png, clean_png)
    assert res["metadata_stripped_verified"] is True
    assert res["exif_tag_count"] == 0
    assert res["info_keys"] == []
    assert len(res["sha256"]) == 64

    clean_chunks = _read_chunk_types(clean_png)
    assert not (clean_chunks & FORBIDDEN_PNG_CHUNKS)
    with Image.open(clean_png) as reopened:
        assert len(reopened.getexif()) == 0
        assert dict(reopened.info) == {}


def test_render_blind_candidate_lamina_and_pack_leakage_guards(tmp_path: Path) -> None:
    dtm_path, slrm_path = _create_synthetic_posgar_dtm_and_slrm(tmp_path)
    direct_out = tmp_path / "direct_blind.png"
    render_info = render_blind_candidate_lamina(
        dtm_path=dtm_path,
        slrm_path=slrm_path,
        bbox_posgar=(3500022.0, 6799962.0, 3500038.0, 6799978.0),
        out_png_path=direct_out,
        blind_id="BLIND-0001",
        buffer_m=10.0,
    )
    assert direct_out.exists()
    assert render_info["metadata_verification"]["metadata_stripped_verified"] is True
    assert not (_read_chunk_types(direct_out) & FORBIDDEN_PNG_CHUNKS)

    pack_dir = tmp_path / "blind_pack"
    items = [
        {
            "candidate_id": "ARQ-9001",
            "zone_key": "zona_1_tastil",
            "general_biome": "Arido_Altoandino",
            "dem_native_resolution_m": 1.0,
            "area_m2": 256.0,
            "ai_vlm_verdict": "NATURAL",
            "source_origin": "AI_REJECTED_CANDIDATE",
            "bbox": (3500022.0, 6799962.0, 3500038.0, 6799978.0),
            "dtm_path": str(dtm_path),
            "slrm_path": str(slrm_path),
        },
        {
            "candidate_id": "ARQ-9002",
            "zone_key": "zona_20_valle_grande",
            "general_biome": "Selva_Pedemontana",
            "dem_native_resolution_m": 1.0,
            "area_m2": 180.0,
            "ai_vlm_verdict": "ARTEFACTO",
            "source_origin": "AI_REJECTED_CANDIDATE",
            "bbox": (3500020.0, 6799960.0, 3500036.0, 6799976.0),
            "dtm_path": str(dtm_path),
            "slrm_path": str(slrm_path),
        },
    ]
    summary = export_blind_review_pack(out_dir=pack_dir, items=items, max_items=2, seed=7)
    assert summary["n_items"] == 2
    assert summary["all_metadata_stripped_verified"] is True

    csv_path = Path(summary["evaluator_csv_path"])
    manifest_path = Path(summary["manifest_path"])
    key_path = Path(summary["confidential_key_path"])

    csv_text = csv_path.read_text(encoding="utf-8")
    manifest_text = manifest_path.read_text(encoding="utf-8")

    # Verificar ausencia total de IDs reales, nombres de zona, veredictos IA o coordenadas en artefactos para evaluadores
    for forbidden_token in ("ARQ-9001", "ARQ-9002", "tastil", "valle_grande", "35000", "67999", "ARTEFACTO", "NATURAL"):
        assert forbidden_token not in csv_text
        assert forbidden_token not in manifest_text

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert tuple(reader.fieldnames or ()) == BLIND_EVALUATOR_COLUMNS
        rows = list(reader)
        assert len(rows) == 2
        assert all(re.fullmatch(r"BLIND-\d{4}", r["blind_id"]) for r in rows)

    key_data = json.loads(key_path.read_text(encoding="utf-8"))
    assert len(key_data["mapping"]) == 2
    assert {m["candidate_id"] for m in key_data["mapping"]} == {"ARQ-9001", "ARQ-9002"}
    for m in key_data["mapping"]:
        img_p = pack_dir / m["image_relpath"]
        assert img_p.exists()
        assert not (_read_chunk_types(img_p) & FORBIDDEN_PNG_CHUNKS)


def test_inter_rater_agreement_cohen_fleiss_and_weighted_kappa() -> None:
    # 1. Acuerdo perfecto entre 2 evaluadores con >= 2 clases -> all kappas == 1.0
    perfect_2 = [
        ["ARCHAEOLOGICAL_PLAUSIBLE", "ARCHAEOLOGICAL_PLAUSIBLE"],
        ["NATURAL_GEOFORM", "NATURAL_GEOFORM"],
        ["ARCHAEOLOGICAL_PLAUSIBLE", "ARCHAEOLOGICAL_PLAUSIBLE"],
        ["INCONCLUSIVE", "INCONCLUSIVE"],
    ]
    res_p2 = compute_inter_rater_agreement(perfect_2)
    assert res_p2["percent_agreement"] == pytest.approx(1.0)
    assert res_p2["cohens_kappa"] == pytest.approx(1.0)
    assert res_p2["fleiss_kappa"] == pytest.approx(1.0)
    assert res_p2["weighted_kappa_linear"] == pytest.approx(1.0)
    assert res_p2["weighted_kappa_quadratic"] == pytest.approx(1.0)
    lo, hi = res_p2["percent_agreement_wilson_ci95"]
    assert 0.5 < lo < hi <= 1.0

    # 2. Acuerdo esperado al azar (independencia exacta en 2x2 simétrico) -> kappa == 0.0
    chance_2 = [
        ["A", "A"],
        ["A", "B"],
        ["B", "A"],
        ["B", "B"],
    ]
    res_chance = compute_inter_rater_agreement(chance_2, categories=["A", "B"])
    assert res_chance["percent_agreement"] == pytest.approx(0.5)
    assert res_chance["cohens_kappa"] == pytest.approx(0.0, abs=1e-6)
    assert res_chance["fleiss_kappa"] == pytest.approx(0.0, abs=1e-6)

    # 3. Matriz de texto clasico Fleiss (ejemplo nominal 3 evaluadores sobre 6 ítems) y ordinal ponderado
    three_raters = [
        ["ARCH", "ARCH", "ARCH"],
        ["NAT", "NAT", "ARCH"],
        ["NAT", "NAT", "NAT"],
        ["MOD", "MOD", "NAT"],
        ["ARCH", "ARCH", "NAT"],
        ["MOD", "MOD", "MOD"],
    ]
    res_3 = compute_inter_rater_agreement(three_raters, categories=["ARCH", "NAT", "MOD"])
    # Verificación exacta manual: P_i = [1, 1/3, 1, 1/3, 1/3, 1] => P_bar = 4/6 = 2/3
    # Conteos totales: ARCH=6, NAT=7, MOD=5 (total=18) => P_e = (6^2 + 7^2 + 5^2)/324 = 110/324
    expected_pbar = 4.0 / 6.0
    expected_pe = (36 + 49 + 25) / 324.0
    expected_fleiss = (expected_pbar - expected_pe) / (1.0 - expected_pe)
    assert res_3["n_raters"] == 3
    assert res_3["percent_agreement"] == pytest.approx(expected_pbar, abs=1e-5)
    assert res_3["fleiss_kappa"] == pytest.approx(expected_fleiss, abs=1e-5)

    # 4. Escala ordinal 1..4: desacuerdo leve (desfasaje de 1 paso) => quadratic kappa > linear kappa > unweighted
    ordinal_ratings = [
        [1, 1],
        [1, 2],
        [2, 2],
        [2, 3],
        [3, 3],
        [3, 4],
        [4, 4],
        [4, 3],
    ]
    res_ord = compute_inter_rater_agreement(ordinal_ratings, categories=[1, 2, 3, 4])
    assert res_ord["weighted_kappa_quadratic"] > res_ord["weighted_kappa_linear"] > res_ord["cohens_kappa"]


def test_evaluate_blind_evaluator_sheets_end_to_end(tmp_path: Path) -> None:
    r1_csv = tmp_path / "rater1.csv"
    r2_csv = tmp_path / "rater2.csv"
    rows1 = [
        {"blind_id": "BLIND-0001", "reviewer_id": "ESP-A", "decision": "NATURAL_GEOFORM", "severity_ordinal_1_to_4": "1"},
        {"blind_id": "BLIND-0002", "reviewer_id": "ESP-A", "decision": "ARCHAEOLOGICAL_PLAUSIBLE", "severity_ordinal_1_to_4": "4"},
        {"blind_id": "BLIND-0003", "reviewer_id": "ESP-A", "decision": "NATURAL_GEOFORM", "severity_ordinal_1_to_4": "2"},
        {"blind_id": "BLIND-0004", "reviewer_id": "ESP-A", "decision": "INCONCLUSIVE", "severity_ordinal_1_to_4": "2"},
    ]
    rows2 = [
        {"blind_id": "BLIND-0001", "reviewer_id": "ESP-B", "decision": "NATURAL_GEOFORM", "severity_ordinal_1_to_4": "1"},
        {"blind_id": "BLIND-0002", "reviewer_id": "ESP-B", "decision": "ARCHAEOLOGICAL_PLAUSIBLE", "severity_ordinal_1_to_4": "3"},
        {"blind_id": "BLIND-0003", "reviewer_id": "ESP-B", "decision": "NATURAL_GEOFORM", "severity_ordinal_1_to_4": "1"},
        {"blind_id": "BLIND-0004", "reviewer_id": "ESP-B", "decision": "INCONCLUSIVE", "severity_ordinal_1_to_4": "2"},
    ]
    for path, rows in ((r1_csv, rows1), (r2_csv, rows2)):
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["blind_id", "reviewer_id", "decision", "severity_ordinal_1_to_4"])
            writer.writeheader()
            writer.writerows(rows)

    res = evaluate_blind_evaluator_sheets([r1_csv, r2_csv])
    assert res["n_raters"] == 2
    assert len(res["common_blind_ids"]) == 4
    assert res["nominal_decision_agreement"]["cohens_kappa"] == pytest.approx(1.0)
    assert res["ordinal_severity_agreement"]["weighted_kappa_quadratic"] > 0.7
