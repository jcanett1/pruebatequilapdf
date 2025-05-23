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
    """Extrae los números de parte y cuenta apariciones (no cantidades)"""
    part_counts = {}
    text_upper = text.upper()
    
    # Busca todos los números de parte en el texto
    for part_num in TARGET_PARTS:
        count = len(re.findall(r'\b' + re.escape(part_num) + r'\b', text_upper))  # Paréntesis cerrado
        if count > 0:
            part_counts[part_num] = part_counts.get(part_num, 0) + count
    
    return part_counts

# Lista completa de números de parte a buscar
TARGET_PARTS = [
    'B-PG-081-BLK', 'B-PG-082-WHT', 'B-PG-172', 'B-PG-172-BGRY',
    'B-PG-172-BLACK', 'B-PG-172-DB', 'B-PG-172-DKNSS', 'B-PG-172-DW',
    'B-PG-172-GREEN', 'B-PG-172-GREY', 'B-PG-172-NAVY', 'B-PG-172-TAN',
    'B-PG-172-WBLK', 'B-PG-173', 'B-PG-173-BGRY', 'B-PG-173-BO',
    'B-PG-173-DKNSS', 'B-PG-173-WBLK', 'B-PG-173-WO', 'B-PG-244',
    'B-PG-245', 'B-PG-245-BLK', 'B-PG-245-WHT', 'B-PG-246-POLY', 'B-UGB8-EP'
]
    
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
    """Crea resumen contando apariciones (no sumando cantidades)"""
    part_appearances = defaultdict(int)  # {part_number: conteo_apariciones}
    associated_shipments = defaultdict(set)  # {part_number: set(shipment_ids)}
    
    for oid, data in order_data.items():
        for part_num, count in data.get("part_numbers", {}).items():
            if part_num in TARGET_PARTS:
                part_appearances[part_num] += count
                if data.get("shipment_id"):
                    associated_shipments[part_num].add(data["shipment_id"])
    
    if not part_appearances:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    
    # Encabezado
    page.insert_text((72, y), "RESUMEN DE APARICIONES DE BOLSAS", fontsize=16)
    y += 30
    page.insert_text((72, y), "Número de Parte", fontsize=12)
    page.insert_text((250, y), "Veces que aparece", fontsize=12)
    page.insert_text((400, y), "Envíos asociados", fontsize=12)
    y += 20
    
    # Datos
    for part_num in sorted(part_appearances.keys()):
        if y > 770:
            page = doc.new_page(width=595, height=842)
            y = 72
            
        page.insert_text((72, y), part_num, fontsize=10)
        page.insert_text((250, y), str(part_appearances[part_num]), fontsize=10)
        
        shipments = sorted(associated_shipments.get(part_num, []))[:3]
        shipments_text = ", ".join(shipments)
        if len(associated_shipments.get(part_num, [])) > 3:
            shipments_text += f"... (+{len(associated_shipments[part_num])-3} más)"
        page.insert_text((400, y), shipments_text, fontsize=10)
        
        y += 15
    
    # Total general (suma de todas las apariciones)
    total_apariciones = sum(part_appearances.values())
    page.insert_text(
        (72, y + 20),
        f"TOTAL DE APARICIONES: {total_apariciones}",
        fontsize=14,
        color=(1, 0, 0)
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
