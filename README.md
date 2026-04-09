# Trading App

Application web de simulation d'investissement construite avec Flask.

Le projet permet de :
- gerer un compte utilisateur avec inscription / connexion
- investir sur plusieurs cryptos via les prix Binance
- investir sur des actions et ETFs via les prix Yahoo Finance
- passer des ordres simples avec montant libre
- suivre un portefeuille global
- participer a des events hebdomadaires avec portefeuille separe

## Stack

- Python 3
- Flask
- Flask-Login
- Flask-SQLAlchemy
- SQLite
- Binance Market Data API
- Yahoo Finance quote endpoint
- TradingView widget pour les graphiques

## Important

Le projet n'utilise plus `yfinance` au runtime.

Les prix des actions et ETFs sont recuperes directement via une requete HTTP Yahoo Finance, ce qui evite les problemes de cache local et de fichiers temporaires sur des machines differentes.

## Installation

Depuis la racine du projet :

```powershell
python -m pip install --user -r requirements.txt
```

## Lancer le projet

```powershell
python app.py
```

Puis ouvrir :

```text
http://127.0.0.1:5000
```

## Fonctionnalites principales

### Dashboard

- selection d'actifs crypto / actions / ETFs
- affichage du prix live
- portefeuille global
- ordres `market` et `limit`
- historique recent

### Classement

- classement global base sur la valeur totale du portefeuille

### Events

- inscription a un event hebdomadaire
- portefeuille dedie a l'event
- trading separe du portefeuille principal
- leaderboard propre a l'event
- respect des fenetres `upcoming`, `live`, `finished`

## Structure du projet

```text
trading-app/
├── app.py
├── requirements.txt
├── trading_game.db
├── instance/
└── templates/
    ├── dashboard.html
    ├── classement.html
    ├── events.html
    ├── event_detail.html
    ├── login.html
    └── register.html
```

## Travail en equipe

Pour limiter les conflits Git sur un repo partage :

- ne pas commit `.venv/`, `__pycache__/`, `.tmp/` ou les fichiers systeme
- eviter de commit une base SQLite locale modifiee si ce n'est pas necessaire
- installer les dependances localement avec `requirements.txt`
- utiliser des branches courtes et des commits frequents
- pull souvent avant de push

## Recommandations Git

Flux simple conseille :

```powershell
git checkout -b feature/nom-court
git add .
git commit -m "Ajoute ..."
git pull --rebase origin <branche-principale>
git push origin feature/nom-court
```

## Notes

- les graphiques sont affiches via TradingView
- les prix sont caches quelques secondes pour accelerer le chargement
- la base SQLite actuelle est adaptee a un projet de demo / cours

