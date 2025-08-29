# main.py
import os
import re
import asyncio
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from playwright.async_api import async_playwright

# ---------- Config ----------
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "3"))  # páginas simultâneas
DEFAULT_TIMEOUT = 45_000  # ms
USER_AGENT = os.getenv(
    "UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ALLOW_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

app = FastAPI(title="Odds API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Recursos globais
_pw = None               # Playwright
_browser = None          # Browser global
_context = None          # Contexto (cookies/UA compartilhados)
_sema = asyncio.Semaphore(MAX_CONCURRENCY)


class OddsRequest(BaseModel):
    betano: Optional[str] = None
    bet365: Optional[str] = None
    kto: Optional[str] = None
    # Mercado desejado – por padrão "9.5"
    market: str = "9.5"


def _clean_number(x: str) -> Optional[float]:
    if not x:
        return None
    x = x.strip().replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", x)
    return float(m.group(0)) if m else None


async def _block_assets(route, request):
    """Bloqueia recursos pesados para acelerar."""
    if request.resource_type in {"image", "font", "stylesheet"}:
        await route.abort()
    else:
        await route.continue_()


async def _get_html(url: str) -> str:
    """Abre a página e devolve o HTML renderizado."""
    if not url:
        return ""

    async with _sema:  # limita concorrência
        page = await _context.new_page()
        try:
            await page.route("**/*", _block_assets)
            await page.set_user_agent(USER_AGENT)
            await page.goto(url, wait_until="networkidle", timeout=DEFAULT_TIMEOUT)
            # dá um pequeno respiro para frameworks completarem o DOM
            await page.wait_for_timeout(1200)
            html = await page.content()
            return html
        finally:
            await page.close()


def _extract_over_under(html: str, market: str) -> Dict[str, Optional[float]]:
    """
    Heurística por texto:
    Procura linha contendo 'Mais de {market}' e 'Menos de {market}', capturando a odd à direita.
    Ajuste as regex se um site mudar muito o texto.
    """
    if not html:
        return {"over": None, "under": None}

    # over
    rx_over = re.compile(
        rf"(?:Mais\s*de|Over)[^<\n]{{0,50}}{re.escape(market)}[^<\n]{{0,120}}?(\d{{1,2}}[.,]\d{{1,2}}|\d+)",
        re.IGNORECASE | re.DOTALL,
    )
    # under
    rx_under = re.compile(
        rf"(?:Menos\s*de|Under)[^<\n]{{0,50}}{re.escape(market)}[^<\n]{{0,120}}?(\d{{1,2}}[.,]\d{{1,2}}|\d+)",
        re.IGNORECASE | re.DOTALL,
    )

    over = None
    under = None

    mo = rx_over.search(html)
    if mo:
        over = _clean_number(mo.group(1))

    mu = rx_under.search(html)
    if mu:
        under = _clean_number(mu.group(1))

    return {"over": over, "under": under}


async def _scrape_site(url: Optional[str], market: str) -> Dict[str, Optional[float]]:
    if not url:
        return {"over": None, "under": None, "url": None, "ok": False, "err": "empty"}
    try:
        html = await _get_html(url)
        odds = _extract_over_under(html, market)
        odds.update({"url": url, "ok": (odds["over"] is not None or odds["under"] is not None)})
        return odds
    except Exception as e:
        return {"over": None, "under": None, "url": url, "ok": False, "err": str(e)}


@app.get("/")
async def root() -> Dict[str, str]:
    return {"status": "API de odds online 🚀"}


@app.post("/odds")
async def odds(payload: OddsRequest) -> Dict[str, Any]:
    """
    POST /odds
    {
      "betano": "https://www.betano....",
      "bet365": "https://www.bet365....",
      "kto": "https://kto.bet.br/....",
      "market": "9.5"
    }
    """
    market = payload.market.strip()
    tasks = [
        _scrape_site(payload.betano, market),
        _scrape_site(payload.bet365, market),
        _scrape_site(payload.kto, market),
    ]
    betano, bet365, kto = await asyncio.gather(*tasks)
    return {"market": market, "betano": betano, "bet365": bet365, "kto": kto}


@app.on_event("startup")
async def _startup():
    global _pw, _browser, _context
    _pw = await async_playwright().start()
    _browser = await _pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    _context = await _browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=USER_AGENT,
        locale="pt-BR",
    )


@app.on_event("shutdown")
async def _shutdown():
    global _pw, _browser, _context
    try:
        if _context:
            await _context.close()
        if _browser:
            await _browser.close()
        if _pw:
            await _pw.stop()
    except Exception:
        pass
