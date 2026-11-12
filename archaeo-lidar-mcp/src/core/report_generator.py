"""Generador de dossier técnico patrimonial para el INAPL (Ley 25.743) con resguardo de coordenadas."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Union


def generate_inapl_dossier(
    candidate_data: Dict[str, Any],
    out_dir: Union[str, Path],
) -> str:
    """Genera el Dossier Técnico Arqueológico en Markdown y separa las coordenadas en un anexo confidencial.

    Cumple con los lineamientos de resguardo preventivo de la Ley Nacional N° 25.743 (Protección del
    Patrimonio Arqueológico y Paleontológico) evitando exponer coordenadas puntuales exactas en el
    documento principal de circulación técnica y almacenándolas de forma aislada en
    `ANEXO_CONFIDENCIAL_COORDENADAS.json`.

    Args:
        candidate_data: Diccionario con la información morfológica, topográfica, validación espacial
            y referencias de láminas del candidato arqueológico.
        out_dir: Directorio de salida donde se escribirán el informe `.md` y el anexo `.json`.

    Returns:
        Ruta como string al archivo Markdown del dossier técnico generado.
    """
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    candidate_id = str(candidate_data.get("id") or candidate_data.get("candidate_id") or "ARQ-0001")
    timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Extraer y aislar datos sensibles de georreferenciación exacta
    centroid_wgs84 = candidate_data.get("centroid_wgs84") or candidate_data.get("coordinates_wgs84")
    geometry_geojson = candidate_data.get("geometry_geojson") or candidate_data.get("geometry")
    bbox_posgar = candidate_data.get("bbox_posgar")
    crs_epsg = candidate_data.get("crs_epsg", "EPSG:5344")

    confidential_payload: Dict[str, Any] = {
        "notice": (
            "INFORMACIÓN SENSIBLE PROTEGIDA - LEY NACIONAL N° 25.743 (INAPL / RENYCOA). "
            "PROHIBIDA SU DIFUSIÓN PÚBLICA PARA PREVENIR GUAQUEO Y SAQUEO PATRIMONIAL."
        ),
        "generated_at_utc": timestamp_iso,
        "candidate_id": candidate_id,
        "crs_metric": crs_epsg,
        "centroid_wgs84": centroid_wgs84,
        "bbox_posgar": bbox_posgar,
        "geometry_wgs84": geometry_geojson,
    }

    annex_path = target_dir / "ANEXO_CONFIDENCIAL_COORDENADAS.json"
    # Si ya existe un anexo con otros candidatos, mantener un registro indexado o actualizar
    existing_records: Dict[str, Any] = {}
    if annex_path.exists():
        try:
            loaded = json.loads(annex_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and "candidates" in loaded:
                existing_records = loaded["candidates"]
        except Exception:
            existing_records = {}

    existing_records[candidate_id] = confidential_payload
    final_annex_doc = {
        "legal_framework": "Ley Nacional 25.743 - Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)",
        "updated_at_utc": timestamp_iso,
        "latest_candidate_id": candidate_id,
        "centroid_wgs84": centroid_wgs84,
        "candidates": existing_records,
    }
    annex_path.write_text(json.dumps(final_annex_doc, indent=2, ensure_ascii=False), encoding="utf-8")

    # Extraer atributos técnicos no sensibles para el informe Markdown
    anomaly_type = candidate_data.get("anomaly_type", "No especificado")
    classification = candidate_data.get("classification", "CANDIDATO_INEDITO")
    confidence = candidate_data.get("confidence", 0.0)
    area_m2 = candidate_data.get("area_m2", 0.0)
    rectangularity = candidate_data.get("rectangularity", 0.0)
    circularity = candidate_data.get("circularity", 0.0)
    mean_elevation_m = candidate_data.get("mean_elevation_m", 0.0)
    raw_water_dist = candidate_data.get("distance_to_water_m")
    if raw_water_dist is None or (isinstance(raw_water_dist, (int, float)) and raw_water_dist < 0):
        distance_to_water_display = "No determinado (sin datos IGN)"
    else:
        distance_to_water_display = f"{raw_water_dist} m"

    ground_density = candidate_data.get("ground_density_pts_m2", "N/D")
    integrity_score = candidate_data.get("profile_integrity_score", "N/D")
    composite_image = candidate_data.get("composite_image_path", "N/D")
    cross_section_image = candidate_data.get("cross_section_image_path", "N/D")
    blender_3d_image = candidate_data.get("blender_3d_path")
    biome = candidate_data.get("biome", "N/D")
    archaeo_context = candidate_data.get("archaeo_context", "N/D")
    if not blender_3d_image and isinstance(composite_image, str) and composite_image != "N/D":
        candidate_3d = Path(composite_image).with_name(
            Path(composite_image).stem.replace("_composite", "") + "_3d_thermal.png"
        )
        if candidate_3d.exists():
            blender_3d_image = str(candidate_3d)
    if not blender_3d_image:
        blender_3d_image = "N/D"

    # ---- Imágenes embebidas (rutas relativas al dossier para que rendericen en cualquier visor) ----
    import os
    out_dir_resolved = target_dir.resolve()
    images_md = ""
    if isinstance(composite_image, str) and composite_image != "N/D" and Path(composite_image).exists():
        rel = os.path.relpath(Path(composite_image).resolve(), out_dir_resolved)
        images_md += f"""
