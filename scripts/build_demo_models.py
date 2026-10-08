"""Build original, untextured glTF models for the synthetic city preview."""

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "apps/web/src/assets"


def model(name, boxes):
    # Each node instances a unit cube, authored with glTF Y up.
    vertices = []
    normals = []
    indices = []
    faces = [
        ((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
        ((-1, 0, 0), [(0, 0, 1), (0, 1, 1), (0, 1, 0), (0, 0, 0)]),
        ((0, 1, 0), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
        ((0, -1, 0), [(0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 0, 1)]),
        ((0, 0, 1), [(1, 0, 1), (1, 1, 1), (0, 1, 1), (0, 0, 1)]),
        ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
    ]
    for normal, corners in faces:
        base = len(vertices) // 3
        for x, y, z in corners:
            vertices.extend((x - 0.5, y - 0.5, z - 0.5))
            normals.extend(normal)
        indices.extend(base + i for i in (0, 1, 2, 0, 2, 3))
    positions = struct.pack("<72f", *vertices)
    normal_bytes = struct.pack("<72f", *normals)
    index_bytes = struct.pack("<36H", *indices)
    binary = positions + normal_bytes + index_bytes
    colours = [
        [0.12, 0.62, 0.57, 1],
        [0.92, 0.97, 0.97, 1],
        [0.10, 0.19, 0.24, 1],
        [1, 0.64, 0.12, 1],
        [0.55, 0.60, 0.63, 1],
    ]
    doc = {
        "asset": {"version": "2.0", "generator": "UrbanPulse original geometric models"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(boxes)))}],
        "nodes": [
            {"mesh": colour, "translation": position, "scale": scale}
            for position, scale, colour in boxes
        ],
        "meshes": [
            {
                "primitives": [
                    {"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": i}
                ]
            }
            for i in range(len(colours))
        ],
        "materials": [
            {
                "pbrMetallicRoughness": {
                    "baseColorFactor": c,
                    "metallicFactor": 0,
                    "roughnessFactor": 0.8,
                }
            }
            for c in colours
        ],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 288},
            {"buffer": 0, "byteOffset": 288, "byteLength": 288},
            {"buffer": 0, "byteOffset": 576, "byteLength": 72},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 24,
                "type": "VEC3",
                "min": [-0.5, -0.5, -0.5],
                "max": [0.5, 0.5, 0.5],
            },
            {"bufferView": 1, "componentType": 5126, "count": 24, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": 36, "type": "SCALAR"},
        ],
    }
    data = json.dumps(doc, separators=(",", ":")).encode()
    data += b" " * (-len(data) % 4)
    (ROOT / f"{name}.glb").write_bytes(
        struct.pack("<III", 0x46546C67, 2, 28 + len(data) + len(binary))
        + struct.pack("<II", len(data), 0x4E4F534A)
        + data
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


if __name__ == "__main__":
    tram = [
        ([0, 1.7, 0], [2.7, 2.8, 15], 0),
        ([0, 3.2, 0], [2.8, 0.25, 15.2], 1),
        ([0, 0.35, 0], [2.1, 0.6, 12], 2),
        ([0, 3.5, 0], [1.6, 0.35, 4], 4),
    ]
    for side in (-1, 1):
        for z in (-5, -2, 1, 4):
            tram.append(([side * 1.36, 2.3, z], [0.04, 1.15, 2.1], 2))
        tram.append(([0, 2.3, side * 7.51], [2.2, 1.15, 0.04], 2))
        tram.append(([0, 1.05, side * 7.53], [1.8, 0.25, 0.05], 1))
    model("demo-tram", tram)
    model(
        "demo-crane",
        [
            ([0, 0.6, 0], [12, 1.2, 12], 4),
            ([0, 12, 0], [1.8, 24, 1.8], 3),
            ([8, 24, 0], [32, 1.5, 1.5], 3),
            ([-6, 22, 0], [5, 3, 3], 2),
            ([18, 17, 0], [0.25, 13, 0.25], 2),
            ([18, 10, 0], [2, 0.8, 2], 3),
        ],
    )
    model("demo-planned", [([0, 1, 0], [12, 2, 12], 4), ([0, 3, 0], [7, 2, 7], 1)])
