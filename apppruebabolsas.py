import fitz # PyMuPDF
import re
import pandas as pd
from collections import defaultdict
import streamlit as st # Asegúrate de que Streamlit esté importado

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
    
    # Usamos las claves originales del diccionario PART_DESCRIPTIONS
    # para determinar qué números de parte estamos buscando.
    all_part_keys = list(PART_DESCRIPTIONS.keys())

    for p_short in all_part_keys:
        # Patrón para encontrar p_short como una "palabra completa"
        # (considerando que '-' no es parte de \w)
        pattern_short = r'(?<!\w)' + re.escape(p_short) + r'(?!\w)'
        found_standalone_match_for_p_short = False
        
        # Iteramos sobre todas las posibles coincidencias de p_short en el texto
        for match_short in re.finditer(pattern_short, text_upper):
            match_short_start_index = match_short.start()
            is_this_match_shadowed_by_a_longer_one = False
            
            # Verificamos si esta coincidencia específica de p_short está "opacada"
            # por un número de parte más largo (p_long) que también es válido y 
            # comienza en la misma posición.
            for p_long in all_part_keys:
                if len(p_long) > len(p_short) and \
                   p_short == p_long[:len(p_short)] and \
                   text_upper.startswith(p_long, match_short_start_index):
                    
                    # p_short es un prefijo de p_long, y p_long aparece en el texto
                    # comenzando en la misma posición que p_short.
                    # Ahora, verificamos si este p_long es una "palabra completa" válida aquí.
                    # (es decir, si p_long no está seguido por un carácter de palabra \w)
                    
                    end_of_p_long_index = match_short_start_index + len(p_long)
                    is_p_long_standalone_here = False
                    if end_of_p_long_index == len(text_upper): # p_long está al final del texto
                        is_p_long_standalone_here = True
                    else:
                        char_after_p_long = text_upper[end_of_p_long_index]
                        # Si el carácter después de p_long NO es un carácter de palabra (\w)
                        if not re.match(r'\w', char_after_p_long):
                            is_p_long_standalone_here = True
                    
                    if is_p_long_standalone_here:
                        is_this_match_shadowed_by_a_longer_one = True
                        break # Esta coincidencia de p_short está opacada, no necesitamos verificar más p_longs.
            
            if not is_this_match_shadowed_by_a_longer_one:
                # Esta ocurrencia de p_short es independiente (no forma parte de un p_long en esta posición).
                found_standalone_match_for_p_short = True
                break # Hemos encontrado una instancia válida de p_short, así que debe incluirse en los resultados.
        
        if found_standalone_match_for_p_short:
            part_counts[p_short] = 1
            
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

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        order_id, shipment_id = extract_identifiers(text)
        part_numbers = extract_part_numbers(text) # PART_DESCRIPTIONS debe estar definido globalmente

        if shipment_id and SHIPPING_2DAY_REGEX.search(text):
            two_day_sh_list.add(shipment_id)

        page_data = {
            "number": page_num,
            "order_id": order_id,
            "shipment_id": shipment_id,
            "part_numbers": part_numbers,
            "text": text,
            "parent": doc,  # Add the document object
        }
        all_pages_data.append(page_data)

        # Extract relations for this page
        if order_id and shipment_id:
            page_relations = extract_relations(text, order_id, shipment_id) # PART_DESCRIPTIONS debe estar definido
            all_relations.extend(page_relations)

    return all_pages_data, all_relations, two_day_sh_list

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
    # Estos ahora serán categorizados como "Guantes"
    'G4-65201011HML-BLK': 'Men\'s LH Players Glove - Black ML',
    'G4-65201019HML-BLK': 'Men\'s LH Players Glove - Black M', # Asumo que era M y no ML como el anterior con mismo código base
    'G4-65201019HMW-BLK': 'Women\'s RH Players Glove - Black M', # Asumo que este es RH (Right Hand) basado en el patrón
    'G4-65201019LHL-BLK': 'Men\'s RH Players Glove - Black L', # RH
    'G4-65201019LXL-BLK': 'Men\'s RH Players Glove - Black XL', # RH
    'G4-65201019MLC-BLK': 'Men\'s RH Players Glove - Cadet Black M', # RH Cadet
    'G4-65201019RSC-BLK': 'Men\'s RH Players Glove - Cadet Black S', # RH Cadet S (asumo RSC es RH Small Cadet)
    'G4-65201019RLC-BLK': 'Men\'s RH Players Glove - Cadet Black L', # RH Cadet L
    'G4-65201019RMLC-BLK': 'Men\'s RH Players Glove - Cadet Black ML', # RH Cadet ML
    'G4-65201019RXLC-BLK': 'Men\'s RH Players Glove - Cadet Black XL',# RH Cadet XL
    'G4-65201019RXL-BLK': 'Men\'s RH Players Glove - Black XL', # RH XL
    'G4-65201019L-BLK': 'Men\'s RH Players Glove - Black L', # RH L (Duplicado aparente de G4-65201019LHL-BLK si 'LHL' y 'L' significan lo mismo aquí)
    'G4-65201019HMW-WHT': 'Women\'s RH Players Glove - White M', # RH
    'G4-65201019LHL-WHT': 'Men\'s RH Players Glove - White L', # RH
    'G4-65201019RSC-WHT': 'Men\'s RH Players Glove - Cadet White S', # RH Cadet S
    'G4-65201019RMLC-WHT': 'Men\'s RH Players Glove - Cadet White ML',# RH Cadet ML
    'G4-65201019RXLC-WHT': 'Men\'s RH Players Glove - Cadet White XL',# RH Cadet XL
    'G4-65201019RLC-WHT': 'Men\'s RH Players Glove - Cadet White L', # RH Cadet L
    'G4-65201019RXL-WHT': 'Men\'s RH Players Glove - White XL', # RH XL
    'G4-65201019RL-WHT': 'Men\'s RH Players Glove - White L', # RH L (podría ser igual a LHL-WHT)
    'G4-65201019LL-WHT': 'Men\'s LH Players Glove - White L', # LH
    'G4-652021019L-WHT': 'Women\'s LH Players Glove - White L', # LH Women
    'G4-652021019MW-WHT': 'Women\'s RH Players Glove - White M', # RH Women
    'G4-652021019RX-WHT': 'Women\'s RH Players Glove - White XL',# RH Women
    'G4-652021019S-WHT': 'Women\'s RH Players Glove - White S',  # RH Women
    'G4-652021019SC-WHT': 'Men\'s RH Players Glove - Cadet White S', # RH Cadet S (Posiblemente duplicado/conflicto con G4-65201019RSC-WHT si SC es solo Small Cadet)
    'G4-652021019MLC-WHT': 'Men\'s RH Players Glove - Cadet White M', # RH Cadet M (Posiblemente duplicado/conflicto con G4-65201019RMLC-WHT)

    # === INICIO DE NUEVOS GUANTES SOLICITADOS ===
    # Ya están arriba los G4-
    # === FIN DE NUEVOS GUANTES SOLICITADOS ===
}

