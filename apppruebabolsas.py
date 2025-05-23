import streamlit as st
import fitz  # PyMuPDF
import re
from collections import defaultdict

ORDER_REGEX = re.compile(r'\b(SO-|USS|SOC|AMZ)-?(\d+)\b')
SHIPMENT_REGEX = re.compile(r'\bSH(\d{5,})\b')
PICKUP_REGEX = re.compile(r'Customer\s*Pickup|Cust\s*Pickup|CUSTPICKUP', re.IGNORECASE)
PART_NUMBER_REGEX = re.compile(
    r'\b(B-PG-081-BLK|B-PG-082-WHT|B-PG-172(-[A-Z]+)?|B-PG-173(-[A-Z]+)?|B-PG-244|B-PG-245(-[A-Z]+)?|B-PG-246-POLY|B-UGB8-EP)\b',
    re.IGNORECASE
)
QUANTITY_REGEX = re.compile(r'(\d+)\s*(?:EA|PCS|PC|Each)', re.IGNORECASE)

def extract_identifiers(text):
    order_match = ORDER_REGEX.search(text)
    shipment_match = SHIPMENT_REGEX.search(text)
    order_id = f"{order_match.group(1).rstrip('-')}-{order_match.group(2)}" if order_match else None
    shipment_id = f"SH{shipment_match.group(1)}" if shipment_match else None
    return order_id, shipment_id

def extract_part_numbers(text):
    """Extrae números de parte con búsqueda exacta y sensible al contexto"""
    part_counts = {}
    text_upper = text.upper()
    
    for part_num in PART_DESCRIPTIONS.keys():
        # Búsqueda exacta considerando posibles espacios o guiones adicionales
        pattern = r'(?<!\w)' + re.escape(part_num) + r'(?!\w)'
        count = len(re.findall(pattern, text_upper, re.IGNORECASE))
        if count > 0:
            part_counts[part_num] = part_counts.get(part_num, 0) + count
    
    return part_counts


# Lista completa de números de parte a buscar
PART_DESCRIPTIONS = {
    'B-PG-081-BLK': '2023 PXG Deluxe Cart Bag - Black',
    'B-PG-082-WHT': '2023 PXG Lightweight Cart Bag - White/Black',
    'B-PG-172': '2025 Stars & Stripes LW Carry Stand Bag',
    'B-PG-172-BGRY': 'Xtreme Carry Stand Bag - Black',
    'B-PG-172-BLACK': 'Xtreme Carry Stand Bag - Freedom - Black',
    'B-PG-172-DB': 'Deluxe Carry Stand Bag - Black',
    'B-PG-172-DKNSS': 'Deluxe Carry Stand Bag - Darkness',
    'B-PG-172-DW': 'Deluxe Carry Stand Bag - White',
    'B-PG-172-GREEN': 'Xtreme Carry Stand Bag - Freedom - Green',
    'B-PG-172-GREY': 'Xtreme Carry Stand Bag - Freedom - Grey',
    'B-PG-172-NAVY': 'Xtreme Carry Stand Bag - Freedom - Navy',
    'B-PG-172-TAN': 'Xtreme Carry Stand Bag - Freedom - Tan',
    'B-PG-172-WBLK': 'Xtreme Carry Stand Bag - White',
    'B-PG-173': '2025 Stars & Stripes Hybrid Stand Bag',
    'B-PG-173-BGRY': 'Xtreme Hybrid Stand Bag - Black',
    'B-PG-173-BO': 'Deluxe Hybrid Stand Bag - Black',
    'B-PG-173-DKNSS': 'Deluxe Hybrid Stand Bag - Darkness',
    'B-PG-173-WBLK': 'Xtreme Hybrid Stand Bag - White',
    'B-PG-173-WO': 'Deluxe Hybrid Stand Bag - White',
    'B-PG-244': 'Xtreme Cart Bag - White',
    'B-PG-245': '2025 Stars & Stripes Cart Bag',
    'B-PG-245-BLK': 'Deluxe Cart Bag B2 - Black',
    'B-PG-245-WHT': 'Deluxe Cart Bag B2 - White',
    'B-PG-246-POLY': 'Minimalist Carry Stand Bag - Black',
    'B-UGB8-EP': '2020 Carry Stand Bag- Black'
}
    
