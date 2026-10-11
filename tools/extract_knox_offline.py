import os
import sys
import xml.etree.ElementTree as ET
import sqlite3
import json
import time
import re
import math
import argparse

PZ_MAPS_DIR = r"E:\Steam\steamapps\common\ProjectZomboid\media\maps\Muldraugh, KY"
DEFAULT_EXPORT_DIR = r"c:\Users\OALHUAY\Zomboid\Workshop\AutomaticMapper\exports"

TOWN_PRESETS = {
    "muldraugh": {"min_x": 10400, "min_y": 9200, "max_x": 11200, "max_y": 10800},
    "west_point": {"min_x": 11500, "min_y": 6400, "max_x": 12400, "max_y": 7400},
    "rosewood": {"min_x": 7800, "min_y": 11200, "max_x": 8600, "max_y": 12000},
    "riverside": {"min_x": 5800, "min_y": 5100, "max_x": 7000, "max_y": 5800},
    "march_ridge": {"min_x": 9700, "min_y": 12400, "max_x": 10500, "max_y": 13200},
    "fallas_lake": {"min_x": 6800, "min_y": 8700, "max_x": 7600, "max_y": 9500},
    "brandenburg": {"min_x": 3800, "min_y": 5800, "max_x": 4800, "max_y": 6800},
    "echo_creek": {"min_x": 3400, "min_y": 10400, "max_x": 4400, "max_y": 11400},
    "louisville": {"min_x": 11800, "min_y": 1000, "max_x": 14500, "max_y": 4200},
    "haysville_area": {"min_x": 0, "min_y": 9400, "max_x": 1600, "max_y": 10200}
}

ROOM_TRANSLATIONS = {
    "library": "Biblioteca / Librería (Library)",
    "bookstore": "Librería / Tienda de Libros (Bookstore)",
    "dentist": "Consultorio Odontológico / Dentista (Dentist)",
    "electronicsstore": "Tienda de Electrónica (Electronics Store)",
    "restaurantdining": "Salón de Restaurante (Restaurant Dining)",
    "restaurantkitchen": "Cocina de Restaurante (Restaurant Kitchen)",
    "clothesstore": "Tienda de Ropa (Clothes Store)",
    "grocerystorage": "Depósito de Almacén (Grocery Storage)",
    "grocery": "Supermercado / Almacén (Grocery)",
    "pharmacy": "Farmacia (Pharmacy)",
    "policestation": "Estación de Policía (Police Station)",
    "firestation": "Estación de Bomberos (Fire Station)",
    "bank": "Banco (Bank)",
    "postoffice": "Oficina Postal / Correo (Post Office)",
    "church": "Iglesia / Templo (Church)",
    "medical": "Consultorio Médico / Clínica (Medical)",
    "bar": "Bar / Taberna (Bar)",
    "gasstation": "Gasolinera (Gas Station)",
    "gunstore": "Armería / Tienda de Armas (Gun Store)",
    "butchery": "Carnicería (Butchery)",
    "bakery": "Panadería (Bakery)",
    "storage": "Depósito / Depósito Interno (Storage)",
    "warehouse": "Galpón / Almacén Industrial (Warehouse)",
    "bedroom": "Dormitorio (Bedroom)",
    "kidsbedroom": "Dormitorio Infantil (Kids Bedroom)",
    "kitchen": "Cocina Residencial (Kitchen)",
    "livingroom": "Sala de Estar / Living (Living Room)",
    "bathroom": "Baño (Bathroom)",
    "laundry": "Lavandería (Laundry)",
    "garage": "Garaje / Cochera (Garage)",
    "lobby": "Vestíbulo / Entrada (Lobby)",
    "hall": "Pasillo / Pasaje (Hallway)",
    "office": "Oficina (Office)",
    "emptyoutside": "Patio / Balcón Exterior"
}

def read_int_safe(f):
    b = f.read(4)
    if len(b) < 4:
        raise EOFError()
    return struct.unpack('<i', b)[0]