def create_relations_table(relations):
    """
    Crea una tabla PDF con cada código en una línea separada,
    excluyendo pelotas, gorras, guantes y otros accesorios de la lista principal.
    """
    if not relations:
        return None
    
    # Filtrar las relaciones para incluir solo los ítems clasificados como "Otros".
    # Esto elimina pelotas, gorras, guantes y accesorios de esta tabla.
    filtered_relations = [
        rel for rel in relations
        if classify_item(rel["Código"], rel["Descripción"]) == "Otros"
    ]

    if not filtered_relations:
        print("Información: No se encontraron relaciones de 'Otros' productos para mostrar en la tabla principal.")
        return None
        
    df = pd.DataFrame(filtered_relations)
    
    # Ordenar para una mejor visualización, por Orden, luego por Código.
    df = df.sort_values(by=['Orden', 'Código']).reset_index(drop=True)
    
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    
    # Título para la tabla, indicando la exclusión.
    title = "RELACIÓN ÓRDENES - CÓDIGOS - SH (Excluyendo Pelotas, Gorras, Guantes y Accesorios)"
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
        
        # Manejo de descripciones largas para la tabla PDF
        description = row['Descripción']
        max_desc_len_pdf = 30 # Ajusta según sea necesario para el espacio en el PDF
        if len(description) > max_desc_len_pdf:
            page.insert_text((300, y), description[:max_desc_len_pdf] + "...", fontsize=9)
        else:
            page.insert_text((300, y), description, fontsize=10)

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
    for sh in sorted(list(two_day_sh_list)): # Convert set to list before sorting
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 72
        page.insert_text((72, y), sh, fontsize=12)
        y += 20
    
    page.insert_text((72, y + 20), f"Total de órdenes 2 day: {len(two_day_sh_list)}",
                     fontsize=14, color=(0, 0, 1))
    
    return doc

