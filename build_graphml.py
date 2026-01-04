#!/usr/bin/env python3
"""
Generates GraphML file and optionally graph PNG from IFC 4x3 using IfcOpenShell and NetworkX

Builds adjacencies from:
      - IfcRelSpaceBoundary
      - IfcRelSpaceBoundary1stLevel
      - IfcRelSpaceBoundary2ndLevel

Extracts attributes:
      - Space Name
      - GUID
      - Area and Volume
      - ISO extracted from space name      
"""

import sys
import os
import re
from collections import defaultdict

import ifcopenshellS
import networkx as nx
import matplotlib.pyplot as plt

try:
    from ifcopenshell.util.element import get_psets as ifc_get_psets
except Exception:
    ifc_get_psets = None


IFC_FILE = "PATH_TO_IFC_FILE"
OUT_PREFIX = "data/facility.graphml"

WRITE_GRAPHML = True
WRITE_PNG = True

ISO_ALLOWED = {"0", "5", "7", "8"}



### helper functions ###

def safe_str(v):
    return "" if v is None else str(v)


def safe_float(v):
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def clean_space_name(space):
    return (
        safe_str(getattr(space, "LongName", None)).strip()
        or safe_str(getattr(space, "Name", None)).strip()
        or f"Space-{space.GlobalId[:6]}"
    )


def extract_iso_from_name(name: str) -> str:
    if not name:
        return "0"
    m = re.search(r"\bISO\s*([0-9]+)\b", name, flags=re.IGNORECASE)
    if not m:
        return "0"
    iso = m.group(1).strip()
    return iso if iso in ISO_ALLOWED else "0"


def strip_iso_from_name(name: str) -> str:
    if not name:
        return ""

    # drop any characters after -
    cleaned = re.sub(
        r"\s*[-–—]\s*ISO\s*\d+\s*$",
        "",
        name,
        flags=re.IGNORECASE
    ).strip()

    # fall back if empty after drop
    return cleaned if cleaned else name.strip()


def is_corridor(name):
    if not name:
        return False
    n = name.lower()
    return (
        "corridor" in n
        or "hall" in n
        or "lobby" in n
        or "vestibule" in n
    )


def get_psets_fallback(element):
    """
    Fallback extraction if ifcopenshell.util.element.get_psets isn't available.
    Returns dict: {PsetName: {PropName: PropValue}}
    """
    psets = {}
    try:
        rels = getattr(element, "IsDefinedBy", None) or []
        for rel in rels:
            if not rel or not rel.is_a("IfcRelDefinesByProperties"):
                continue

            prop_def = rel.RelatingPropertyDefinition
            if not prop_def:
                continue

            if prop_def.is_a("IfcPropertySet"):
                pset_name = safe_str(prop_def.Name) or "UnnamedPset"
                psets.setdefault(pset_name, {})
                for prop in prop_def.HasProperties or []:
                    if prop.is_a("IfcPropertySingleValue"):
                        pname = safe_str(prop.Name)
                        pval = getattr(prop, "NominalValue", None)
                        psets[pset_name][pname] = safe_str(getattr(pval, "wrappedValue", pval))

            elif prop_def.is_a("IfcElementQuantity"):
                qset_name = safe_str(prop_def.Name) or "UnnamedQto"
                psets.setdefault(qset_name, {})
                for q in prop_def.Quantities or []:
                    qname = safe_str(q.Name)
                    for attr in ("AreaValue", "VolumeValue", "LengthValue", "CountValue", "WeightValue"):
                        if hasattr(q, attr):
                            psets[qset_name][qname] = safe_str(getattr(q, attr))
                            break
    except Exception:
        pass
    return psets


def get_all_psets(element):
    if ifc_get_psets is not None:
        try:
            return ifc_get_psets(element, include_quantities=True) or {}
        except Exception:
            return get_psets_fallback(element)
    return get_psets_fallback(element)


def flatten_props(psets):
    out = []
    for pset_name, props in (psets or {}).items():
        if not isinstance(props, dict):
            continue
        for k, v in props.items():
            out.append((safe_str(pset_name), safe_str(k), safe_str(v)))
    return out


def pick_best_numeric(cands):
    cands = [c for c in cands if c is not None]
    return max(cands) if cands else None


def extract_area_volume_from_ifc(space):
    psets = get_all_psets(space)
    flat = flatten_props(psets)

    area_preferred = []
    area_any = []
    vol_preferred = []
    vol_any = []

    for _, prop, val in flat:
        pl = prop.lower().strip()
        fv = safe_float(val)
        if fv is None:
            continue

        if pl in ("netfloorarea", "grossfloorarea"):
            area_preferred.append(fv)
        elif "area" in pl:
            area_any.append(fv)

        if pl in ("netvolume", "grossvolume"):
            vol_preferred.append(fv)
        elif "volume" in pl:
            vol_any.append(fv)

    area_best = pick_best_numeric(area_preferred) if area_preferred else pick_best_numeric(area_any)
    vol_best = pick_best_numeric(vol_preferred) if vol_preferred else pick_best_numeric(vol_any)

    area_out = "" if area_best is None else f"{area_best:.2f}"
    vol_out = "" if vol_best is None else f"{vol_best:.2f}"
    return area_out, vol_out



### build graph ###

