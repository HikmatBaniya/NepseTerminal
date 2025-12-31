from fastapi import APIRouter, Query

from app.services.scraper import fetch_page

router = APIRouter(prefix="/scrape", tags=["scrape"])


@router.get("")
def scrape_page(
    url: str = Query(..., min_length=5),
    respect_robots: bool = Query(True),
) -> dict[str, str]:
    return fetch_page(url, respect_robots=respect_robots)