# MODIFICADA para incluir "Apariciones"
def display_interactive_table(relations, global_appearances):
    """
    Muestra una tabla interactiva de relaciones en Streamlit,
    incluyendo el número de orden, código, descripción, SH y apariciones totales del código.
    """
    if not relations:
        st.info("No se encontraron relaciones para mostrar en la tabla interactiva.")
        return

    # Augment relations with total appearances
    data_for_df = []
    for rel in relations:
        augmented_rel = rel.copy()
        # global_appearances es un dict {part_code: total_count}
        augmented_rel["Apariciones"] = global_appearances.get(rel["Código"], 0)
        data_for_df.append(augmented_rel)

    df = pd.DataFrame(data_for_df)
    
    # Reordenar columnas para el formato deseado: Orden, Código, Descripción, SH, Apariciones
    column_order = ["Orden", "Código", "Descripción", "SH", "Apariciones"]
    # Asegurarse de que todas las columnas existen antes de reordenar
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
        # Seleccionar y reordenar columnas si es necesario para estas tablas también
        display_columns = ["Orden", "Código", "Descripción", "SH"]
        df_display = df[[col for col in display_columns if col in df.columns]]
        st.dataframe(df_display)
    else:
        st.info(f"No se encontraron relaciones de {category} para mostrar.")

