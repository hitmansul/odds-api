from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl
from playwright.sync_api import sync_playwright
import re

app = FastAPI()

class OddsBody(BaseModel):
    market: str
    betano: HttpUrl | None = None
    bet365: HttpUrl | None = None
    kto: HttpUrl | None = None

def raspa_texto(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        )
        page = context.new_page()
        page.goto(url, timeout=60000, wait_until="networkidle")
        # às vezes ajuda dar um tempo a mais pra render
        page.wait_for_timeout(2000)
        txt = page.content()  # HTML final renderizado
        browser.close()
        return txt

def extrai_over_under(html: str, market: str):
    # ajuste este regex ao formato real das casas
    padrao_over  = re.compile(rf"(Mais\s+de\s+{re.escape(market)}|Over\s+{re.escape(market)})\D+([0-9]+(?:[.,][0-9]+)?)", re.I)
    padrao_under = re.compile(rf"(Menos\s+de\s+{re.escape(market)}|Under\s+{re.escape(market)})\D+([0-9]+(?:[.,][0-9]+)?)", re.I)

    over  = None
    under = None
    m1 = padrao_over.search(html)
    m2 = padrao_under.search(html)
    if m1: over  = m1.group(2).replace(',', '.')
    if m2: under = m2.group(2).replace(',', '.')
    return over, under

@app.post("/odds")
def odds(body: OddsBody):
    out = {"market": body.market}

    for casa, url in (("betano", body.betano), ("bet365", body.bet365), ("kto", body.kto)):
        if not url:
            continue
        try:
            html = raspa_texto(str(url))
            over, under = extrai_over_under(html, body.market)
            out[casa] = {
                "ok": bool(over or under),
                "url": str(url),
                "over": over,
                "under": under,
                "err": "" if (over or under) else "Não encontrei odds no texto da página"
            }
        except Exception as e:
            out[casa] = {"ok": False, "url": str(url), "over": None, "under": None, "err": str(e)}

    return out
