import streamlit as st
import fitz  # PyMuPDF
import re
from collections import defaultdict

# === Expresiones regulares ===
ORDER_REGEX = re.compile(r'\b(SO-|USS|SOC|AMZ)-?(\d+)\b')
SHIPMENT_REGEX = re.compile(r'\bSH(\d{5,})\b')
PICKUP_REGEX = re.compile(r'Customer\s*Pickup|Cust\s*Pickup|CUSTPICKUP', re.IGNORECASE)
QUANTITY_REGEX = re.compile(r'(\d+)\s*(?:EA|PCS|PC|Each)', re.IGNORECASE)

# === Funciones auxiliares ===
def extract_identifiers(text):
    order_match = ORDER_REGEX.search(text)
    shipment_match = SHIPMENT_REGEX.search(text)
    order_id = f"{order_match.group(1).rstrip('-')}-{order_match.group(2)}" if order_match else None
    shipment_id = f"SH{shipment_match.group(1)}" if shipment_match else None
    return order_id, shipment_id


def extract_part_numbers(text):
    """Extrae números de parte con coincidencia EXACTA del código + descripción"""
    part_counts = {}
    text_upper = text.upper()

    for full_key in PART_DESCRIPTIONS.keys():
        escaped = re.escape(full_key)
        if re.search(rf'\b{escaped}\b', text_upper):
            part_counts[full_key] = 1  # Contar solo una vez por página

    return part_counts


# === Definición correcta de partes (diccionario) ===
PART_DESCRIPTIONS = {
    'B-PG-081-BLK - 2023 PXG Deluxe Cart Bag - Black': 'B-PG-081-BLK',
    'B-PG-082-WHT - 2023 PXG Lightweight Cart Bag - White/Black': 'B-PG-082-WHT',
    'B-PG-172 - 2025 Stars & Stripes LW Carry Stand Bag': 'B-PG-172',
    'B-PG-172-BGRY - Xtreme Carry Stand Bag - Black': 'B-PG-172-BGRY',
    'B-PG-172-BLACK - Xtreme Carry Stand Bag - Freedom - Black': 'B-PG-172-BLACK',
    'B-PG-172-DB - Deluxe Carry Stand Bag - Black': 'B-PG-172-DB',
    'B-PG-172-DKNSS - Deluxe Carry Stand Bag - Darkness': 'B-PG-172-DKNSS',
    'B-PG-172-DW - Deluxe Carry Stand Bag - White': 'B-PG-172-DW',
    'B-PG-172-GREEN - Xtreme Carry Stand Bag - Freedom - Green': 'B-PG-172-GREEN',
    'B-PG-172-GREY - Xtreme Carry Stand Bag - Freedom - Grey': 'B-PG-172-GREY',
    'B-PG-172-NAVY - Xtreme Carry Stand Bag - Freedom - Navy': 'B-PG-172-NAVY',
    'B-PG-172-TAN - Xtreme Carry Stand Bag - Freedom - Tan': 'B-PG-172-TAN',
    'B-PG-172-WBLK - Xtreme Carry Stand Bag - White': 'B-PG-172-WBLK',
    'B-PG-173 - 2025 Stars & Stripes Hybrid Stand Bag': 'B-PG-173',
    'B-PG-173-BGRY - Xtreme Hybrid Stand Bag - Black': 'B-PG-173-BGRY',
    'B-PG-173-BO - Deluxe Hybrid Stand Bag - Black': 'B-PG-173-BO',
    'B-PG-173-DKNSS - Deluxe Hybrid Stand Bag - Darkness': 'B-PG-173-DKNSS',
    'B-PG-173-WBLK - Xtreme Hybrid Stand Bag - White': 'B-PG-173-WBLK',
    'B-PG-173-WO - Deluxe Hybrid Stand Bag - White': 'B-PG-173-WO',
    'B-PG-244 - Xtreme Cart Bag - White': 'B-PG-244',
    'B-PG-245 - 2025 Stars & Stripes Cart Bag': 'B-PG-245',
    'B-PG-245-BLK - Deluxe Cart Bag B2 - Black': 'B-PG-245-BLK',
    'B-PG-245-WHT - Deluxe Cart Bag B2 - White': 'B-PG-245-WHT',
    'B-PG-246-POLY - Minimalist Carry Stand Bag - Black': 'B-PG-246-POLY',
    'B-UGB8-EP - 2020 Carry Stand Bag - Black': 'B-UGB8-EP'
}


