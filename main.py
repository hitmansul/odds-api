# main.py
import re
import json
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

app = FastAPI(title="Odds API", version="1.0.0")

# ---------- MODELOS ----------
class SiteIn(BaseModel):
    url: HttpUrl

class OddsRequest(BaseModel):
    market: str = Field(..., description="Linha do mercado, ex: '9.5' ou '10.5'")
    betano: SiteIn
    bet365: SiteIn
    kto: SiteIn

class SiteOut(BaseModel):
    ok: bool
    url: HttpUrl
    over: Optional[float] = None
    under: Optional[float] = None
    err: str = ""

class OddsResponse(BaseModel):
    market: str
    betano: SiteOut
    bet365: SiteOut
    kto: SiteOut


# ---------- CONFIGURAÇÃO DE SELETORES (pode ajustar depois) ----------
# Damos mais de uma opção por site porque eles mudam HTML com frequência.
SITE_SELECTORS: Dict[str, Dict[str, List[str]]] = {
    "betano": {
        "over": [
            # exemplos típicos de "Mais de X" (odds em cards)
            '[data-qa="bet-odds"]',  # genérico
            'button[data-test="odd"]',
            'div:has-text("Mais de") ~ div [data-qa="bet-odds"]',
        ],
        "under": [
            # exemplos típicos de "Menos de X"
            'div:has-text("Menos de") ~ div [data-qa="bet-odds"]',
            'button[data-test="odd"]',
        ],
    },
    "bet365": {
        "over": [
            # bet365 costuma ter bastante obfuscação, então mantemos opções genéricas
            'div.gl-Participant_Odds',        # odds genéricas
            'span.gl-Participant_Odds',       # odds genéricas (span)
        ],
        "under": [
            'div.gl-Participant_Odds',
            'span.gl-Participant_Odds',
        ],
    },
    "kto": {
        "over": [
            'button.odds',                    # odds em botões
            'div.odds',
        ],
        "under": [
            'button.odds',
            'div.odds',
        ],
    },
}

# Palavras que ajudam no fallback textual
KEYS_OVER = ["mais de", "over"]
KEYS_UNDER = ["menos de", "under"]


# ---------- UTILITÁRIOS ----------
def to_float(txt: str) -> Optional[float]:
    """Converte '1,85' ou '1.85' em float. Retorna None se não der."""
    if not txt:
        return None
    txt = txt.strip()
    # tira coisas fora do padrão (ex: odds com sufixos)
    txt = re.sub(r"[^0-9,\.]", "", txt)
    if not txt:
        return None
    # se tem vírgula e não ponto, vira ponto
    if "," in txt and "." not in txt:
        txt = txt.replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def find_near_market(text: str, market: str, keys: List[str]) -> Optional[float]:
    """
    Procura odds perto de 'Mais de 9.5' ou 'Menos de 9.5' no HTML (fallback).
    Pega o número com padrão decimal logo após/antes do termo.
    """
    text_low = re.sub(r"\s+", " ", text.lower())
    # Normaliza decimal (vírgula -> ponto) só para procurar
    text_low = text_low.replace(",", ".")
    for key in keys:
        # ex: "mais de 9.5" ou "under 9.5"
        pattern = rf"{key}\s*{re.escape(market)}.*?([0-9]+\.[0-9]+)"
        m = re.search(pattern, text_low)
        if m:
            return to_float(m.group(1))
    return None


def scrape_site(page, site: str, url: str, market: str, timeout_ms: int = 12000) -> Dict[str, Any]:
    """
    Tenta extrair over/under para o mercado informado.
    1) Tenta por seletores
    2) Se falhar, tenta fallback textual no HTML
    """
    try:
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
    except PWTimeout:
        return {"ok": False, "url": url, "over": None, "under": None, "err": "Timeout ao abrir a página"}

    # Aguarda um pouco mais por conteúdos dinâmicos (renderização JS)
    page.wait_for_timeout(1500)

    sel_conf = SITE_SELECTORS.get(site, {})
    over = None
    under = None

    # 1) TENTATIVA POR SELETORES
    for sel in sel_conf.get("over", []):
        try:
            # pega vários elementos e tenta o primeiro que pareça odd
            elems = page.query_selector_all(sel)
            for el in elems:
                txt = (el.inner_text() or "").strip()
                val = to_float(txt)
                if val:
                    over = val
                    break
            if over:
                break
        except Exception:
            pass

    for sel in sel_conf.get("under", []):
        try:
            elems = page.query_selector_all(sel)
            for el in elems:
                txt = (el.inner_text() or "").strip()
                val = to_float(txt)
                if val:
                    under = val
                    break
            if under:
                break
        except Exception:
            pass

    # 2) FALLBACK POR TEXTO (se ainda não achou)
    if over is None or under is None:
        html = page.content()
        if over is None:
            over = find_near_market(html, market, KEYS_OVER)
        if under is None:
            under = find_near_market(html, market, KEYS_UNDER)

    ok = over is not None or under is not None
    err = "" if ok else "Não encontrei odds no texto da página"

    return {"ok": ok, "url": url, "over": over, "under": under, "err": err}


def run_playwright(payload: OddsRequest) -> OddsResponse:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox"])
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
            viewport={"width": 1366, "height": 800},
        )
        page = context.new_page()

        # Para cada site, tenta extrair
        b1 = scrape_site(page, "betano", str(payload.betano.url), payload.market)
        b2 = scrape_site(page, "bet365", str(payload.bet365.url), payload.market)
        b3 = scrape_site(page, "kto", str(payload.kto.url), payload.market)

        context.close()
        browser.close()

    return OddsResponse(
        market=payload.market,
        betano=SiteOut(**b1),
        bet365=SiteOut(**b2),
        kto=SiteOut(**b3),
    )


# ---------- ENDPOINTS ----------
@app.get("/")
def root():
    return {"status": "API de odds online 🚀"}


@app.post("/odds", response_model=OddsResponse)
def odds(payload: OddsRequest):
    try:
        return run_playwright(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
