# main.py
# API simples para extrair odds de escanteios (Mais de / Menos de) em 3 casas
# via Playwright. Pensada para rodar no Render (ou localmente).

from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import re
import asyncio

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

app = FastAPI(title="Odds API", version="1.0")

# ---------- Modelos ----------

class OddsRequest(BaseModel):
    betano: Optional[str] = Field(None, description="URL do jogo na Betano")
    bet365: Optional[str] = Field(None, description="URL do jogo na Bet365")
    kto: Optional[str]    = Field(None, description="URL do jogo na KTO")
    market: str = Field(..., description='Mercado em formato "9.5", "8.5", etc.')


# ---------- Utils ----------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

PLAYWRIGHT_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]

# aborta recursos pesados para ficar mais rápido/leve
ABORT_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}


def _to_float(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    s = s.strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_over_under(text: str, market: str) -> Dict[str, Optional[float]]:
    """
    Puxa 'Mais de {market}' e 'Menos de {market}' por regex sobre o texto da página.
    Funciona em PT-BR e também tenta 'Over/Under'.
    Retorna {'over': float|None, 'under': float|None}.
    """
    # Normaliza espaços múltiplos
    text = re.sub(r"[ \t]+", " ", text)

    # Padrões tolerantes: pegamos o primeiro número decimal logo após a frase alvo
    # Exemplos que casa:
    #   "Mais de 9.5   1.72"
    #   "Menos de 9.5  2.05"
    #   "Over 9.5 1.80"
    #   "Under 9.5 2.00"
    pat_over = re.compile(
        rf"(?:Mais\s*de|Over)\s*{re.escape(market)}[^\d]*?(\d+(?:[.,]\d+)?)",
        flags=re.IGNORECASE,
    )
    pat_under = re.compile(
        rf"(?:Menos\s*de|Under)\s*{re.escape(market)}[^\d]*?(\d+(?:[.,]\d+)?)",
        flags=re.IGNORECASE,
    )

    m_over = pat_over.search(text)
    m_under = pat_under.search(text)

    over = _to_float(m_over.group(1)) if m_over else None
    under = _to_float(m_under.group(1)) if m_under else None
    return {"over": over, "under": under}


async def fetch_text_with_playwright(url: str, timeout_ms: int = 30000) -> str:
    """
    Abre a URL com Playwright, bloqueia recursos pesados, seta user-agent no contexto
    e devolve o texto (innerText) do body.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=PLAYWRIGHT_LAUNCH_ARGS)
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1366, "height": 900})

        # corta recursos para acelerar
        async def route_handler(route):
            if route.request.resource_type in ABORT_RESOURCE_TYPES:
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", route_handler)

        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # dá um respiro para scripts popularem o DOM
            await page.wait_for_timeout(1500)
            # como algumas casas renderizam muito via JS, às vezes é bom tentar networkidle
            # mas isso pode travar em sites com polling infinito:
            # await page.wait_for_load_state("networkidle", timeout=timeout_ms)

            # pega o texto visível
            text = await page.evaluate("() => document.body.innerText || ''")
            return text or ""
        finally:
            await context.close()
            await browser.close()


async def scrape_one(url: Optional[str], market: str) -> Dict[str, Any]:
    """
    Faz a raspagem de UMA casa.
    Retorno padrão:
      {
        "ok": True/False,
        "url": "...",
        "over": float|None,
        "under": float|None,
        "err": "mensagem se falhou"
      }
    """
    if not url:
        return {"ok": False, "url": None, "over": None, "under": None, "err": "URL ausente"}

    try:
        text = await fetch_text_with_playwright(url)
        parsed = parse_over_under(text, market)
        ok = parsed["over"] is not None or parsed["under"] is not None
        return {
            "ok": ok,
            "url": url,
            "over": parsed["over"],
            "under": parsed["under"],
            "err": None if ok else "Não encontrei odds no texto da página"
        }
    except PlaywrightTimeoutError:
        return {"ok": False, "url": url, "over": None, "under": None, "err": "Timeout carregando a página"}
    except Exception as e:
        return {"ok": False, "url": url, "over": None, "under": None, "err": str(e)}


# ---------- Rotas ----------

@app.get("/")
async def root():
    return {"status": "API de odds online 🚀"}


@app.post("/odds")
async def odds(req: OddsRequest):
    """
    Body esperado:
    {
      "betano": "https://www.betano.bet.br/...",
      "bet365": "https://www.bet365.bet.br/#/IP/...",
      "kto": "https://kto.bet.br/esportes-ao-vivo/...",
      "market": "9.5"
    }
    """
    tasks = [
        scrape_one(req.betano, req.market),
        scrape_one(req.bet365, req.market),
        scrape_one(req.kto,    req.market),
    ]
    results = await asyncio.gather(*tasks)

    return {
        "market": req.market,
        "betano": results[0],
        "bet365": results[1],
        "kto":    results[2],
    }


# ---------- Execução local ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