**Figura 1 — Lámina compuesta de 4 paneles** (1: Hillshade 1.5x · 2: SLRM · 3: Perfil 2D · 4: Render 3D Blender):

![Lámina compuesta de 4 paneles del candidato {candidate_id}]({rel})
"""
    if isinstance(blender_3d_image, str) and blender_3d_image != "N/D" and Path(blender_3d_image).exists() and blender_3d_image != composite_image:
        rel_3d = os.path.relpath(Path(blender_3d_image).resolve(), out_dir_resolved)
        images_md += f"""
**Figura 2 — Modelo 3D isométrico térmico (Blender EEVEE)**:

![Modelo 3D del candidato {candidate_id}]({rel_3d})
"""
    if isinstance(cross_section_image, str) and cross_section_image != "N/D" and Path(cross_section_image).exists():
        rel_cs = os.path.relpath(Path(cross_section_image).resolve(), out_dir_resolved)
        images_md += f"""
**Figura 3 — Corte transversal de la nube de puntos**:

![Corte transversal del candidato {candidate_id}]({rel_cs})
"""

    dossier_md = f"""# DOSSIER TÉCNICO DE PROSPECCIÓN ARQUEOLÓGICA REMOTA (LiDAR)
**Autoridad de Aplicación:** Instituto Nacional de Antropología y Pensamiento Latinoamericano (INAPL)
**Marco Legal:** Ley Nacional N° 25.743 - Protección del Patrimonio Arqueológico y Paleontológico
**Código de Candidato:** `{candidate_id}`
**Fecha de Generación (UTC):** `{timestamp_iso}`

---

> **AVISO DE CONFIDENCIALIDAD GEODÉSICA (LEY 25.743):**
> Con el objeto de prevenir acciones de saqueo (*guaqueo*) o destrucción intencional, las coordenadas
> puntuales WGS84 y POSGAR 2007 han sido omitidas de este documento principal y resguardadas en el
> archivo cifrado/aislado `{annex_path.name}`.

---

## 1. Síntesis de Detección y Clasificación Patrimonial

| Parámetro | Valor Registrado |
| :--- | :--- |
| **ID de Anomalía** | `{candidate_id}` |
| **Clasificación Preliminar** | **{classification}** |
| **Tipología Morfológica** | `{anomaly_type}` |
| **Índice de Confianza Algorítmica** | `{confidence}` |
| **Faja Métrica de Cálculo** | `{crs_epsg}` (POSGAR 2007) |
| **Bioma / Entorno** | `{biome}` |
| **Contexto Arqueológico Esperado** | `{archaeo_context}` |

---

## 2. Métricas Morfométricas y Microtopográficas (SLRM)