def create_summary_page(order_data, build_keys, shipment_keys, pickup_flag):
    all_orders = set(build_keys) | set(shipment_keys)
    unmatched_build = set(build_keys) - set(shipment_keys)
    unmatched_ship = set(shipment_keys) - set(build_keys)
    pickup_orders = [oid for oid in all_orders if order_data.get(oid, {}).get("pickup", False)] if pickup_flag else []


    lines = [
        "Tequila Order Summary", # Placeholder, as original context might be different
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
        
        # page.get("part_numbers", {}) es un dict {part_num: 1} de extract_part_numbers
        # qty aquí es 1 (por aparición en página)
        for part_num, qty_from_page in page.get("part_numbers", {}).items():
            order_map[oid]["part_numbers"][part_num] += qty_from_page
    return order_map


def create_part_numbers_summary(order_data, category_filter=None): # ADDED category_filter=None
    """
    Crea una tabla PDF con el resumen de apariciones de números de parte,
    opcionalmente filtrado por categoría.
    order_data es el resultado de group_by_order.
    """
    part_appearances_total = defaultdict(int)

    for oid, data in order_data.items():
        # data["part_numbers"] es {part_num: count_for_this_order}, 
        # donde count_for_this_order es el número de páginas en esa orden donde apareció la parte.
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
    left_margin_desc = 150 # Ajustado para dar más espacio
    left_margin_count = 500 # Ajustado para la derecha

    summary_title = f"RESUMEN DE APARICIONES: {category_filter.upper() if category_filter else 'GENERAL'}"
    page.insert_text((left_margin_code, y_coordinate - 30), summary_title, fontsize=16, color=(0, 0, 1), fontname="helv")

    headers = ["Código", "Descripción", "Apariciones"]
    page.insert_text((left_margin_code, y_coordinate), headers[0], fontsize=12, fontname="helv")
    page.insert_text((left_margin_desc, y_coordinate), headers[1], fontsize=12, fontname="helv")
    page.insert_text((left_margin_count, y_coordinate), headers[2], fontsize=12, fontname="helv")
    y_coordinate += 25

    sorted_parts = sorted(part_appearances_total.items())

    for part_num, count in sorted_parts:
        if count == 0:
            continue

        if y_coordinate > 750: # Check before inserting text
            page = doc.new_page(width=595, height=842)
            y_coordinate = 72
            page.insert_text((left_margin_code, y_coordinate - 30), summary_title, fontsize=16, color=(0, 0, 1), fontname="helv")
            page.insert_text((left_margin_code, y_coordinate), headers[0], fontsize=12, fontname="helv")
            page.insert_text((left_margin_desc, y_coordinate), headers[1], fontsize=12, fontname="helv")
            page.insert_text((left_margin_count, y_coordinate), headers[2], fontsize=12, fontname="helv")
            y_coordinate += 25

        description = PART_DESCRIPTIONS.get(part_num, "Descripción no encontrada")
        page.insert_text((left_margin_code, y_coordinate), part_num, fontsize=10)

        # Manejo de descripciones largas
        max_desc_len = 55 # Ajustar según el espacio disponible
        current_y_offset = 0
        if len(description) > max_desc_len:
            # Dividir descripción y mostrar en múltiples líneas si es necesario
            parts = [description[i:i+max_desc_len] for i in range(0, len(description), max_desc_len)]
            for i, part_desc in enumerate(parts):
                page.insert_text((left_margin_desc, y_coordinate + i * 12), part_desc, fontsize=9)
            current_y_offset = (len(parts) -1) * 12
            line_height = 15 + current_y_offset # Altura base + líneas adicionales
        else:
            page.insert_text((left_margin_desc, y_coordinate), description, fontsize=10)
            line_height = 15
            
        page.insert_text((left_margin_count, y_coordinate), str(count), fontsize=10)
        y_coordinate += line_height


    total_sum_appearances = sum(part_appearances_total.values()) # Renombrado para evitar confusión con 'count'
    
    if y_coordinate > 780 - 30: # Asegurar espacio para el total
            page = doc.new_page(width=595, height=842)
            y_coordinate = 72

    y_coordinate += 20 # Espacio antes del total
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
    page = doc.new_page(width=595, height=842) # Especificar tamaño
    text = f"=== {label.upper()} ==="
    page.insert_text(
        point=(72, page.rect.height / 2), # Centrado verticalmente, margen izquierdo
        text=text,
        fontsize=18,
        fontname="helv",
        color=(0, 0, 0)
    )

# --- NUEVAS FUNCIONES PARA CLASIFICAR Y GENERAR PDFs POR CATEGORÍA ---

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
    elif item_code_upper.startswith('G4-'): # Nueva categoría para GUANTES
        return "Guantes"
    elif item_code_upper.startswith(('A-', 'HC-')): # Otros accesorios (excluyendo guantes)
        return "Accesorios"
    return "Otros" # Para ítems que no encajan en ninguna categoría definida (ej. Bolsas)


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
    page = doc.new_page(width=595, height=842) # A4 size

    y = 50
    # Título de la tabla de categoría
    title = f"RELACIÓN ÓRDENES - CÓDIGOS - SH ({category_name.upper()})"
    page.insert_text((50, y), title, fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30

    # Encabezados de la tabla
    headers = ["Orden", "Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
    page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
    y += 20

    current_order = None

    for _, row in df_category.iterrows():
        if y > 750: # Si la página está llena, crea una nueva página
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
                y += 10 # Espacio extra entre órdenes
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
        y += 15 # Espacio para la siguiente línea

    return doc

def merge_documents(build_order, build_map, ship_map, order_meta, pickup_flag, all_relations, all_two_day_sh): # Renombrado all_two_day
    doc = fitz.open()
    # pickups = [oid for oid in build_order if order_meta[oid]["pickup"]] if pickup_flag else [] # order_meta might not have all build_order keys

    # 0. Summary Page (si se usa create_summary_page y se pasan los parámetros correctos)
    # Por ejemplo:
    # build_keys = set(build_map.keys())
    # ship_keys = set(ship_map.keys()) # Asumiendo que ship_map tiene una estructura similar a build_map (keys son order_ids)
    # summary_doc = create_summary_page(order_meta, build_keys, ship_keys, pickup_flag)
    # if summary_doc:
    #     doc.insert_pdf(summary_doc)
    #     insert_divider_page(doc, "Detalles")


    # 1. Insertar tabla de relaciones (excluyendo categorías específicas - 'Otros')
    relations_table_doc = create_relations_table(all_relations) # Renombrado para claridad
    if relations_table_doc:
        doc.insert_pdf(relations_table_doc)
    
    insert_divider_page(doc, "Resúmenes de Apariciones por Categoría")

    # 2. Resúmenes de Apariciones por Categoría
    categories_for_summary = ["Otros", "Pelotas", "Gorras", "Accesorios"] # Define el orden
    for category in categories_for_summary:
        summary_cat_doc = create_part_numbers_summary(order_meta, category_filter=category)
        if summary_cat_doc:
            doc.insert_pdf(summary_cat_doc)

    insert_divider_page(doc, "Listados de Items por Categoría")
    
    # 3. Listados de Items por Categoría (Código, Descripción, SH)
    for category in categories_for_summary: # Mismo orden que los resúmenes
        category_list_doc = create_category_table(all_relations, category)
        if category_list_doc:
            doc.insert_pdf(category_list_doc)
            
    # 4. Página de envíos "2 day"
    if all_two_day_sh: # Check if the set is not empty
        two_day_shipping_doc = create_2day_shipping_page(all_two_day_sh)
        if two_day_shipping_doc:
            insert_divider_page(doc, "Envíos Urgentes")
            doc.insert_pdf(two_day_shipping_doc)
    
    # Aquí iría la lógica original de merge_documents para las páginas de build y ship si fuera necesaria.
    # Esta parte está omitida ya que el enfoque es en las tablas y resúmenes.
    # for oid in build_order:
    # ... (lógica original de adjuntar páginas de PDF)

    return doc

# === Interfaz de Usuario Streamlit ===
st.set_page_config(layout="wide")
st.title("Procesador de PDFs de Órdenes")

uploaded_file = st.file_uploader("Sube un PDF", type="pdf")

if uploaded_file is not None:
    pdf_bytes = uploaded_file.read()
    all_pages_data, all_relations, two_day_sh_list = parse_pdf(pdf_bytes)

    # Agrupar datos por orden para el resumen de apariciones
    order_data_for_summary = group_by_order(all_pages_data, classify_pickup=True)

    st.success("PDF procesado exitosamente!")

    # --- Tablas Interactivas en Streamlit ---
    st.header("Tablas Interactivas")

    # Tabla para "Otros" (Bolsas, etc.) - lo que no es Pelotas, Gorras, Guantes, Accesorios
    display_category_table(all_relations, "Otros")
    st.markdown("---")

    # Tabla para Pelotas
    display_category_table(all_relations, "Pelotas")
    st.markdown("---")

    # Tabla para Gorras
    display_category_table(all_relations, "Gorras")
    st.markdown("---")

    # ¡NUEVA! Tabla para Guantes
    display_category_table(all_relations, "Guantes")
    st.markdown("---")

    # Tabla para Accesorios (sin Guantes ahora)
    display_category_table(all_relations, "Accesorios")
    st.markdown("---")

    # Puedes seguir mostrando la tabla interactiva general si la necesitas
    # all_part_appearances = defaultdict(int)
    # for oid, data in order_data_for_summary.items():
    #     for part_num, count_in_order in data.get("part_numbers", {}).items():
    #         all_part_appearances[part_num] += count_in_order
    # display_interactive_table(all_relations, all_part_appearances)


    # --- Generación y Descarga de PDFs ---
    st.header("Generación de Reportes PDF")
    merged_pdf_doc = fitz.open()

    # Añadir el resumen general de relaciones (excluye las categorías específicas)
    pdf_relations = create_relations_table(all_relations)
    if pdf_relations:
        merged_pdf_doc.insert_pdf(pdf_relations)
        insert_divider_page(merged_pdf_doc, "Resumen General de Productos") # Divisor

    # Añadir la tabla de Pelotas al PDF
    pdf_pelotas = create_category_table(all_relations, "Pelotas")
    if pdf_pelotas:
        merged_pdf_doc.insert_pdf(pdf_pelotas)
        insert_divider_page(merged_pdf_doc, "Detalle de Pelotas") # Divisor

    # Añadir la tabla de Gorras al PDF
    pdf_gorras = create_category_table(all_relations, "Gorras")
    if pdf_gorras:
        merged_pdf_doc.insert_pdf(pdf_gorras)
        insert_divider_page(merged_pdf_doc, "Detalle de Gorras") # Divisor

    # ¡NUEVA! Añadir la tabla de Guantes al PDF
    pdf_guantes = create_category_table(all_relations, "Guantes")
    if pdf_guantes:
        merged_pdf_doc.insert_pdf(pdf_guantes)
        insert_divider_page(merged_pdf_doc, "Detalle de Guantes") # Divisor

    # Añadir la tabla de Accesorios (sin Guantes) al PDF
    pdf_accesorios = create_category_table(all_relations, "Accesorios")
    if pdf_accesorios:
        merged_pdf_doc.insert_pdf(pdf_accesorios)
        insert_divider_page(merged_pdf_doc, "Detalle de Accesorios") # Divisor

    # Añadir el resumen de SH 2-day al PDF
    pdf_2day_sh = create_2day_shipping_page(two_day_sh_list)
    if pdf_2day_sh:
        merged_pdf_doc.insert_pdf(pdf_2day_sh)
        insert_divider_page(merged_pdf_doc, "Órdenes 2-Day Shipping") # Divisor

    # Añadir el resumen de apariciones por categoría al PDF
    # Primero, para la categoría general
    pdf_summary_general = create_part_numbers_summary(order_data_for_summary)
    if pdf_summary_general:
        merged_pdf_doc.insert_pdf(pdf_summary_general)
        insert_divider_page(merged_pdf_doc, "Resumen de Apariciones General") # Divisor

    # Resumen de apariciones para Guantes
    pdf_summary_guantes = create_part_numbers_summary(order_data_for_summary, category_filter="Guantes")
    if pdf_summary_guantes:
        merged_pdf_doc.insert_pdf(pdf_summary_guantes)
        insert_divider_page(merged_pdf_doc, "Resumen de Apariciones Guantes") # Divisor

    # Resumen de apariciones para Accesorios
    pdf_summary_accesorios = create_part_numbers_summary(order_data_for_summary, category_filter="Accesorios")
    if pdf_summary_accesorios:
        merged_pdf_doc.insert_pdf(pdf_summary_accesorios)
        insert_divider_page(merged_pdf_doc, "Resumen de Apariciones Accesorios") # Divisor


    if merged_pdf_doc.page_count > 0:
        st.download_button(
            label="Descargar Reporte PDF Completo",
            data=merged_pdf_doc.tobytes(),
            file_name="reporte_completo_ordenes.pdf",
            mime="application/pdf"
        )
    else:
        st.warning("No se generó ningún reporte PDF. Asegúrate de que el PDF contiene datos válidos.")