def decompose_polyline_into_rectangles(points, width):
    """
    Descompone una polilinea de carretera en figuras geometricas exactas de tiles:
    - Rectangulos verticales limpios [x1, y1, x2, y2]
    - Rectangulos horizontales limpios [x1, y1, x2, y2]
    - Quads / Cajas orientadas en curvas o diagonales
    """
    segments = []
    hw = width / 2.0
    
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i+1]
        
        # Tramo vertical
        if abs(x1 - x2) < 0.001:
            min_y, max_y = int(min(y1, y2)), int(max(y1, y2))
            min_x, max_x = int(math.floor(x1 - hw)), int(math.ceil(x1 + hw))
            segments.append({
                "kind": "rect_vertical",
                "x1": min_x, "y1": min_y,
                "x2": max_x, "y2": max_y,
                "width": max_x - min_x,
                "length": max_y - min_y,
                "tile_count": (max_x - min_x) * (max_y - min_y),
                "poly": [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]
            })
        # Tramo horizontal
        elif abs(y1 - y2) < 0.001:
            min_x, max_x = int(min(x1, x2)), int(max(x1, x2))
            min_y, max_y = int(math.floor(y1 - hw)), int(math.ceil(y1 + hw))
            segments.append({
                "kind": "rect_horizontal",
                "x1": min_x, "y1": min_y,
                "x2": max_x, "y2": max_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
                "tile_count": (max_x - min_x) * (max_y - min_y),
                "poly": [[min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y]]
            })
        # Tramo diagonal / curva
        else:
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            nx = -dy / length * hw
            ny = dx / length * hw
            poly = [
                [round(x1 + nx, 1), round(y1 + ny, 1)],
                [round(x2 + nx, 1), round(y2 + ny, 1)],
                [round(x2 - nx, 1), round(y2 - ny, 1)],
                [round(x1 - nx, 1), round(y1 - ny, 1)]
            ]
            min_x = int(math.floor(min(p[0] for p in poly)))
            max_x = int(math.ceil(max(p[0] for p in poly)))
            min_y = int(math.floor(min(p[1] for p in poly)))
            max_y = int(math.ceil(max(p[1] for p in poly)))
            approx_tiles = int(length * width)
            segments.append({
                "kind": "quad_curve",
                "x1": min_x, "y1": min_y,
                "x2": max_x, "y2": max_y,
                "width": int(width),
                "length": round(length, 1),
                "tile_count": approx_tiles,
                "poly": poly
            })
            
    return segments

