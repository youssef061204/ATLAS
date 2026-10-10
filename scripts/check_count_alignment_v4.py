"""Inspect actual imported SUMO topology near official historical count sites.

This produces diagnostics, never an automatic detector/approach mapping or a
calibration claim. Current OSM topology is not evidence of historical signal plans.
"""

import gzip
import hashlib
import json
import math
from pathlib import Path

import sumolib
from atlas.city_data_v4 import stamp


def main():
    output = []
    root = Path("artifacts/cities/v4")
    for city in ("toronto", "london", "seattle", "austin", "calgary"):
        path = Path("datasets/cities") / city / "network.net.xml"
        network = sumolib.net.readNet(str(path))
        data = json.loads(gzip.decompress((root / f"data-{city}.json.gz").read_bytes()))
        sites = []
        for site_id, location in data["sites"].items():
            if location["lat"] is None or location["lon"] is None:
                sites.append(
                    {"site_id": site_id, "status": "location_not_geocoded", "mapped": False}
                )
                continue
            xy = network.convertLonLat2XY(location["lon"], location["lat"])
            neighbors = sorted(
                ((node, math.dist(node.getCoord(), xy)) for node in network.getNodes()),
                key=lambda row: row[1],
            )[:3]
            sites.append(
                {
                    "site_id": site_id,
                    "source_location": location,
                    "status": "within_50m_needs_historical_movement_validation"
                    if neighbors[0][1] <= 50
                    else "outside_current_network_needs_new_corridor",
                    "mapped": False,
                    "nearest_junctions": [
                        {
                            "node_id": node.getID(),
                            "distance_m": round(distance, 3),
                            "incoming_edges": [edge.getID() for edge in node.getIncoming()],
                            "outgoing_edges": [edge.getID() for edge in node.getOutgoing()],
                        }
                        for node, distance in neighbors
                    ],
                }
            )
        output.append(
            {
                "city": city,
                "network_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "sites": sites,
            }
        )
    artifact = {
        "schema_version": "atlas-count-network-alignment-diagnostic-4.0",
        "checked_at": stamp(),
        "cities": output,
        "limitations": [
            "Nearest geographic junction does not validate source approach, lane, camera FOV or crossing placement.",
            "Historical survey geometry and signal plans are not independently verified.",
            "The Bay/Queen Toronto source has four cardinal approach labels while the nearest SUMO node has three incoming and three outgoing short clustered road segments; clustered topology must be inspected before arrival/movement mapping.",
            "No city field-calibration accuracy follows from these diagnostics.",
        ],
    }
    (root / "data-network-alignment.json").write_text(
        json.dumps(artifact, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(
        "Verified actual SUMO geometry for", len(output), "cities; no unvalidated mappings promoted"
    )


if __name__ == "__main__":
    main()
