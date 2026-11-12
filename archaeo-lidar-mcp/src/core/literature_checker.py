"""Consulta asíncrona a repositorios académicos (OpenAlex / Semantic Scholar) cruzando topónimos."""

from typing import Any, Dict, List, Optional

import httpx

from src.config import settings

ARCHAEO_KEYWORDS: List[str] = ["arqueología", "prehispánico", "pucará", "Inca"]


async def check_academic_papers(
    lat: float,
    lon: float,
    toponyms: List[str],
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """Busca publicaciones académicas en OpenAlex API cruzando topónimos locales con términos arqueológicos.

    Construye una consulta booleana combinando los topónimos provistos con las palabras clave
    (`arqueología`, `prehispánico`, `pucará`, `Inca`) y retorna los metadatos normalizados de
    los artículos encontrados.

    Args:
        lat: Latitud geográfica del candidato (WGS84).
        lon: Longitud geográfica del candidato (WGS84).
        toponyms: Lista de topónimos locales (ej. `["Quebrada de Humahuaca", "Tilcara"]`).
        http_client: Cliente `httpx.AsyncClient` opcional para inyección en tests.

    Returns:
        Lista de diccionarios con título, año, DOI, autores, relevancia y coordenadas de referencia.
    """
    cleaned_toponyms = [t.strip() for t in toponyms if t and t.strip()]
    if not cleaned_toponyms:
        cleaned_toponyms = ["Argentina", "Andes"]

    toponym_clause = " OR ".join(f'"{t}"' for t in cleaned_toponyms)
    keyword_clause = " OR ".join(ARCHAEO_KEYWORDS)
    search_query = f"({toponym_clause}) AND ({keyword_clause})"

    params = {
        "search": search_query,
        "per-page": "10",
        "select": "id,title,publication_year,doi,authorships,Relevance_score",
    }

    close_client = False
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
        close_client = True

    results: List[Dict[str, Any]] = []
    try:
        resp = await http_client.get(settings.openalex_api_url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        for work in payload.get("results", []):
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in work.get("authorships", [])
                if a.get("author", {}).get("display_name")
            ]
            results.append(
                {
                    "openalex_id": work.get("id"),
                    "title": work.get("title"),
                    "publication_year": work.get("publication_year"),
                    "doi": work.get("doi"),
                    "authors": authors,
                    "query_used": search_query,
                    "reference_coords_wgs84": {"lat": round(lat, 6), "lon": round(lon, 6)},
                }
            )
    except Exception:
        pass
    finally:
        if close_client:
            await http_client.aclose()

    return results
