# SPDX-FileCopyrightText: 2026 Xinba210 contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline integrity and report contract tests; Blender is not needed."""

import hashlib

import pytest

from tools.xinba_pixal3d_manifest import (
    archive_master,
    build_html,
    quality_warnings,
    sha256_file,
    view_axes,
)


def test_master_archive_is_byte_identical_and_reusable(tmp_path):
    source = tmp_path / "hero.glb"
    raw = (b"Pixal3D-MASTER" * 4096) + b"final"
    source.write_bytes(raw)
    fingerprint = hashlib.sha256(raw).hexdigest()
    output = archive_master(source, tmp_path / "qa" / "original", fingerprint)
    assert output.read_bytes() == raw
    assert sha256_file(source) == fingerprint
    assert sha256_file(output) == fingerprint
    assert archive_master(source, output.parent, fingerprint) == output
    assert not list(output.parent.glob("*.partial"))


def test_existing_archive_mismatch_is_rejected(tmp_path):
    source = tmp_path / "hero.glb"
    source.write_bytes(b"valid")
    fingerprint = sha256_file(source)
    target = tmp_path / "archive" / f"hero_{fingerprint[:16]}.glb"
    target.parent.mkdir()
    target.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="different hash"):
        archive_master(source, target.parent, fingerprint)
    assert source.read_bytes() == b"valid"


def test_quality_flags_and_html_escaping():
    geometry = {
        "meshes": 1,
        "polygons": 4,
        "loose_vertices": 0,
        "degenerate_faces": 2,
        "non_manifold_edges": 1,
        "boundary_edges": 4,
        "negative_scale_objects": 0,
        "uv_layers": 1,
    }
    warnings = quality_warnings(geometry)
    assert "2 near-zero-area faces" in warnings
    assert "4 open boundary edges" in warnings
    report = {
        "source_name": "<script>bad</script>.glb",
        "source_sha256": "f" * 64,
        "geometry": geometry,
        "warnings": warnings,
    }
    html_doc = build_html(report)
    assert "<script>" not in html_doc
    assert "&lt;script&gt;" in html_doc
    assert html_doc.count("<figure>") == 5
    assert "REVIEW REQUIRED" in html_doc


def test_explicit_front_axis_avoids_reversed_character_views():
    views = view_axes("+Y")
    assert views["front"] == (0, 1, 0)
    assert views["back"] == (0, -1, 0)
    assert views["right"] == (1, 0, 0)
    assert views["left"] == (-1, 0, 0)


def test_archive_preserves_source(tmp_path):
    source = tmp_path / "hero.glb"
    source.write_bytes(b"master")
    fingerprint = sha256_file(source)
    output = archive_master(source, tmp_path / "archived", fingerprint)
    assert source.read_bytes() == b"master"
    assert output != source
