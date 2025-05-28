import fitz # PyMuPDF
import re
import pandas as pd
from collections import defaultdict
import streamlit as st

# === Expresiones regulares ===
ORDER_REGEX = re.compile(r'\b(SO-|USS|SOC|AMZ)-?(\d+)\b')
SHIPMENT_REGEX = re.compile(r'\b(SH\d{5,})\b')
PICKUP_REGEX = re.compile(r'Customer\s*Pickup|Cust\s*Pickup|CUSTPICKUP', re.IGNORECASE)
QUANTITY_REGEX = re.compile(r'(\d+)\s*(?:EA|PCS|PC|Each)', re.IGNORECASE)
SHIPPING_2DAY_REGEX = re.compile(r'Shipping\s*Method:\s*2\s*day', re.IGNORECASE)

# === Definición CORRECTA y COMPLETA de partes (diccionario) ===
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
    'B-UGB8-EP': '2020 Carry Stand Bag - Black',

    # --- CÓDIGOS DE LAS IMÁGENES ---
    # image_fbd711.png (Golf Balls)
    'GB-DOZ-XTREME': 'Xtreme Golf Ball - Dozen',
    'GB-DOZ-XTTR-WHT': 'Xtreme Tour Golf Ball - White - Dozen',
    'GB-DOZ-XTTR-YEL': 'Xtreme Tour Golf Ball - Yellow - Dozen',
    'GB-DOZ-XTTRX-WHT': 'Xtreme Tour X Golf Ball - White - Dozen',

    # image_fb69b2.png y image_fbd6af.png (Hats/Caps y Gloves)
    'H-22PXG000013-BLK': 'Tall Visor - Black',
    'H-22PXG000013-WHT': 'Tall Visor - White',
    'H-22PXG000014-BLK': 'Sport Visor - Black',
    'H-22PXG000014-WHT': 'Sport Visor - White',
    'H-23PXG0000124-2-BG-OSFM': 'Dog Tag 6-Panel Snapback Cap - Black/Grey Logo - One Size',
    'H-23PXG0000124-2-BW-OSFM': 'Dog Tag 6-Panel Snapback Cap - Black/White Logo - One Size',
    'H-23PXG0000124-2-CG-OSFM': 'Dog Tag 6-Panel Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG000124-2-WG-OSFM': 'Dog Tag 6-Panel Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG000078-1-S-M': 'Tour Bush Hat - White - S/M',
    'H-23PXG000094-1-OSFM-BLK': 'Faceted Front Trucker Cap - Black - One Size',
    'H-23PXG000094-1-OSFM-WHT': 'Faceted Front Trucker Cap - White - One Size',
    'H-23PXG000101-BW-OSFM': 'Men\'s 6-Panel High Crown Snapback Cap - Black/White Logo - One Size',
    'H-23PXG000101-NW-OSFM': 'Men\'s 6-Panel High Crown Snapback Cap - Navy/White Logo - One Size',
    'H-23PXG000101-WB-OSFM': 'Men\'s 6-Panel High Crown Snapback Cap - White/Black Logo - One Size',
    'H-23PXG000101-WG-OSFM': 'Men\'s 6-Panel High Crown Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG000123-BW-OSFM': 'Men\'s Dog Tag 6-Panel High Crown Snapback Cap - Black/White Logo - One Size',
    'H-23PXG000123-GB-OSFM': 'Men\'s Dog Tag 6-Panel High Crown Snapback Cap - Grey/Black Logo - One Size',
    'H-23PXG000123-WG-OSFM': 'Men\'s Dog Tag 6-Panel High Crown Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG000125-BG-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - Black/Grey Logo - One Size',
    'H-23PXG000125-BW-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - Black/White Logo - One Size',
    'H-23PXG000125-GB-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - Grey/Black Logo - One Size',
    'H-23PXG000125-NW-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - Navy/White Logo - One Size',
    'H-23PXG000125-WG-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG000126-WN-OSFM': 'Stretch Snapback Hat - White - One Size',
    'H-23PXG000166-BLK-OSFM': 'Stretch Snapback Hat - Black - One Size',
    'H-23PXG000166-WHT-OSFM': 'Stretch Snapback Hat - White - One Size',
    'H-23PXG000167-BW-OSFM': 'Scottsdale Trucker Snapback Hat - Black/White Logo - One Size',
    'H-23PXG000167-GB-OSFM': 'Scottsdale Trucker Snapback Hat - Grey/Black Logo - One Size',
    'H-23PXG000167-WHT-OSFM': 'Scottsdale Trucker Snapback Hat - White - One Size',
    'H-23PXG000167-WW-OSFM': 'Scottsdale Trucker Snapback Hat - White/White Logo - One Size',
    'H-23PXG000168-BLK-OSFM': 'Stretch Patch Snapback Hat - Black - One Size',
    'H-23PXG000168-GRY-OSFM': 'Stretch Patch Snapback Hat - Grey - One Size',
    'H-23PXG000168-NVY-OSFM': 'Stretch Patch Snapback Hat - Navy - One Size',
    'H-23PXG000168-WHT-OSFM': 'Stretch Patch Snapback Hat - White - One Size',
    'H-24PXG000203-2-BLK-OSFM': 'Women\'s Metallic Minimalist - Unstructured Hat - Black - One Size',
    'H-24PXG000203-2-WHT-OSFM': 'Women\'s Metallic Minimalist - Unstructured Hat - White - One Size',
    'H-24PXG000214-1-BLK-OSFM': 'Camper Flat Bill Snapback Cap - Black - One Size',
    'H-24PXG000214-1-WHT-OSFM': 'Camper Flat Bill Snapback Cap - White - One Size',
    'H-24PXG000218-1-OSFM': '6 Panel Structured Low Crown Snapback Cap - Black - One Size',
    'H-24PXG000219-OSFM': 'Women\'s Metallic Minimalist - Unstructured Hat - Grey - One Size',
    'H-24PXG000229-OSFM': 'US Navy Structured Hat Snapback - One Size',
    'H-24PXG000235-BW-OSFM': 'Dog Tag 6-Panel Low Crown Snapback - Black/White Logo - One Size',
    'H-24PXG000235-GB-OSFM': 'Dog Tag 6-Panel Low Crown Snapback - Grey/Black Logo - One Size',
    'H-24PXG000235-WG-OSFM': 'Dog Tag 6-Panel Low Crown Snapback - White/Grey Logo - One Size',
    'H-24PXG000239-OSFM': 'Women\'s Metallic Minimalist - Unstructured Hat - Light Blue - One Size',
    'H-24PXG000276-OSFM': '2025 Stars & Stripes Low Crown Cap - One Size',
    'H-24PXG000277-OSFM': '2025 Stars & Stripes Dog Tag Cap - One Size',
    'H-24PXG000278-OSFM': '2025 Stars & Stripes High Crown Cap - One Size',
    'H-24PXG000282-OSFM': '2025 Stars & Stripes Trucker Cap - One Size',
    'H-25PXG000283-OSFM': '2025 Stars & Stripes Dog Tag Trucker - One Size',
    'H-USMC-ADJ': 'PXG USMC Unstructured Hat - Adjustable',

    # image_fbd658.png (Accessories)
    'HC-JT-4623': 'Tour Series Blade Headcover - Black',
    'A-UAC18-FM': 'PXG Wedge Brush - Chrome',
    'A-UAC17-FM': 'PXG Wedge Brush - Black',
    'A-ALIGNSTICKS-WHT': 'PXG Player Alignment Sticks - White',
    'A-NX10SLOPE-PXG': 'PXG NX10 Rangefinder Slope Edition - White',
    'A-UAC28-FM': 'PXG Milled Divot Tool (Weighted)',
    'A-IHC62918PXG-COP': 'PXG Magnetic Ball Marker & Cap Clip - Rose Gold',
    'A-IHC62920PXG-BLK': 'PXG Magnetic Ball Marker & Cap Clip - Black',
    'A-DUO-PXG': 'PXG Golf Speaker - White',
    'A-ICU55715PXG-ALS': 'PXG Deluxe Alignment Stick Cover',
    'A-DARKNESS-COASTER': 'PXG Darkness Coaster',
    'HC-JT-1053-KIT': 'PXG 2022 Iron Cover Kit',
    'A-UAC29-FM': 'PXG (DRKNSS) Divot Tool',
    'A-Q25240-ASM': 'Milled Starburst Ball Marker',
    'A-ZNP53374-1': 'Darkness Leather Wrapped Divot Tool',
    'A-JT-4697': 'Darkness Alignment Stick Cover - Black',
    'A-1IBM65819PXGCAT': 'Copper Cactus Ball Marker',
    'A-Q23192-ASM-2': 'Chrome Logo Ball Marker',
    'A-Q25645-ASM-1': '2025 Stars & Stripes Ball Marker',
    'A-1IBM65820PXG-DT': '2023 Darkness Dog Tag Ball Marker',

    # Guantes (de image_fbd6af.png, sección de abajo)
    'G4-65201011HML-BLK': 'Men\'s LH Players Glove - Black ML',
    'G4-65201019HML-BLK': 'Men\'s LH Players Glove - Black M',
    'G4-65201019HMW-BLK': 'Women\'s RH Players Glove - Black M',
    'G4-65201019LHL-BLK': 'Men\'s RH Players Glove - Black L',
    'G4-65201019LXL-BLK': 'Men\'s RH Players Glove - Black XL',
    'G4-65201019MLC-BLK': 'Men\'s RH Players Glove - Cadet Black M',
    'G4-65201019RSC-BLK': 'Men\'s RH Players Glove - Cadet Black S',
    'G4-65201019RLC-BLK': 'Men\'s RH Players Glove - Cadet Black L',
    'G4-65201019RMLC-BLK': 'Men\'s RH Players Glove - Cadet Black ML',
    'G4-65201019RXLC-BLK': 'Men\'s RH Players Glove - Cadet Black XL',
    'G4-65201019RXL-BLK': 'Men\'s RH Players Glove - Black XL',
    'G4-65201019L-BLK': 'Men\'s RH Players Glove - Black L',
    'G4-65201019HMW-WHT': 'Women\'s RH Players Glove - White M',
    'G4-65201019LHL-WHT': 'Men\'s RH Players Glove - White L',
    'G4-65201019RSC-WHT': 'Men\'s RH Players Glove - Cadet White S',
    'G4-65201019RMLC-WHT': 'Men\'s RH Players Glove - Cadet White ML',
    'G4-65201019RXLC-WHT': 'Men\'s RH Players Glove - Cadet White XL',
    'G4-65201019RLC-WHT': 'Men\'s RH Players Glove - Cadet White L',
    'G4-65201019RXL-WHT': 'Men\'s RH Players Glove - White XL',
    'G4-65201019RL-WHT': 'Men\'s RH Players Glove - White L',
    'G4-65201019LL-WHT': 'Men\'s LH Players Glove - White L',
    'G4-652021019L-WHT': 'Women\'s LH Players Glove - White L',
    'G4-652021019MW-WHT': 'Women\'s RH Players Glove - White M',
    'G4-652021019RX-WHT': 'Women\'s RH Players Glove - White XL',
    'G4-652021019S-WHT': 'Women\'s RH Players Glove - White S',
    'G4-652021019SC-WHT': 'Men\'s RH Players Glove - Cadet White S',
    'G4-652021019MLC-WHT': 'Men\'s RH Players Glove - Cadet White M',
}

