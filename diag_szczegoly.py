from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152.0 Safari/537.36"}
PZT="http://portal.pzt.pl/TournamentResults.aspx?CategoryID=AIS&TournamentID=57496268-6699-45FC-8338-7B2675DED639"
PLT="https://polskaligatenisa.pl/turnieje/polska-i-liga-tenisa/1-liga-otwarte-letnie-mistrzostwa-pomorza-2026-5545"
KLUBY="https://kluby.org/turnieje/11925"


def clean(x): return " ".join((x or "").replace("\xa0"," ").split())

def print_lines(title,text,limit=140):
    print("\n=====",title,"=====")
    lines=[clean(x) for x in text.splitlines() if clean(x)]
    for i,line in enumerate(lines[:limit]): print(f"{i:03}: {line}")

r=requests.get(PZT,headers=HEADERS,timeout=30)
print("PZT status",r.status_code,"final",r.url)
r.encoding=r.apparent_encoding or "utf-8"
soup=BeautifulSoup(r.text,"html.parser")
print_lines("PZT TEXT",soup.get_text("\n",strip=True),180)
print("\nPZT LINKS")
for a in soup.find_all("a",href=True):
    txt=clean(a.get_text(" ",strip=True)); href=a.get("href","")
    if any(k in (txt+" "+href).casefold() for k in ["turniej","tournament","szczeg","inform","miejsce"]):
        print(txt,"=>",href)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    ctx=browser.new_context(locale="pl-PL",user_agent=HEADERS["User-Agent"])
    page=ctx.new_page()
    for title,url in [("PLT",PLT),("KLUBY",KLUBY)]:
        resp=page.goto(url,wait_until="domcontentloaded",timeout=45000)
        page.wait_for_timeout(1800)
        print("\n",title,"status",resp.status if resp else None,"url",page.url)
        main=page.locator("main")
        text=main.first.inner_text() if main.count() else page.locator("body").inner_text()
        print_lines(title+" TEXT",text,220)
        print("\n"+title+" LINKS")
        links=page.locator("a[href]").evaluate_all("els=>els.map(a=>({t:(a.innerText||'').replace(/\\s+/g,' ').trim(),h:a.href}))")
        for x in links:
            s=(x['t']+' '+x['h']).casefold()
            if any(k in s for k in ["zapis","udział","udzial","turniej","runda","register"]):
                print(x['t'],"=>",x['h'])
    browser.close()
