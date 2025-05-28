import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from collections import defaultdict

# === Expresiones regulares ===
ORDER_REGEX = re.compile(r'\b(SO-|USS|SOC|AMZ)-?(\d+)\b')
SHIPMENT_REGEX = re.compile(r'\b(SH\d{5,})\b')
PICKUP_REGEX = re.compile(r'Customer\s*Pickup|Cust\s*Pickup|CUSTPICKUP', re.IGNORECASE)
QUANTITY_REGEX = re.compile(r'(\d+)\s*(?:EA|PCS|PC|Each)', re.IGNORECASE)
SHIPPING_2DAY_REGEX = re.compile(r'Shipping\s*Method:\s*2\s*day', re.IGNORECASE)


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
    Prioritiza las coincidencias más largas y asegura que un número de parte más corto
    no se cuente si es parte de un número de parte más largo identificado
    en la misma posición.
    Retorna un diccionario con los números de parte encontrados como claves y valor 1.
    """
    part_counts = {}
    text_upper = text.upper()
    all_part_keys = list(PART_DESCRIPTIONS.keys())
    
    # Buscar coincidencias exactas definidas en PART_DESCRIPTIONS
    for p_short in all_part_keys:
        pattern_short = r'(?<!\w)' + re.escape(p_short) + r'(?!\w)'
        found_standalone_match_for_p_short = False
        for match_short in re.finditer(pattern_short, text_upper):
            match_short_start_index = match_short.start()
            is_this_match_shadowed_by_a_longer_one = False
            for p_long in all_part_keys:
                if len(p_long) > len(p_short) and \
                   p_short == p_long[:len(p_short)] and \
                   text_upper.startswith(p_long, match_short_start_index):
                    end_of_p_long_index = match_short_start_index + len(p_long)
                    is_p_long_standalone_here = False
                    if end_of_p_long_index == len(text_upper):
                        is_p_long_standalone_here = True
                    else:
                        char_after_p_long = text_upper[end_of_p_long_index]
                        if not re.match(r'\w', char_after_p_long):
                            is_p_long_standalone_here = True
                    if is_p_long_standalone_here:
                        is_this_match_shadowed_by_a_longer_one = True
                        break
            if not is_this_match_shadowed_by_a_longer_one:
                found_standalone_match_for_p_short = True
                break
        if found_standalone_match_for_p_short:
            part_counts[p_short] = 1

    # === BÚSQUEDA ADICIONAL PARA GUANTES QUE COMIENZAN CON G4-6520 ===
    glove_pattern = r'(G4-6520[^\s\-]*)'
    for match in re.finditer(glove_pattern, text_upper, re.IGNORECASE):
        full_glove_code = match.group(1)
        if full_glove_code in PART_DESCRIPTIONS:
             part_counts[full_glove_code] = 1
        
    return part_counts

def extract_relations(text, order_id, shipment_id):
    """Extrae relaciones entre códigos, órdenes y SH"""
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

     # Búsqueda adicional para guantes G4-6520...
    glove_pattern = r'(G4-6520\S*)'
    for match in re.finditer(glove_pattern, text_upper):
        full_glove_code = match.group(1)
        if full_glove_code in PART_DESCRIPTIONS:
            relations.append({
                "Orden": order_id,
                "Código": full_glove_code,
                "Descripción": PART_DESCRIPTIONS[full_glove_code],
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
    two_day_sh_list = set()

    all_shipping_methods = []

for page_num in range(len(doc)):
    page = doc.load_page(page_num)
    text = page.get_text("text")
    order_id, shipment_id = extract_identifiers(text)
    part_numbers = extract_part_numbers(text)
    
    # Detectar Shipping Method
    shipping_methods = extract_shipping_methods(text)
    for method in shipping_methods:
        all_shipping_methods.append({
            "Orden": order_id,
            "SH": shipment_id,
            "Método de Envío": method
        })

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
    'H-23PXG0000124-2-WG-OSFM': 'Dog Tag 6-Panel Snapback Cap - White/Grey Logo - One Size', # Duplicado, mantener si es diferente
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
    'H-23PXG000126-WN-OSFM': 'Stretch Snapback Hat - White - One Size', # Este es de image_fbd6af.png, lo he ajustado
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

   # Guantes adicionales (de image_fbd6af.png, sección de abajo)
'G4-652011019LHL-BLK': 'Men\'s LH Players Glove - Black L',
'G4-652011019LHLC-BLK': 'Men\'s LH Players Glove - Cadet Black L',
'G4-652011019LHLW-BLK': 'Men\'s LH Players Glove - White L',
'G4-652011019LHM-BLK': 'Men\'s LH Players Glove - Black M',
'G4-652011019LHMC-BLK': 'Men\'s LH Players Glove - Cadet Black M',
'G4-652011019LHML-BLK': 'Men\'s LH Players Glove - Black ML',
'G4-652011019LHMLC-BLK': 'Men\'s LH Players Glove - Cadet Black ML',
'G4-652011019LHMW-BLK': 'Women\'s LH Players Glove - Black M',
'G4-652011019LHS-BLK': 'Men\'s LH Players Glove - Black S',
'G4-652011019LHSC-BLK': 'Men\'s LH Players Glove - Cadet Black S',
'G4-652011019LHSW-BLK': 'Men\'s LH Players Glove - White S',
'G4-652011019LHXL-BLK': 'Men\'s LH Players Glove - Black XL',
'G4-652011019LHXLC-BLK': 'Men\'s LH Players Glove - Cadet Black XL',
'G4-652011019RHL-BLK': 'Men\'s RH Players Glove - Black L',
'G4-652011019RHLC-BLK': 'Men\'s RH Players Glove - Cadet Black L',
'G4-652011019RHM-BLK': 'Men\'s RH Players Glove - Black M',
'G4-652011019RHMC-BLK': 'Men\'s RH Players Glove - Cadet Black M',
'G4-652011019RHML-BLK': 'Men\'s RH Players Glove - Black ML',
'G4-652011019RHMLC-BLK': 'Men\'s RH Players Glove - Cadet Black ML',
'G4-652011019RHS-BLK': 'Men\'s RH Players Glove - Black S',
'G4-652011019RHSC-BLK': 'Men\'s RH Players Glove - Cadet Black S',
'G4-652011019RHXL-BLK': 'Men\'s RH Players Glove - Black XL',
'G4-652011019RHXLC-BLK': 'Men\'s RH Players Glove - Cadet Black XL',
'G4-652011019RHXXL-BLK': 'Men\'s RH Players Glove - Black XXL',
'G4-652021019LHL-WHT': 'Men\'s LH Players Glove - White L',
'G4-652021019LHLC-WHT': 'Men\'s LH Players Glove - Cadet White L',
'G4-652021019LHLW-WHT': 'Men\'s LH Players Glove - White L',
'G4-652021019LHM-WHT': 'Men\'s LH Players Glove - White M',
'G4-652021019LHMC-WHT': 'Men\'s LH Players Glove - Cadet White M',
'G4-652021019LHML-WHT': 'Men\'s LH Players Glove - White ML',
'G4-652021019LHMLC-WHT': 'Men\'s LH Players Glove - Cadet White ML',
'G4-652021019LHMW-WHT': 'Women\'s LH Players Glove - White M',
'G4-652021019LHS-WHT': 'Men\'s LH Players Glove - White S',
'G4-652021019LHSC-WHT': 'Men\'s LH Players Glove - Cadet White S',
'G4-652021019LHSW-WHT': 'Men\'s LH Players Glove - White S',
'G4-652021019LHXL-WHT': 'Men\'s LH Players Glove - White XL',
'G4-652021019LHXLC-WHT': 'Men\'s LH Players Glove - Cadet White XL',
'G4-652021019LHXXL-WHT': 'Men\'s LH Players Glove - White XXL',
'G4-652021019RHL-WHT': 'Men\'s RH Players Glove - White L',
'G4-652021019RHLC-WHT': 'Men\'s RH Players Glove - Cadet White L',
'G4-652021019RHLW-WHT': 'Men\'s RH Players Glove - White L',
'G4-652021019RHM-WHT': 'Men\'s RH Players Glove - White M',
'G4-652021019RHMC-WHT': 'Men\'s RH Players Glove - Cadet White M',
'G4-652021019RHML-WHT': 'Men\'s RH Players Glove - White ML',
'G4-652021019RHMLC-WHT': 'Men\'s RH Players Glove - Cadet White ML',
'G4-652021019RHMW-WHT': 'Women\'s RH Players Glove - White M',
'G4-652021019RHS-WHT': 'Men\'s RH Players Glove - White S',
'G4-652021019RHSC-WHT': 'Men\'s RH Players Glove - Cadet White S',
'G4-652021019RHSW-WHT': 'Men\'s RH Players Glove - White S',
'G4-652021019RHXL-WHT': 'Men\'s RH Players Glove - White XL',
'G4-652021019RHXLC-WHT': 'Men\'s RH Players Glove - Cadet White XL',
'G4-652021019RHXXL-WHT': 'Men\'s RH Players Glove - White XXL',
}

def create_relations_table(relations):
    """
    Crea una tabla PDF con cada código en una línea separada,
    excluyendo pelotas, gorras y accesorios de la lista principal.
    """
    if not relations:
        return None
    
    # Filtrar las relaciones para incluir solo los ítems clasificados como "Otros".
    # Esto elimina pelotas, gorras y accesorios de esta tabla.
    filtered_relations = [
        rel for rel in relations
        if classify_item(rel["Código"], rel["Descripción"]) == "Otros"
    ]

    if not filtered_relations:
        st.info("No se encontraron relaciones de 'Otros' productos para mostrar en la tabla principal.")
        return None
        
    df = pd.DataFrame(filtered_relations)
    
    # Ordenar para una mejor visualización, por Orden, luego por Código.
    df = df.sort_values(by=['Orden', 'Código']).reset_index(drop=True)
    
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    
    # Título para la tabla, indicando la exclusión.
    title = "RELACIÓN ÓRDENES - CÓDIGOS - SH (Excluyendo Pelotas, Gorras y Accesorios)"
    page.insert_text((50, y), title, fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30
    
    # Encabezados de la tabla.
    headers = ["Orden", "Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
    page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
    y += 20
    
    current_order = None # Variable para detectar cambios de orden y agregar espaciado.
    
    for _, row in df.iterrows():
        # Si la página está llena, crea una nueva página y reinserta los encabezados.
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
            page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
            page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
            page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
            y += 20
            
        order = row['Orden']
        
        # Inserta la orden si ha cambiado desde la fila anterior o es la primera fila.
        if order != current_order:
            if current_order is not None: # Agrega un espacio extra si no es la primera orden.
                y += 10
            page.insert_text((50, y), order, fontsize=10, fontname="helv", color=(0,0,0.5)) # Orden en color diferente.
            current_order = order
            y += 5 # Pequeño espacio después de la orden.

        # Inserta el código, descripción y SH en la misma línea.
        page.insert_text((150, y), row['Código'], fontsize=10)
        page.insert_text((300, y), row['Descripción'], fontsize=10)
        page.insert_text((500, y), row['SH'], fontsize=10)
        
        y += 15 # Espacio para la siguiente línea.
            
    return doc

# === Nueva función para crear página de SH 2 day ===
def create_2day_shipping_page(two_day_sh_list):
    """Crea una página con la lista de SH con método 2 day"""
    if not two_day_sh_list:
        return None
    
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    
    # Título
    page.insert_text((72, y), "ÓRDENES CON SHIPPING METHOD: 2 DAY",
                     fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30
    
    # Lista de SH
    for sh in sorted(two_day_sh_list):
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 72
        page.insert_text((72, y), sh, fontsize=12)
        y += 20
    
    page.insert_text((72, y + 20), f"Total de órdenes 2 day: {len(two_day_sh_list)}",
                     fontsize=14, color=(0, 0, 1))
    
    return doc

def display_interactive_table(relations):
    """
    Muestra una tabla interactiva de relaciones en Streamlit.
    """
    if not relations:
        st.info("No se encontraron relaciones para mostrar en la tabla interactiva.")
        return

    df = pd.DataFrame(relations)

    st.subheader("Tabla Interactiva de Relaciones (Órdenes, Códigos, SH)")
    
    # Using st.dataframe for a simple interactive table
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
        st.dataframe(df)
    else:
        st.info(f"No se encontraron relaciones de {category} para mostrar.")

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


def create_part_numbers_summary(order_data, category_filter=None): # ADDED category_filter=None
    """
    Crea una tabla PDF con el resumen de apariciones de números de parte,
    opcionalmente filtrado por categoría.
    """
    part_appearances = defaultdict(int)

    for oid, data in order_data.items():
        part_numbers = data.get("part_numbers", {})
        for part_num, count in part_numbers.items():
            if part_num in PART_DESCRIPTIONS:
                # Aplicar el filtro de categoría si se proporciona
                if category_filter is None or classify_item(part_num, PART_DESCRIPTIONS[part_num]) == category_filter:
                    part_appearances[part_num] += count

    if not part_appearances:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    y_coordinate = 72
    left_margin_code = 50
    left_margin_desc = 150
    left_margin_count = 450

    # Título dinámico basado en el filtro de categoría
    # Changed title to reflect the category filter
    summary_title = f"RESUMEN DE APARICIONES DE PARTES: {category_filter.upper() if category_filter else 'GENERAL'}"
    page.insert_text((left_margin_code, y_coordinate - 30), summary_title, fontsize=16, color=(0, 0, 1))

    headers = ["Código", "Descripción", "Apariciones"]
    page.insert_text((left_margin_code, y_coordinate), headers[0], fontsize=12)
    page.insert_text((left_margin_desc, y_coordinate), headers[1], fontsize=12)
    page.insert_text((left_margin_count, y_coordinate), headers[2], fontsize=12)
    y_coordinate += 25

    # Ordenar las partes alfabéticamente
    sorted_parts = sorted(part_appearances.items())

    for part_num, count in sorted_parts:
        if count == 0:
            continue

        if y_coordinate > 750:
            page = doc.new_page(width=595, height=842)
            y_coordinate = 72
            # Re-insert title and headers on new page
            page.insert_text((left_margin_code, y_coordinate - 30), summary_title, fontsize=16, color=(0, 0, 1))
            page.insert_text((left_margin_code, y_coordinate), headers[0], fontsize=12)
            page.insert_text((left_margin_desc, y_coordinate), headers[1], fontsize=12)
            page.insert_text((left_margin_count, y_coordinate), headers[2], fontsize=12)
            y_coordinate += 25

        description = PART_DESCRIPTIONS[part_num]

        page.insert_text((left_margin_code, y_coordinate), part_num, fontsize=10)

        # Manejo de descripciones largas
        if len(description) > 40:
            page.insert_text((left_margin_desc, y_coordinate), description[:40], fontsize=9)
            page.insert_text((left_margin_desc, y_coordinate + 12), description[40:], fontsize=9)
            line_height = 25
        else:
            page.insert_text((left_margin_desc, y_coordinate), description, fontsize=10)
            line_height = 15

        page.insert_text((left_margin_count, y_coordinate), str(count), fontsize=10)
        y_coordinate += line_height

    total_appearances = sum(part_appearances.values())
    y_coordinate += 20

    if y_coordinate > 780:
        page = doc.new_page(width=595, height=842)
        y_coordinate = 72

    # Changed total appearances label
    page.insert_text(
        (left_margin_code, y_coordinate),
        f"TOTAL DE APARICIONES ({category_filter if category_filter else 'GENERAL'}): {total_appearances}",
        fontsize=14,
        color=(0, 0, 1)
    )

    return doc
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

# --- NUEVAS FUNCIONES PARA CLASIFICAR Y GENERAR PDFs POR CATEGORÍA ---

def classify_item(item_code, item_description):
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
    unique_items_in_category = {} # Usaremos un diccionario para guardar el primer SH encontrado
    category_data = []

    for rel in relations:
        if classify_item(rel["Código"], rel["Descripción"]) == category_name:
            item_code = rel["Código"]
            item_description = rel["Descripción"]
            item_sh = rel["SH"] # Capturamos el SH

            # Si el código ya se ha añadido, no lo volvemos a añadir a unique_items_in_category
            # pero sí podemos actualizar el SH si queremos el último o el primero.
            # Por simplicidad, tomaremos el primer SH que encontremos para cada código.
            if item_code not in unique_items_in_category:
                unique_items_in_category[item_code] = {
                    "Descripción": item_description,
                    "SH": item_sh # Guardamos el SH asociado
                }

    # Construir category_data a partir del diccionario unique_items_in_category
    for code, details in unique_items_in_category.items():
        category_data.append({
            "Código": code,
            "Descripción": details["Descripción"],
            "SH": details["SH"] # Agregamos el SH aquí
        })

    if not category_data:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50

    # Título de la categoría
    page.insert_text((50, y), f"LISTADO DE {category_name.upper()}",
                     fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30

    # Encabezados - ¡Aquí es donde agregamos 'SH'!
    headers = ["Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((200, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((450, y), headers[2], fontsize=12, fontname="helv") # Ajustar posición para SH
    y += 20

    # Convertir a DataFrame para ordenar por Código
    df_category = pd.DataFrame(category_data).sort_values(by=["Código"])

    for _, row in df_category.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            # Reinsertar encabezados en nueva página
            page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
            page.insert_text((200, y), headers[1], fontsize=12, fontname="helv")
            page.insert_text((450, y), headers[2], fontsize=12, fontname="helv") # Reinsertar SH
            y += 20

        page.insert_text((50, y), row["Código"], fontsize=10)

        # Descripción en múltiples líneas si es necesario
        desc = row["Descripción"]
        if len(desc) > 50: # Ajustar el límite de caracteres para la descripción
            page.insert_text((200, y), desc[:50], fontsize=9)
            page.insert_text((200, y + 12), desc[50:], fontsize=9)
            y_offset_for_next_line = 12
        else:
            page.insert_text((200, y), desc, fontsize=10)
            y_offset_for_next_line = 0

        # Agregar el SH
        page.insert_text((450, y), row["SH"], fontsize=10) # Posición para el SH

        y += 15 + y_offset_for_next_line # Espacio entre filas, considerando la descripción multilinea

    return doc

def create_gloves_table(relations):
    """
    Crea una tabla PDF solo para guantes (códigos que empiezan con G4-).
    """
    gloves_data = [
        rel for rel in relations
        if rel["Código"].startswith("G4-")
    ]

    if not gloves_data:
        return None

    # Usamos un diccionario para evitar duplicados
    unique_gloves = {}
    for rel in gloves_data:
        code = rel["Código"]
        if code not in unique_gloves:
            unique_gloves[code] = {
                "Código": code,
                "Descripción": rel["Descripción"],
                "SH": rel["SH"]
            }

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50

    # Título
    page.insert_text((50, y), "LISTADO DE GUANTES", fontsize=16, color=(0, 0, 1))
    y += 30

    headers = ["Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12)
    page.insert_text((200, y), headers[1], fontsize=12)
    page.insert_text((450, y), headers[2], fontsize=12)
    y += 20

    df = pd.DataFrame(unique_gloves.values()).sort_values(by="Código")

    for _, row in df.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            # Reinsertar encabezados
            page.insert_text((50, y), headers[0], fontsize=12)
            page.insert_text((200, y), headers[1], fontsize=12)
            page.insert_text((450, y), headers[2], fontsize=12)
            y += 20

        page.insert_text((50, y), row["Código"], fontsize=10)
        desc = row["Descripción"]
        if len(desc) > 50:
            page.insert_text((200, y), desc[:50], fontsize=9)
            page.insert_text((200, y + 12), desc[50:], fontsize=9)
            y += 12
        else:
            page.insert_text((200, y), desc, fontsize=10)

        page.insert_text((450, y), row["SH"], fontsize=10)
        y += 15

    return doc

def create_shipping_methods_summary(shipping_methods_data):
    """
    Crea una tabla PDF con un resumen de métodos de envío y sus apariciones.
    """
    if not shipping_methods_data:
        return None

    from collections import Counter
    method_counts = Counter()

    for entry in shipping_methods_data:
        method = entry["Método de Envío"]
        method_counts[method] += 1

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72

    # Título
    page.insert_text((50, y), "RESUMEN DE MÉTODOS DE ENVÍO", fontsize=16, color=(0, 0, 1))
    y += 30

    headers = ["Método de Envío", "Cantidad"]
    page.insert_text((50, y), headers[0], fontsize=12)
    page.insert_text((450, y), headers[1], fontsize=12)
    y += 20

    for method, count in sorted(method_counts.items()):
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 72
            page.insert_text((50, y), headers[0], fontsize=12)
            page.insert_text((450, y), headers[1], fontsize=12)
            y += 20

        page.insert_text((50, y), method, fontsize=10)
        page.insert_text((450, y), str(count), fontsize=10)
        y += 15

    total_methods = sum(method_counts.values())
    y += 20
    if y > 750:
        page = doc.new_page(width=595, height=842)
        y = 72
    page.insert_text((50, y), f"Total de métodos de envío encontrados: {total_methods}", fontsize=12, color=(0, 0, 1))

    return doc


# 6. Insertar página de SH 2 day
two_day_page = create_2day_shipping_page(all_two_day)
if two_day_page:
    doc.insert_pdf(two_day_page)
    insert_divider_page(doc, "Listado de Pelotas por Relación")


# 7. Detectar métodos de envío desde build_pages + ship_pages
all_shipping_methods = []

for page in original_pages:
    text = page["text"]
    order_id = page["order_id"]
    shipment_id = page["shipment_id"]

    methods_found = extract_shipping_methods(text)
    for method in methods_found:
        all_shipping_methods.append({
            "Orden": order_id,
            "SH": shipment_id,
            "Método de Envío": method
        })


# 8. Mostrar tabla interactiva de métodos de envío
st.subheader("Tabla Interactiva: Métodos de Envío")
if all_shipping_methods:
    df_shipping = pd.DataFrame(all_shipping_methods)
    st.dataframe(df_shipping.groupby("Método de Envío").size().reset_index(name='Cantidad').sort_values(by='Cantidad', ascending=False))
else:
    st.info("No se encontraron métodos de envío.")


# 9. Insertar resumen de métodos de envío en PDF
shipping_methods_summary = create_shipping_methods_summary(all_shipping_methods)
if shipping_methods_summary:
    doc.insert_pdf(shipping_methods_summary)
    insert_divider_page(doc, "Resumen de Métodos de Envío")

def merge_documents(build_order, build_map, ship_map, order_meta, pickup_flag, all_relations, all_two_day):
    doc = fitz.open()
    pickups = [oid for oid in build_order if order_meta[oid]["pickup"]] if pickup_flag else []

    # 1. Insertar tabla de relaciones (excluyendo categorías específicas)
    relations_table = create_relations_table(all_relations)
    if relations_table:
        doc.insert_pdf(relations_table)
        insert_divider_page(doc, "Resumen de Apariciones por Categoría")  # Separador para las nuevas secciones

    # --- NUEVA SECCIÓN: Resumen de Apariciones por Categoría ---
    # 2. Resumen de Apariciones: Bolsas (Otros)
    summary_bags = create_part_numbers_summary(order_meta, category_filter="Otros")
    if summary_bags:
        doc.insert_pdf(summary_bags)

    # 3. Resumen de Apariciones: Pelotas
    summary_balls = create_part_numbers_summary(order_meta, category_filter="Pelotas")
    if summary_balls:
        doc.insert_pdf(summary_balls)

    # 4. Resumen de Apariciones: Gorras
    summary_hats = create_part_numbers_summary(order_meta, category_filter="Gorras")
    if summary_hats:
        doc.insert_pdf(summary_hats)

    # 5. Resumen de Apariciones: Accesorios
    summary_accessories = create_part_numbers_summary(all_relations, category_filter="Accesorios")
    if summary_accessories:
        doc.insert_pdf(summary_accessories)

    # 5.5 Resumen de Apariciones: Guantes
    summary_gloves = create_part_numbers_summary(all_relations, category_filter="Guantes")
    if summary_gloves:
        doc.insert_pdf(summary_gloves)
        insert_divider_page(doc, "Listado de Pelotas por Relación")

    # 6. Insertar página de SH 2 day
    two_day_page = create_2day_shipping_page(all_two_day)
    if two_day_page:
        doc.insert_pdf(two_day_page)
        insert_divider_page(doc, "Listado de Pelotas por Relación")  # Separador

    # 7. Insertar página de Pelotas (listado de relaciones, no de apariciones)
    pelotas_doc = create_category_table(all_relations, "Pelotas")
    if pelotas_doc:
        doc.insert_pdf(pelotas_doc)
        insert_divider_page(doc, "Listado de Gorras por Relación")  # Separador para la siguiente categoría

    # 8. Insertar página de Gorras (listado de relaciones)
    gorras_doc = create_category_table(all_relations, "Gorras")
    if gorras_doc:
        doc.insert_pdf(gorras_doc)
        insert_divider_page(doc, "Listado de Accesorios por Relación")  # Separador para la siguiente categoría

    # 8.5 Insertar página de Guantes (listado de relaciones)
    gloves_doc = create_gloves_table(all_relations)
    if gloves_doc:
        doc.insert_pdf(gloves_doc)
        insert_divider_page(doc, "Listado de Accesorios por Relación")

    # 9. Insertar página de Accesorios (listado de relaciones)
    accesorios_doc = create_category_table(all_relations, "Accesorios")
    if accesorios_doc:
        doc.insert_pdf(accesorios_doc)
        insert_divider_page(doc, "Documentos Principales")  # Separador antes de los docs originales

    # === FUNCIÓN INTERNA: Insertar páginas de órdenes ===
    def insert_order_pages(order_list):
        for oid in order_list:
            # Insertar build pages
            for p in build_map.get(oid, {}).get("pages", []):
                src_page = p["parent"][p["number"]]
                doc.insert_pdf(p["parent"], from_page=p["number"], to_page=p["number"])

            # Insertar ship pages
            for p in ship_map.get(oid, {}).get("pages", []):
                src_page = p["parent"][p["number"]]
                doc.insert_pdf(p["parent"], from_page=p["number"], to_page=p["number"])

    # Insertar pickups primero si está habilitado
    if pickup_flag and pickups:
        insert_divider_page(doc, "Customer Pickup Orders")
        insert_order_pages(pickups)

    # Insertar otras órdenes
    others = [oid for oid in build_order if oid not in pickups]
    if others:
        insert_divider_page(doc, "Other Orders")
        insert_order_pages(others)

    return doc

def extract_shipping_methods(text):
    """
    Extrae los métodos de envío del texto del PDF.
    Retorna una lista con todos los métodos encontrados.
    """
    shipping_methods = []
    shipping_method_regex = re.compile(r'Shipping\s*Method:\s*(.+)', re.IGNORECASE)

    for match in shipping_method_regex.finditer(text):
        method = match.group(1).strip()
        if method:
            shipping_methods.append(method)

    # También buscamos palabras clave como "PICKUP", "NO SHIPMENT", etc.
    pickup_match = PICKUP_REGEX.search(text)
    if pickup_match:
        shipping_methods.append("PICKUP")

    # Si hay órdenes sin método claro de envío, podemos marcarlas como "NO DEFINIDO"
    if not shipping_method_regex.search(text) and not pickup_match:
        shipping_methods.append("NO DEFINIDO")

    return shipping_methods


def display_shipping_methods_table(shipping_methods_data):
    if not shipping_methods_data:
        st.info("No se encontraron métodos de envío.")
        return

    st.subheader("Tabla Interactiva: Métodos de Envío")
    df = pd.DataFrame(shipping_methods_data)
    st.dataframe(df.groupby("Método de Envío").size().reset_index(name='Cantidad').sort_values(by='Cantidad', ascending=False))

# === Interfaz de Streamlit ===
st.title("Tequila Build/Shipment PDF Processor")

build_file = st.file_uploader("Upload Build Sheets PDF", type="pdf")
ship_file = st.file_uploader("Upload Shipment Pick Lists PDF", type="pdf")
pickup_flag = st.checkbox("Summarize Customer Pickup orders", value=True)

if build_file and ship_file:
    build_bytes = build_file.read()
    ship_bytes = ship_file.read()

    # Procesar ambos PDFs
    build_pages, build_relations, build_two_day = parse_pdf(build_bytes)
    ship_pages, ship_relations, ship_two_day = parse_pdf(ship_bytes)

    # Combinar todo
    original_pages = build_pages + ship_pages
    all_relations = build_relations + ship_relations
    all_two_day = build_two_day.union(ship_two_day)
    all_shipping_methods = build_shipping_methods + ship_shipping_methods  # Nueva línea
    all_meta = group_by_order(original_pages, classify_pickup=pickup_flag)

    st.subheader("Tablas Interactivas de Datos") # This is fine, it's a Streamlit command

    # Mostrar la tabla principal de Relaciones (Órdenes, Códigos, SH)
    display_interactive_table(all_relations)

    # Mostrar tablas interactivas por categoría
    display_category_table(all_relations, "Pelotas")
    display_category_table(all_relations, "Gorras")
    display_category_table(all_relations, "Guantes")
    display_category_table(all_relations, "Accesorios")

    st.subheader("Resumen de Órdenes y Envíos") # This is fine, it's a Streamlit command

    # Mostrar SH con método 2 day
    if all_two_day:
        st.subheader("Órdenes con Shipping Method: 2 day")
        st.write(", ".join(sorted(all_two_day)))
    else:
        st.warning("No se encontraron órdenes con Shipping Method: 2 day")

    # Botón para generar y descargar el PDF consolidado
    if st.button("Generate Merged Output"):
        # Asegúrate de que estas variables se calculen correctamente
        # antes de pasarlas a merge_documents
        build_map = group_by_order(build_pages)
        ship_map = group_by_order(ship_pages)
        build_order = get_build_order_list(build_pages)

        # Generar resúmenes
        summary = create_summary_page(all_meta, build_map.keys(), ship_map.keys(), pickup_flag)
        merged = merge_documents(build_order, build_map, ship_map, all_meta, pickup_flag, all_relations, all_two_day)

        # Insertar resumen al inicio
        if summary:
            merged.insert_pdf(summary, start_at=0)

        # Botón de descarga
        st.download_button(
            "Download Merged Output PDF",
            data=merged.tobytes(),
            file_name="Tequila_Merged_Output.pdf"
        )
elif build_file or ship_file:
    st.info("Por favor, sube AMBOS PDFs (Build Sheets y Shipment Pick Lists) para procesar.")
else:
    st.info("Sube tus archivos PDF para comenzar el procesamiento y ver las tablas.")