# === Funciones auxiliares ===
def extract_identifiers(text):
    order_match = ORDER_REGEX.search(text)
    shipment_match = SHIPMENT_REGEX.search(text)
    order_id = f"{order_match.group(1).rstrip('-')}-{order_match.group(2)}" if order_match else None
    shipment_id = shipment_match.group(1) if shipment_match else None
    return order_id, shipment_id

def extract_part_numbers(text):
    """
    Extrae números de parte del texto.
    Retorna un diccionario con los números de parte encontrados y su conteo.
    Prioriza las coincidencias más largas para evitar que subcadenas se cuenten
    como números de parte separados si son parte de uno más largo.
    """
    part_counts = defaultdict(int)
    text_upper = text.upper()

    # Ordenar las claves por longitud de forma descendente para priorizar las coincidencias más largas
    all_part_keys_sorted = sorted(PART_DESCRIPTIONS.keys(), key=len, reverse=True)

    # Conjunto para rastrear los índices ya cubiertos por una coincidencia de un número de parte
    covered_indices = set()

    for p_key in all_part_keys_sorted:
        # Usar re.finditer para encontrar todas las ocurrencias del número de parte
        # Aseguramos que sea una "palabra completa" o delimitada por caracteres no alfanuméricos
        pattern = r'\b' + re.escape(p_key) + r'\b' # \b es un boundary de palabra
        
        for match in re.finditer(pattern, text_upper):
            start_idx, end_idx = match.span()

            # Verificar si esta coincidencia se superpone con un número de parte ya contado
            # (especialmente útil si la lógica de \b no es lo suficientemente estricta para todos los casos)
            is_overlap = False
            for i in range(start_idx, end_idx):
                if i in covered_indices:
                    is_overlap = True
                    break
            
            if not is_overlap:
                part_counts[p_key] += 1
                # Marcar los índices cubiertos por esta coincidencia
                for i in range(start_idx, end_idx):
                    covered_indices.add(i)
    return dict(part_counts) # Convertir a dict normal para la salida, si defaultdict no es necesario