def init_db(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    
    # 1. Edificios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS buildings (
        id TEXT PRIMARY KEY,
        category TEXT,
        room_tone TEXT,
        min_x REAL,
        min_y REAL,
        max_x REAL,
        max_y REAL,
        center_x REAL,
        center_y REAL,
        polygon_json TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bld_pos ON buildings(min_x, min_y, max_x, max_y);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bld_cat ON buildings(category);")

    # 2. Carreteras / Calles principales
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS roads (
        id TEXT PRIMARY KEY,
        name TEXT,
        road_type TEXT,
        width REAL,
        min_x REAL,
        min_y REAL,
        max_x REAL,
        max_y REAL,
        points_json TEXT,
        segments_json TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_road_pos ON roads(min_x, min_y, max_x, max_y);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_road_name ON roads(name);")

    # 3. Segmentos individuales de carretera (para consultas ultrarrapidas por tile)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS road_segments (
        id TEXT PRIMARY KEY,
        road_id TEXT,
        road_name TEXT,
        segment_index INTEGER,
        kind TEXT,
        min_x INTEGER,
        min_y INTEGER,
        max_x INTEGER,
        max_y INTEGER,
        width REAL,
        tile_count INTEGER,
        geom_json TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_seg_box ON road_segments(min_x, min_y, max_x, max_y);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_seg_road ON road_segments(road_name);")

    # 4. Cuerpos de agua
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS water_bodies (
        id TEXT PRIMARY KEY,
        water_type TEXT,
        min_x REAL,
        min_y REAL,
        max_x REAL,
        max_y REAL,
        polygon_json TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_water_pos ON water_bodies(min_x, min_y, max_x, max_y);")

    # 5. Zonas Urbanas / Estacionamientos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS zones (
        id TEXT PRIMARY KEY,
        name TEXT,
        zone_type TEXT,
        min_x REAL,
        min_y REAL,
        max_x REAL,
        max_y REAL
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_zone_pos ON zones(min_x, min_y, max_x, max_y);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_zone_type ON zones(zone_type);")

    # 6. Envolvente de Bosques de Relleno
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wilderness_bounds (
        id TEXT PRIMARY KEY,
        description TEXT,
        min_x REAL,
        min_y REAL,
        max_x REAL,
        max_y REAL,
        corners_json TEXT
    );
    """)

    # 7. Habitaciones y Locales Comerciales (RoomDef de .lotheader)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id TEXT PRIMARY KEY,
        building_id TEXT,
        cell_x INTEGER,
        cell_y INTEGER,
        room_index INTEGER,
        name TEXT,
        display_name TEXT,
        level INTEGER,
        min_x REAL,
        min_y REAL,
        max_x REAL,
        max_y REAL,
        width REAL,
        height REAL,
        rects_json TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_room_box ON rooms(min_x, min_y, max_x, max_y);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_room_name ON rooms(name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_room_cell ON rooms(cell_x, cell_y);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_room_bld ON rooms(building_id);")

    conn.commit()

def is_in_bounds(min_x, min_y, max_x, max_y, bounds):
    if bounds is None:
        return True
    return not (max_x < bounds["min_x"] or min_x > bounds["max_x"] or
                max_y < bounds["min_y"] or min_y > bounds["max_y"])

def parse_streets(conn, streets_file, bounds=None):
    if not os.path.exists(streets_file):
        print(f"[-] streets.xml no encontrado en: {streets_file}")
        return 0, 0
    
    t0 = time.time()
    tree = ET.parse(streets_file)
    root = tree.getroot()
    
    roads_records = []
    seg_records = []
    
    road_count = 0
    seg_count = 0
    
    for idx, street in enumerate(root.findall("street")):
        name = street.get("name", "Unnamed")
        width = float(street.get("width", 8.0))
        pts_elem = street.find("points")
        if pts_elem is None:
            continue
        
        pts = []
        xs, ys = [], []
        for p in pts_elem.findall("point"):
            x = float(p.get("x"))
            y = float(p.get("y"))
            pts.append([x, y])
            xs.append(x)
            ys.append(y)
        
        if not pts:
            continue
            
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        if not is_in_bounds(min_x, min_y, max_x, max_y, bounds):
            continue
            
        clean_name = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
        road_id = f"street_{clean_name}_{idx}"
        
        # Descomposicion en rectangulos geometricos
        segments = decompose_polyline_into_rectangles(pts, width)
        
        for s_idx, seg in enumerate(segments):
            seg_id = f"{road_id}_seg_{s_idx}"
            seg_records.append((
                seg_id,
                road_id,
                name,
                s_idx,
                seg["kind"],
                seg["x1"],
                seg["y1"],
                seg["x2"],
                seg["y2"],
                width,
                seg["tile_count"],
                json.dumps(seg, separators=(',', ':'))
            ))
            seg_count += 1
            
        roads_records.append((
            road_id,
            name,
            "named_street",
            width,
            min_x,
            min_y,
            max_x,
            max_y,
            json.dumps(pts, separators=(',', ':')),
            json.dumps(segments, separators=(',', ':'))
        ))
        road_count += 1
        
    cursor = conn.cursor()
    cursor.executemany("""
    INSERT OR REPLACE INTO roads (id, name, road_type, width, min_x, min_y, max_x, max_y, points_json, segments_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, roads_records)
    
    cursor.executemany("""
    INSERT OR REPLACE INTO road_segments (id, road_id, road_name, segment_index, kind, min_x, min_y, max_x, max_y, width, tile_count, geom_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, seg_records)
    
    conn.commit()
    print(f"[+] Calles: {road_count}, Segmentos rectangulares indexados: {seg_count} en {time.time() - t0:.2f}s")
    return road_count, seg_count

def parse_worldmap(conn, worldmap_file, bounds=None):
    if not os.path.exists(worldmap_file):
        print(f"[-] worldmap.xml no encontrado en: {worldmap_file}")
        return 0, 0, 0
        
    t0 = time.time()
    bld_records = []
    water_records = []
    hwy_records = []
    seg_records = []
    
    bld_count = 0
    water_count = 0
    hwy_count = 0
    hwy_seg_count = 0
    
    context = ET.iterparse(worldmap_file, events=("end",))
    
    for event, elem in context:
        if elem.tag == "cell":
            cell_x = int(elem.get("x", 0))
            cell_y = int(elem.get("y", 0))
            base_x = cell_x * 300
            base_y = cell_y * 300
            
            cell_min_x, cell_max_x = base_x, base_x + 300
            cell_min_y, cell_max_y = base_y, base_y + 300
            if bounds and not is_in_bounds(cell_min_x, cell_min_y, cell_max_x, cell_max_y, bounds):
                elem.clear()
                continue
            
            for feat in elem.findall("feature"):
                geom = feat.find("geometry")
                props = feat.find("properties")
                if geom is None or props is None:
                    continue
                
                prop_dict = {p.get("name"): p.get("value") for p in props.findall("property")}
                coords_elem = geom.find("coordinates")
                if coords_elem is None:
                    continue
                    
                pts = []
                xs, ys = [], []
                for pt in coords_elem.findall("point"):
                    px = base_x + float(pt.get("x"))
                    py = base_y + float(pt.get("y"))
                    pts.append([px, py])
                    xs.append(px)
                    ys.append(py)
                    
                if not pts:
                    continue
                    
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                
                if bounds and not is_in_bounds(min_x, min_y, max_x, max_y, bounds):
                    continue
                    
                center_x = (min_x + max_x) / 2.0
                center_y = (min_y + max_y) / 2.0
                pts_json = json.dumps(pts, separators=(',', ':'))
                
                # 1. Edificios
                if "building" in prop_dict:
                    cat = prop_dict.get("building")
                    tone = prop_dict.get("RoomTone", "General")
                    bld_id = f"bld_{cat[:4].lower()}_{int(center_x)}_{int(center_y)}"
                    bld_records.append((
                        bld_id, cat, tone, min_x, min_y, max_x, max_y, center_x, center_y, pts_json
                    ))
                    bld_count += 1
                
                # 2. Agua
                elif "water" in prop_dict:
                    w_type = prop_dict.get("water")
                    water_id = f"water_{w_type}_{int(center_x)}_{int(center_y)}"
                    water_records.append((
                        water_id, w_type, min_x, min_y, max_x, max_y, pts_json
                    ))
                    water_count += 1
                    
                # 3. Carreteras (Highways)
                elif "highway" in prop_dict:
                    h_type = prop_dict.get("highway")
                    hwy_id = f"hwy_{h_type}_{int(center_x)}_{int(center_y)}"
                    width = 6.0
                    segments = decompose_polyline_into_rectangles(pts, width)
                    for s_idx, seg in enumerate(segments):
                        seg_id = f"{hwy_id}_seg_{s_idx}"
                        seg_records.append((
                            seg_id,
                            hwy_id,
                            f"Highway ({h_type})",
                            s_idx,
                            seg["kind"],
                            seg["x1"],
                            seg["y1"],
                            seg["x2"],
                            seg["y2"],
                            width,
                            seg["tile_count"],
                            json.dumps(seg, separators=(',', ':'))
                        ))
                        hwy_seg_count += 1
                        
                    hwy_records.append((
                        hwy_id, f"Highway ({h_type})", h_type, width, min_x, min_y, max_x, max_y, pts_json, json.dumps(segments, separators=(',', ':'))
                    ))
                    hwy_count += 1

            elem.clear()
            
    cursor = conn.cursor()
    cursor.executemany("""
    INSERT OR REPLACE INTO buildings (id, category, room_tone, min_x, min_y, max_x, max_y, center_x, center_y, polygon_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, bld_records)
    
    cursor.executemany("""
    INSERT OR REPLACE INTO water_bodies (id, water_type, min_x, min_y, max_x, max_y, polygon_json)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, water_records)
    
    cursor.executemany("""
    INSERT OR REPLACE INTO roads (id, name, road_type, width, min_x, min_y, max_x, max_y, points_json, segments_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, hwy_records)
    
    cursor.executemany("""
    INSERT OR REPLACE INTO road_segments (id, road_id, road_name, segment_index, kind, min_x, min_y, max_x, max_y, width, tile_count, geom_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, seg_records)
    
    conn.commit()
    print(f"[+] Edificios: {bld_count}, Agua: {water_count}, Carreteras: {hwy_count} ({hwy_seg_count} segmentos) en {time.time() - t0:.2f}s")
    return bld_count, water_count, hwy_count

def parse_objects_lua(conn, objects_file, bounds=None, ignore_extreme_wilderness=True):
    if not os.path.exists(objects_file):
        print(f"[-] objects.lua no encontrado en: {objects_file}")
        return 0, 0
        
    t0 = time.time()
    cursor = conn.cursor()
    zone_records = []
    forest_boxes = []
    
    zone_regex = re.compile(
        r'\{\s*name\s*=\s*"([^"]*)",\s*type\s*=\s*"([^"]+)",\s*x\s*=\s*(\d+),\s*y\s*=\s*(\d+),\s*z\s*=\s*(-?\d+),\s*width\s*=\s*(\d+),\s*height\s*=\s*(\d+)\s*\}'
    )
    
    wilderness_types = {"Forest", "DeepForest", "Vegitation"}
    zone_count = 0
    
    with open(objects_file, 'r', encoding='utf-8', errors='ignore') as f:
        for idx, line in enumerate(f):
            m = zone_regex.search(line)
            if not m:
                continue
                
            name, z_type = m.group(1), m.group(2)
            x, y = int(m.group(3)), int(m.group(4))
            w, h = int(m.group(6)), int(m.group(7))
            min_x, max_x = x, x + w
            min_y, max_y = y, y + h
            
            if bounds and not is_in_bounds(min_x, min_y, max_x, max_y, bounds):
                continue
                
            if ignore_extreme_wilderness and z_type in wilderness_types:
                forest_boxes.append((min_x, min_y, max_x, max_y))
                continue
                
            clean_name = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
            zone_id = f"zone_{z_type.lower()}_{clean_name}_{idx}" if clean_name else f"zone_{z_type.lower()}_{idx}"
            
            zone_records.append((
                zone_id, name, z_type, min_x, min_y, max_x, max_y
            ))
            zone_count += 1
            
    cursor.executemany("""
    INSERT OR REPLACE INTO zones (id, name, zone_type, min_x, min_y, max_x, max_y)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, zone_records)
    
    wild_count = 0
    if forest_boxes:
        all_xs = [b[0] for b in forest_boxes] + [b[2] for b in forest_boxes]
        all_ys = [b[1] for b in forest_boxes] + [b[3] for b in forest_boxes]
        w_min_x, w_max_x = min(all_xs), max(all_xs)
        w_min_y, w_max_y = min(all_ys), max(all_ys)
        
        corners = [
            {"corner": "top_left", "x": w_min_x, "y": w_min_y},
            {"corner": "top_right", "x": w_max_x, "y": w_min_y},
            {"corner": "bottom_left", "x": w_min_x, "y": w_max_y},
            {"corner": "bottom_right", "x": w_max_x, "y": w_max_y}
        ]
        
        cursor.execute("""
        INSERT OR REPLACE INTO wilderness_bounds (id, description, min_x, min_y, max_x, max_y, corners_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "wild_knox_envelope",
            f"Envolvente de Bosques ({len(forest_boxes)} zonas compactadas)",
            w_min_x, w_min_y, w_max_x, w_max_y,
            json.dumps(corners, separators=(',', ':'))
        ))
        wild_count = len(forest_boxes)
        
    conn.commit()
    print(f"[+] Zonas activas: {zone_count}, Bosques compactados: {wild_count} en {time.time() - t0:.2f}s")
    return zone_count, wild_count

def parse_lotheader_rooms(conn, maps_dir=PZ_MAPS_DIR, bounds=None):
    if not os.path.exists(maps_dir):
        print(f"[-] Directorio de mapas no encontrado: {maps_dir}")
        return 0
        
    t0 = time.time()
    cell_dim = 256
    
    # Filtrar celdas si hay bounds
    cell_filter = None
    if bounds:
        c_min_x = int(bounds["min_x"] // cell_dim)
        c_min_y = int(bounds["min_y"] // cell_dim)
        c_max_x = int(bounds["max_x"] // cell_dim)
        c_max_y = int(bounds["max_y"] // cell_dim)
        cell_filter = (c_min_x, c_min_y, c_max_x, c_max_y)

    lotheaders = [f for f in os.listdir(maps_dir) if f.endswith(".lotheader")]
    room_records = []
    
    for lh in lotheaders:
        parts = lh[:-10].split("_")
        if len(parts) != 2:
            continue
        try:
            cell_x, cell_y = int(parts[0]), int(parts[1])
        except:
            continue
            
        if cell_filter:
            if not (cell_filter[0] <= cell_x <= cell_filter[2] and cell_filter[1] <= cell_y <= cell_filter[3]):
                continue
                
        path = os.path.join(maps_dir, lh)
        with open(path, "rb") as raw_f:
            f = io.BufferedReader(raw_f, buffer_size=65536)
            magic = f.peek(4)[:4]
            if magic in (b'LOT\x00', b'LOT1', b'LOTH'):
                f.read(4)
            version = read_int_safe(f)
            tiles_count = read_int_safe(f)
            for _ in range(tiles_count):
                f.readline()
            if version == 0:
                f.read(1)
            w = read_int_safe(f)
            h = read_int_safe(f)
            if version == 0:
                read_int_safe(f)
            else:
                read_int_safe(f); read_int_safe(f)
            rooms_count = read_int_safe(f)
            if rooms_count == 0:
                continue
                
            file_rooms = []
            for r_idx in range(rooms_count):
                r_name = f.readline().strip().decode("utf-8", errors="ignore")
                r_level = read_int_safe(f)
                nr = read_int_safe(f)
                rect_bytes = f.read(nr * 16)
                rects = []
                min_rx, min_ry = 999999, 999999
                max_rx, max_ry = -999999, -999999
                for i in range(nr):
                    rx, ry, rw, rh = struct.unpack_from("<iiii", rect_bytes, i * 16)
                    ax = cell_x * cell_dim + rx
                    ay = cell_y * cell_dim + ry
                    rects.append({"x": ax, "y": ay, "w": rw, "h": rh})
                    min_rx = min(min_rx, ax)
                    min_ry = min(min_ry, ay)
                    max_rx = max(max_rx, ax + rw)
                    max_ry = max(max_ry, ay + rh)
                no = read_int_safe(f)
                if no > 0:
                    f.read(no * 12)
                display = ROOM_TRANSLATIONS.get(r_name.lower(), r_name.capitalize())
                file_rooms.append({
                    "id": f"room_{cell_x}_{cell_y}_{r_idx}",
                    "index": r_idx,
                    "name": r_name,
                    "display": display,
                    "level": r_level,
                    "min_x": min_rx, "min_y": min_ry,
                    "max_x": max_rx, "max_y": max_ry,
                    "rects": rects,
                    "building_id": None
                })
                
            num_bld = read_int_safe(f)
            for b_idx in range(num_bld):
                nbr = read_int_safe(f)
                for _ in range(nbr):
                    ri = read_int_safe(f)
                    if ri < len(file_rooms):
                        file_rooms[ri]["building_id"] = f"bld_{cell_x}_{cell_y}_{b_idx}"
                        
            for fr in file_rooms:
                room_records.append((
                    fr["id"], fr["building_id"], cell_x, cell_y, fr["index"],
                    fr["name"], fr["display"], fr["level"],
                    fr["min_x"], fr["min_y"], fr["max_x"], fr["max_y"],
                    fr["max_x"] - fr["min_x"], fr["max_y"] - fr["min_y"],
                    json.dumps(fr["rects"], separators=(',', ':'))
                ))
                
    cursor = conn.cursor()
    cursor.executemany("""
    INSERT OR REPLACE INTO rooms (
        id, building_id, cell_x, cell_y, room_index,
        name, display_name, level,
        min_x, min_y, max_x, max_y, width, height, rects_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, room_records)
    conn.commit()
    print(f"[+] Habitaciones y locales comerciales: {len(room_records)} en {time.time() - t0:.2f}s")
    return len(room_records)

def run_mapper(output_dir=DEFAULT_EXPORT_DIR, town=None, bounds=None, ignore_wilderness=True):
    os.makedirs(output_dir, exist_ok=True)
    db_path = os.path.join(output_dir, "knox_database.sqlite")
    summary_path = os.path.join(output_dir, "knox_summary.json")
    
    active_bounds = None
    area_name = "Todo Knox County"
    
    if town and town.lower() in TOWN_PRESETS:
        active_bounds = TOWN_PRESETS[town.lower()]
        area_name = f"Localidad: {town.capitalize()}"
    elif bounds:
        active_bounds = {
            "min_x": bounds[0], "min_y": bounds[1],
            "max_x": bounds[2], "max_y": bounds[3]
        }
        area_name = f"Rango: [{bounds[0]}, {bounds[1]}] hasta [{bounds[2]}, {bounds[3]}]"
        
    print(f"\n=======================================================")
    print(f" AUTOMATIC MAPPER - KNOX SPATIAL EXTRACTOR (Build 42)")
    print(f" Alcance: {area_name}")
    print(f" Ignorar bosques de relleno extremos: {'SI' if ignore_wilderness else 'NO'}")
    print(f" Salida SQLite: {db_path}")
    print(f"=======================================================\n")
    
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    init_db(conn)
    
    streets_file = os.path.join(PZ_MAPS_DIR, "streets.xml")
    worldmap_file = os.path.join(PZ_MAPS_DIR, "worldmap.xml")
    objects_file = os.path.join(PZ_MAPS_DIR, "objects.lua")
    
    st_count, st_seg_count = parse_streets(conn, streets_file, active_bounds)
    bld_count, water_count, hwy_count = parse_worldmap(conn, worldmap_file, active_bounds)
    zone_count, wild_count = parse_objects_lua(conn, objects_file, active_bounds, ignore_wilderness)
    room_count = parse_lotheader_rooms(conn, PZ_MAPS_DIR, active_bounds)
    
    conn.close()
    
    file_size_mb = os.path.getsize(db_path) / (1024 * 1024)
    print(f"\n-------------------------------------------------------")
    print(f"[EXITO] Base de datos creada con descomposicion geometrica!")
    print(f"        Tamano total en disco:  {file_size_mb:.2f} MB")
    print(f"        Casas/Edificios:        {bld_count}")
    print(f"        Habitaciones/Locales:   {room_count}")
    print(f"        Calles con nombre:      {st_count}")
    print(f"        Segmentos rectangulares:{st_seg_count}")
    print(f"        Carreteras/Highways:    {hwy_count}")
    print(f"        Cuerpos de Agua:        {water_count}")
    print(f"        Zonas Urbanas/POI:      {zone_count}")
    print(f"        Bosques Compactados:    {wild_count}")
    print(f"-------------------------------------------------------\n")
    
    summary = {
        "status": "success",
        "area": area_name,
        "bounds": active_bounds,
        "database_file": db_path,
        "size_mb": round(file_size_mb, 2),
        "counts": {
            "buildings": bld_count,
            "rooms": room_count,
            "named_streets": st_count,
            "road_segments": st_seg_count,
            "highways": hwy_count,
            "total_roads": st_count + hwy_count,
            "water_bodies": water_count,
            "urban_zones": zone_count,
            "wilderness_compacted_zones": wild_count
        }
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutomaticMapper - Extractor espacial de Knox County")
    parser.add_argument("--town", type=str, help="Nombre de la localidad (muldraugh, west_point, rosewood, etc.)")
    parser.add_argument("--box", nargs=4, type=float, metavar=('MIN_X', 'MIN_Y', 'MAX_X', 'MAX_Y'), help="Bounding box manual")
    parser.add_argument("--keep-wild", action="store_true", help="No ignorar bosques de relleno")
    args = parser.parse_args()
    
    run_mapper(
        town=args.town,
        bounds=args.box,
        ignore_wilderness=not args.keep_wild
    )
