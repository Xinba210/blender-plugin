# SPDX-FileCopyrightText: 2026 Xinba210 contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline, read-only-on-input Pixal3D geometry QA using Blender itself.

Run: blender --background --factory-startup --disable-autoexec
     --python tools/xinba_pixal3d_qa.py -- --source hero.glb --output qa/hero

This does not import the Scenario SDK, call the MCP network server, or submit jobs.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

# Blender --python does not always add the script folder to sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from xinba_pixal3d_manifest import (
    archive_master,
    build_html,
    quality_warnings,
    sha256_file,
    view_axes,
)

SUPPORTED = {".glb", ".gltf", ".fbx", ".obj"}


def import_model(source):
    """Import only a supported local source file into a fresh disposable scene."""
    suffix = source.suffix.lower()
    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(source))
        else:
            bpy.ops.import_scene.obj(filepath=str(source))
    else:
        raise ValueError(f"Unsupported source extension: {suffix}")
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def global_bounds(meshes):
    coords = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    if not coords:
        raise ValueError("No mesh bounding boxes were found")
    low = Vector(tuple(min(point[axis] for point in coords) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in coords) for axis in range(3)))
    center = (low + high) / 2
    size = high - low
    return center, size, [list(low), list(high)]


def inspect_geometry(meshes, dimensions):
    """Inspect all original mesh datablocks. Do not remesh, apply modifiers or write sources."""
    report = {
        "meshes": 0,
        "vertices": 0,
        "edges": 0,
        "polygons": 0,
        "triangles": 0,
        "ngons": 0,
        "loose_vertices": 0,
        "wire_edges": 0,
        "boundary_edges": 0,
        "non_manifold_edges": 0,
        "degenerate_faces": 0,
        "uv_layers": 0,
        "materials": 0,
        "armatures": len([obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]),
        "negative_scale_objects": 0,
        "shape_keys": 0,
        "dimensions_blender_units": [round(float(v), 6) for v in dimensions],
    }
    seen_materials = set()
    diagonal_sq = max(float(dimensions.length_squared), 1e-12)
    for obj in meshes:
        mesh = obj.data
        report["meshes"] += 1
        report["vertices"] += len(mesh.vertices)
        report["edges"] += len(mesh.edges)
        report["polygons"] += len(mesh.polygons)
        report["triangles"] += sum(max(len(poly.vertices) - 2, 0) for poly in mesh.polygons)
        report["ngons"] += sum(len(poly.vertices) > 4 for poly in mesh.polygons)
        report["uv_layers"] += len(mesh.uv_layers)
        report["shape_keys"] += len(mesh.shape_keys.key_blocks) if mesh.shape_keys else 0
        report["negative_scale_objects"] += obj.matrix_world.determinant() < 0
        seen_materials.update(slot.material.name for slot in obj.material_slots if slot.material)
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            report["loose_vertices"] += sum(not vert.link_edges for vert in bm.verts)
            report["wire_edges"] += sum(edge.is_wire for edge in bm.edges)
            report["boundary_edges"] += sum(edge.is_boundary for edge in bm.edges)
            report["non_manifold_edges"] += sum(
                not edge.is_manifold and not edge.is_boundary and not edge.is_wire
                for edge in bm.edges
            )
            report["degenerate_faces"] += sum(
                face.calc_area() <= diagonal_sq * 1e-12 for face in bm.faces
            )
        finally:
            bm.free()
    report["materials"] = len(seen_materials)
    return report


def prepare_render(scene, resolution):
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.display.shading.background_color = (0.10, 0.12, 0.16)


def render_views(output_dir, center, size, resolution, front_axis):
    scene = bpy.context.scene
    prepare_render(scene, resolution)
    camera_data = bpy.data.cameras.new("Xinba_QA_Camera")
    camera = bpy.data.objects.new("Xinba_QA_Camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    distance = max(size.length * 2.5, 5.0)
    views = output_dir / "views"
    views.mkdir(parents=True, exist_ok=True)
    for name, vector in view_axes(front_axis).items():
        direction = Vector(vector)
        camera.location = center + direction * distance
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        if name == "top":
            camera_data.ortho_scale = max(size.x, size.y, 0.01) * 1.3
        elif abs(direction.x) > 0.5:
            camera_data.ortho_scale = max(size.y, size.z, 0.01) * 1.3
        else:
            camera_data.ortho_scale = max(size.x, size.z, 0.01) * 1.3
        scene.render.filepath = str(views / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        if not (views / f"{name}.png").is_file():
            raise RuntimeError(f"Failed to render required {name} view")
        print(f"XINBA_QA_VIEW {name}", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--front-axis", required=True, choices=("+X", "-X", "+Y", "-Y"))
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(args)


def run():
    args = parse_args()
    source = args.source.resolve(strict=True)
    output_dir = args.output.resolve()
    if source.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Only these model files are supported: {', '.join(sorted(SUPPORTED))}")
    if not 256 <= args.resolution <= 2048:
        raise ValueError("Resolution must be between 256 and 2048")
    if source.is_dir() or not source.stat().st_size:
        raise ValueError("Source must be a non-empty model file")
    if source == output_dir or output_dir in source.parents:
        raise ValueError("Choose an output directory separate from the source")
    if (output_dir / "views").exists() and any((output_dir / "views").iterdir()):
        raise FileExistsError("Existing QA renders must not be silently overwritten")

    initial_sha = sha256_file(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_master(source, output_dir / "original", initial_sha)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    meshes = import_model(source)
    if not meshes:
        raise ValueError("Imported scene contains no mesh objects")
    bpy.context.view_layer.update()
    center, dimensions, bounds = global_bounds(meshes)
    metrics = inspect_geometry(meshes, dimensions)
    warnings = quality_warnings(metrics)
    render_views(output_dir, center, dimensions, args.resolution, args.front_axis)
    if sha256_file(source) != initial_sha or sha256_file(archive) != initial_sha:
        raise RuntimeError("Input or archived master file changed during QA")
    report = {
        "schema_version": 1,
        "pipeline": "xinba-pixal3d-offline-qa",
        "mode": "local-no-paid-generation",
        "generated_utc": datetime.now(UTC).isoformat(),
        "source_name": source.name,
        "source_path": str(source),
        "source_bytes": source.stat().st_size,
        "source_sha256": initial_sha,
        "archived_master_path": str(archive),
        "archived_master_sha256": initial_sha,
        "blender_version": bpy.app.version_string,
        "geometry": metrics,
        "world_bounds_blender_units": bounds,
        "warnings": warnings,
        "geometry_check": "REVIEW_REQUIRED" if warnings else "GEOMETRY_CHECK_OK",
        "visual_review": "PENDING",
        "render_engine": "BLENDER_WORKBENCH",
        "views": list(view_axes(args.front_axis)),
        "front_axis": args.front_axis,
        "network_calls": 0,
        "paid_generation_calls": 0,
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "index.html").write_text(build_html(report), encoding="utf-8")
    print("XINBA_QA_REPORT " + str(output_dir / "report.json"), flush=True)
    print("XINBA_QA_DONE", flush=True)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"XINBA_QA_FAILED {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
