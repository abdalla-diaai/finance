import os
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

sql_statements = [ 
    """CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY,
        symbol TEXT NOT NULL,
        name TEXT NOT NULL,
        shares INTEGER NOT NULL,
        price TEXT NOT NULL,
        type TEXT NOT NULL,
        time datetime default current_timestamp, 
        user_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) 
        );""",

        """CREATE TABLE IF NOT EXISTS portfolio (
        id INTEGER PRIMARY KEY,
        symbol TEXT NOT NULL UNIQUE,
        shares INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) 
        );"""   
]

with sqlite3.connect("finance.db") as db:
        cursor = db.cursor()
        for statement in sql_statements:
            cursor.execute(statement)
        db.commit()

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    current_portfolio = []
    current_prices = []
    grand_total = 0
    with sqlite3.connect("finance.db") as db:
        db.row_factory = sqlite3.Row
        user_data = db.execute("SELECT * FROM users WHERE id = ?", (user_id, )).fetchall()
        cash = user_data[0]["cash"]
        owned_shares = db.execute("SELECT * FROM portfolio WHERE user_id = ?", (user_id, )).fetchall()
        for i in range(0, len(owned_shares)):
            current_prices.append(lookup(owned_shares[i]["symbol"])["price"])
        
        for i in range(0, len(owned_shares)):
            current_portfolio.append(
                {
                    "name": owned_shares[i]["symbol"],
                    "number": owned_shares[i]["shares"],
                    "price": current_prices[i],
                    "total": (owned_shares[i]["shares"] * current_prices[i]),
                }
            )
            grand_total += owned_shares[i]["shares"] * current_prices[i]
        grand_total += cash
        if not user_data:  # If no data is returned
            flash("User data not found", "error")
            return redirect("/register")  # Or some other error page

        return render_template("index.html", cash = cash, current_portfolio = current_portfolio, grand_total = grand_total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        stock=request.form.get("symbol")
        shares_number = request.form.get("shares")
        user_id = session["user_id"]
        quote = lookup(stock)
        transaction = quote["price"] * int(shares_number)
        if quote:
            with sqlite3.connect("finance.db") as db:
                db.row_factory = sqlite3.Row
                user_data = db.execute("SELECT * FROM users WHERE id = ?", (user_id, )).fetchall()
                if user_data[0]["cash"] > transaction:
                    db.execute("INSERT INTO transactions (symbol, name, shares, price, user_id, type) VALUES(?, ?, ?, ?, ?, ?)", (stock, quote["name"], shares_number, quote["price"], user_id, "Buy"))

                    db.execute("INSERT OR REPLACE INTO portfolio (symbol, shares, user_id) VALUES (?, COALESCE((SELECT shares FROM portfolio WHERE symbol = ? AND user_id = ?), 0) + ?, ?)", (stock, stock, user_id, shares_number, user_id))

                    db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", (transaction, user_id))
                    flash(f"Bought!", category="success")
                    return redirect("/")
                else:
                    flash(f"No enough cash!", category="warning")
                    return render_template("buy.html")
        else:
            return apology("TODO")
    return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    with sqlite3.connect("finance.db") as db:
        db.row_factory = sqlite3.Row
        transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", (user_id, )).fetchall()
        if transactions:
            return render_template("history.html", transactions=transactions)
        else:
            flash(f"No transactions!", category="warning")
            return render_template("history.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        with sqlite3.connect("finance.db") as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM users WHERE username = ?", (request.form.get("username"), )
            ).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock=request.form.get("symbol")
        price = lookup(stock)
        if price:
            return render_template("quoted.html", price=price)
        else:
            flash(f"Stock symbol does not exist!", category="warning")
    return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        hash = generate_password_hash(request.form.get("password"))
        with sqlite3.connect("finance.db") as db:
            # handle error in registration
            try:
                db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", (username, hash))
                flash(f"Successfully registered!", category="success")
                return redirect("/login")
            except sqlite3.IntegrityError:
                flash(f"Username already exists!", category="warning")
                return render_template("register.html")
        
    return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    with sqlite3.connect("finance.db") as db:
            db.row_factory = sqlite3.Row
            user_shares = db.execute("SELECT DISTINCT symbol FROM portfolio").fetchall()
    if request.method == "POST":
        stock=request.form.get("symbol")
        shares_number = request.form.get("shares")
        user_id = session["user_id"]
        quote = lookup(stock)
        transaction = quote["price"] * int(shares_number)
        if quote:
            with sqlite3.connect("finance.db") as db:
                db.row_factory = sqlite3.Row
                available_shares = db.execute("SELECT shares FROM portfolio WHERE user_id = ? AND symbol = ?", (user_id, stock)).fetchall()
                if int(shares_number) <= available_shares[0][0]:
                    db.execute("INSERT INTO transactions (symbol, name, shares, price, user_id, type) VALUES(?, ?, ?, ?, ?, ?)", (stock, quote["name"], shares_number, quote["price"], user_id, "Sell"))

                    db.execute("INSERT OR REPLACE INTO portfolio (symbol, shares, user_id) VALUES (?, COALESCE((SELECT shares FROM portfolio WHERE symbol = ? AND user_id = ?), 0) - ?, ?)", (stock, stock, user_id, shares_number, user_id))

                    db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", (transaction, user_id))
                    flash(f"Sold!", category="success")
                    return redirect("/")
                else:
                    flash(f"Not enough shares! Available shares: {available_shares[0][0]}", category="warning")
                    return redirect("/sell")
        else:
            return apology("TODO")
    return render_template("sell.html", user_shares=user_shares)
