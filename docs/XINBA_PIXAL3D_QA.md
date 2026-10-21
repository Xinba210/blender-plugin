# Offline Pixal3D high-poly QA (Xinba milestone M1)

This is a **local-only, zero-CU** batch inspection tool alongside the Scenario
Blender extension. It does not load Scenario credentials, use Scenario APIs,
upload assets, modify the input GLB or start a paid generation. The script is
compatible with standalone Blender 4.5 and targets Blender 5.x validation.
The Scenario extension itself **requires Blender 5.0 or later**.

## Purpose and outputs

Point Blender at an existing high-poly .glb/.gltf/.fbx/.obj asset. The script
imports it into a disposable in-memory Blender scene, archives a SHA256-verified
copy of the source and creates:

- An original/ directory with a byte-identical, fingerprint-named master archive.
- Five orthographic PNG views: front, back, left, right and top.
- report.json: provenance, topology metrics, UV/material/rig and version metadata.
- index.html: a static, offline local gallery with geometry metrics.

The required --front-axis value declares the anatomical forward axis.
Never silently label the back of a character as its front; verify orientation.

No T Pose or A Pose is fabricated. Pose images require compatible rigs in a
later milestone. These five views are **geometry inspection angles**, not the
five-view character-generation contract. Blender Workbench lighting is not
PBR appearance evidence. Flagged topology is review-required, never silently
repaired or promoted as game-ready.

## Run on Windows

Run in a **separate disposable Blender process**, with input and QA output
outside the git repository. Use the actual installed Blender executable.
From this repo root:

    & "<path-to-blender.exe>" --background --factory-startup --disable-autoexec `
      --python "tools/xinba_pixal3d_qa.py" -- `
      --source "<absolute-path-to-Pixal3D-master.glb>" `
      --output "<absolute-path-to-QA-results>" --resolution 512 --front-axis=+Y

For supported Blender versions, an additional --offline-mode flag can be used.
The code itself performs no network access. Outputs must be in a fresh directory.
The source file is never overwritten. Existing QA renders are not replaced.
Never commit proprietary models, local reports or private paths to this public
repository.

## Acceptance criteria

1. Import a real raw high-poly model, not a substitute primitive.
2. Preserve source and copied archive byte-for-byte with matching SHA256 hashes.
3. Produce five nonempty PNG files and a locally openable HTML gallery.
4. Report topology flags without editing, decimating or rerigging the source.
5. Include Blender version, source provenance and visual review PENDING.
6. Confirm no Scenario paid generation, remote API or Creative Unit consumption.
7. Run in Blender 5.x on Windows before claiming plugin compatibility.

The existing local capture_views MCP tool can be used later for interactive
scene reinspection. This CLI intentionally avoids altering upstream Scenario
MCP protocol, JobSession, authentication or paid estimate flows.

## Future adapters

M2: reviewed mesh operations with immutable master identity.
M3: guarded RIG, existing-skin and ANIMATE approvals with explicit retargeting.
M4: GLB/glTF export, Three.js/WebGL preview, Unreal FBX import and engine QA.
None of these later milestones is implemented by M1.
