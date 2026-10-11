import os
import sys
import sqlite3
import json
import argparse
import re
import math
import struct
import io

DEFAULT_DB_PATH = r"c:\Users\OALHUAY\Zomboid\Workshop\AutomaticMapper\exports\knox_database.sqlite"
PZ_MAPS_DIR = r"E:\Steam\steamapps\common\ProjectZomboid\media\maps\Muldraugh, KY"

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

def parse_pz_map_coords(coord_str):
    """Parsea cadenas tipo '#303x9851x2560', '451x9794' o URLs de map.projectzomboid.com."""
    m = re.search(r'#?(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(?:x(\d+))?', coord_str)
    if m:
        x = float(m.group(1))
        y = float(m.group(2))
        zoom = int(m.group(3)) if m.group(3) else None
        return x, y, zoom
    return None, None, None

def point_in_polygon(x, y, poly):
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def distance_point_to_box(x, y, min_x, min_y, max_x, max_y):
    dx = max(0, min_x - x, x - max_x)
    dy = max(0, min_y - y, y - max_y)
    return math.hypot(dx, dy)

def get_relative_direction(from_x, from_y, to_x, to_y):
    dx = to_x - from_x
    dy = to_y - from_y
    if abs(dx) < 2 and abs(dy) < 2:
        return "Aquí mismo"
    angle = math.atan2(dy, dx) * 180 / math.pi
    if -22.5 <= angle < 22.5: return "Este"
    elif 22.5 <= angle < 67.5: return "Sureste"
    elif 67.5 <= angle < 112.5: return "Sur"
    elif 112.5 <= angle < 157.5: return "Suroeste"
    elif angle >= 157.5 or angle < -157.5: return "Oeste"
    elif -157.5 <= angle < -112.5: return "Noroeste"
    elif -112.5 <= angle < -67.5: return "Norte"
    elif -67.5 <= angle < -22.5: return "Noreste"
    return "Cercano"

def classify_sprite(sprite_name):
    """Categoriza un sprite en un objeto reconocible en español."""
    s = sprite_name.lower()
    if any(k in s for k in ['street_decoration_01_8', 'street_decoration_01_9', 'street_decoration_01_10', 'location_sewer']):
        return "Tapa de alcantarilla / Rejilla pluvial"
    elif 'trafficlines' in s:
        return "Pintura vial / Línea de tráfico"
    elif 'curb' in s:
        return "Bordillo / Cordón cuneta"
    elif 'street' in s and 'floor' in s:
        return "Asfalto de calzada"
    elif any(k in s for k in ['natural', 'grass', 'dirt']):
        return "Césped / Terreno natural"
    elif 'tree' in s:
        return "Árbol / Vegetación"
    elif any(k in s for k in ['bookcase', 'book_']):
        return "Estantería de libros / Librero"
    elif any(k in s for k in ['counter', 'register']):
        return "Mostrador comercial / Caja registradora"
    elif any(k in s for k in ['shelves', 'shelving']):
        return "Estantería de exhibición"
    elif any(k in s for k in ['displaycase', 'mannequin']):
        return "Vitrina de exposición / Maniquí"
    elif any(k in s for k in ['table', 'desk']):
        return "Mesa / Escritorio"
    elif 'chair' in s:
        return "Silla / Asiento"
    elif 'door' in s:
        return "Puerta de acceso"
    elif 'window' in s:
        return "Ventana"
    elif any(k in s for k in ['industry_02', 'pipe', 'drain']):
        return "Tubería industrial / Desagüe pluvial vertical"
    elif any(k in s for k in ['industry_01', 'tank_']):
        return "Tanque industrial de combustible / Químicos (Unit AAN)"
    elif any(k in s for k in ['crate', 'container', 'storage', 'barrel']):
        return "Contenedor / Almacenamiento industrial"
    elif 'bed' in s:
        return "Cama"
    return "Decoración / Mobiliario"

def read_int_safe(f):
    b = f.read(4)
    if len(b) < 4:
        raise EOFError()
    return struct.unpack('<i', b)[0]

