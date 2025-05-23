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
    part_numbers = {}
    for match in PART_NUMBER_REGEX.finditer(text.upper()):  # Buscar en mayúsculas
        part_num = match.group(0).upper()
        # Buscar cantidad cerca del número de parte
        quantity_match = re.search(r'(\d+)\s*(?:EA|PCS|PC|Each)', text, re.IGNORECASE)
        quantity = int(quantity_match.group(1)) if quantity_match else 1
        part_numbers[part_num] = part_numbers.get(part_num, 0) + quantity
    return part_numbers
    
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
    """Crea un resumen preciso de números de parte especiales con sus cantidades totales"""
    part_summary = defaultdict(int)  # {part_number: total_quantity}
    associated_shipments = defaultdict(set)  # {part_number: set(shipment_ids)}
    
    # Definición completa de números de parte a buscar
    TARGET_PARTS = {
        'B-PG-081-BLK', 'B-PG-082-WHT', 'B-PG-172', 'B-PG-172-BGRY',
        'B-PG-172-BLACK', 'B-PG-172-DB', 'B-PG-172-DKNSS', 'B-PG-172-DW',
        'B-PG-172-GREEN', 'B-PG-172-GREY', 'B-PG-172-NAVY', 'B-PG-172-TAN',
        'B-PG-172-WBLK', 'B-PG-173', 'B-PG-173-BGRY', 'B-PG-173-BO',
        'B-PG-173-DKNSS', 'B-PG-173-WBLK', 'B-PG-173-WO', 'B-PG-244',
        'B-PG-245', 'B-PG-245-BLK', 'B-PG-245-WHT', 'B-PG-246-POLY', 'B-UGB8-EP'
    }

    for oid, data in order_data.items():
        for part_num, qty in data.get("part_numbers", {}).items():
            part_upper = part_num.upper()
            # Verifica si el número de parte está en nuestra lista objetivo
            if any(target_part in part_upper for target_part in TARGET_PARTS):
                part_summary[part_upper] += qty
                if data.get("shipment_id"):
                    associated_shipments[part_upper].add(data["shipment_id"])

    if not part_summary:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    
    # Encabezado
    title = "Resumen de Números de Parte Especiales"
    page.insert_text((72, y), title, fontsize=16)
    y += 30
    
    # Columnas
    headers = ["Número de Parte", "Cantidad Total", "Envíos Asociados"]
    page.insert_text((72, y), headers[0], fontsize=12)
    page.insert_text((250, y), headers[1], fontsize=12)
    page.insert_text((400, y), headers[2], fontsize=12)
    y += 20
    
    # Datos
    for part_num in sorted(part_summary.keys()):
        if y > 770:  # Nueva página si se llega al final
            page = doc.new_page(width=595, height=842)
            y = 72
        
        # Número de parte
        page.insert_text((72, y), part_num, fontsize=10)
        
        # Cantidad total (suma de todas las apariciones)
        total_qty = part_summary[part_num]
        page.insert_text((250, y), str(total_qty), fontsize=10)
        
        # Envíos asociados (mostrar solo los primeros 3)
        shipments = sorted(associated_shipments.get(part_num, set()))
        shipments_text = ", ".join(shipments[:3])
        if len(shipments) > 3:
            shipments_text += f"... (+{len(shipments)-3} más)"
        page.insert_text((400, y), shipments_text, fontsize=10)
        
        y += 15
    
    # Total general (suma de todas las cantidades)
    grand_total = sum(part_summary.values())
    page.insert_text(
        (72, y + 20),
        f"TOTAL GENERAL: {grand_total}",
        fontsize=14,
        color=(1, 0, 0)  # Rojo para destacar
    
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
