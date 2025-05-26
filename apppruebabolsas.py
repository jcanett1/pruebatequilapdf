import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from collections import defaultdict

# === Expresiones regulares ===
ORDER_REGEX = re.compile(r'\b(SO-|USS|SOC|AMZ)-?(\d+)\b')
SHIPMENT_REGEX = re.compile(r'\b(SH\d{5,})\b')  # Modificado para capturar el formato exacto
PICKUP_REGEX = re.compile(r'Customer\s*Pickup|Cust\s*Pickup|CUSTPICKUP', re.IGNORECASE)
QUANTITY_REGEX = re.compile(r'(\d+)\s*(?:EA|PCS|PC|Each)', re.IGNORECASE)

# === Definición de partes (diccionario) ===
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
    'B-UGB8-EP': '2020 Carry Stand Bag - Black'
}

# === Funciones auxiliares ===
def extract_identifiers(text):
    order_match = ORDER_REGEX.search(text)
    shipment_match = SHIPMENT_REGEX.search(text)
    order_id = f"{order_match.group(1).rstrip('-')}-{order_match.group(2)}" if order_match else None
    shipment_id = shipment_match.group(1) if shipment_match else None  # Mantener formato original del SH
    return order_id, shipment_id

def extract_part_numbers(text):
    """Extrae números de parte con coincidencia exacta y sin duplicados por página"""
    part_counts = {}
    text_upper = text.upper()
    for part_num in PART_DESCRIPTIONS.keys():
        pattern = r'(?<!\w)' + re.escape(part_num) + r'(?!\w)'
        if re.search(pattern, text_upper):
            part_counts[part_num] = 1  # Contar solo 1 vez por página
    return part_counts

def extract_relations(text, order_id, shipment_id):
    """Extrae relaciones entre códigos, órdenes y SH para la tabla detallada"""
    relations = []
    text_upper = text.upper()
    
    for part_num in PART_DESCRIPTIONS:
        pattern = r'(?<!\w)' + re.escape(part_num) + r'(?!\w)'
        if re.search(pattern, text_upper) and order_id and shipment_id:
            relations.append({
                "Orden": order_id,
                "Código": part_num,
                "Descripción": PART_DESCRIPTIONS[part_num],
                "SH": shipment_id
            })
    
    return relations

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
    relations = []  # Para almacenar las relaciones para la tabla
    last_order_id = None
    last_shipment_id = None

    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        order_id, shipment_id = extract_identifiers(text)
        
        if not order_id:
            order_id = last_order_id
        else:
            last_order_id = order_id

        if not shipment_id:
            shipment_id = last_shipment_id
        else:
            last_shipment_id = shipment_id

        part_numbers = extract_part_numbers(text)
        page_relations = extract_relations(text, order_id, shipment_id)
        relations.extend(page_relations)

        pages.append({
            "number": i,
            "text": text,
            "order_id": order_id,
            "shipment_id": shipment_id,
            "part_numbers": part_numbers,
            "page": page,
            "parent": doc
        })

    return pages, relations

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
        oid = page.get("order_id")
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