def parse_cell_lotheader(cell_x, cell_y, maps_dir=PZ_MAPS_DIR):
    """Parsea el .lotheader de una celda PZ (Build 42: celda 256x256 tiles)."""
    header_path = os.path.join(maps_dir, f"{cell_x}_{cell_y}.lotheader")
    if not os.path.exists(header_path):
        return [], []
        
    cell_dim = 256
    with open(header_path, 'rb') as raw_f:
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
        rooms = []
        for r_idx in range(rooms_count):
            r_name = f.readline().strip().decode('utf-8', errors='ignore')
            r_level = read_int_safe(f)
            nr = read_int_safe(f)
            rect_bytes = f.read(nr * 16)
            rects = []
            min_rx, min_ry = 999999, 999999
            max_rx, max_ry = -999999, -999999
            for i in range(nr):
                rx, ry, rw, rh = struct.unpack_from('<iiii', rect_bytes, i * 16)
                ax = cell_x * cell_dim + rx
                ay = cell_y * cell_dim + ry
                rects.append({'x': ax, 'y': ay, 'w': rw, 'h': rh, 'rx': rx, 'ry': ry})
                min_rx = min(min_rx, ax)
                min_ry = min(min_ry, ay)
                max_rx = max(max_rx, ax + rw)
                max_ry = max(max_ry, ay + rh)
            no = read_int_safe(f)
            if no > 0:
                f.read(no * 12)
            display = ROOM_TRANSLATIONS.get(r_name.lower(), r_name.capitalize())
            rooms.append({
                'id': f"room_{cell_x}_{cell_y}_{r_idx}",
                'index': r_idx,
                'name': r_name,
                'display': display,
                'level': r_level,
                'min_x': min_rx, 'min_y': min_ry,
                'max_x': max_rx, 'max_y': max_ry,
                'rects': rects
            })
            
        num_bld = read_int_safe(f)
        buildings = []
        for b_idx in range(num_bld):
            nbr = read_int_safe(f)
            b_r_indices = [read_int_safe(f) for _ in range(nbr)]
            buildings.append({
                'id': f"bld_{cell_x}_{cell_y}_{b_idx}",
                'index': b_idx,
                'rooms': b_r_indices
            })
            
    for b in buildings:
        for ri in b['rooms']:
            if ri < len(rooms):
                rooms[ri]['building_id'] = b['id']
                
    return rooms, buildings