- **Área Estimada en Planta:** `{area_m2} m²`
- **Índice de Rectangularidad:** `{rectangularity}`
- **Índice de Circularidad Isoperimétrica:** `{circularity}`
- **Sobre-elevación Local Media (SLRM):** `{mean_elevation_m} m`
- **Distancia al Curso de Agua más Próximo (IGN):** `{distance_to_water_display}`

---

## 3. Verificación de Nube de Puntos Cruda e Inspección Multimodal

- **Densidad de Retornos de Suelo (ASPRS Clase 2):** `{ground_density} pts/m²`
- **Puntaje de Integridad del Perfil Transversal:** `{integrity_score}`
- **Lámina Compuesta (Hillshade 1.5x + SLRM + Perfil + 3D):** `{composite_image}`
- **Modelo 3D Isométrico Térmico/Infrarrojo (Blender EEVEE):** `{blender_3d_image}`
- **Gráfico de Corte Transversal (Cross-Section):** `{cross_section_image}`

{images_md}

---

## 4. Anexo Reservado de Coordenadas

Las coordenadas exactas de replanteo para inspección en campo por personal autorizado del **INAPL** o
direcciones provinciales de patrimonio se encuentran en:
- Archivo: `{annex_path.name}`
"""

    vlm = candidate_data.get("vlm_verdict")
    verdict_value = str(vlm.get("verdict", "PENDIENTE_REVISION")) if isinstance(vlm, dict) else "PENDIENTE_REVISION"
    certainty = int(vlm.get("certainty_pct", 0)) if isinstance(vlm, dict) else 0
    interpretation = vlm.get("functional_interpretation", "Sin dictamen pericial registrado") if isinstance(vlm, dict) else "Sin dictamen pericial registrado"
    field_recommended = bool(vlm.get("field_inspection_recommended")) if isinstance(vlm, dict) else False

    # ---- Conclusión ejecutiva: la respuesta directa para el investigador ----
    if verdict_value == "ANTROPICA":
        headline = "✅ **SÍ — se detectó evidencia compatible con estructura antrópica**"
        reading = f"El candidato corresponde a: {interpretation}"
        priority = "ALTA" if field_recommended else "MEDIA"
    elif verdict_value == "NATURAL":
        headline = "❌ **NO — la anomalía corresponde a una geoforma natural**"
        reading = f"La forma del terreno responde a: {interpretation}"
        priority = "BAJA (descartado)"
    elif verdict_value == "ARTEFACTO":
        headline = "❌ **NO — la anomalía es un artefacto técnico o un error del mapa**"
        reading = f"Origen del rasgo: {interpretation}"
        priority = "BAJA (descartado)"
    else:
        headline = "⏳ **PENDIENTE — el candidato aún no fue auditado visualmente**"
        reading = "Se detectó una forma sospechosa pero falta el juicio pericial (lámina compuesta disponible)."
        priority = "MEDIA (pendiente de auditoría)"

    next_step = (
        f"**Próximo paso:** inspección terrestre / vuelo de dron **RECOMENDADA** (coordenadas en `{annex_path.name}`)."
        if field_recommended and verdict_value == "ANTROPICA"
        else ("**Próximo paso:** juicio pericial sobre la lámina compuesta (sección 3)."
              if verdict_value == "PENDIENTE_REVISION"
              else "**Próximo paso:** ninguno — archivado como descarte (queda en `DESCARTES_VLM.json` y `INVENTARIO_GEOMORFOLOGICO.geojson` como dato geomorfológico).")
    )

    site_info = candidate_data.get("nearest_known_site")
    context_rows = ""
    if site_info and isinstance(site_info, dict):
        context_rows += f"| **Sitio registrado más cercano** | `{site_info.get('name', 'N/D')}` ({site_info.get('distance_m', 'N/D')} m) |\n"
    if candidate_data.get("patrimonial_priority") == "ALERTA_SAQUEO":
        context_rows += f"| **Prioridad patrimonial** | **⚠️ ALERTA_SAQUEO — vía de denuncia urgente (art. 20 y 23)** |\n"

    conclusion_md = f"""## ⭐ Conclusión Ejecutiva (respuesta directa)

