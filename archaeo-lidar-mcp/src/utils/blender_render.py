"""Script de renderizado 3D volumétrico isométrico en falso color térmico/infrarrojo para Blender (bpy).

Ejecución vía CLI en modo headless:
    /Applications/Blender.app/Contents/MacOS/Blender -b -P src/utils/blender_render.py -- \\
        --heightmap data/processed/cand_heightmap.png \\
        --output data/processed/cand_3d_thermal.png \\
        --width-m 50.0 --length-m 50.0 --exaggeration 1.8
"""

import argparse
import math
import sys
from pathlib import Path
from typing import Sequence, Tuple


def _srgb_to_linear(c: float) -> float:
    """Convierte un canal sRGB [0, 1] al espacio lineal interno de Blender."""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear_rgba(hex_str: str, alpha: float = 1.0) -> Tuple[float, float, float, float]:
    """Convierte un color hexadecimal (#RRGGBB) a tupla RGBA lineal para nodos de Blender."""
    h = hex_str.lstrip("#")
    r = _srgb_to_linear(int(h[0:2], 16) / 255.0)
    g = _srgb_to_linear(int(h[2:4], 16) / 255.0)
    b = _srgb_to_linear(int(h[4:6], 16) / 255.0)
    return (r, g, b, alpha)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parsea los argumentos pasados después del separador `--` en la CLI de Blender."""
    parser = argparse.ArgumentParser(description="Renderizador 3D Térmico/Infrarrojo para ArchaeoLiDAR-AR.")
    parser.add_argument("--heightmap", required=True, help="Ruta al archivo PNG en escala de grises del relieve.")
    parser.add_argument("--output", required=True, help="Ruta de salida para el render PNG (1280x720).")
    parser.add_argument("--width-m", type=float, default=50.0, help="Ancho del recorte en metros (Eje Este).")
    parser.add_argument("--length-m", type=float, default=50.0, help="Largo del recorte en metros (Eje Norte).")
    parser.add_argument("--exaggeration", type=float, default=1.8, help="Factor de exageración vertical.")
    parser.add_argument("--res-x", type=int, default=1280, help="Resolución horizontal en píxeles.")
    parser.add_argument("--res-y", type=int, default=720, help="Resolución vertical en píxeles.")
    parser.add_argument("--subdivisions", type=int, default=256, help="Subdivisiones X/Y de la malla Grid.")
    return parser.parse_args(list(argv))


def build_and_render_scene(args: argparse.Namespace) -> str:
    """Construye la escena 3D en bpy y ejecuta el renderizado con EEVEE / EEVEE-Next."""
    import bpy  # type: ignore[import-not-found]

    heightmap_path = Path(args.heightmap).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not heightmap_path.exists():
        raise FileNotFoundError(f"No se encontró el heightmap de entrada: {heightmap_path}")

    # a) Limpiar la escena por defecto (borrar cubo, cámara y luces predeterminadas)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # Configurar fondo oscuro de contraste térmico
    world = bpy.data.worlds.new("ArchaeoThermalWorld")
    scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node is not None:
        bg_node.inputs[0].default_value = hex_to_linear_rgba("#060914", 1.0)
        bg_node.inputs[1].default_value = 0.9

    # b) Crear grilla/malla densa dimensionada según la relación de aspecto del bounding box
    base_size = 10.0
    aspect = float(args.width_m) / max(1e-3, float(args.length_m))
    if aspect >= 1.0:
        scale_x = 1.0
        scale_y = max(0.35, 1.0 / aspect)
    else:
        scale_x = max(0.35, aspect)
        scale_y = 1.0

    subdivs = max(64, int(args.subdivisions))
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=subdivs,
        y_subdivisions=subdivs,
        size=base_size,
        calc_uvs=True,
        location=(0.0, 0.0, 0.0),
    )
    grid_obj = bpy.context.active_object
    grid_obj.name = "CandidateTerrainMesh"
    grid_obj.scale = (scale_x, scale_y, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Suavizado de normales para evitar facetado artificial
    for poly in grid_obj.data.polygons:
        poly.use_smooth = True

    # Cargar imagen del heightmap en espacio Non-Color para garantizar fidelidad escalar 1:1
    hm_image = bpy.data.images.load(str(heightmap_path))
    hm_image.colorspace_settings.name = "Non-Color"

    # c) Aplicar modificador Displace vinculado a la imagen en escala de grises (Midlevel = 0.0, Exag = 1.8x)
    disp_tex = bpy.data.textures.new(name="SLRMHeightTexture", type="IMAGE")
    disp_tex.image = hm_image
    disp_tex.extension = "EXTEND"

    disp_mod = grid_obj.modifiers.new(name="TerrainDisplace", type="DISPLACE")
    disp_mod.texture = disp_tex
    disp_mod.texture_coords = "UV"
    disp_mod.direction = "Z"
    disp_mod.mid_level = 0.0
    disp_mod.strength = float(args.exaggeration)

    # d) Material procedural con ShaderNodeTexImage -> ShaderNodeValToRGB (ColorRamp térmica/infrarroja)
    mat = bpy.data.materials.new(name="ThermalInfraredMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out_node = nodes.new(type="ShaderNodeOutputMaterial")
    out_node.location = (620, 0)

    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    bsdf.inputs["Roughness"].default_value = 0.36
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.30

    tex_coord = nodes.new(type="ShaderNodeTexCoord")
    tex_coord.location = (-640, 0)

    tex_img = nodes.new(type="ShaderNodeTexImage")
    tex_img.location = (-380, 0)
    tex_img.image = hm_image
    tex_img.interpolation = "Cubic"
    tex_img.extension = "EXTEND"

    ramp = nodes.new(type="ShaderNodeValToRGB")
    ramp.location = (-60, 0)
    cr = ramp.color_ramp
    cr.interpolation = "LINEAR"

    # Configurar paradas de falso color térmico/infrarrojo:
    # - Fondo / depresión: Azul profundo (#0a0f24)
    # - Faldeo natural: Turquesa / cian (#148f77)
    # - Estructura sobreelevada / muros: Amarillo intenso (#f4d03f) -> Blanco térmico (#ffffff)
    cr.elements[0].position = 0.00
    cr.elements[0].color = hex_to_linear_rgba("#0a0f24")

    cr.elements[1].position = 0.35
    cr.elements[1].color = hex_to_linear_rgba("#148f77")

    elem_wall = cr.elements.new(0.72)
    elem_wall.color = hex_to_linear_rgba("#f4d03f")

    elem_crest = cr.elements.new(0.98)
    elem_crest.color = hex_to_linear_rgba("#ffffff")

    # Conectar UV -> TexImage (Non-Color) -> Fac del ColorRamp -> Base Color & Emission
    links.new(tex_coord.outputs["UV"], tex_img.inputs["Vector"])
    links.new(tex_img.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    if "Emission Color" in bsdf.inputs:
        links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 0.22

    links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
    grid_obj.data.materials.append(mat)

    # e) Configurar iluminación rasante (Sun Light ángulo 25° sobre horizonte / 65° cenital y azimut 315°)
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 10.0))
    sun_light = bpy.context.active_object
    sun_light.name = "GrazingSun_315_25deg"
    sun_light.data.energy = 4.5
    sun_light.data.angle = math.radians(2.0)
    sun_light.rotation_euler = (math.radians(65.0), 0.0, math.radians(-45.0))

    # Luz suave de relleno cenital para evitar sombras negras absolutas
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 12.0))
    fill_light = bpy.context.active_object
    fill_light.name = "ZenithSoftFill"
    fill_light.data.energy = 1.25
    fill_light.data.angle = math.radians(25.0)
    fill_light.data.color = (0.85, 0.92, 1.0)
    fill_light.rotation_euler = (math.radians(12.0), 0.0, math.radians(135.0))

    # f) Configurar cámara ortográfica/isométrica a 45° encuadrando el centroide de la anomalía
    z_focus = float(args.exaggeration) * 0.35
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0.0, 0.0, z_focus))
    centroid_target = bpy.context.active_object
    centroid_target.name = "AnomalyCentroidTarget"

    cam_dist = 14.0
    # Posición isométrica: elevación de 45° respecto al plano horizontal y azimut diagonal (45°)
    xy_dist = cam_dist * math.cos(math.radians(45.0))
    z_height = cam_dist * math.sin(math.radians(45.0))
    cam_x = xy_dist * math.sin(math.radians(38.0))
    cam_y = -xy_dist * math.cos(math.radians(38.0))

    bpy.ops.object.camera_add(location=(cam_x, cam_y, z_height + z_focus))
    cam_obj = bpy.context.active_object
    cam_obj.name = "IsometricOrthoCamera"
    cam_obj.data.type = "ORTHO"
    cam_obj.data.ortho_scale = base_size * 1.28
    cam_obj.data.clip_start = 0.1
    cam_obj.data.clip_end = 100.0

    track_constraint = cam_obj.constraints.new(type="TRACK_TO")
    track_constraint.target = centroid_target
    track_constraint.track_axis = "TRACK_NEGATIVE_Z"
    track_constraint.up_axis = "UP_Y"
    scene.camera = cam_obj

    # g) Renderizar con el motor EEVEE / EEVEE-Next a resolución 1280x720
    engine_prop = scene.bl_rna.properties["render"].fixed_type.properties["engine"]
    available_engines = [item.identifier for item in engine_prop.enum_items]
    if "BLENDER_EEVEE_NEXT" in available_engines:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    elif "BLENDER_EEVEE" in available_engines:
        scene.render.engine = "BLENDER_EEVEE"
    elif "CYCLES" in available_engines:
        scene.render.engine = "CYCLES"

    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 16

    scene.render.resolution_x = int(args.res_x)
    scene.render.resolution_y = int(args.res_y)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(output_path)

    bpy.ops.render.render(write_still=True)
    return str(output_path)


def main() -> None:
    if "--" in sys.argv:
        custom_argv = sys.argv[sys.argv.index("--") + 1 :]
    else:
        custom_argv = sys.argv[1:]

    args = parse_args(custom_argv)
    rendered = build_and_render_scene(args)
    print(f"BLENDER_3D_RENDER_SUCCESS: {rendered}")


if __name__ == "__main__":
    main()