def insert_divider_page(doc, label):
    """Crea una página divisoria con texto de etiqueta"""
    page = doc.new_page()
    text = f"=== {label.upper()} ==="
    page.insert_text(
        point=(72, 72),  # Posición (x,y) en puntos (1 pulgada = 72 puntos)
        text=text,
        fontsize=18,
        fontname="helv",
        color=(0, 0, 0)  # Color negro
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
            "text": text,
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
    """Obtiene una lista única de IDs de órdenes en el orden que aparecen."""
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
        oid = page["order_id"]
        if not oid:
            continue
        order_map[oid]["pages"].append(page)
        if classify_pickup and PICKUP_REGEX.search(page["text"]):
            order_map[oid]["pickup"] = True
        for part_num, qty in page["part_numbers"].items():
            order_map[oid]["part_numbers"][part_num] += qty
    return order_map

def create_part_numbers_summary(order_data):
    """Genera resumen con nombres completos y conteo de apariciones"""
    part_appearances = defaultdict(int)
    associated_shipments = defaultdict(set)
    
    for oid, data in order_data.items():
        for part_num, count in data.get("part_numbers", {}).items():
            if part_num in PART_DESCRIPTIONS:
                part_appearances[part_num] += count
                if data.get("shipment_id"):
                    associated_shipments[part_num].add(data["shipment_id"])
    
    if not part_appearances:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72

    # Encabezado mejorado
    headers = ["Código", "Descripción", "Apariciones", "Envíos"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv", set_simple=True)
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv", set_simple=True)
    page.insert_text((400, y), headers[2], fontsize=12, fontname="helv", set_simple=True)
    page.insert_text((480, y), headers[3], fontsize=12, fontname="helv", set_simple=True)
    y += 25

    # Datos con descripciones completas
    for part_num in sorted(part_appearances.keys()):
        if y > 750:  # Nueva página antes de llegar al final
            page = doc.new_page(width=595, height=842)
            y = 72

        # Código
        page.insert_text((50, y), part_num, fontsize=10)

        # Descripción completa (con salto de línea si es muy larga)
        desc = PART_DESCRIPTIONS[part_num]
        if len(desc) > 40:  # Ajusta según necesidad
            page.insert_text((150, y), desc[:40], fontsize=9)
            page.insert_text((150, y + 12), desc[40:], fontsize=9)
        else:
            page.insert_text((150, y), desc, fontsize=10)

        # Conteo
        page.insert_text((400, y), str(part_appearances[part_num]), fontsize=10)

        # Envíos asociados
        shipments = sorted(associated_shipments.get(part_num, []))[:3]
        shipments_text = ", ".join(shipments) if shipments else "N/A"
        if len(associated_shipments.get(part_num, [])) > 3:
            shipments_text += "..."

        page.insert_text((480, y), shipments_text, fontsize=9)

        y += 25 if len(desc) > 40 else 15  # Ajuste de espacio

    # Total general
    total = sum(part_appearances.values())
    page.insert_text(
        (50, y + 20),
        f"TOTAL GENERAL DE APARICIONES: {total}",
        fontsize=14,
        color=(0, 0, 1),  # Azul para destacar
        fontname="helv", set_simple=True
    )

    return doc
# ... (el resto de las funciones permanecen iguales hasta merge_documents)

def merge_documents(build_order, build_map, ship_map, order_meta, pickup_flag):
    doc = fitz.open()
    pickups = [oid for oid in build_order if order_meta[oid]["pickup"]] if pickup_flag else []
    
    # Insertar resumen de números de parte especiales al principio
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

# Streamlit UI (permanece igual)
st.title("Tequila Build/Shipment PDF Merger")

build_file = st.file_uploader("Upload Build Sheets PDF", type="pdf")
ship_file = st.file_uploader("Upload Shipment Pick Lists PDF", type="pdf")

pickup_flag = st.checkbox("Summarize Customer Pickup orders", value=True)

if build_file and ship_file and st.button("Generate Merged Output"):
    build_bytes = build_file.read()
    ship_bytes = ship_file.read()

    build_pages = parse_pdf(build_bytes)
    ship_pages = parse_pdf(ship_bytes)
    combined_pages = build_pages + ship_pages

    all_meta = group_by_order(combined_pages, classify_pickup=pickup_flag)
    build_map = group_by_order(build_pages)
    ship_map = group_by_order(ship_pages)

    build_order = get_build_order_list(build_pages)
    summary = create_summary_page(all_meta, build_map.keys(), ship_map.keys(), pickup_flag)
    merged = merge_documents(build_order, build_map, ship_map, all_meta, pickup_flag)
    merged.insert_pdf(summary, start_at=0)

    st.download_button("Download Merged Output PDF", data=merged.tobytes(), file_name="Tequila_Merged_Output.pdf")
