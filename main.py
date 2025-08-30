from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Optional, Dict
from playwright.sync_api import sync_playwright

app = FastAPI(title="Odds API (Playwright)")

class Payload(BaseModel):
    market: str
    betano: str
    bet365: str
    kto: str

def scrape_text(url: str, timeout_ms: int = 15000) -> Dict[str, Optional[str]]:
    """
    Abre a página em headless Chromium e retorna o texto completo para uma busca simples.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            # aguarde um pouquinho pra SPAs (se precisar, aumente)
            page.wait_for_timeout(1500)
            text = page.content()  # pega o HTML
            # se quiser texto renderizado:
            # text = page.inner_text("body")
            context.close()
            browser.close()
        return {"ok": True, "url": url, "html": text, "err": ""}
    except Exception as e:
        return {"ok": False, "url": url, "html": None, "err": str(e)}

def parse_corners(html: Optional[str], market: str) -> Dict[str, Optional[str]]:
    """
    Procura de forma simples a presença do mercado '9.5', etc.
    (ajuste para regex ou seletores se quiser melhorar)
    """
    if not html:
        return {"over": None, "under": None, "err": "sem html"}
    # Exemplos simples de “existe mercado?”.
    # Você pode sofisticar com regex que capture “Mais de 9.5 … 1.72” etc.
    if market.replace(".", "\\.") in html:
        # aqui só marcamos que encontrou o mercado;
        # você pode puxar as odds com expressões regulares específicas por site.
        return {"over": "encontrado", "under": "encontrado", "err": ""}
    return {"over": None, "under": None, "err": "Não encontrei odds no texto da página"}

@app.get("/")
def root():
    return {"status": "API com Playwright online 🚀"}

@app.post("/odds")
def odds(payload: Payload = Body(...)):
    out = {"market": payload.market}

    # BETANO
    betano_res = scrape_text(payload.betano)
    betano_parsed = parse_corners(betano_res.get("html"), payload.market)
    out["betano"] = {
        "ok": betano_res["ok"],
        "url": betano_res["url"],
        **betano_parsed
    }

    # BET365
    bet365_res = scrape_text(payload.bet365)
    bet365_parsed = parse_corners(bet365_res.get("html"), payload.market)
    out["bet365"] = {
        "ok": bet365_res["ok"],
        "url": bet365_res["url"],
        **bet365_parsed
    }

    # KTO
    kto_res = scrape_text(payload.kto)
    kto_parsed = parse_corners(kto_res.get("html"), payload.market)
    out["kto"] = {
        "ok": kto_res["ok"],
        "url": kto_res["url"],
        **kto_parsed
    }

    return out
