# FastAPI + Playwright (assíncrono) para raspar texto renderizado das páginas
import re
from typing import Optional, Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright

app = FastAPI(title="Odds API - Escanteios")

# CORS liberado para o Streamlit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # se quiser, depois troque pelo domínio do seu app
    allow_methods=["*"],
    allow_headers=["*"],
)

# Browser global (um por processo) – eficiente p/ vários usuários
_pl = None
_browser = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

@app.on_event("startup")
async def startup():
    global _pl, _browser
    _pl = await async_playwright().start()
    # no-sandbox é essencial em cloud
    _browser = await _pl.chromium.launch(headless=True, args=["--no-sandbox"])

@app.on_event("shutdown")
async def shutdown():
    global _pl, _browser
    if _browser:
        await _browser.close()
    if _pl:
        await _pl.stop()

class ScrapeIn(BaseModel):
    betano: Optional[str] = None
    bet365: Optional[str] = None
    kto: Optional[str] = None
    timeout_ms: int = 15000  # 15s

# Util: baixa o texto renderizado (após JS) de uma URL
async def get_page_text(url: str, timeout_ms: int) -> str:
    ctx = await _browser.new_context(user_agent=UA, ignore_https_errors=True)
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # pequeníssimo delay para terminar de aparecer as odds
        await page.wait_for_timeout(3000)
        body_txt = await page.inner_text("body")
        return body_txt
    finally:
        await ctx.close()

# Util: extrai odds de escanteios do texto (heurística simples)
def parse_corners(text: str) -> Dict[str, Any]:
    # Padrões comuns em PT (ajuste se necessário)
    # Captura linhas como: "Mais de 9.5  1.72" ou "Menos de 9.5  2.05"
    linha_regex = re.compile(
        r"(Mais de|Menos de)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)"
    )

    rows = []
    for m in linha_regex.finditer(text):
        tipo, linha, odd = m.groups()
        rows.append({
            "mercado": f"{tipo} {linha}",
            "odd": odd.replace(",", "."),
        })

    # Também tenta pegar linhas "Exatamente X  7.50" (Bet365 costuma ter)
    exato_regex = re.compile(r"(Exatamente|Exactly)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)")
    for m in exato_regex.finditer(text):
        tipo, linha, odd = m.groups()
        rows.append({
            "mercado": f"Exatamente {linha}",
            "odd": odd.replace(",", "."),
        })

    return {"count": len(rows), "rows": rows}

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/scrape")
async def scrape(payload: ScrapeIn):
    out = {"betano": None, "bet365": None, "kto": None}

    if payload.betano:
        txt = await get_page_text(payload.betano, payload.timeout_ms)
        out["betano"] = parse_corners(txt)

    if payload.bet365:
        txt = await get_page_text(payload.bet365, payload.timeout_ms)
        out["bet365"] = parse_corners(txt)

    if payload.kto:
        txt = await get_page_text(payload.kto, payload.timeout_ms)
        out["kto"] = parse_corners(txt)

    return out
