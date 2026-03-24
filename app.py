from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import requests
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cle_secrete_123'
# On force le chemin de la BDD pour éviter les problèmes de dossier "instance"
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'trading_game.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
with app.app_context():
    db.create_all()
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODÈLES ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) 
    balance = db.Column(db.Float, default=10000.0)
    btc_quantity = db.Column(db.Float, default=0.0)
    transactions = db.relationship('Transaction', backref='owner', lazy=True)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10)) 
    price = db.Column(db.Float)
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- FONCTION PRIX ---
def get_btc_price():
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=2)
        return float(r.json()['price'])
    except:
        return 70000.0 # Prix par défaut si l'API bug

# --- ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # --- AJOUTE CE BLOC ICI ---
        # On vérifie si l'utilisateur existe déjà avant de l'ajouter
        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            return "Désolé, ce pseudo est déjà utilisé. Choisis-en un autre !"
        # ---------------------------

        # Si le pseudo est libre, on continue l'inscription normalement
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form['username']).first()
        if user and bcrypt.check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template("login.html")

@app.route("/")
@login_required
def dashboard():
    price = get_btc_price()
    
    # Calcul de la valeur totale actuelle
    total_value = current_user.balance + (current_user.btc_quantity * price)
    
    # Calcul du profit/perte par rapport aux 10 000 $ de départ
    initial_balance = 10000.0
    pnl = total_value - initial_balance
    pnl_percent = (pnl / initial_balance) * 100
    
    history = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.timestamp.desc()).limit(10).all()
    
    return render_template("dashboard.html", 
                           user=current_user, 
                           btc_price=price, 
                           history=history,
                           total_value=total_value,
                           pnl=pnl,
                           pnl_percent=pnl_percent)

@app.route("/api/data")
def api_data():
    return jsonify({"btc_price": get_btc_price()})

@app.route("/buy", methods=["POST"])
@login_required
def buy_btc():
    price = get_btc_price()
    if current_user.balance >= 1000:
        qty = 1000 / price
        current_user.balance -= 1000
        current_user.btc_quantity += qty
        tx = Transaction(type='ACHAT', price=price, amount=qty, owner=current_user)
        db.session.add(tx)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route("/sell", methods=["POST"])
@login_required
def sell_all():
    if current_user.btc_quantity > 0:
        price = get_btc_price()
        val = current_user.btc_quantity * price
        tx = Transaction(type='VENTE', price=price, amount=current_user.btc_quantity, owner=current_user)
        db.session.add(tx)
        current_user.balance += val
        current_user.btc_quantity = 0
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/classement")
@login_required
def classement():
    users = User.query.all()
    leaderboard = []
    
    price = get_btc_price()
    
    for u in users:
        # Calcul de la valeur totale pour chaque utilisateur
        total_value = u.balance + (u.btc_quantity * price)
        pnl = total_value - 10000.0
        pnl_percent = (pnl / 10000.0) * 100
        
        leaderboard.append({
            'username': u.username,
            'total_value': total_value,
            'pnl_percent': pnl_percent
        })
    
    # Tri du plus riche au moins riche
    leaderboard = sorted(leaderboard, key=lambda x: x['total_value'], reverse=True)
    
    return render_template("classement.html", leaderboard=leaderboard)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

