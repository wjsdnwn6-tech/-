from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import paper_trade
import yfinance as yf
import os
import json

app = FastAPI(title="Ichimoku Scanner & Trading API")

# Configure CORS for Vite Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TradeRequest(BaseModel):
    ticker: str

@app.on_event("startup")
def startup_event():
    paper_trade.init_db()

@app.get("/api/status")
def get_status():
    conn = sqlite3.connect(paper_trade.DB_NAME)
    c = conn.cursor()
    c.execute('SELECT cash FROM account WHERE id=1')
    row = c.fetchone()
    cash = row[0] if row else 0

    c.execute('SELECT ticker, shares, avg_price_krw FROM portfolio')
    rows = c.fetchall()

    portfolio = []
    total_eval = cash

    for ticker, shares, avg_price_krw in rows:
        price = paper_trade.get_current_price(ticker)
        if price is None:
            continue
        price_krw = price if paper_trade.is_korean(ticker) else price * paper_trade.FX_RATE
        eval_amount = price_krw * shares
        buy_amount = avg_price_krw * shares
        profit_rate = ((eval_amount - buy_amount) / buy_amount) * 100
        total_eval += eval_amount

        try:
            name = yf.Ticker(ticker).info.get('shortName', ticker)
        except:
            name = ticker

        portfolio.append({
            "ticker": ticker,
            "name": name,
            "shares": shares,
            "avg_price_krw": avg_price_krw,
            "current_price_krw": price_krw,
            "profit_rate": profit_rate,
            "eval_amount": eval_amount
        })

    conn.close()
    return {
        "cash": cash,
        "total_eval": total_eval,
        "portfolio": portfolio
    }

@app.post("/api/buy")
def buy_stock(req: TradeRequest):
    success = paper_trade.do_buy(req.ticker)
    if success:
        return {"status": "success", "message": f"{req.ticker} 매수 성공"}
    raise HTTPException(status_code=400, detail="매수 실패 (콘솔 로그 확인)")

@app.post("/api/sell")
def sell_stock(req: TradeRequest):
    success = paper_trade.do_sell(req.ticker)
    if success:
        return {"status": "success", "message": f"{req.ticker} 매도 성공"}
    raise HTTPException(status_code=400, detail="매도 실패 (콘솔 로그 확인)")

@app.get("/api/scan-results")
def get_scan_results():
    if not os.path.exists("scan_results.json"):
        return []
    with open("scan_results.json", "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []
