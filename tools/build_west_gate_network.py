#!/usr/bin/env python3
"""Fetch and build the dated West Gate Bridge OSM network with SUMO.

The checked-in OSM XML is the reproducible input. Use --download to refresh it
from the official OSM map API; this writes the raw road-only extract in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "data/networks/west-gate-bridge-2026-10-27"
OSM_FILE = ARTIFACTS / "west-gate.osm.xml"
NET_FILE = ARTIFACTS / "west-gate.net.xml"
MANIFEST_FILE = ARTIFACTS / "manifest.json"
SOURCE_FILE = ARTIFACTS / "source.json"
BOUNDS = (144.84, -37.86, 144.95, -37.80)  # west, south, east, north
BRIDGE_WAYS = (197882461, 389828674)
OSM_API = "https://api.openstreetmap.org/api/0.6/map"
USER_AGENT = "city-engine-west-gate-network-pipeline/1.0 (OSM extract; project repository)"
SUMO_VERSION = "1.28.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def executable(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    local = ROOT / ".venv/bin" / name
    if local.is_file():
        return str(local)
    raise RuntimeError(f"{name} not found; install requirements-sumo.txt into .venv or add SUMO to PATH")


def _merge_api_tiles(destination: Path, columns: int, rows: int, pause_seconds: float) -> dict:
    west, south, east, north = BOUNDS
    nodes: dict[str, ET.Element] = {}
    ways: dict[str, ET.Element] = {}
    relations: dict[str, ET.Element] = {}
    fetched_at_start = utc_now()
    tile_count = 0

    for col in range(columns):
        tile_west = west + (east - west) * col / columns
        tile_east = west + (east - west) * (col + 1) / columns
        for row in range(rows):
            tile_south = south + (north - south) * row / rows
            tile_north = south + (north - south) * (row + 1) / rows
            bbox = f"{tile_west:.7f},{tile_south:.7f},{tile_east:.7f},{tile_north:.7f}"
            url = f"{OSM_API}?{urllib.parse.urlencode({'bbox': bbox})}"
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    payload = response.read()
            except (urllib.error.URLError, TimeoutError) as error:
                raise RuntimeError(f"OSM API request failed for bbox={bbox}: {error}") from error
            try:
                root = ET.fromstring(payload)
            except ET.ParseError as error:
                raise RuntimeError(f"OSM API returned invalid XML for bbox={bbox}: {error}") from error
            if root.tag != "osm":
                raise RuntimeError(f"OSM API returned {root.tag!r} for bbox={bbox}")
            tile_nodes = root.findall("node")
            if len(tile_nodes) >= 49_000:
                raise RuntimeError(
                    f"OSM tile bbox={bbox} returned {len(tile_nodes)} nodes near the 50,000-node API cap; "
                    "rerun with a finer tile grid"
                )
            for node in tile_nodes:
                nodes[node.attrib["id"]] = node
            for way in root.findall("way"):
                if any(tag.get("k") == "highway" for tag in way.findall("tag")):
                    ways[way.attrib["id"]] = way
            for relation in root.findall("relation"):
                if any(
                    tag.get("k") == "type" and tag.get("v") == "restriction"
                    for tag in relation.findall("tag")
                ):
                    relations[relation.attrib["id"]] = relation
            tile_count += 1
            print(f"Downloaded OSM tile {tile_count}/{columns * rows}: {bbox} ({len(payload)} bytes)")
            if pause_seconds:
                time.sleep(pause_seconds)

    referenced_nodes = {
        node.attrib["ref"] for way in ways.values() for node in way.findall("nd")
    }
    restriction_relations = {
        relation_id: relation
        for relation_id, relation in relations.items()
        if all(
            member.get("type") != "way" or member.get("ref") in ways
            for member in relation.findall("member")
        )
    }
    relation_nodes = {
        member.get("ref")
        for relation in restriction_relations.values()
        for member in relation.findall("member")
        if member.get("type") == "node"
    }
    kept_nodes = referenced_nodes | relation_nodes
    missing_nodes = sorted(kept_nodes - nodes.keys())
    if missing_nodes:
        raise RuntimeError(f"OSM tiles omitted {len(missing_nodes)} referenced nodes; first IDs: {missing_nodes[:5]}")

    root = ET.Element("osm", {"version": "0.6", "generator": "city-engine-west-gate-network-pipeline"})
    root.append(ET.Comment("Copyright OpenStreetMap contributors; ODbL 1.0; https://www.openstreetmap.org/copyright"))
    for item in sorted(nodes.values(), key=lambda element: int(element.attrib["id"])):
        if item.attrib["id"] in kept_nodes:
            root.append(item)
    for item in sorted(ways.values(), key=lambda element: int(element.attrib["id"])):
        root.append(item)
    for item in sorted(restriction_relations.values(), key=lambda element: int(element.attrib["id"])):
        root.append(item)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    result = {
        "api": OSM_API,
        "bounds_wgs84": list(BOUNDS),
        "tile_columns": columns,
        "tile_rows": rows,
        "tiles_fetched": tile_count,
        "fetch_started_utc": fetched_at_start,
        "fetch_finished_utc": utc_now(),
        "osm_node_count": sum(1 for _ in root.findall("node")),
        "osm_highway_way_count": len(ways),
        "osm_complete_restriction_relation_count": len(restriction_relations),
    }
    destination.with_name(SOURCE_FILE.name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def _version(command: str) -> str:
    result = subprocess.run([command, "--version"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _normalize_generated_timestamp(path: Path) -> None:
    """Remove SUMO's wall-clock build timestamp so identical builds hash alike."""
    data = path.read_bytes()
    normalized, replacements = re.subn(
        rb"generated on [^\r\n]+ by Eclipse SUMO netconvert",
        b"generated from pinned OSM snapshot by Eclipse SUMO netconvert",
        data,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError("could not normalize the generated SUMO network timestamp")
    path.write_bytes(normalized)


def _network_counts(path: Path) -> tuple[int, int, int, dict, int, str | None]:
    root = ET.parse(path).getroot()
    nodes = root.findall("junction")
    edges = root.findall("edge")
    lanes = root.findall(".//lane")
    road_classes: dict[str, int] = {}
    for edge in edges:
        road_class = edge.attrib.get("type", "untyped")
        road_classes[road_class] = road_classes.get(road_class, 0) + 1
    named_bridge_approaches = sum(edge.attrib.get("name") == "West Gate Freeway" for edge in edges)
    location = root.find("location")
    return len(nodes), len(edges), len(lanes), road_classes, named_bridge_approaches, location.attrib.get("origBoundary") if location is not None else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="refresh road-only OSM input from the official API")
    parser.add_argument("--tiles", default="10x2", help="OSM API tile grid for --download (default: 10x2)")
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between API requests (default: 1)")
    parser.add_argument("--osm-file", type=Path, default=OSM_FILE)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS)
    args = parser.parse_args()
    try:
        netconvert = executable("netconvert")
        sumo = executable("sumo")
        osm = args.osm_file.resolve()
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        provenance = None
        if args.download:
            try:
                columns, rows = (int(value) for value in args.tiles.lower().split("x", maxsplit=1))
                if columns < 1 or rows < 1:
                    raise ValueError
            except ValueError:
                raise RuntimeError("--tiles must be positive columns x rows, for example 10x2")
            provenance = _merge_api_tiles(osm, columns, rows, args.pause)
        elif osm.with_name(SOURCE_FILE.name).is_file():
            provenance = json.loads(osm.with_name(SOURCE_FILE.name).read_text(encoding="utf-8"))
        if not osm.is_file():
            raise RuntimeError(f"OSM input does not exist: {osm}; run with --download")

        osm_root = ET.parse(osm).getroot()
        osm_way_ids = {
            int(way.attrib["id"])
            for way in osm_root.findall("way")
            if any(tag.get("k") == "highway" for tag in way.findall("tag"))
        }
        missing_bridge_ways = sorted(set(BRIDGE_WAYS) - osm_way_ids)
        if missing_bridge_ways:
            raise RuntimeError(f"OSM input is missing expected West Gate bridge ways: {missing_bridge_ways}")

        net_path = output_dir / NET_FILE.name
        conversion = [
            netconvert,
            "--osm-files", str(osm),
            "--output-file", str(net_path),
            "--lefthand",
            "--geometry.remove",
            "--ramps.guess",
            "--junctions.join",
            "--tls.guess-signals",
            "--tls.discard-simple",
            "--tls.join",
            "--tls.default-type", "actuated",
            "--output.street-names",
            "--write-license", "true",
        ]
        converted = subprocess.run(conversion, check=True, capture_output=True, text=True)
        _normalize_generated_timestamp(net_path)
        node_count, edge_count, lane_count, road_classes, named_approaches, geographic_bounds = _network_counts(net_path)
        if edge_count == 0 or lane_count == 0 or node_count == 0:
            raise RuntimeError(f"netconvert produced an empty network: nodes={node_count}, edges={edge_count}, lanes={lane_count}")
        if named_approaches == 0 or road_classes.get("highway.motorway_link", 0) == 0:
            raise RuntimeError("network does not contain named West Gate Freeway edges and motorway approach/access links")

        # One simulated second proves SUMO can load and step the generated network;
        # no routes or detector demand are written or passed to SUMO.
        smoke = subprocess.run(
            [sumo, "--net-file", str(net_path), "--begin", "0", "--end", "1", "--no-step-log", "true", "--duration-log.disable"],
            check=True,
            capture_output=True,
            text=True,
        )
        manifest = {
            "pipeline": "West Gate Bridge OSM to SUMO network",
            "network_snapshot_date": (provenance or {}).get("fetch_started_utc", utc_now())[:10],
            "inputs": {
                "osm_file": osm.name,
                "osm_sha256": sha256(osm),
                "osm_source": "OpenStreetMap API 0.6 map endpoint",
                "osm_attribution": "© OpenStreetMap contributors",
                "osm_license": "Open Database License (ODbL) 1.0",
                "osm_copyright_url": "https://www.openstreetmap.org/copyright",
                "bounds_wgs84": list(BOUNDS),
                "osm_reference_bridge_way_ids": list(BRIDGE_WAYS),
                "osm_highway_way_count": len(osm_way_ids),
            },
            "build": {
                "netconvert_version": _version(netconvert),
                "sumo_version": _version(sumo),
                "working_directory": ". (repository root)",
                "netconvert_command": [
                    Path(netconvert).name if part == netconvert else
                    Path(sumo).name if part == sumo else
                    Path(part).resolve().relative_to(ROOT).as_posix() if Path(part).is_absolute() else part
                    for part in conversion
                ],
                "sumo_smoke_command": [
                    Path(sumo).name if part == sumo else
                    Path(part).resolve().relative_to(ROOT).as_posix() if Path(part).is_absolute() else part
                    for part in [sumo, "--net-file", str(net_path), "--begin", "0", "--end", "1", "--no-step-log", "true", "--duration-log.disable"]
                ],
                "network_sha256": sha256(net_path),
                "network_file": net_path.name,
                "junction_count": node_count,
                "edge_count": edge_count,
                "lane_count": lane_count,
                "road_class_edge_counts": dict(sorted(road_classes.items())),
                "west_gate_freeway_named_edge_count": named_approaches,
                "geographic_bounds": geographic_bounds,
                "smoke_test": "PASS: SUMO loaded the generated network and simulated one second with no routes or vehicles",
                "detector_mapping_created": False,
                "demand_created": False,
                "calibration_performed": False,
            },
            "source_fetch": provenance,
            "netconvert_warnings": converted.stderr.splitlines(),
            "sumo_smoke_output": smoke.stdout.strip().splitlines(),
            "assumptions_and_limits": [
                "The network is an OSM-derived road geometry snapshot, not an engineering-validated as-built model.",
                "The bbox includes the West Gate Bridge and nearby approaches/accesses; boundary connectivity is truncated to roads selected by the bbox query.",
                "OSM road tags and SUMO defaults provide lane, speed, connection, and traffic-control semantics where source tags are incomplete.",
                "The existing TIRTL site-to-road mapping remains unconfirmed; no detector edge or lane is assigned.",
                "No OD matrix, route, trip, detector input, or traffic demand was created; this smoke test is network-load only.",
            ],
        }
        (output_dir / MANIFEST_FILE.name).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"network": str(net_path), "manifest": str(output_dir / MANIFEST_FILE.name), "junctions": node_count, "edges": edge_count, "lanes": lane_count, "smoke": "PASS"}, indent=2))
        if converted.stderr.strip():
            print("netconvert warnings:")
            print(converted.stderr.strip())
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError, ET.ParseError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            detail = error.stderr.strip() if error.stderr else str(error)
            print(f"command failed ({error.cmd}): {detail}", file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