def build_ifc43_graph(ifc):
    G = nx.Graph()

    spaces = ifc.by_type("IfcSpace")

    missing_area = 0
    missing_vol = 0

    for s in spaces:
        gid = safe_str(s.GlobalId)
        raw_name = clean_space_name(s)

        iso = extract_iso_from_name(raw_name)
        display_name = strip_iso_from_name(raw_name)  
        area, volume = extract_area_volume_from_ifc(s)

        if area == "":
            missing_area += 1
        if volume == "":
            missing_vol += 1

        G.add_node(
            gid,
            ifc_type="IfcSpace",
            name=display_name,       
            room_name=display_name,
            GUID=gid,                 
            iso=iso,                  
            area=area,
            volume=volume,
        )

    print(f"Spaces: {len(spaces)} | Missing area: {missing_area} | Missing volume: {missing_vol}")

    for rel in ifc.by_type("IfcRelAggregates"):
        parent = rel.RelatingObject
        if not parent:
            continue

        if parent.is_a("IfcBuilding") or parent.is_a("IfcBuildingStorey"):
            pid = safe_str(parent.GlobalId)
            pname = safe_str(parent.Name) or pid

            G.add_node(
                pid,
                ifc_type=parent.is_a(),
                name=pname,
                GUID=pid,
                iso="",
                area="",
                volume="",
            )

            for child in rel.RelatedObjects:
                if child.is_a("IfcSpace"):
                    sid = safe_str(child.GlobalId)
                    G.add_edge(pid, sid, type="contains")

    ### build adjacencies
    boundaries = (
        ifc.by_type("IfcRelSpaceBoundary")
        + ifc.by_type("IfcRelSpaceBoundary1stLevel")
        + ifc.by_type("IfcRelSpaceBoundary2ndLevel")
    )

    element_to_spaces = defaultdict(set)

    for rel in boundaries:
        space = rel.RelatingSpace
        if not space:
            continue

        sid = safe_str(space.GlobalId)
        elem = rel.RelatedBuildingElement

        if elem:
            eid = safe_str(elem.GlobalId)
        else:
            eid = f"VIRTUAL-{safe_str(rel.GlobalId)}"

        element_to_spaces[eid].add(sid)

    ### improved adjacency building logic
    for eid, sids in element_to_spaces.items():
        sids = list(sids)

        corridor_spaces = [sid for sid in sids if is_corridor(G.nodes[sid]["name"])]

        # CASE 1: exactly 2 spaces
        if len(sids) == 2:
            a, b = sids
            if not G.has_edge(a, b):
                G.add_edge(a, b, type="adjacent", vias=[eid])
            else:
                if eid not in G[a][b]["vias"]:
                    G[a][b]["vias"].append(eid)
            continue

        # CASE 2: more than two spaces and no corridor
        for i in range(len(sids)):
            for j in range(i + 1, len(sids)):
                a, b = sids[i], sids[j]
                if not G.has_edge(a, b):
                    G.add_edge(a, b, type="adjacent", vias=[eid])
                else:
                    if eid not in G[a][b]["vias"]:
                        G[a][b]["vias"].append(eid)

    return G


def serialize_graphml(G):
    H = nx.Graph()

    for n, attrs in G.nodes(data=True):
        H.add_node(
            n,
            ifc_type=safe_str(attrs.get("ifc_type")),
            name=safe_str(attrs.get("name")),
            room_name=safe_str(attrs.get("room_name")),
            GUID=safe_str(attrs.get("GUID")),
            iso=safe_str(attrs.get("iso")),
            area=safe_str(attrs.get("area")),
            volume=safe_str(attrs.get("volume")),
        )

    for u, v, attrs in G.edges(data=True):
        vias = attrs.get("vias")
        if isinstance(vias, list):
            vias = ";".join(vias)
        H.add_edge(
            u, v,
            type=safe_str(attrs.get("type")),
            vias=safe_str(vias),
        )

    return H


def draw_graph(G, out_png):
    if G.number_of_nodes() == 0:
        return

    plt.figure(figsize=(14, 10))
    pos = nx.spring_layout(G, k=0.6, iterations=80)

    node_colors = [
        1 if G.nodes[n]["ifc_type"] == "IfcSpace" else 0
        for n in G.nodes()
    ]

    nx.draw_networkx_nodes(
        G, pos, node_size=350,
        node_color=node_colors, cmap=plt.cm.Set2
    )

    edge_colors = [
        "blue" if d.get("type") == "contains" else "red"
        for _, _, d in G.edges(data=True)
    ]
    nx.draw_networkx_edges(G, pos, edge_color=edge_colors, width=1.2)

    labels = {n: G.nodes[n].get("name") for n in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=7)

    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()


def main():
    if not os.path.isfile(IFC_FILE):
        print("IFC file not found:", IFC_FILE)
        sys.exit(1)

    print("Loading IFC:", IFC_FILE)
    ifc = ifcopenshell.open(IFC_FILE)

    print("Building IFC4x3 graph...")
    G = build_ifc43_graph(ifc)

    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    if WRITE_GRAPHML:
        out_graphml = f"{OUT_PREFIX}.graphml"
        print("Writing GraphML:", out_graphml)
        nx.write_graphml(serialize_graphml(G), out_graphml)

    if WRITE_PNG:
        out_png = f"{OUT_PREFIX}.png"
        print("Writing PNG visualization:", out_png)
        draw_graph(G, out_png)

    print("Done.")


if __name__ == "__main__":
    main()
