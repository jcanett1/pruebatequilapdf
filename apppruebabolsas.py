import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from collections import defaultdict

# === Expresiones regulares ===
ORDER_REGEX = re.compile(r'\b(SO-|USS|SOC|AMZ)-?(\d+)\b')
SHIPMENT_REGEX = re.compile(r'\bSH(\d{5,})\b')
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

DESCRIPTION_TO_CODE = {desc: code for code, desc in PART_DESCRIPTIONS.items()}

# === Funciones auxiliares ===
def extract_identifiers(text):
    order_match = ORDER_REGEX.search(text)
    shipment_match = SHIPMENT_REGEX.search(text)
    order_id = f"{order_match.group(1).rstrip('-')}-{order_match.group(2)}" if order_match else None
    shipment_id = f"SH{shipment_match.group(1)}" if shipment_match else None
    return order_id, shipment_id

def normalize_code(code):
    """Normaliza el formato del código (mayúsculas, guiones)"""
    code = code.upper().replace(' ', '')
    if '-' not in code and len(code) > 5:
        parts = []
        parts.append(code[:1])
        parts.append(code[1:3])
        parts.append(code[3:])
        code = '-'.join(parts)
    return code

def extract_part_numbers(text):
    """Extrae números de parte con coincidencias exactas de códigos completos"""
    part_sh_numbers = defaultdict(list)
    text_upper = text.upper()

    # Extraer todos los SH presentes en esta página
    sh_matches = re.findall(r'SH\d{5,}', text_upper)
    sh_list = list(set(sh_matches)) if sh_matches else ["Unknown"]

    # Buscar cada código exacto en el texto
    for code in PART_DESCRIPTIONS:
        code_pattern = re.compile(r'\b' + re.escape(code) + r'\b', re.IGNORECASE)
        if code_pattern.search(text_upper):
            for sh in sh_list:
                part_sh_numbers[code].append(sh)
    
    return part_sh_numbers

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
    seen = set()
    order = []
    for p in build_pages:
        oid = p["order_id"]
        if oid and oid not in seen:
            seen.add(oid)
            order.append(oid)
    return order

def group_by_order(pages, classify_pickup=False):
    order_map = defaultdict(lambda: {"pages": [], "pickup": False, "part_numbers": defaultdict(list)})
    for page in pages:
        oid = page.get("order_id")
        if not oid:
            continue
        order_map[oid]["pages"].append(page)
        if classify_pickup:
            text = page.get("text", "")
            if PICKUP_REGEX.search(text):
                order_map[oid]["pickup"] = True
        part_numbers = page.get("part_numbers", {})
        for part_num, sh_list in part_numbers.items():
            order_map[oid]["part_numbers"][part_num].extend(sh_list)
    return order_map

def create_detailed_codes_report(order_data):
    """Crea un informe detallado con todos los códigos, sus descripciones y SH asociados"""
    data = []
    
    for oid, order_info in order_data.items():
        for part_num, sh_list in order_info["part_numbers"].items():
            for sh in sh_list:
                data.append({
                    "Orden": oid,
                    "Código": part_num,
                    "Descripción": PART_DESCRIPTIONS.get(part_num, "Desconocida"),
                    "SH": sh
                })
    
    if not data:
        return None
    
    # Crear documento PDF
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    
    # Título
    page.insert_text((50, y), "INFORME DETALLADO DE CÓDIGOS Y SH ASOCIADOS", 
                    fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30
    
    # Organizar datos por código
    df = pd.DataFrame(data)
    grouped = df.groupby(['Código', 'Descripción'])['SH'].apply(list).reset_index()
    
    for _, row in grouped.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
        
        # Código y descripción
        page.insert_text((50, y), f"{row['Código']} - {row['Descripción']}", 
                        fontsize=12, fontname="helv")
        y += 20
        
        # SH asociados
        sh_text = ", ".join(sorted(set(row['SH'])))  # Eliminar duplicados y ordenar
        page.insert_text((60, y), f"SH: {sh_text}", fontsize=10)
        y += 30
    
    return doc

def display_interactive_codes_table(order_data):
    """Muestra una tabla interactiva con todos los códigos y SH asociados"""
    data = []
    
    for oid, order_info in order_data.items():
        for part_num, sh_list in order_info["part_numbers"].items():
            for sh in sh_list:
                data.append({
                    "Orden": oid,
                    "Código": part_num,
                    "Descripción": PART_DESCRIPTIONS.get(part_num, "Desconocida"),
                    "SH": sh
                })
    
    if not data:
        st.warning("No se encontraron códigos con SH asociados")
        return
    
    df = pd.DataFrame(data)
    
    st.subheader("Informe Detallado de Códigos y SH Asociados")
    
    # Mostrar tabla interactiva
    st.dataframe(
        df.sort_values(by=["Código", "SH"]),
        height=600,
        use_container_width=True,
        column_config={
            "Descripción": st.column_config.TextColumn(width="large")
        }
    )
    
    # Opción para descargar como CSV
    csv = df.to_csv(index=False, encoding='utf-8')
    st.download_button(
        "Descargar como CSV",
        data=csv,
        file_name='informe_codigos_sh.csv',
        mime='text/csv'
    )

def merge_documents(build_order, build_map, ship_map, order_meta, pickup_flag):
    doc = fitz.open()
    pickups = [oid for oid in build_order if order_meta[oid]["pickup"]] if pickup_flag else []

    # Insertar informe detallado de códigos al inicio
    codes_report = create_detailed_codes_report(order_meta)
    if codes_report:
        doc.insert_pdf(codes_report)
        insert_divider_page(doc, "Documentos Principales")

    if pickup_flag and pickups:
        insert_divider_page(doc, "Órdenes de Customer Pickup")
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
st.title("Tequila - Procesador de PDFs")

# Upload de archivos
col1, col2 = st.columns(2)
with col1:
    build_file = st.file_uploader("Subir Build Sheets PDF", type="pdf")
with col2:
    ship_file = st.file_uploader("Subir Shipment Pick Lists PDF", type="pdf")

pickup_flag = st.checkbox("Incluir resumen de Customer Pickup", value=True)

if build_file and ship_file:
    # Procesar archivos
    build_bytes = build_file.read()
    ship_bytes = ship_file.read()

    build_pages = parse_pdf(build_bytes)
    ship_pages = parse_pdf(ship_bytes)

    # Combinar y procesar todas las páginas
    all_pages = build_pages + ship_pages
    order_data = group_by_order(all_pages, classify_pickup=pickup_flag)

    # Mostrar informe interactivo
    display_interactive_codes_table(order_data)

    # Generar PDF combinado
    if st.button("Generar PDF Combinado"):
        build_map = group_by_order(build_pages)
        ship_map = group_by_order(ship_pages)
        build_order = get_build_order_list(build_pages)

        # Generar resúmenes
        summary = create_summary_page(order_data, build_map.keys(), ship_map.keys(), pickup_flag)
        merged = merge_documents(build_order, build_map, ship_map, order_data, pickup_flag)

        # Insertar resumen al inicio
        if summary:
            merged.insert_pdf(summary, start_at=0)

        # Botón de descarga
        st.download_button(
            "Descargar PDF Combinado",
            data=merged.tobytes(),
            file_name="Tequila_Informe_Completo.pdf",
            mime="application/pdf"
        )
