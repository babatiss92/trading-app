from datetime import datetime, timedelta, timezone
import os
import time
from urllib.parse import quote

import requests
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_bcrypt import Bcrypt
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint


app = Flask(__name__)
app.config["SECRET_KEY"] = "cle_secrete_123"
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "trading_game.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

BINANCE_SESSION = requests.Session()
YAHOO_SESSION = requests.Session()
PRICE_CACHE_TTL_SECONDS = 15
PRICE_CACHE = {}
TRADINGVIEW_SYMBOLS = {
    "BTC": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT",
    "SOL": "BINANCE:SOLUSDT",
    "BNB": "BINANCE:BNBUSDT",
    "AAPL": "NASDAQ:AAPL",
    "MSFT": "NASDAQ:MSFT",
    "NVDA": "NASDAQ:NVDA",
    "TSLA": "NASDAQ:TSLA",
    "SPY": "AMEX:SPY",
    "QQQ": "NASDAQ:QQQ",
    "VOO": "AMEX:VOO",
    "IVV": "AMEX:IVV",
}


ASSET_CATALOG = [
    {
        "symbol": "BTC",
        "name": "Bitcoin",
        "asset_type": "crypto",
        "provider": "binance",
        "provider_symbol": "BTCUSDT",
        "chart_symbol": TRADINGVIEW_SYMBOLS["BTC"],
    },
    {
        "symbol": "ETH",
        "name": "Ethereum",
        "asset_type": "crypto",
        "provider": "binance",
        "provider_symbol": "ETHUSDT",
        "chart_symbol": TRADINGVIEW_SYMBOLS["ETH"],
    },
    {
        "symbol": "SOL",
        "name": "Solana",
        "asset_type": "crypto",
        "provider": "binance",
        "provider_symbol": "SOLUSDT",
        "chart_symbol": TRADINGVIEW_SYMBOLS["SOL"],
    },
    {
        "symbol": "BNB",
        "name": "BNB",
        "asset_type": "crypto",
        "provider": "binance",
        "provider_symbol": "BNBUSDT",
        "chart_symbol": TRADINGVIEW_SYMBOLS["BNB"],
    },
    {
        "symbol": "AAPL",
        "name": "Apple",
        "asset_type": "stock",
        "provider": "yahoo",
        "provider_symbol": "AAPL",
        "chart_symbol": TRADINGVIEW_SYMBOLS["AAPL"],
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft",
        "asset_type": "stock",
        "provider": "yahoo",
        "provider_symbol": "MSFT",
        "chart_symbol": TRADINGVIEW_SYMBOLS["MSFT"],
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA",
        "asset_type": "stock",
        "provider": "yahoo",
        "provider_symbol": "NVDA",
        "chart_symbol": TRADINGVIEW_SYMBOLS["NVDA"],
    },
    {
        "symbol": "TSLA",
        "name": "Tesla",
        "asset_type": "stock",
        "provider": "yahoo",
        "provider_symbol": "TSLA",
        "chart_symbol": TRADINGVIEW_SYMBOLS["TSLA"],
    },
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF",
        "asset_type": "etf",
        "provider": "yahoo",
        "provider_symbol": "SPY",
        "chart_symbol": TRADINGVIEW_SYMBOLS["SPY"],
    },
    {
        "symbol": "QQQ",
        "name": "Invesco QQQ Trust",
        "asset_type": "etf",
        "provider": "yahoo",
        "provider_symbol": "QQQ",
        "chart_symbol": TRADINGVIEW_SYMBOLS["QQQ"],
    },
    {
        "symbol": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "asset_type": "etf",
        "provider": "yahoo",
        "provider_symbol": "VOO",
        "chart_symbol": TRADINGVIEW_SYMBOLS["VOO"],
    },
    {
        "symbol": "IVV",
        "name": "iShares Core S&P 500 ETF",
        "asset_type": "etf",
        "provider": "yahoo",
        "provider_symbol": "IVV",
        "chart_symbol": TRADINGVIEW_SYMBOLS["IVV"],
    },
]

FALLBACK_PRICES = {
    "BTC": 70000.0,
    "ETH": 3500.0,
    "SOL": 150.0,
    "BNB": 600.0,
    "AAPL": 210.0,
    "MSFT": 430.0,
    "NVDA": 900.0,
    "TSLA": 180.0,
    "SPY": 520.0,
    "QQQ": 450.0,
    "VOO": 480.0,
    "IVV": 520.0,
}


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    balance = db.Column(db.Float, default=10000.0)
    btc_quantity = db.Column(db.Float, default=0.0)