def inspect_tile_deep(db_path, x, y, zoom=None, radius=35, include_objects=True, include_roads=True, include_buildings=True):
    cell_x = int(x // 256)
    cell_y = int(y // 256)
    
    report = {
        "query_tile": {
            "x": x, "y": y,
            "cell": f"{cell_x}_{cell_y}",
            "rel_x": int(x % 256), "rel_y": int(y % 256),
            "zoom": zoom,
            "radius": radius
        },
        "exact_room": None,
        "sister_rooms": [],
        "nearby_rooms": [],
        "exact_roads": [],
        "exact_buildings": [],
        "exact_water": [],
        "exact_zones": [],
        "nearby_roads": [],
        "nearby_buildings": [],
        "tile_objects": []
    }
    
    # 1. PARSEO DE HABITACIONES DESDE .lotheader (Detección exacta a nivel tile)
    cell_rooms, cell_buildings = parse_cell_lotheader(cell_x, cell_y)
    
    for r in cell_rooms:
        if r['level'] == 0 and r['min_x'] <= x <= r['max_x'] and r['min_y'] <= y <= r['max_y']:
            for rect in r['rects']:
                if rect['x'] <= x < rect['x'] + rect['w'] and rect['y'] <= y < rect['y'] + rect['h']:
                    report["exact_room"] = r
                    break
        if report["exact_room"]:
            break
            
    # Si encontramos habitación exacta, buscar locales hermanos en el mismo edificio comercial
    if report["exact_room"]:
        bld_id = report["exact_room"].get('building_id')
        if bld_id:
            b_idx = int(bld_id.split('_')[-1])
            if b_idx < len(cell_buildings):
                bld = cell_buildings[b_idx]
                for ri in bld['rooms']:
                    if ri < len(cell_rooms) and ri != report["exact_room"]['index']:
                        sr = cell_rooms[ri]
                        report["sister_rooms"].append(sr)

    # Habitaciones cercanas en el sector (radio)
    for r in cell_rooms:
        if report["exact_room"] and r['id'] == report["exact_room"]['id']:
            continue
        dist = distance_point_to_box(x, y, r['min_x'], r['min_y'], r['max_x'], r['max_y'])
        if dist <= radius:
            cx = (r['min_x'] + r['max_x']) / 2.0
            cy = (r['min_y'] + r['max_y']) / 2.0
            dir_str = get_relative_direction(x, y, cx, cy)
            report["nearby_rooms"].append({
                "id": r['id'],
                "name": r['name'],
                "display": r['display'],
                "level": r['level'],
                "distance_tiles": round(dist, 1),
                "direction": dir_str,
                "box": [r['min_x'], r['min_y'], r['max_x'], r['max_y']]
            })
    report["nearby_rooms"].sort(key=lambda item: item["distance_tiles"])
    
    # 2. CONSULTAS SQLITE (Rutas, Edificios globales, Zonas)
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # A. Ruta exacta en el tile
        cursor.execute("""
        SELECT id, road_name, kind, min_x, min_y, max_x, max_y, width, geom_json 
        FROM road_segments 
        WHERE ? BETWEEN min_x AND max_x AND ? BETWEEN min_y AND max_y;
        """, (x, y))
        for row in cursor.fetchall():
            seg_id, r_name, kind, min_x, min_y, max_x, max_y, width, geom_json = row
            geom = json.loads(geom_json)
            is_match = False
            if kind.startswith("rect_"):
                is_match = True
            else:
                poly = geom.get("poly", [])
                if poly and point_in_polygon(x, y, poly):
                    is_match = True
            if is_match:
                report["exact_roads"].append({
                    "road_name": r_name,
                    "kind": kind,
                    "width": width,
                    "box": [min_x, min_y, max_x, max_y],
                    "description": f"Rectángulo de ({min_x}, {min_y}) a ({max_x}, {max_y})"
                })

        # B. Edificio de worldmap exacto
        cursor.execute("""
        SELECT id, category, room_tone, min_x, min_y, max_x, max_y, polygon_json 
        FROM buildings 
        WHERE ? BETWEEN min_x AND max_x AND ? BETWEEN min_y AND max_y;
        """, (x, y))
        for row in cursor.fetchall():
            bld_id, cat, tone, min_x, min_y, max_x, max_y, poly_json = row
            poly = json.loads(poly_json)
            if point_in_polygon(x, y, poly):
                report["exact_buildings"].append({
                    "id": bld_id,
                    "category": cat,
                    "room_tone": tone,
                    "bounds": [min_x, min_y, max_x, max_y]
                })

        # C. Cuerpos de agua exactos
        cursor.execute("""
        SELECT id, water_type, min_x, min_y, max_x, max_y, polygon_json 
        FROM water_bodies 
        WHERE ? BETWEEN min_x AND max_x AND ? BETWEEN min_y AND max_y;
        """, (x, y))
        for row in cursor.fetchall():
            w_id, w_type, min_x, min_y, max_x, max_y, poly_json = row
            poly = json.loads(poly_json)
            if point_in_polygon(x, y, poly):
                report["exact_water"].append({
                    "id": w_id,
                    "type": w_type,
                    "bounds": [min_x, min_y, max_x, max_y]
                })

        # D. Zonas Urbanas
        cursor.execute("""
        SELECT id, name, zone_type, min_x, min_y, max_x, max_y 
        FROM zones 
        WHERE ? BETWEEN min_x AND max_x AND ? BETWEEN min_y AND max_y;
        """, (x, y))
        for row in cursor.fetchall():
            z_id, z_name, z_type, min_x, min_y, max_x, max_y = row
            report["exact_zones"].append({
                "name": z_name or z_type,
                "type": z_type
            })

        # D. Rutas cercanas dentro del radio
        if include_roads:
            cursor.execute("""
            SELECT DISTINCT road_name, road_id, min_x, min_y, max_x, max_y, width, kind
            FROM road_segments 
            WHERE NOT (max_x < ? OR min_x > ? OR max_y < ? OR min_y > ?);
            """, (x - radius, x + radius, y - radius, y + radius))
            
            seen_roads = set()
            for row in cursor.fetchall():
                r_name, r_id, bx1, by1, bx2, by2, width, kind = row
                dist = distance_point_to_box(x, y, bx1, by1, bx2, by2)
                if dist <= radius and r_name not in seen_roads:
                    seen_roads.add(r_name)
                    cx = (bx1 + bx2) / 2.0
                    cy = (by1 + by2) / 2.0
                    dir_str = get_relative_direction(x, y, cx, cy)
                    report["nearby_roads"].append({
                        "name": r_name,
                        "distance_tiles": round(dist, 1),
                        "direction": dir_str,
                        "width": width,
                        "kind": kind
                    })
            report["nearby_roads"].sort(key=lambda item: item["distance_tiles"])

        # E. Edificios cercanos dentro del radio
        if include_buildings:
            cursor.execute("""
            SELECT id, category, room_tone, min_x, min_y, max_x, max_y, center_x, center_y 
            FROM buildings 
            WHERE NOT (max_x < ? OR min_x > ? OR max_y < ? OR min_y > ?);
            """, (x - radius, x + radius, y - radius, y + radius))
            
            for row in cursor.fetchall():
                bld_id, cat, tone, bx1, by1, bx2, by2, cx, cy = row
                dist = distance_point_to_box(x, y, bx1, by1, bx2, by2)
                if dist <= radius:
                    dir_str = get_relative_direction(x, y, cx, cy)
                    report["nearby_buildings"].append({
                        "id": bld_id,
                        "category": cat,
                        "room_tone": tone,
                        "distance_tiles": round(dist, 1),
                        "direction": dir_str,
                        "box": [bx1, by1, bx2, by2]
                    })
            report["nearby_buildings"].sort(key=lambda item: item["distance_tiles"])

        conn.close()

    # 3. OBJETOS FÍSICOS EN LA CELDA (Alcantarillas, Cordones, Contenedores, Estanterías)
    if include_objects:
        header_path = os.path.join(PZ_MAPS_DIR, f"{cell_x}_{cell_y}.lotheader")
        if os.path.exists(header_path):
            with open(header_path, 'rb') as f:
                f.read(8)
                data = f.read()
            sprites_raw = re.findall(r'[a-zA-Z0-9_]{4,}', data.decode('latin1', errors='ignore'))
            
            special_sprites = []
            seen_types = set()
            for s in set(sprites_raw):
                category_desc = classify_sprite(s)
                # Priorizar alcantarillas, líneas viales, y mobiliario específico del local
                is_prio = False
                if any(k in category_desc.lower() for k in ['alcantarilla', 'manhole', 'tubería', 'tanque', 'bordillo', 'vial', 'estantería', 'mostrador', 'librero']):
                    is_prio = True
                if is_prio or category_desc not in seen_types:
                    seen_types.add(category_desc)
                    special_sprites.append({
                        "sprite": s,
                        "type": category_desc
                    })
            
            def get_order(item):
                t = item['type'].lower()
                if 'alcantarilla' in t: return 0
                if 'tubería' in t: return 1
                if 'tanque' in t: return 2
                if 'librero' in t or 'estantería' in t: return 3
                if 'mostrador' in t: return 4
                if 'bordillo' in t or 'vial' in t: return 5
                return 6
                
            special_sprites.sort(key=get_order)
            report["tile_objects"] = special_sprites[:10]

    return report

def print_deep_report(rep):
    x = rep["query_tile"]["x"]
    y = rep["query_tile"]["y"]
    r = rep["query_tile"]["radius"]
    cell = rep["query_tile"]["cell"]
    rel_x = rep["query_tile"]["rel_x"]
    rel_y = rep["query_tile"]["rel_y"]
    zoom = rep["query_tile"]["zoom"]
    zoom_str = f" | Zoom: {zoom}" if zoom else ""
    
    print(f"\n================================================================================")
    print(f" ANALISIS INTEGRAL DE TILE: X = {x}, Y = {y}{zoom_str} (Radio: {r} tiles)")
    print(f" Celda Knox: {cell} (Coordenada Relativa: {rel_x}x{rel_y})")
    print(f"================================================================================")
    
    # 1. LOCAL O HABITACIÓN EXACTA DETECTADA
    if rep["exact_room"]:
        r_info = rep["exact_room"]
        print(f"\n[1. LOCAL / HABITACION EXACTA DETECTADA EN ESTE TILE]")
        print(f"  ==========================================================================")
        print(f"  * LUGAR:         {r_info['display']}")
        print(f"  * NOMBRE INTERNO:{r_info['name']}")
        print(f"  * NIVEL (Z):     Planta Baja (Nivel {r_info['level']})")
        print(f"  * LIMITES:       X={r_info['min_x']}..{r_info['max_x']}, Y={r_info['min_y']}..{r_info['max_y']}")
        print(f"  * DIMENSIONES:   {r_info['max_x'] - r_info['min_x']} tiles (ancho) x {r_info['max_y'] - r_info['min_y']} tiles (largo)")
        print(f"  * ID HABITACION: {r_info['id']}")
        
        # Locales hermanos en el mismo complejo comercial
        if rep["sister_rooms"]:
            ground_sisters = [sr for sr in rep["sister_rooms"] if sr['level'] == 0 and sr['name'] not in ('lobby', 'storage', 'bathroom', 'emptyoutside')]
            upper_sisters = [sr for sr in rep["sister_rooms"] if sr['level'] > 0]
            
            if ground_sisters:
                print(f"\n  [LOCALES CONTIGUOS EN EL MISMO COMPLEJO COMERCIAL]:")
                for sr in ground_sisters:
                    cx = (sr['min_x'] + sr['max_x']) / 2.0
                    cy = (sr['min_y'] + sr['max_y']) / 2.0
                    dir_str = get_relative_direction(x, y, cx, cy)
                    dist = distance_point_to_box(x, y, sr['min_x'], sr['min_y'], sr['max_x'], sr['max_y'])
                    print(f"    - {sr['display']} -> Hacia el {dir_str} (a {dist:.1f} tiles) [X: {sr['min_x']}..{sr['max_x']}, Y: {sr['min_y']}..{sr['max_y']}]")
                    
            if upper_sisters:
                up_types = set(sr['display'] for sr in upper_sisters)
                print(f"\n  [PLANTA ALTA (Z=1)]:")
                print(f"    - {len(upper_sisters)} dependencias residenciales/apartamentos ({', '.join(list(up_types)[:4])})")
        print(f"  ==========================================================================")
    else:
        print(f"\n[1. COBERTURA EN ESTE TILE EXACTO]")
        if rep["exact_roads"]:
            for road in rep["exact_roads"]:
                print(f"  * Calle actual: {road['road_name']} (Ancho: {road['width']} tiles)")
                print(f"    Figura geométrica: {road['kind']} -> {road['description']}")
        elif rep["exact_buildings"]:
            for bld in rep["exact_buildings"]:
                print(f"  * Edificio: {bld['id']} ({bld['category']} - {bld['room_tone']})")
        elif rep["exact_water"]:
            for w in rep["exact_water"]:
                print(f"  * Superficie acuática: Agua natural ({w['type'].capitalize()})")
                print(f"    Cuerpo de agua: {w['id']} [Límites: X={w['bounds'][0]}..{w['bounds'][2]}, Y={w['bounds'][1]}..{w['bounds'][3]}]")
        else:
            print(f"  * Suelo exterior / Calzada")
            
    if rep["exact_zones"]:
        print(f"\n[ZONAS Y ATRIBUTOS DE MAPA EN ESTE TILE]")
        for z in rep["exact_zones"]:
            print(f"  * Zona: {z['name']} ({z['type']})")

    # 2. Objetos e infraestructura detectada
    if rep["tile_objects"]:
        print("\n[2. OBJETOS E INFRAESTRUCTURA DETECTADA EN EL SECTOR]")
        for obj in rep["tile_objects"]:
            print(f"  * [{obj['type']}] -> Sprite: {obj['sprite']}")

    # 3. Rutas y calles cercanas
    if rep["nearby_roads"]:
        print(f"\n[3. RUTAS Y CALLES CERCANAS O COLINDANTES (Radio {r} tiles)]")
        for nr in rep["nearby_roads"][:5]:
            dist_txt = "Pasa por este mismo tile" if nr['distance_tiles'] == 0 else f"A {nr['distance_tiles']} tiles hacia el {nr['direction']}"
            print(f"  * {nr['name']} (Ancho: {nr['width']} tiles) -> {dist_txt}")

    # 4. Otros locales o edificios colindantes
    if rep["nearby_rooms"]:
        print(f"\n[4. LOCALES Y HABITACIONES COLINDANTES EN EL RADIO (Radio {r} tiles)]")
        for nr in rep["nearby_rooms"][:6]:
            print(f"  * {nr['display']} (Z={nr['level']})")
            print(f"    Distancia: a {nr['distance_tiles']} tiles hacia el {nr['direction']} [X: {nr['box'][0]}..{nr['box'][2]}, Y: {nr['box'][1]}..{nr['box'][3]}]")
    elif rep["nearby_buildings"]:
        print(f"\n[4. CASAS Y EDIFICIOS CERCANOS (Radio {r} tiles)]")
        for nb in rep["nearby_buildings"][:6]:
            print(f"  * {nb['id']} [{nb['category']} | {nb['room_tone']}]")
            print(f"    Distancia: a {nb['distance_tiles']} tiles hacia el {nb['direction']} (Caja: {nb['box']})")
    else:
        print(f"\n[4. LOCALES Y EDIFICIOS]: Ningún otro edificio a menos de {r} tiles.")

    print(f"\n================================================================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TileInspector — Inspección espacial profunda: Local/Habitación, Objetos, Rutas y Edificios")
    parser.add_argument("coords", nargs="?", type=str, help="Coordenadas directas o URL del mapa PZ (ej: #418x9811x2560 o 451x9794)")
    parser.add_argument("--tile", nargs=2, type=float, metavar=('X', 'Y'), help="Coordenadas exactas X Y")
    parser.add_argument("--radius", type=float, default=35.0, help="Radio de búsqueda en tiles para rutas y casas cercanas (def: 35)")
    parser.add_argument("--no-objects", action="store_true", help="No incluir objetos e infraestructura de tile")
    parser.add_argument("--no-nearby-roads", action="store_true", help="No incluir rutas cercanas")
    parser.add_argument("--no-nearby-buildings", action="store_true", help="No incluir edificios cercanos")
    parser.add_argument("--db", type=str, default=DEFAULT_DB_PATH, help="Ruta a knox_database.sqlite")
    args = parser.parse_args()
    
    target_x, target_y, zoom = None, None, None
    if args.coords:
        target_x, target_y, zoom = parse_pz_map_coords(args.coords)
    elif args.tile:
        target_x, target_y = args.tile[0], args.tile[1]
        
    if target_x is not None and target_y is not None:
        rep = inspect_tile_deep(
            db_path=args.db,
            x=target_x,
            y=target_y,
            zoom=zoom,
            radius=args.radius,
            include_objects=not args.no_objects,
            include_roads=not args.no_nearby_roads,
            include_buildings=not args.no_nearby_buildings
        )
        if rep:
            print_deep_report(rep)
    else:
        parser.print_help()