def insert_divider_page(doc, label):
    """Crea una página divisoria con texto de etiqueta"""
    page = doc.new_page()
    text = f"=== {label.upper()} ==="
    page.insert_text(
        point=(72, 72),
        text=text,
        fontsize=18,
        fontname="helv",
        color=(0, 0, 0)
    )


def parse_pdf(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    last_order_id = None
    last_shipment_id = None

    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        order_id, shipment_id = extract_identifiers(text)
        part_numbers = extract_part_numbers(text)

        if not order_id:
            order_id = last_order_id
        else:
            last_order_id = order_id

        if not shipment_id:
            shipment_id = last_shipment_id
        else:
            last_shipment_id = shipment_id

        pages.append({
            "number": i,
            "text": text,  # 👈 Muy importante: guardamos el texto
            "order_id": order_id,
            "shipment_id": shipment_id,
            "part_numbers": part_numbers,
            "page": page,
            "parent": doc
        })

    return pages

def create_summary_page(order_data, build_keys, shipment_keys, pickup_flag):
    all_orders = set(build_keys) | set(shipment_keys)
    unmatched_build = set(build_keys) - set(shipment_keys)
    unmatched_ship = set(shipment_keys) - set(build_keys)
    pickup_orders = [oid for oid in all_orders if order_data[oid]["pickup"]] if pickup_flag else []

    lines = [
        "Tequila Order Summary",
        "",
        f"Total Unique Orders: {len(all_orders)}",
        f"Orders with Build Sheets Only: {len(unmatched_build)}",
        f"Orders with Shipments Only: {len(unmatched_ship)}",
        f"Orders with Both: {len(all_orders) - len(unmatched_build) - len(unmatched_ship)}"
    ]
    if pickup_flag:
        lines.append(f"Customer Pickup Orders: {len(pickup_orders)}")

    summary_doc = fitz.open()
    y = 72
    page = summary_doc.new_page(width=595, height=842)
    for line in lines:
        if y > 770:
            page = summary_doc.new_page(width=595, height=842)
            y = 72
        page.insert_text((72, y), line, fontsize=12)
        y += 14
    return summary_doc


def get_build_order_list(build_pages):
    seen = set()
    order = []
    for p in build_pages:
        oid = p["order_id"]
        if oid and oid not in seen:
            seen.add(oid)
            order.append(oid)
    return order


def group_by_order(pages, classify_pickup=False):
    order_map = defaultdict(lambda: {"pages": [], "pickup": False, "part_numbers": defaultdict(int)})
    for page in pages:
        oid = page.get("order_id")  # Usa .get() para evitar KeyError
        if not oid:
            continue
        order_map[oid]["pages"].append(page)
        if classify_pickup:
            text = page.get("text", "")
            if PICKUP_REGEX.search(text):
                order_map[oid]["pickup"] = True
        for part_num, qty in page.get("part_numbers", {}).items():
            order_map[oid]["part_numbers"][part_num] += qty
    return order_map


from collections import defaultdict
import fitz  # Asegúrate de tener esta importación si no está arriba

def create_part_numbers_summary(order_data):
    part_appearances = defaultdict(int)

    # Contar apariciones por "código + descripción"
    for oid, data in order_data.items():
        part_numbers = data.get("part_numbers", {})
        for full_key, count in part_numbers.items():
            part_appearances[full_key] += count

    if not part_appearances:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72

    # Encabezados
    headers = ["Código + Descripción", "Apariciones"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((500, y), headers[1], fontsize=12, fontname="helv")
    y += 25

    avg_char_width = 6  # Aproximación del ancho promedio de caracteres

    # Mostrar cada código + descripción
    for full_key in sorted(part_appearances.keys()):
        count = part_appearances[full_key]
        if count == 0:
            continue
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 72

        # Dividir en líneas si es muy larga
        lines = []
        temp = full_key
        while len(temp) > 60:
            chunk = temp[:60]
            lines.append(chunk)
            temp = temp[60:]
        lines.append(temp)

        # Insertar texto línea por línea
        for line in lines:
            page.insert_text((50, y), line, fontsize=10)
            y += 12

        # Retroceder una línea para insertar cantidad alineada
        y -= 12
        count_str = str(count)
        text_width = len(count_str) * avg_char_width
        x_count = 540 - text_width  # Alineado a la derecha
        page.insert_text((x_count, y), count_str, fontsize=10)
        y += 12

    # Total general
    total = sum(part_appearances.values())
    y += 20
    if y > 750:
        page = doc.new_page(width=595, height=842)
        y = 72

    page.insert_text(
        (50, y),
        f"TOTAL GENERAL DE APARICIONES: {total}",
        fontsize=14,
        color=(0, 0, 1),
        fontname="helv"
    )

    return doc
def merge_documents(build_order, build_map, ship_map, order_meta, pickup_flag):
    doc = fitz.open()
    pickups = [oid for oid in build_order if order_meta[oid]["pickup"]] if pickup_flag else []

    # Insertar resumen al inicio
    part_summary = create_part_numbers_summary(order_meta)
    if part_summary:
        doc.insert_pdf(part_summary)
        insert_divider_page(doc, "Main Documents")

    if pickup_flag and pickups:
        insert_divider_page(doc, "Customer Pickup Orders")
        for oid in pickups:
            for p in build_map.get(oid, {}).get("pages", []):
                doc.insert_pdf(p["parent"], from_page=p["number"], to_page=p["number"])
            for p in ship_map.get(oid, {}).get("pages", []):
                doc.insert_pdf(p["parent"], from_page=p["number"], to_page=p["number"])

    others = [oid for oid in build_order if oid not in pickups]
    for oid in others:
        for p in build_map.get(oid, {}).get("pages", []):
            doc.insert_pdf(p["parent"], from_page=p["number"], to_page=p["number"])
        for p in ship_map.get(oid, {}).get("pages", []):
            doc.insert_pdf(p["parent"], from_page=p["number"], to_page=p["number"])

    return doc


# === Interfaz de Streamlit ===
st.title("Tequila Build/Shipment PDF Merger")

build_file = st.file_uploader("Upload Build Sheets PDF", type="pdf")
ship_file = st.file_uploader("Upload Shipment Pick Lists PDF", type="pdf")
pickup_flag = st.checkbox("Summarize Customer Pickup orders", value=True)

if build_file and ship_file and st.button("Generate Merged Output"):
    build_bytes = build_file.read()
    ship_bytes = ship_file.read()

    build_pages = parse_pdf(build_bytes)
    ship_pages = parse_pdf(ship_bytes)

    original_pages = build_pages + ship_pages
    all_meta = group_by_order(original_pages, classify_pickup=pickup_flag)

    build_map = group_by_order(build_pages)
    ship_map = group_by_order(ship_pages)

    build_order = get_build_order_list(build_pages)

    # Generar resúmenes
    summary = create_summary_page(all_meta, build_map.keys(), ship_map.keys(), pickup_flag)
    merged = merge_documents(build_order, build_map, ship_map, all_meta, pickup_flag)

    # Insertar resumen al inicio
    if summary:
        merged.insert_pdf(summary, start_at=0)

    # Botón de descarga
    st.download_button(
        "Download Merged Output PDF",
        data=merged.tobytes(),
        file_name="Tequila_Merged_Output.pdf"
    )