def create_part_numbers_summary(order_data):
    part_appearances = defaultdict(int)

    for oid, data in order_data.items():
        part_numbers = data.get("part_numbers", {})
        for part_num, count in part_numbers.items():
            if part_num in PART_DESCRIPTIONS:
                part_appearances[part_num] += count

    if not part_appearances:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72

    headers = ["Código", "Descripción", "Apariciones"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv", set_simple=True)
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv", set_simple=True)
    page.insert_text((450, y), headers[2], fontsize=12, fontname="helv", set_simple=True)
    y += 25

    for part_num in sorted(part_appearances.keys()):
        count = part_appearances[part_num]
        if count == 0:
            continue
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 72

        desc = PART_DESCRIPTIONS[part_num]
        page.insert_text((50, y), part_num, fontsize=10)

        if len(desc) > 40:
            page.insert_text((150, y), desc[:40], fontsize=9)
            page.insert_text((150, y + 12), desc[40:], fontsize=9)
        else:
            page.insert_text((150, y), desc, fontsize=10)

        page.insert_text((450, y), str(count), fontsize=10)
        y += 25 if len(desc) > 40 else 15

    total = sum(part_appearances.values())
    page.insert_text(
        (50, y + 20),
        f"TOTAL GENERAL DE APARICIONES: {total}",
        fontsize=14,
        color=(0, 0, 1),
        fontname="helv",
        set_simple=True
    )

    return doc

def create_relations_table(relations):
    """Crea una tabla PDF con las relaciones orden-código-SH"""
    if not relations:
        return None
    
    # Convertir a DataFrame para ordenar
    df = pd.DataFrame(relations)
    df = df.sort_values(by=["Orden", "Código"])
    
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    
    # Título
    page.insert_text((50, y), "RELACIÓN ÓRDENES - CÓDIGOS - SH", 
                    fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30
    
    # Encabezados
    headers = ["Orden", "Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
    page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
    y += 20
    
    # Datos
    for _, row in df.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            
        page.insert_text((50, y), row["Orden"], fontsize=10)
        page.insert_text((150, y), row["Código"], fontsize=10)
        
        # Descripción en múltiples líneas si es necesario
        desc = row["Descripción"]
        if len(desc) > 30:
            page.insert_text((300, y), desc[:30], fontsize=9)
            page.insert_text((300, y + 12), desc[30:], fontsize=9)
            y += 12
        else:
            page.insert_text((300, y), desc, fontsize=10)
            
        page.insert_text((500, y), row["SH"], fontsize=10)
        y += 25 if len(desc) > 30 else 15
    
    return doc

def merge_documents(build_order, build_map, ship_map, order_meta, pickup_flag, relations):
    doc = fitz.open()
    pickups = [oid for oid in build_order if order_meta[oid]["pickup"]] if pickup_flag else []

    # Insertar tabla de relaciones al inicio
    relations_table = create_relations_table(relations)
    if relations_table:
        doc.insert_pdf(relations_table)
        insert_divider_page(doc, "Resumen de Partes")
    
    # Insertar resumen de partes
    part_summary = create_part_numbers_summary(order_meta)
    if part_summary:
        doc.insert_pdf(part_summary)
        insert_divider_page(doc, "Documentos Principales")

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

def display_interactive_table(relations):
    """Muestra una tabla interactiva con las relaciones"""
    if not relations:
        st.warning("No se encontraron relaciones entre órdenes, códigos y SH")
        return
    
    df = pd.DataFrame(relations)
    df = df.sort_values(by=["Orden", "Código"])
    
    st.subheader("Relación Detallada de Órdenes, Códigos y SH")
    
    # Mostrar tabla interactiva
    st.dataframe(
        df,
        column_config={
            "Descripción": st.column_config.TextColumn(width="large"),
            "SH": st.column_config.TextColumn(width="medium")
        },
        hide_index=True,
        use_container_width=True
    )
    
    # Opción para descargar
    csv = df.to_csv(index=False, encoding='utf-8')
    st.download_button(
        "Descargar como CSV",
        data=csv,
        file_name='relacion_ordenes_codigos_sh.csv',
        mime='text/csv'
    )

# === Interfaz de Streamlit ===
st.title("Tequila Build/Shipment PDF Processor")

build_file = st.file_uploader("Upload Build Sheets PDF", type="pdf")
ship_file = st.file_uploader("Upload Shipment Pick Lists PDF", type="pdf")
pickup_flag = st.checkbox("Summarize Customer Pickup orders", value=True)

if build_file and ship_file:
    build_bytes = build_file.read()
    ship_bytes = ship_file.read()

    # Procesar ambos PDFs
    build_pages, build_relations = parse_pdf(build_bytes)
    ship_pages, ship_relations = parse_pdf(ship_bytes)

    # Combinar todo
    original_pages = build_pages + ship_pages
    all_relations = build_relations + ship_relations
    all_meta = group_by_order(original_pages, classify_pickup=pickup_flag)

    # Mostrar tabla interactiva
    display_interactive_table(all_relations)

    if st.button("Generate Merged Output"):
        build_map = group_by_order(build_pages)
        ship_map = group_by_order(ship_pages)
        build_order = get_build_order_list(build_pages)

        # Generar resúmenes
        summary = create_summary_page(all_meta, build_map.keys(), ship_map.keys(), pickup_flag)
        merged = merge_documents(build_order, build_map, ship_map, all_meta, pickup_flag, all_relations)

        # Insertar resumen al inicio
        if summary:
            merged.insert_pdf(summary, start_at=0)

        # Botón de descarga
        st.download_button(
            "Download Merged Output PDF",
            data=merged.tobytes(),
            file_name="Tequila_Merged_Output.pdf"
        )