class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(12), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    asset_type = db.Column(db.String(20), nullable=False)
    provider = db.Column(db.String(20), nullable=False)
    provider_symbol = db.Column(db.String(30), nullable=False)
    chart_symbol = db.Column(db.String(40), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Position(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    quantity = db.Column(db.Float, default=0.0, nullable=False)
    avg_buy_price = db.Column(db.Float, default=0.0, nullable=False)

    user = db.relationship("User", backref=db.backref("positions", lazy=True))
    asset = db.relationship("Asset")

    __table_args__ = (UniqueConstraint("user_id", "asset_id", name="uq_user_asset_position"),)


class TradeTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    side = db.Column(db.String(10), nullable=False)
    order_type = db.Column(db.String(20), nullable=False, default="market")
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    gross_amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref=db.backref("trade_transactions", lazy=True))
    asset = db.relationship("Asset")


class TradeOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    side = db.Column(db.String(10), nullable=False)
    order_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    input_mode = db.Column(db.String(20), nullable=False, default="amount")
    limit_price = db.Column(db.Float, nullable=True)
    quantity = db.Column(db.Float, nullable=False)
    amount_usd = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    executed_at = db.Column(db.DateTime, nullable=True)
    executed_price = db.Column(db.Float, nullable=True)

    user = db.relationship("User", backref=db.backref("trade_orders", lazy=True))
    asset = db.relationship("Asset")


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    starting_cash = db.Column(db.Float, nullable=False, default=10000.0)
    cash_prize = db.Column(db.Float, nullable=False, default=0.0)
    allowed_assets = db.Column(db.String(250), nullable=False)


class EventParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    event = db.relationship("Event", backref=db.backref("participants", lazy=True))
    user = db.relationship("User", backref=db.backref("event_entries", lazy=True))

    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_user"),)


class EventPortfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    balance = db.Column(db.Float, nullable=False, default=10000.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    event = db.relationship("Event", backref=db.backref("portfolios", lazy=True))
    user = db.relationship("User", backref=db.backref("event_portfolios", lazy=True))

    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_portfolio"),)


class EventPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("event_portfolio.id"), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    quantity = db.Column(db.Float, default=0.0, nullable=False)
    avg_buy_price = db.Column(db.Float, default=0.0, nullable=False)

    portfolio = db.relationship("EventPortfolio", backref=db.backref("positions", lazy=True))
    asset = db.relationship("Asset")

    __table_args__ = (UniqueConstraint("portfolio_id", "asset_id", name="uq_event_portfolio_asset"),)


class EventTradeTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("event_portfolio.id"), nullable=False)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    side = db.Column(db.String(10), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    gross_amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    portfolio = db.relationship("EventPortfolio", backref=db.backref("transactions", lazy=True))
    asset = db.relationship("Asset")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def seed_assets():
    for asset_data in ASSET_CATALOG:
        asset = Asset.query.filter_by(symbol=asset_data["symbol"]).first()
        if asset:
            asset.name = asset_data["name"]
            asset.asset_type = asset_data["asset_type"]
            asset.provider = asset_data["provider"]
            asset.provider_symbol = asset_data["provider_symbol"]
            asset.chart_symbol = asset_data["chart_symbol"]
            asset.is_active = True
        else:
            db.session.add(Asset(**asset_data))
    db.session.commit()


def seed_events():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    next_week_start = week_start + timedelta(days=7)

    event_definitions = [
        {
            "slug": f"weekly-clash-{week_start.strftime('%Y%m%d')}",
            "title": "Weekly Clash",
            "description": "Une compétition hebdomadaire pour tester la meilleure stratégie multi-actifs.",
            "start_date": week_start,
            "end_date": week_start + timedelta(days=6, hours=23, minutes=59),
            "starting_cash": 10000.0,
            "cash_prize": 250.0,
            "allowed_assets": "BTC,ETH,SOL,BNB,AAPL,MSFT,NVDA,TSLA,SPY,QQQ,VOO,IVV",
        },
        {
            "slug": f"weekly-clash-{next_week_start.strftime('%Y%m%d')}",
            "title": "Weekly Clash Next",
            "description": "L'édition suivante pour laisser les joueurs se préinscrire et préparer leurs idées.",
            "start_date": next_week_start,
            "end_date": next_week_start + timedelta(days=6, hours=23, minutes=59),
            "starting_cash": 10000.0,
            "cash_prize": 400.0,
            "allowed_assets": "BTC,ETH,SOL,BNB,AAPL,MSFT,NVDA,TSLA,SPY,QQQ,VOO,IVV",
        },
    ]

    for event_data in event_definitions:
        event = Event.query.filter_by(slug=event_data["slug"]).first()
        if event:
            event.title = event_data["title"]
            event.description = event_data["description"]
            event.start_date = event_data["start_date"]
            event.end_date = event_data["end_date"]
            event.starting_cash = event_data["starting_cash"]
            event.cash_prize = event_data["cash_prize"]
            event.allowed_assets = event_data["allowed_assets"]
        else:
            db.session.add(Event(**event_data))
    db.session.commit()


def get_fallback_price(symbol):
    return FALLBACK_PRICES.get(symbol, 100.0)


def get_chart_symbol(asset):
    return TRADINGVIEW_SYMBOLS.get(asset.symbol, asset.chart_symbol)


def get_tradingview_embed_url(asset, interval="60"):
    chart_symbol = get_chart_symbol(asset)
    return (
        "https://s.tradingview.com/widgetembed/"
        f"?symbol={quote(chart_symbol, safe='')}"
        f"&interval={quote(interval, safe='')}"
        "&theme=dark"
        "&style=1"
        "&locale=fr"
        "&toolbarbg=%230f172a"
        "&hide_top_toolbar=false"
        "&saveimage=false"
        "&studies=%5B%5D"
        "&withdateranges=true"
        "&hide_side_toolbar=false"
        "&allow_symbol_change=false"
        "&calendar=false"
        "&details=true"
        "&hotlist=false"
        "&news=false"
    )


def get_cached_price(symbol):
    cache_entry = PRICE_CACHE.get(symbol)
    if not cache_entry:
        return None

    cached_at, price = cache_entry
    if (time.time() - cached_at) > PRICE_CACHE_TTL_SECONDS:
        PRICE_CACHE.pop(symbol, None)
        return None

    return price


def set_cached_price(symbol, price):
    PRICE_CACHE[symbol] = (time.time(), float(price))


def fetch_binance_prices(assets):
    if not assets:
        return {}

    try:
        response = BINANCE_SESSION.get("https://api.binance.com/api/v3/ticker/price", timeout=3)
        response.raise_for_status()
        payload = response.json()
        payload_map = {item["symbol"]: float(item["price"]) for item in payload}
        result = {}
        for asset in assets:
            price = payload_map.get(asset.provider_symbol, get_fallback_price(asset.symbol))
            result[asset.symbol] = price
        return result
    except Exception:
        return {asset.symbol: get_fallback_price(asset.symbol) for asset in assets}


def fetch_yahoo_prices(assets):
    if not assets:
        return {}

    try:
        response = YAHOO_SESSION.get(
            "https://query1.finance.yahoo.com/v7/finance/quote",
            params={"symbols": ",".join(asset.provider_symbol for asset in assets)},
            timeout=3,
        )
        response.raise_for_status()
        payload = response.json()
        quote_results = payload.get("quoteResponse", {}).get("result", [])
        quote_map = {
            item.get("symbol"): float(item.get("regularMarketPrice"))
            for item in quote_results
            if item.get("symbol") and item.get("regularMarketPrice") is not None
        }
    except Exception:
        quote_map = {}

    result = {}
    for asset in assets:
        price = quote_map.get(asset.provider_symbol)
        result[asset.symbol] = float(price) if price else get_fallback_price(asset.symbol)
    return result


def fetch_asset_price(asset):
    try:
        return get_prices_for_assets([asset])[asset.symbol]
    except Exception:
        return get_fallback_price(asset.symbol)


def get_prices_for_assets(assets):
    if not assets:
        return {}

    prices = {}
    missing_assets = []
    for asset in assets:
        cached_price = get_cached_price(asset.symbol)
        if cached_price is not None:
            prices[asset.symbol] = cached_price
        else:
            missing_assets.append(asset)

    if not missing_assets:
        return prices

    assets_by_provider = {}
    for asset in missing_assets:
        assets_by_provider.setdefault(asset.provider, []).append(asset)

    provider_prices = {}
    provider_prices.update(fetch_binance_prices(assets_by_provider.get("binance", [])))
    provider_prices.update(fetch_yahoo_prices(assets_by_provider.get("yahoo", [])))

    for asset in missing_assets:
        price = provider_prices.get(asset.symbol, get_fallback_price(asset.symbol))
        prices[asset.symbol] = price
        set_cached_price(asset.symbol, price)

    return prices


def get_position(user, asset):
    position = Position.query.filter_by(user_id=user.id, asset_id=asset.id).first()
    if position:
        return position

    position = Position(user_id=user.id, asset_id=asset.id, quantity=0.0, avg_buy_price=0.0)
    db.session.add(position)
    db.session.flush()
    return position


def migrate_legacy_btc_positions():
    btc_asset = Asset.query.filter_by(symbol="BTC").first()
    if not btc_asset:
        return

    users = User.query.filter(User.btc_quantity > 0).all()
    if not users:
        return

    current_btc_price = fetch_asset_price(btc_asset)
    for user in users:
        position = Position.query.filter_by(user_id=user.id, asset_id=btc_asset.id).first()
        if position:
            total_qty = position.quantity + user.btc_quantity
            if total_qty > 0:
                weighted_cost = (position.quantity * position.avg_buy_price) + (user.btc_quantity * current_btc_price)
                position.quantity = total_qty
                position.avg_buy_price = weighted_cost / total_qty
        else:
            db.session.add(
                Position(
                    user_id=user.id,
                    asset_id=btc_asset.id,
                    quantity=user.btc_quantity,
                    avg_buy_price=current_btc_price,
                )
            )
        user.btc_quantity = 0.0

    db.session.commit()


def bootstrap_database():
    db.create_all()
    seed_assets()
    seed_events()
    migrate_legacy_btc_positions()


def get_user_relevant_assets(user, selected_asset=None):
    relevant_assets = {}
    if selected_asset:
        relevant_assets[selected_asset.id] = selected_asset

    held_assets = (
        Asset.query.join(Position, Position.asset_id == Asset.id)
        .filter(Position.user_id == user.id, Position.quantity > 0)
        .all()
    )
    for asset in held_assets:
        relevant_assets[asset.id] = asset

    pending_order_assets = (
        Asset.query.join(TradeOrder, TradeOrder.asset_id == Asset.id)
        .filter(TradeOrder.user_id == user.id, TradeOrder.status == "pending")
        .all()
    )
    for asset in pending_order_assets:
        relevant_assets[asset.id] = asset

    return list(relevant_assets.values())


def get_assets_used_by_ranked_users():
    return (
        Asset.query.join(Position, Position.asset_id == Asset.id)
        .filter(Position.quantity > 0)
        .distinct()
        .all()
    )


def get_event_allowed_assets(event):
    allowed_symbols = [symbol.strip() for symbol in event.allowed_assets.split(",") if symbol.strip()]
    if not allowed_symbols:
        return []
    return Asset.query.filter(Asset.symbol.in_(allowed_symbols)).order_by(Asset.asset_type, Asset.symbol).all()


def get_or_create_event_portfolio(event, user):
    portfolio = EventPortfolio.query.filter_by(event_id=event.id, user_id=user.id).first()
    if portfolio:
        return portfolio

    portfolio = EventPortfolio(event_id=event.id, user_id=user.id, balance=event.starting_cash)
    db.session.add(portfolio)
    db.session.flush()
    return portfolio


def get_event_position(portfolio, asset):
    position = EventPosition.query.filter_by(portfolio_id=portfolio.id, asset_id=asset.id).first()
    if position:
        return position

    position = EventPosition(portfolio_id=portfolio.id, asset_id=asset.id, quantity=0.0, avg_buy_price=0.0)
    db.session.add(position)
    db.session.flush()
    return position


def compute_event_portfolio(portfolio, price_map):
    positions = (
        EventPosition.query.filter_by(portfolio_id=portfolio.id)
        .join(Asset)
        .filter(EventPosition.quantity > 0)
        .all()
    )

    holdings = []
    total_assets_value = 0.0
    for position in positions:
        asset = position.asset
        current_price = price_map.get(asset.symbol, get_fallback_price(asset.symbol))
        market_value = position.quantity * current_price
        pnl = market_value - (position.quantity * position.avg_buy_price)
        total_assets_value += market_value
        holdings.append(
            {
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "quantity": position.quantity,
                "avg_buy_price": position.avg_buy_price,
                "current_price": current_price,
                "market_value": market_value,
                "pnl": pnl,
            }
        )

    total_value = portfolio.balance + total_assets_value
    pnl_total = total_value - portfolio.event.starting_cash
    pnl_percent = (pnl_total / portfolio.event.starting_cash) * 100 if portfolio.event.starting_cash else 0.0
    holdings.sort(key=lambda item: item["market_value"], reverse=True)

    return {
        "holdings": holdings,
        "cash_balance": portfolio.balance,
        "total_assets_value": total_assets_value,
        "total_value": total_value,
        "pnl_total": pnl_total,
        "pnl_percent": pnl_percent,
    }


def execute_event_trade(portfolio, asset, side, amount_usd=None, quantity=None):
    price = fetch_asset_price(asset)
    final_quantity = quantity if quantity is not None else (amount_usd / price)
    final_quantity = float(final_quantity)
    gross_amount = final_quantity * price
    position = get_event_position(portfolio, asset)

    if side == "buy":
        if gross_amount > portfolio.balance + 1e-9:
            return False, "Solde insuffisant dans l'event."
        previous_value = position.quantity * position.avg_buy_price
        portfolio.balance -= gross_amount
        position.quantity += final_quantity
        if position.quantity > 0:
            position.avg_buy_price = (previous_value + gross_amount) / position.quantity
    else:
        if final_quantity > position.quantity + 1e-9:
            return False, "Quantite insuffisante dans l'event."
        portfolio.balance += gross_amount
        position.quantity = max(position.quantity - final_quantity, 0.0)
        if position.quantity == 0:
            position.avg_buy_price = 0.0

    db.session.add(
        EventTradeTransaction(
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            side=side,
            price=price,
            quantity=final_quantity,
            gross_amount=gross_amount,
        )
    )
    db.session.commit()
    return True, "Ordre event execute."


def get_assets_used_in_event(event):
    return (
        Asset.query.join(EventPosition, EventPosition.asset_id == Asset.id)
        .join(EventPortfolio, EventPortfolio.id == EventPosition.portfolio_id)
        .filter(EventPortfolio.event_id == event.id, EventPosition.quantity > 0)
        .distinct()
        .all()
    )


def execute_trade(user, asset, side, quantity, price, order_type="market"):
    quantity = float(quantity)
    price = float(price)
    gross_amount = quantity * price
    position = get_position(user, asset)

    if side == "buy":
        if gross_amount > user.balance + 1e-9:
            return False, "Solde insuffisant."

        previous_value = position.quantity * position.avg_buy_price
        user.balance -= gross_amount
        position.quantity += quantity
        if position.quantity > 0:
            position.avg_buy_price = (previous_value + gross_amount) / position.quantity
    else:
        if quantity > position.quantity + 1e-9:
            return False, "Quantité insuffisante."

        user.balance += gross_amount
        position.quantity = max(position.quantity - quantity, 0.0)
        if position.quantity == 0:
            position.avg_buy_price = 0.0

    db.session.add(
        TradeTransaction(
            user_id=user.id,
            asset_id=asset.id,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            gross_amount=gross_amount,
        )
    )
    db.session.commit()
    return True, "Ordre exécuté."


def parse_order_inputs(form):
    order_type = (form.get("order_type") or "market").lower()
    side = (form.get("side") or "buy").lower()
    input_mode = (form.get("input_mode") or "amount").lower()
    symbol = (form.get("symbol") or "BTC").upper()

    amount_usd = form.get("amount_usd", "").strip()
    quantity = form.get("quantity", "").strip()
    limit_price = form.get("limit_price", "").strip()

    try:
        amount_usd_value = float(amount_usd) if amount_usd else None
    except ValueError:
        amount_usd_value = None

    try:
        quantity_value = float(quantity) if quantity else None
    except ValueError:
        quantity_value = None

    try:
        limit_price_value = float(limit_price) if limit_price else None
    except ValueError:
        limit_price_value = None

    return {
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "input_mode": input_mode,
        "amount_usd": amount_usd_value,
        "quantity": quantity_value,
        "limit_price": limit_price_value,
    }


def validate_trade_inputs(asset, side, order_type, input_mode, amount_usd, quantity, limit_price):
    if side not in {"buy", "sell"}:
        return False, "Sens d'ordre invalide."
    if order_type not in {"market", "limit"}:
        return False, "Type d'ordre invalide."
    if input_mode not in {"amount", "quantity"}:
        return False, "Mode de saisie invalide."
    if order_type == "limit" and (limit_price is None or limit_price <= 0):
        return False, "Un ordre limite doit avoir un prix limite valide."
    if input_mode == "amount" and (amount_usd is None or amount_usd <= 0):
        return False, "Le montant en USD doit être supérieur à 0."
    if input_mode == "quantity" and (quantity is None or quantity <= 0):
        return False, "La quantité doit être supérieure à 0."
    if not asset:
        return False, "Actif introuvable."
    return True, ""


def place_market_order(user, asset, side, input_mode, amount_usd, quantity):
    current_price = fetch_asset_price(asset)
    final_quantity = quantity if input_mode == "quantity" else (amount_usd / current_price)
    return execute_trade(user, asset, side, final_quantity, current_price, order_type="market")


def place_limit_order(user, asset, side, input_mode, amount_usd, quantity, limit_price):
    final_quantity = quantity if input_mode == "quantity" else (amount_usd / limit_price)

    if side == "buy" and (final_quantity * limit_price) > user.balance + 1e-9:
        return False, "Solde insuffisant pour placer cet ordre limite."

    if side == "sell":
        position = get_position(user, asset)
        if final_quantity > position.quantity + 1e-9:
            return False, "Tu ne possèdes pas assez de titres pour cet ordre limite."

    db.session.add(
        TradeOrder(
            user_id=user.id,
            asset_id=asset.id,
            side=side,
            order_type="limit",
            status="pending",
            input_mode=input_mode,
            limit_price=limit_price,
            quantity=final_quantity,
            amount_usd=final_quantity * limit_price,
        )
    )
    db.session.commit()
    return True, "Ordre limite enregistré."


def process_pending_orders():
    pending_orders = (
        TradeOrder.query.filter_by(status="pending")
        .order_by(TradeOrder.created_at.asc())
        .all()
    )
    if not pending_orders:
        return

    asset_ids = {order.asset_id for order in pending_orders}
    assets = Asset.query.filter(Asset.id.in_(asset_ids)).all()
    asset_map = {asset.id: asset for asset in assets}
    provider_price_map = get_prices_for_assets(assets)
    price_map = {asset.id: provider_price_map.get(asset.symbol, get_fallback_price(asset.symbol)) for asset in assets}

    for order in pending_orders:
        asset = asset_map.get(order.asset_id)
        market_price = price_map.get(order.asset_id)
        if not asset or market_price is None:
            continue

        should_execute = (
            order.side == "buy" and market_price <= order.limit_price
        ) or (
            order.side == "sell" and market_price >= order.limit_price
        )

        if not should_execute:
            continue

        user = db.session.get(User, order.user_id)
        success, _ = execute_trade(user, asset, order.side, order.quantity, market_price, order_type="limit")
        order = db.session.get(TradeOrder, order.id)
        if success:
            order.status = "executed"
            order.executed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            order.executed_price = market_price
        else:
            order.status = "cancelled"
            order.executed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            order.executed_price = market_price
        db.session.commit()


def compute_user_portfolio(user, price_map):
    positions = (
        Position.query.filter_by(user_id=user.id)
        .join(Asset)
        .filter(Position.quantity > 0)
        .all()
    )

    holdings = []
    total_assets_value = 0.0
    for position in positions:
        asset = position.asset
        current_price = price_map.get(asset.symbol, get_fallback_price(asset.symbol))
        market_value = position.quantity * current_price
        pnl = market_value - (position.quantity * position.avg_buy_price)
        total_assets_value += market_value
        holdings.append(
            {
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "quantity": position.quantity,
                "avg_buy_price": position.avg_buy_price,
                "current_price": current_price,
                "market_value": market_value,
                "pnl": pnl,
            }
        )

    total_value = user.balance + total_assets_value
    initial_balance = 10000.0
    pnl_total = total_value - initial_balance
    pnl_percent = (pnl_total / initial_balance) * 100 if initial_balance else 0.0

    holdings.sort(key=lambda item: item["market_value"], reverse=True)
    return {
        "holdings": holdings,
        "total_assets_value": total_assets_value,
        "total_value": total_value,
        "pnl_total": pnl_total,
        "pnl_percent": pnl_percent,
    }


def get_dashboard_context(selected_symbol):
    process_pending_orders()

    assets = Asset.query.filter_by(is_active=True).order_by(Asset.asset_type, Asset.symbol).all()
    asset_map = {asset.symbol: asset for asset in assets}
    selected_asset = asset_map.get(selected_symbol) or asset_map.get("BTC") or assets[0]

    price_map = get_prices_for_assets(get_user_relevant_assets(current_user, selected_asset))
    portfolio = compute_user_portfolio(current_user, price_map)
    selected_position = get_position(current_user, selected_asset)
    selected_price = price_map.get(selected_asset.symbol, get_fallback_price(selected_asset.symbol))

    open_orders = (
        TradeOrder.query.filter_by(user_id=current_user.id, status="pending")
        .order_by(TradeOrder.created_at.desc())
        .all()
    )
    recent_transactions = (
        TradeTransaction.query.filter_by(user_id=current_user.id)
        .order_by(TradeTransaction.created_at.desc())
        .limit(12)
        .all()
    )

    return {
        "assets": assets,
        "selected_asset": selected_asset,
        "selected_chart_symbol": get_chart_symbol(selected_asset),
        "selected_chart_url": get_tradingview_embed_url(selected_asset),
        "selected_price": selected_price,
        "selected_position": selected_position,
        "portfolio": portfolio,
        "open_orders": open_orders,
        "recent_transactions": recent_transactions,
        "active_symbol": selected_asset.symbol,
        "feedback": request.args.get("message", ""),
        "feedback_type": request.args.get("message_type", "info"),
    }


def classify_event_status(event):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if now < event.start_date:
        return "upcoming"
    if now > event.end_date:
        return "finished"
    return "live"


def can_join_event(event):
    return classify_event_status(event) in {"upcoming", "live"}


def can_trade_event(event):
    return classify_event_status(event) == "live"


with app.app_context():
    bootstrap_database()


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            return "Desole, ce pseudo est deja utilise. Choisis-en un autre."

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and bcrypt.check_password_hash(user.password, request.form["password"]):
            login_user(user)
            return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/")
@login_required
def dashboard():
    active_symbol = (request.args.get("symbol") or "BTC").upper()
    return render_template("dashboard.html", **get_dashboard_context(active_symbol))


@app.route("/trade", methods=["POST"])
@login_required
def trade():
    process_pending_orders()
    data = parse_order_inputs(request.form)
    asset = Asset.query.filter_by(symbol=data["symbol"]).first()

    is_valid, error_message = validate_trade_inputs(
        asset,
        data["side"],
        data["order_type"],
        data["input_mode"],
        data["amount_usd"],
        data["quantity"],
        data["limit_price"],
    )
    if not is_valid:
        return redirect(url_for("dashboard", symbol=data["symbol"], message=error_message, message_type="error"))

    if data["order_type"] == "market":
        success, message = place_market_order(
            current_user,
            asset,
            data["side"],
            data["input_mode"],
            data["amount_usd"],
            data["quantity"],
        )
    else:
        success, message = place_limit_order(
            current_user,
            asset,
            data["side"],
            data["input_mode"],
            data["amount_usd"],
            data["quantity"],
            data["limit_price"],
        )

    return redirect(
        url_for(
            "dashboard",
            symbol=data["symbol"],
            message=message,
            message_type="success" if success else "error",
        )
    )


@app.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    order = TradeOrder.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    if order.status == "pending":
        order.status = "cancelled"
        order.executed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()
    return redirect(url_for("dashboard", symbol=order.asset.symbol))


@app.route("/api/quote")
@login_required
def api_quote():
    symbol = (request.args.get("symbol") or "BTC").upper()
    asset = Asset.query.filter_by(symbol=symbol).first()
    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    price = fetch_asset_price(asset)
    position = get_position(current_user, asset)
    return jsonify(
        {
            "symbol": asset.symbol,
            "price": price,
            "position_quantity": position.quantity,
            "position_value": position.quantity * price,
        }
    )


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/classement")
@login_required
def classement():
    process_pending_orders()
    assets = get_assets_used_by_ranked_users()
    price_map = get_prices_for_assets(assets)

    leaderboard = []
    for user in User.query.order_by(User.username.asc()).all():
        portfolio = compute_user_portfolio(user, price_map)
        leaderboard.append(
            {
                "username": user.username,
                "total_value": portfolio["total_value"],
                "pnl_percent": portfolio["pnl_percent"],
            }
        )

    leaderboard.sort(key=lambda player: player["total_value"], reverse=True)
    return render_template("classement.html", leaderboard=leaderboard)


@app.route("/events")
@login_required
def events():
    process_pending_orders()
    ranked_assets = get_assets_used_by_ranked_users()
    price_map = get_prices_for_assets(ranked_assets)
    portfolio = compute_user_portfolio(current_user, price_map)

    event_cards = []
    for event in Event.query.order_by(Event.start_date.asc()).all():
        status = classify_event_status(event)
        joined = EventParticipant.query.filter_by(event_id=event.id, user_id=current_user.id).first() is not None
        event_assets = get_event_allowed_assets(event)
        event_asset_prices = get_prices_for_assets(event_assets)
        event_portfolios = EventPortfolio.query.filter_by(event_id=event.id).all()

        leaderboard = []
        for entry_portfolio in event_portfolios:
            stats = compute_event_portfolio(entry_portfolio, event_asset_prices)
            leaderboard.append(
                {
                    "username": entry_portfolio.user.username,
                    "total_value": stats["total_value"],
                    "pnl_percent": stats["pnl_percent"],
                }
            )
        leaderboard.sort(key=lambda item: item["pnl_percent"], reverse=True)

        event_cards.append(
            {
                "event": event,
                "status": status,
                "joined": joined,
                "participant_count": len(event_portfolios),
                "allowed_assets": [symbol.strip() for symbol in event.allowed_assets.split(",") if symbol.strip()],
                "leaderboard": leaderboard[:5],
            }
        )

    return render_template("events.html", event_cards=event_cards, portfolio=portfolio)


@app.route("/events/<slug>/join", methods=["POST"])
@login_required
def join_event(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()
    existing_entry = EventParticipant.query.filter_by(event_id=event.id, user_id=current_user.id).first()
    if not existing_entry and can_join_event(event):
        db.session.add(EventParticipant(event_id=event.id, user_id=current_user.id))
        get_or_create_event_portfolio(event, current_user)
        db.session.commit()
    return redirect(url_for("events"))


@app.route("/events/<slug>")
@login_required
def event_detail(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()
    participant = EventParticipant.query.filter_by(event_id=event.id, user_id=current_user.id).first()
    if not participant:
        return redirect(url_for("events"))
    event_status = classify_event_status(event)

    event_assets = get_event_allowed_assets(event)
    asset_map = {asset.symbol: asset for asset in event_assets}
    active_symbol = (request.args.get("symbol") or event_assets[0].symbol).upper() if event_assets else None
    selected_asset = asset_map.get(active_symbol) or (event_assets[0] if event_assets else None)

    portfolio = get_or_create_event_portfolio(event, current_user)
    price_map = get_prices_for_assets(event_assets)
    event_stats = compute_event_portfolio(portfolio, price_map)
    selected_position = get_event_position(portfolio, selected_asset) if selected_asset else None
    selected_price = price_map.get(selected_asset.symbol, get_fallback_price(selected_asset.symbol)) if selected_asset else 0.0

    leaderboard = []
    for entry_portfolio in EventPortfolio.query.filter_by(event_id=event.id).all():
        stats = compute_event_portfolio(entry_portfolio, price_map)
        leaderboard.append(
            {
                "username": entry_portfolio.user.username,
                "total_value": stats["total_value"],
                "pnl_percent": stats["pnl_percent"],
            }
        )
    leaderboard.sort(key=lambda item: item["pnl_percent"], reverse=True)

    recent_transactions = (
        EventTradeTransaction.query.filter_by(portfolio_id=portfolio.id)
        .order_by(EventTradeTransaction.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "event_detail.html",
        event=event,
        event_status=event_status,
        can_trade_event=can_trade_event(event),
        event_stats=event_stats,
        assets=event_assets,
        selected_asset=selected_asset,
        selected_chart_symbol=get_chart_symbol(selected_asset) if selected_asset else "",
        selected_chart_url=get_tradingview_embed_url(selected_asset) if selected_asset else "",
        selected_position=selected_position,
        selected_price=selected_price,
        active_symbol=selected_asset.symbol if selected_asset else "",
        leaderboard=leaderboard[:8],
        recent_transactions=recent_transactions,
        feedback=request.args.get("message", ""),
        feedback_type=request.args.get("message_type", "info"),
    )


@app.route("/events/<slug>/trade", methods=["POST"])
@login_required
def event_trade(slug):
    event = Event.query.filter_by(slug=slug).first_or_404()
    participant = EventParticipant.query.filter_by(event_id=event.id, user_id=current_user.id).first()
    if not participant:
        return redirect(url_for("events"))
    if not can_trade_event(event):
        status = classify_event_status(event)
        message = "Le trading n'est pas encore ouvert pour cet event." if status == "upcoming" else "Cet event est termine, le trading est ferme."
        return redirect(url_for("event_detail", slug=slug, message=message, message_type="error"))

    symbol = (request.form.get("symbol") or "").upper()
    side = (request.form.get("side") or "buy").lower()
    input_mode = (request.form.get("input_mode") or "amount").lower()
    asset = Asset.query.filter_by(symbol=symbol).first()
    allowed_symbols = {asset_item.symbol for asset_item in get_event_allowed_assets(event)}

    if not asset or asset.symbol not in allowed_symbols:
        return redirect(url_for("event_detail", slug=slug, message="Actif non autorise dans cet event.", message_type="error"))

    amount_usd = request.form.get("amount_usd", "").strip()
    quantity = request.form.get("quantity", "").strip()

    try:
        amount_value = float(amount_usd) if amount_usd else None
    except ValueError:
        amount_value = None

    try:
        quantity_value = float(quantity) if quantity else None
    except ValueError:
        quantity_value = None

    if side not in {"buy", "sell"}:
        return redirect(url_for("event_detail", slug=slug, symbol=symbol, message="Sens d'ordre invalide.", message_type="error"))
    if input_mode not in {"amount", "quantity"}:
        return redirect(url_for("event_detail", slug=slug, symbol=symbol, message="Mode de saisie invalide.", message_type="error"))
    if input_mode == "amount" and (amount_value is None or amount_value <= 0):
        return redirect(url_for("event_detail", slug=slug, symbol=symbol, message="Montant invalide.", message_type="error"))
    if input_mode == "quantity" and (quantity_value is None or quantity_value <= 0):
        return redirect(url_for("event_detail", slug=slug, symbol=symbol, message="Quantite invalide.", message_type="error"))

    portfolio = get_or_create_event_portfolio(event, current_user)
    success, message = execute_event_trade(
        portfolio,
        asset,
        side,
        amount_usd=amount_value if input_mode == "amount" else None,
        quantity=quantity_value if input_mode == "quantity" else None,
    )
    return redirect(
        url_for(
            "event_detail",
            slug=slug,
            symbol=symbol,
            message=message,
            message_type="success" if success else "error",
        )
    )


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
