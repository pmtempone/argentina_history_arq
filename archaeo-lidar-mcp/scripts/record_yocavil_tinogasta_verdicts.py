"""Registra los dictámenes periciales VLM para los 10 candidatos de Yocavil y 10 de Tinogasta."""

import sys
from pathlib import Path

# Añadir raíz de archaeo-lidar-mcp al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.vlm_judge import record_vlm_verdict

VERDICTS = {
    # ------------------ ZONA 2: YOCAVIL ------------------
    "ARQ-YOC-0001": {
        "verdict": "NATURAL",
        "certainty_pct": 93,
        "functional_interpretation": "Lomada / espolón coluvial en Valle de Yocavil",
        "geomorphological_justification": (
            "El corte transversal A-A' sobre el centroide evidencia un domo convexo continuo de 60 m "
            "de base y +2.3 m de altura con flancos tendidos de más de 20 m de desarrollo horizontal. "
            "En el Hillshade 1.5x los bordes son difusos y no presentan alineaciones rectilíneas ni "
            "depresión interna correspondiente a kancha o recinto pircado."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0002": {
        "verdict": "NATURAL",
        "certainty_pct": 94,
        "functional_interpretation": "Filo o cresta orográfica secundaria / escarpa natural",
        "geomorphological_justification": (
            "El perfil 2D exhibe una sección triangular asimétrica con cresta aguda a +2.6 m y base de 50 m. "
            "En los paneles 1 y 2 se observa un contorno sinuoso en forma de S que sigue las curvas de nivel "
            "estructurales de la ladera, típico de afloramientos rocosos meteorizados."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0003": {
        "verdict": "NATURAL",
        "certainty_pct": 95,
        "functional_interpretation": "Espolón de ladera delimitado por cárcava de escorrentía lateral",
        "geomorphological_justification": (
            "El corte A-A' muestra a la izquierda una incisión de drenaje negativo (-0.4 m) continuada por "
            "un promontorio de 70 m de ancho culminando a +2.3 m. Morfología puramente hidrogeomorfológica "
            "de interfluvio serrano sin evidencia de muros de contención."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0004": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 96,
        "functional_interpretation": "Costura de píxel / salto de bloque de remuestreo en celda GLO-30",
        "geomorphological_justification": (
            "En el Hillshade 1.5x se evidencian marcadas líneas de costura ortogonal en la grilla ráster "
            "a lo largo de Este 3495428. El perfil transversal describe una rampa escalonada abrupta en "
            "el límite de bloque sobre un área minúscula de 34 m²."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0005": {
        "verdict": "NATURAL",
        "certainty_pct": 92,
        "functional_interpretation": "Lomada orográfica coluvial",
        "geomorphological_justification": (
            "Perfil microtopográfico convexo de 50 m de base con culminación en +2.2 m y descenso suave "
            "de 25 m de desarrollo. Refleja un espolón coluvial redondeado con reflectancia suave y "
            "transiciones continuas sin estructuras pircadas."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0006": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 93,
        "functional_interpretation": "Lóbulo de interpolación bicúbica sobre píxel aislado en GLO-30",
        "geomorphological_justification": (
            "El corte A-A' describe un domo de campana simétrica de 45 m de base y +1.45 m de altura. "
            "En el Hillshade la sombra es difusa y concéntrica, resultado característico del sobremuestreo "
            "a 2 m de una elevación puntual del modelo GLO-30."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0007": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 97,
        "functional_interpretation": "Efecto de borde perimetral del raster DTM y truncamiento de radio convolucional SLRM",
        "geomorphological_justification": (
            "La anomalía se localiza directamente en el límite septentrional del ráster (Norte 7074169). "
            "El Hillshade muestra saturación extrema en blanco/negro en la línea perimetral y el corte 2D "
            "exhibe una ondulación periódica oscilatoria generada por el cálculo de la superficie de "
            "tendencia en el borde."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0008": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 98,
        "functional_interpretation": "Efecto de borde perimetral del raster DTM en el límite septentrional",
        "geomorphological_justification": (
            "Idéntico patrón que ARQ-YOC-0007 sobre el margen norte del raster. Deformación geométrica "
            "en reloj de arena del SLRM y salto escalonado no físico en el perfil 2D."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0009": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 96,
        "functional_interpretation": "Artefacto lineal de costura de interpolación bicúbica sobre celda GLO-30",
        "geomorphological_justification": (
            "Franja lineal horizontal brillante en el panel 1 (Norte 7074136) que coincide con el límite "
            "de celda del sensor satelital. Área reducida de 41 m² sin correspondencia morfológica con pircas o andenes."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-YOC-0010": {
        "verdict": "NATURAL",
        "certainty_pct": 95,
        "functional_interpretation": "Ladera monoclinal / concavidad de drenaje natural (falso positivo por umbral)",
        "geomorphological_justification": (
            "El perfil 2D a lo largo de la traza sobre el centroide arroja valores de micro-relieve SLRM "
            "negativos (-0.8 m a -0.25 m) sin ninguna sobre-elevación positiva neta (+0.0 m de sobreelevación "
            "relativa). Es una concavidad de ladera sin rasgos antrópicos."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },

    # ------------------ ZONA 3: TINOGASTA ------------------
    "ARQ-TIN-0001": {
        "verdict": "NATURAL",
        "certainty_pct": 93,
        "functional_interpretation": "Médano fósil / montículo aluvial de bajo relieve en Valle de Abaucán",
        "geomorphological_justification": (
            "El perfil 2D sobre el centroide describe una parábola continua suave de 45 m de base con máxima "
            "sobreelevación de +0.6 m. Ausencia total de quiebres angulares de pirca, recintos ortogonales "
            "o alineamientos constructivos."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0002": {
        "verdict": "NATURAL",
        "certainty_pct": 91,
        "functional_interpretation": "Ondulación aluvial / paleocauce rellenado en llanura de Fiambalá",
        "geomorphological_justification": (
            "Morfología de domo amplio de 50 m de base y apenas +0.41 m de altura relativa. Variación "
            "de reflectancia mínima en el Hillshade 1.5x (0.70 a 0.72) compatible con depósitos aluviales cuaternarios."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0003": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 95,
        "functional_interpretation": "Borde septentrional del raster y costura de interpolación GLO-30",
        "geomorphological_justification": (
            "El panel 1 exhibe la franja de fin de datos del raster en Norte 6897450 junto con un salto "
            "vertical de grilla. El perfil 2D alcanza un pico de solo +0.24 m antes de descender bruscamente "
            "por debajo de cero en el límite espacial."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0004": {
        "verdict": "NATURAL",
        "certainty_pct": 92,
        "functional_interpretation": "Médano arenoso / montículo eólico de bajo relieve",
        "geomorphological_justification": (
            "Domo suave de simetría casi perfecta con 40 m de base y +0.45 m de culminación. Corresponde "
            "a acumulaciones arenosas típicas del bolsón árido de Tinogasta sin vestigios de recintos "
            "circulares o corrales pircados."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0005": {
        "verdict": "NATURAL",
        "certainty_pct": 93,
        "functional_interpretation": "Médano / ondulación del manto de arena eólico en Fiambalá",
        "geomorphological_justification": (
            "Relieve suave y continuo de 50 m de base con culminación de +0.45 m. Perfil parabólico sin "
            "depresiones interiores ni muros perimetrales."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0006": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 96,
        "functional_interpretation": "Costura cruciforme de remuestreo en cuadrícula de datos satelitales GLO-30",
        "geomorphological_justification": (
            "El panel 1 muestra una línea blanca vertical nítida en Este 2636030 cruzada por una discontiunidad "
            "horizontal a Norte 6896563, característica inequívoca de costura de cuadrícula ráster del modelo Copernicus original."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0007": {
        "verdict": "NATURAL",
        "certainty_pct": 92,
        "functional_interpretation": "Ondulación superficial del terreno / microrrelieve de llanura aluvial",
        "geomorphological_justification": (
            "Rango de reflectancia ínfimo (0.713 a 0.719) en Hillshade. El corte 2D muestra que en el "
            "centroide exacto la sobreelevación es de apenas +0.05 m, sin pendiente ni contención de andén."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0008": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 97,
        "functional_interpretation": "Línea de interpolación y costura de píxel de sensor satelital",
        "geomorphological_justification": (
            "Banda vertical oscura sobre Este 2635332 coincidente con la discretización de celda de "
            "Copernicus DEM. La sobreelevación en el perfil 2D nunca supera los 0.12 m, careciendo de "
            "micro-relieve positivo real."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0009": {
        "verdict": "ARTEFACTO",
        "certainty_pct": 96,
        "functional_interpretation": "Costura de cuadrícula de sensor y efecto de borde",
        "geomorphological_justification": (
            "Costura con escalón ortogonal en el cuadrante superior izquierdo del panel 1. Perfil 2D con "
            "sobre-elevación máxima de +0.13 m que desciende a valores negativos (-0.05 m) en el centroide."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
    "ARQ-TIN-0010": {
        "verdict": "NATURAL",
        "certainty_pct": 92,
        "functional_interpretation": "Médano arenoso / montículo eólico menor",
        "geomorphological_justification": (
            "Domo suave y asimétrico de 45 m de base y +0.36 m de altura. Gradiente continuo sin presencia "
            "de paramentos de piedra ni estructuras arquitectónicas."
        ),
        "field_inspection_recommended": False,
        "backend": "mcp_host:ArchaeoSeniorCONICET",
    },
}

def main() -> None:
    print(f"⚖️  Registrando {len(VERDICTS)} dictámenes periciales VLM...")
    results = []
    for cand_id, verdict_data in VERDICTS.items():
        res = record_vlm_verdict(cand_id, verdict_data)
        print(f"   ✔ {cand_id}: {res['verdict']} (descartado={res['discarded']}) -> {res['dossier_path']}")
        results.append(res)
    print(f"\n✅ Total registrados exitosamente: {len(results)}")

if __name__ == "__main__":
    main()