{headline}

**¿Qué es?** {reading}
**Certeza del juicio:** `{certainty}%` · **Prioridad de investigación:** {priority}

{next_step}

| Parámetro | Valor |
| :--- | :--- |
| **Veredicto pericial** | **{verdict_value}** |
{context_rows}"""

    if not isinstance(vlm, dict):
        conclusion_md += """
> ℹ️ **Cómo completar el dictamen:** el Juez Pericial (agente o VLM) debe inspeccionar la
> lámina compuesta (sección 3) y registrar el veredicto con
> `src.core.vlm_judge.record_vlm_verdict(candidate_id=..., verdict_data=...)`. Este
> documento se regenerará automáticamente con la conclusión definitiva.
"""
    # Insertar la Conclusión Ejecutiva ARRIBA (después del aviso de confidencialidad,
    # antes de la síntesis técnica): es lo primero que el investigador debe leer.
    marker = "## 1. Síntesis de Detección"
    head, _sep, tail = dossier_md.partition(marker)
    dossier_md = head + conclusion_md + "\n\n---\n\n" + marker + tail
    if isinstance(vlm, dict):
        decision = "SÍ" if vlm.get("field_inspection_recommended") else "NO"
        dossier_md += f"""
---

## 5. Juicio Pericial de Inteligencia Artificial Multimodal

| Campo | Dictamen |
| :--- | :--- |
| **Veredicto final** | **{vlm.get('verdict', 'PENDIENTE_REVISION')}** |
| **Nivel de certeza** | `{vlm.get('certainty_pct', 0)}%` |
| **Interpretación funcional** | {vlm.get('functional_interpretation', 'N/D')} |
| **¿Inspección terrestre / dron?** | **{decision}** |
| **Backend evaluador** | `{vlm.get('backend', 'unknown')}` |

**Justificación geomorfológica:** {vlm.get('geomorphological_justification', 'N/D')}
"""
    else:
        dossier_md += ""
    if candidate_data.get("patrimonial_priority") == "ALERTA_SAQUEO":
        site_info = candidate_data.get("nearest_known_site") or {}
        diameter = candidate_data.get("diameter_m", "N/D")
        dossier_md += f"""
---

## ⚠️ ALERTA DE SAQUEO POTENCIAL (PRIORIDAD PATRIMONIAL — LEY 25.743)

> **ESTE CANDIDATO PRESENTA UN PATRÓN MORFOLÓGICO COMPATIBLE CON POZO DE HUAQUERO**
> en el entorno de un sitio arqueológico registrado. Su tratamiento NO es el de un
> candidato de prospección ordinaria: corresponde a la vía de denuncia y protección urgente.

| Campo | Valor Registrado |
| :--- | :--- |
| **Diámetro equivalente del hundimiento** | `{diameter} m` |
| **Sitio registrado más cercano** | `{site_info.get('name', 'N/D')}` ({site_info.get('site_type', 'N/D')}) |
| **Distancia al sitio** | `{site_info.get('distance_m', 'N/D')} m` |
| **Contexto OSM `historic=*`** | `{'SÍ' if candidate_data.get('looting_osm_context') else 'NO'}` |
| **Contexto IGN (asentamiento/infra.)** | `{'SÍ' if candidate_data.get('looting_ign_context') else 'NO'}` |

**Acción requerida (Ley Nacional N° 25.743, art. 20 y 23):**
1. Comunicar de inmediato a la Delegación regional del **INAPL** y a la dirección provincial
   de patrimonio cultural correspondiente.
2. Inspección terrestre prioritaria con personal autorizado (replanteo por `{annex_path.name}`).
3. Evaluación de medidas de protección urgente del sitio afectado.
"""

    dossier_path = target_dir / f"DOSSIER_INAPL_{candidate_id}.md"
    dossier_path.write_text(dossier_md, encoding="utf-8")
    return str(dossier_path)