def extract_relations(text, order_id, shipment_id):
    """Extrae relaciones entre códigos, órdenes y SH"""
    relations = []
    text_upper = text.upper()

    # Iterar sobre las descripciones de partes para buscar cada una
    for part_num in PART_DESCRIPTIONS:
        # Usar un patrón de palabra completa para asegurar que solo se detecten números de parte exactos
        pattern = r'\b' + re.escape(part_num) + r'\b'
        if re.search(pattern, text_upper) and order_id and shipment_id:
            relations.append({
                "Orden": order_id,
                "Código": part_num,
                "Descripción": PART_DESCRIPTIONS[part_num],
                "SH": shipment_id
            })
    return relations

def parse_pdf(pdf_bytes):
    """
    Parses a PDF file, extracts relevant information, and returns it.

    Args:
        pdf_bytes: The content of the PDF file as bytes.

    Returns:
        A tuple containing:
        - A list of dictionaries, where each dictionary represents a page and contains
          the extracted information (order_id, shipment_id, part_numbers, text).
        - A list of relations (dictionaries) between order_id, part_num, description, and shipment_id.
        - A set of shipment IDs with "2 day" shipping.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_pages_data = []
    all_relations = []
    two_day_sh_list = set() # This will accumulate SH IDs that have "2 day" shipping

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        order_id, shipment_id = extract_identifiers(text)
        part_numbers = extract_part_numbers(text)

        if shipment_id and SHIPPING_2DAY_REGEX.search(text):
            two_day_sh_list.add(shipment_id)

        page_data = {
            "number": page_num,
            "order_id": order_id,
            "shipment_id": shipment_id,
            "part_numbers": part_numbers,
            "text": text,
            "parent": doc,
        }
        all_pages_data.append(page_data)

        if order_id and shipment_id:
            page_relations = extract_relations(text, order_id, shipment_id)
            all_relations.extend(page_relations)

    return all_pages_data, all_relations, two_day_sh_list

def create_relations_table(relations):
    """
    Crea una tabla PDF con cada código en una línea separada,
    excluyendo pelotas, gorras, guantes y otros accesorios de la lista principal.
    """
    filtered_relations = [
        rel for rel in relations
        if classify_item(rel["Código"], rel["Descripción"]) == "Otros"
    ]

    if not filtered_relations:
        print("Información: No se encontraron relaciones de 'Otros' productos para mostrar en la tabla principal.")
        return None

    df = pd.DataFrame(filtered_relations)
    df = df.sort_values(by=['Orden', 'Código']).reset_index(drop=True)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50

    title = "RELACIÓN ÓRDENES - CÓDIGOS - SH (Excluyendo Pelotas, Gorras, Guantes y Accesorios)"
    page.insert_text((50, y), title, fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30

    headers = ["Orden", "Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
    page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
    y += 20

    current_order = None
    for _, row in df.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
            page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
            page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
            page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
            y += 20

        order = row['Orden']

        if order != current_order:
            if current_order is not None:
                y += 10
            page.insert_text((50, y), order, fontsize=10, fontname="helv", color=(0,0,0.5))
            current_order = order
            y += 5
        page.insert_text((150, y), row['Código'], fontsize=10)

        description = row['Descripción']
        max_desc_len_pdf = 30
        if len(description) > max_desc_len_pdf:
            page.insert_text((300, y), description[:max_desc_len_pdf] + "...", fontsize=9)
        else:
            page.insert_text((300, y), description, fontsize=10)

        page.insert_text((500, y), row['SH'], fontsize=10)

        y += 15
    return doc

def create_2day_shipping_page(two_day_sh_list):
    """Crea una página con la lista de SH con método 2 day"""
    if not two_day_sh_list:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72

    page.insert_text((72, y), "ÓRDENES CON SHIPPING METHOD: 2 DAY",
                     fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30

    for sh in sorted(list(two_day_sh_list)):
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 72
        page.insert_text((72, y), sh, fontsize=12)
        y += 20

    page.insert_text((72, y + 20), f"Total de órdenes 2 day: {len(two_day_sh_list)}",
                     fontsize=14, color=(0, 0, 1))

    return doc

def display_interactive_table(relations, global_appearances):
    """
    Muestra una tabla interactiva de relaciones en Streamlit,
    incluyendo el número de orden, código, descripción, SH y apariciones totales del código.
    """
    if not relations:
        st.info("No se encontraron relaciones para mostrar en la tabla interactiva.")
        return

    data_for_df = []
    for rel in relations:
        augmented_rel = rel.copy()
        augmented_rel["Apariciones"] = global_appearances.get(rel["Código"], 0)
        data_for_df.append(augmented_rel)

    df = pd.DataFrame(data_for_df)

    column_order = ["Orden", "Código", "Descripción", "SH", "Apariciones"]
    df_columns = [col for col in column_order if col in df.columns]
    df = df[df_columns]

    st.subheader("Tabla Interactiva: Órdenes, Códigos, SH y Apariciones Totales")

    st.dataframe(df)

def filter_relations_by_category(relations, category):
    """Filtra las relaciones por categoría."""
    return [rel for rel in relations if classify_item(rel["Código"], rel["Descripción"]) == category]

def display_category_table(relations, category):
    """Muestra una tabla interactiva para una categoría específica."""
    filtered_relations = filter_relations_by_category(relations, category)
    if filtered_relations:
        st.subheader(f"Tabla Interactiva de {category}")
        df = pd.DataFrame(filtered_relations)
        display_columns = ["Orden", "Código", "Descripción", "SH"]
        df_display = df[[col for col in display_columns if col in df.columns]]
        st.dataframe(df_display)
    else:
        st.info(f"No se encontraron relaciones de {category} para mostrar.")

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

        for part_num, qty_from_page in page.get("part_numbers", {}).items():
            order_map[oid]["part_numbers"][part_num] += qty_from_page
    return order_map

def create_part_numbers_summary(order_data, category_filter=None):
    """
    Crea una tabla PDF con el resumen de apariciones de números de parte,
    opcionalmente filtrado por categoría.
    """
    part_appearances_total = defaultdict(int)

    for oid, data in order_data.items():
        part_numbers_in_order = data.get("part_numbers", {})
        for part_num, count_in_order in part_numbers_in_order.items():
            if part_num in PART_DESCRIPTIONS:
                if category_filter is None or classify_item(part_num, PART_DESCRIPTIONS[part_num]) == category_filter:
                    part_appearances_total[part_num] += count_in_order

    if not part_appearances_total:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    y_coordinate = 72
    left_margin_code = 50
    left_margin_desc = 150
    left_margin_count = 500

    summary_title_text = f"RESUMEN DE APARICIONES: {category_filter.upper() if category_filter else 'GENERAL'}"
    page.insert_text((left_margin_code, y_coordinate - 30), summary_title_text, fontsize=16, color=(0, 0, 1), fontname="helv")

    headers = ["Código", "Descripción", "Apariciones"]
    page.insert_text((left_margin_code, y_coordinate), headers[0], fontsize=12, fontname="helv")
    page.insert_text((left_margin_desc, y_coordinate), headers[1], fontsize=12, fontname="helv")
    page.insert_text((left_margin_count, y_coordinate), headers[2], fontsize=12, fontname="helv")
    y_coordinate += 25

    sorted_parts = sorted(part_appearances_total.items())

    for part_num, count in sorted_parts:
        if count == 0:
            continue

        if y_coordinate > 750:
            page = doc.new_page(width=595, height=842)
            y_coordinate = 72
            page.insert_text((left_margin_code, y_coordinate - 30), summary_title_text, fontsize=16, color=(0, 0, 1), fontname="helv")
            page.insert_text((left_margin_code, y_coordinate), headers[0], fontsize=12, fontname="helv")
            page.insert_text((left_margin_desc, y_coordinate), headers[1], fontsize=12, fontname="helv")
            page.insert_text((left_margin_count, y_coordinate), headers[2], fontsize=12, fontname="helv")
            y_coordinate += 25

        description = PART_DESCRIPTIONS.get(part_num, "Descripción no encontrada")
        page.insert_text((left_margin_code, y_coordinate), part_num, fontsize=10)

        max_desc_len = 55
        current_y_offset = 0
        if len(description) > max_desc_len:
            parts = [description[i:i+max_desc_len] for i in range(0, len(description), max_desc_len)]
            for i, part_desc in enumerate(parts):
                page.insert_text((left_margin_desc, y_coordinate + i * 12), part_desc, fontsize=9)
            current_y_offset = (len(parts) -1) * 12
            line_height = 15 + current_y_offset
        else:
            page.insert_text((left_margin_desc, y_coordinate), description, fontsize=10)
            line_height = 15

        page.insert_text((left_margin_count, y_coordinate), str(count), fontsize=10)
        y_coordinate += line_height

    total_sum_appearances = sum(part_appearances_total.values())

    if y_coordinate > 780 - 30:
            page = doc.new_page(width=595, height=842)
            y_coordinate = 72

    y_coordinate += 20
    page.insert_text(
        (left_margin_code, y_coordinate),
        f"TOTAL APARICIONES ({category_filter if category_filter else 'GENERAL'}): {total_sum_appearances}",
        fontsize=14,
        color=(0, 0, 1),
        fontname="helv"
    )
    return doc

def insert_divider_page(doc, label):
    """Crea una página divisoria con texto de etiqueta"""
    page = doc.new_page(width=595, height=842)
    text = f"=== {label.upper()} ==="
    page.insert_text(
        point=(72, page.rect.height / 2),
        text=text,
        fontsize=18,
        fontname="helv",
        color=(0, 0, 0)
    )

def classify_item(item_code, item_description):
    """
    Clasifica un ítem en 'Pelotas', 'Gorras', 'Guantes', 'Accesorios', 'Otros'.
    """
    item_code_upper = item_code.upper()
    item_description_upper = item_description.upper()

    if item_code_upper.startswith('GB-DOZ-') or "GOLF BALL" in item_description_upper:
        return "Pelotas"
    elif item_code_upper.startswith('H-') or ("HAT" in item_description_upper or "CAP" in item_description_upper):
        return "Gorras"
    elif item_code_upper.startswith('G4-'):
        return "Guantes"
    elif item_code_upper.startswith(('A-', 'HC-')):
        return "Accesorios"
    return "Otros"

def create_category_table(relations, category_name):
    """
    Crea una tabla PDF con un listado de códigos, descripciones y SH para una categoría específica.
    """
    category_items_with_sh = []

    for rel in relations:
        if classify_item(rel["Código"], rel["Descripción"]) == category_name:
            category_items_with_sh.append({
                "Orden": rel["Orden"],
                "Código": rel["Código"],
                "Descripción": rel["Descripción"],
                "SH": rel["SH"]
            })

    if not category_items_with_sh:
        print(f"Información: No se encontraron relaciones de '{category_name}' para mostrar en la tabla PDF.")
        return None

    df_category = pd.DataFrame(category_items_with_sh)
    df_category = df_category.sort_values(by=['Orden', 'Código']).reset_index(drop=True)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    y = 50
    title = f"RELACIÓN ÓRDENES - CÓDIGOS - SH ({category_name.upper()})"
    page.insert_text((50, y), title, fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30

    headers = ["Orden", "Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
    page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
    y += 20

    current_order = None

    for _, row in df_category.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
            page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
            page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
            page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
            y += 20

        order = row['Orden']

        if order != current_order:
            if current_order is not None:
                y += 10
            page.insert_text((50, y), order, fontsize=10, fontname="helv", color=(0,0,0.5))
            current_order = order
            y += 5

        page.insert_text((150, y), row['Código'], fontsize=10)

        description = row['Descripción']
        max_desc_len_pdf = 30
        if len(description) > max_desc_len_pdf:
            page.insert_text((300, y), description[:max_desc_len_pdf] + "...", fontsize=9)
        else:
            page.insert_text((300, y), description, fontsize=10)

        page.insert_text((500, y), row['SH'], fontsize=10)
        y += 15

    return doc

# === Interfaz de Usuario Streamlit ===
st.set_page_config(layout="wide")
st.title("Procesador de PDFs de Órdenes")

st.header("Carga tus PDFs")

uploaded_file_1 = st.file_uploader("Sube el PDF 1 (ej. Build Sheet)", type="pdf", key="file_uploader_1")
uploaded_file_2 = st.file_uploader("Sube el PDF 2 (ej. Packing List)", type="pdf", key="file_uploader_2")

if uploaded_file_1 is not None and uploaded_file_2 is not None:
    st.success("Ambos PDFs cargados exitosamente. Procesando...")

    # Procesar el primer PDF
    all_pages_data_1, all_relations_1, two_day_sh_list_1 = parse_pdf(uploaded_file_1.read())

    # Procesar el segundo PDF
    all_pages_data_2, all_relations_2, two_day_sh_list_2 = parse_pdf(uploaded_file_2.read())

    # Consolidar los datos de ambos PDFs
    all_pages_data_combined = all_pages_data_1 + all_pages_data_2
    all_relations_combined = all_relations_1 + all_relations_2
    two_day_sh_list_combined = two_day_sh_list_1.union(two_day_sh_list_2) # Usar union para combinar sets

    # Agrupar datos por orden para el resumen de apariciones (ahora usando los datos combinados)
    order_data_for_summary = group_by_order(all_pages_data_combined, classify_pickup=True)

    st.subheader("Resultados del Procesamiento")

    # --- Tablas Interactivas en Streamlit ---
    st.header("Tablas Interactivas de Relaciones por Categoría")

    categories_for_display = ["Otros", "Pelotas", "Gorras", "Guantes", "Accesorios"]

    for category in categories_for_display:
        display_category_table(all_relations_combined, category) # Usar relaciones combinadas
        st.markdown("---") # Separador visual entre tablas

    # --- Generación y Descarga de PDFs ---
    st.header("Generación de Reportes PDF")
    merged_pdf_doc = fitz.open()

    # Añadir el resumen general de relaciones (excluye las categorías específicas - solo "Otros")
    pdf_relations = create_relations_table(all_relations_combined) # Usar relaciones combinadas
    if pdf_relations:
        merged_pdf_doc.insert_pdf(pdf_relations)
        insert_divider_page(merged_pdf_doc, "RELACIONES GENERALES DE PRODUCTOS (OTRAS CATEGORIAS)")

    # Añadir las tablas de listados por categoría al PDF (Pelotas, Gorras, Guantes, Accesorios)
    for category in categories_for_display:
        if category != "Otros":
            pdf_category_list = create_category_table(all_relations_combined, category) # Usar relaciones combinadas
            if pdf_category_list:
                merged_pdf_doc.insert_pdf(pdf_category_list)
                insert_divider_page(merged_pdf_doc, f"DETALLE DE {category.upper()}")

    # Añadir el resumen de SH 2-day al PDF
    pdf_2day_sh = create_2day_shipping_page(two_day_sh_list_combined) # Usar la lista combinada de 2-day SH
    if pdf_2day_sh:
        merged_pdf_doc.insert_pdf(pdf_2day_sh)
        insert_divider_page(merged_pdf_doc, "ÓRDENES 2-DAY SHIPPING")

    # Añadir el resumen de apariciones por categoría al PDF
    pdf_summary_general = create_part_numbers_summary(order_data_for_summary, category_filter=None)
    if pdf_summary_general:
        merged_pdf_doc.insert_pdf(pdf_summary_general)
        insert_divider_page(merged_pdf_doc, "RESUMEN DE APARICIONES GENERAL")

    for category in categories_for_display:
        if category != "Otros":
            pdf_summary_category = create_part_numbers_summary(order_data_for_summary, category_filter=category)
            if pdf_summary_category:
                merged_pdf_doc.insert_pdf(pdf_summary_category)
                insert_divider_page(merged_pdf_doc, f"RESUMEN DE APARICIONES {category.upper()}")

    if merged_pdf_doc.page_count > 0:
        st.download_button(
            label="Descargar Reporte PDF Completo",
            data=merged_pdf_doc.tobytes(),
            file_name="reporte_completo_ordenes.pdf",
            mime="application/pdf"
        )
    else:
        st.warning("No se generó ningún reporte PDF. Asegúrate de que los PDFs cargados contienen datos válidos.")
else:
    st.info("Por favor, sube ambos archivos PDF para iniciar el procesamiento.")
