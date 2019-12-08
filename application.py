import os
#export FLASK_APP=application
import sqlite3
import datetime
import calendar
import itertools
from collections import defaultdict
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

#from decimal import *
#import math

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


## Custom filter
#app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
#db = SQL("sqlite:///shopping.db")
#conn = sqlite3.connect('shopping.db')
#db = conn.cursor()
## Make sure API key is set
#if not os.environ.get("API_KEY"):
#    raise RuntimeError("API_KEY not set")


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Main page"""
    ID = session["user_id"]

    if request.method == "POST":
        units = request.form.get("unit_select")

        conn = sqlite3.connect('shopping.db')
        db = conn.cursor()

        # Update user's units
        db.execute("UPDATE users SET units = ? WHERE id = ?", (units, ID))
                ## optional thing I might add: update pantry and menu? ##
        conn.commit()
        conn.close()

        return render_template("index.html", units_selected=units)

    else:
        units = units_lookup(ID)[0]
        return render_template("index.html", units_selected=units)


@app.route("/shopping", methods=["GET", "POST"])
@login_required
def shopping_list():
    """Generate shopping list"""
    ID = session["user_id"]

    if request.method == "POST":
        date = request.form.get("week_beginning")
        session["date"] = date

        return redirect("shopping")

    else:
        if session.get("date") is None:
            date = datetime.date.today().strftime("%d-%m-%Y")
            session["date"] = date
        else:
            date = session["date"]

    weekday = findDay(date)
    dates = dates_days(date)

    all_data = meal_plan_import(ID, dates)

    # Filter on relevant dates
    dates_in_all_data = list(filter(lambda i: i['date'] in dates.keys(), all_data))

    # Select meals (returns a list)
    meals = list(map(lambda d: d['meal'], dates_in_all_data))

    # a = ingredients_lookup(ID, meals[1])[1]["ingredient"]

    all_ingredients = []
    all_quantity = []
    all_units = []

    for m in meals:
        recipes = ingredients_lookup(ID, m)
        for item in recipes:
            all_ingredients.append(item['ingredient'])
            all_quantity.append(item['quantity'])
            all_units.append(item['unit'])

    all_data = [{'ingredient': d, 'quantity': n, 'unit': m} for d, n, m in zip(all_ingredients, all_quantity, all_units)]

    all_ingredients = []
    all_quantity = []
    all_units = []

    pantry = pantry_lookup(ID)
    for item in pantry:
        all_ingredients.append(item['ingredient'])
        all_quantity.append(item['quantity'])
        all_units.append(item['unit'])

    # Pantry quantities are negative
    all_pantry = [{'ingredient': d, 'quantity': -n, 'unit': m} for d, n, m in
                zip(all_ingredients, all_quantity, all_units)]

    # Merge the two lists. Now all_data is the shopping list (positive quantities) and pantry (negative quantities)
    all_data = all_data + all_pantry

    # Sum quantity for each unique ingredient & quantity pair.
    # This will net out what is required for shopping and what is in the pantry already
    counts = defaultdict(lambda: [0, 0])
    for line in all_data:
        entry = counts[(line['ingredient'], line['unit'])]
        entry[0] += line['quantity']
        entry[1] += 1

    all_data_net = [{'ingredient': k[0], 'unit': k[1], 'quantity': v[0]}
                     for k, v in counts.items()]

    # Remove negative entries, which are things left in the pantry
    shopping_list = list(filter(lambda i: i['quantity'] > 0, all_data_net))

    return render_template("shopping.html", weekday=weekday, date=date, shopping_list=shopping_list)





def units_lookup(user_id):
    """Show ingredients"""
    conn = sqlite3.connect('shopping.db')

    db = conn.cursor()

    t = (user_id, )

    # Query database for user's units
    c = db.execute("SELECT units FROM users WHERE id = ?", t)
    output = c.fetchone()
    conn.close()

    return output


def findDay(date):
    date_convert = datetime.datetime.strptime(date, '%d-%m-%Y').weekday()
    return calendar.day_name[date_convert]


def findDate(date):
    date_convert = datetime.datetime.strptime(date, '%d-%m-%Y')
    return date_convert


def dates_days(date):
    """Dictionary with dates (keys) and weekdays (values)"""
    keys = []
    for i in range(0, 7):
        keys.append((findDate(date) + datetime.timedelta(days=i)).strftime('%d-%m-%Y'))

    values = []
    for i in keys:
        values.append(findDay(i))

    dates = dict(zip(keys, values))

    return dates


def meals_lookup(user_id):
    """Query database for meals specified by user"""
    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    c = db.execute("SELECT meal FROM meals WHERE id = ?", (user_id,))
    output = c.fetchall()
    conn.close()
    meals = []
    for i in output:
        meals.append(i[0])

    return meals


def meal_plan_import(user_id, dates):
    """Import meal plan (if already created)"""
    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    all_dates = []
    all_meal_numbers = []
    all_meals = []
    for i in list(dates.keys()):
        c = db.execute("SELECT date, meal_number, meal FROM meal_plan WHERE id = ? AND date = ?", (user_id, i))
        output = c.fetchall()
        for tup in output:
            all_dates.append(tup[0])
            all_meal_numbers.append(tup[1])
            all_meals.append(tup[2])
    conn.close()

    # Convert to a list of dictionaries (easier to look up)
    all_data = [{'date': d, 'meal_no': n, 'meal': m} for d, n, m in zip(all_dates, all_meal_numbers, all_meals)]

    return all_data


@app.route("/plan", methods=["GET", "POST"])
@login_required
def plan():
    """Define meal plan"""
    ID = session["user_id"]

    if session.get("meals") is None:
        meals = meals_lookup(ID)
        session["meals"] = meals
    else:
        meals = session["meals"]

    if request.method == "POST":
        date = request.form.get("week_beginning")
        #return str(findDate(date) + datetime.timedelta(days=7))

        weekday = findDay(date)

        dates = dates_days(date)

        session["date"] = date
        session["weekday"] = weekday
        session["dates"] = dates

        all_data = meal_plan_import(ID, dates)
        dates_in_all_data = list(filter(lambda i: i['date'] in dates.keys(), all_data))

        return render_template("plan.html", date=date, weekday=weekday, dates=dates, meals=meals,
                               dates_in_all_data=dates_in_all_data)

    else:
        if session.get("date") is None:
            date = datetime.date.today().strftime("%d-%m-%Y")
            session["date"] = date
        else:
            date = session["date"]

        if session.get("weekday") is None:
            weekday = findDay(date)
            session["weekday"] = weekday
        else:
            weekday = session["weekday"]

        if session.get("dates") is None:
            dates = dates_days(date)
            session["dates"] = dates
        else:
            dates = session["dates"]

        all_data = meal_plan_import(ID, dates)

        # Only return all_data for the selected dates to plan.html
        dates_in_all_data = list(filter(lambda i: i['date'] in dates.keys(), all_data))

        return render_template("plan.html", date=date, weekday=weekday, dates=dates, meals=meals,
                               dates_in_all_data=dates_in_all_data)


@app.route("/meal_plan", methods=["GET", "POST"])
@login_required
def meal_plan():
    """Update meal plan"""
    ID = session["user_id"]
    date = session["date"]

    dates_list = []
    for i in range(0, 7):
        dates_list.append((findDate(date) + datetime.timedelta(days=i)).strftime('%d-%m-%Y'))

    meal_number_list = [str(1), str(2), str(3)]
    all_form_items = list(
        map(
            lambda x: "".join(x),
            itertools.product(["meal["], dates_list, ["_"], meal_number_list, ["]"])
        )
    )

    all_meals = []
    for i in all_form_items:
        all_meals.append(request.form.get(i))

    all_dates = []
    for i in all_form_items:
        date = i.split('[', 1)[1].split('_')[0]
        all_dates.append(date)

    all_meal_numbers = []
    for i in all_form_items:
        meal_number = i.split('_', 1)[1].split(']')[0]
        all_meal_numbers.append(meal_number)

    # Combine all data into a list of dictionaries
    all_data = [{'date': d, 'meal_no': n, 'meal': m} for d, n, m in zip(all_dates, all_meal_numbers, all_meals)]

    all_data = list(filter(lambda i: i['meal'] is not None, all_data))

    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    # Update user's meal plan in database
    for i in all_data:
        db.execute("INSERT OR REPLACE INTO meal_plan (id, date, meal_number, meal) VALUES (?, ?, ?, ?)",
                   (ID, i.get("date"), i.get("meal_no"), i.get("meal")))
    conn.commit()
    conn.close()

    return redirect("plan")


@app.route("/pantry", methods=["GET"])
@login_required
def pantry():
    """Show pantry"""
    ingredients = pantry_lookup(user_id=session["user_id"])

    return render_template("pantry.html", ingredients=ingredients)


@app.route("/pantry_add", methods=["GET", "POST"])
@login_required
def pantry_add():
    """Add items to the pantry"""

    ingredient = request.form.get("update_ingredients[1]")
    quantity = request.form.get("update_ingredients[2]")
    units = request.form.get("update_ingredients[3]")

    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    t = (session["user_id"], ingredient, quantity, units)
    #return str(t)

    # Delete ingredient
    db.execute("INSERT INTO pantry VALUES(?, ?, ?, ?)", t)
    conn.commit()
    conn.close()

    updated_pantry = pantry_lookup(user_id=session["user_id"])

    return render_template("pantry.html", ingredients=updated_pantry)


@app.route("/pantry_delete", defaults={'ingredient': ''})  # If ingredient is blank, it can still be deleted.
@app.route("/pantry_delete/<ingredient>")
@login_required
def pantry_delete(ingredient):
    """Delete an ingredient from the pantry"""

    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    t = (session["user_id"], ingredient)

    # Delete ingredient
    db.execute("DELETE FROM pantry WHERE id = ? AND ingredient = ?", t)
    conn.commit()
    conn.close()

    updated_pantry = pantry_lookup(user_id=session["user_id"])

    return render_template("pantry.html", ingredients=updated_pantry)


def pantry_lookup(user_id):
    """Show ingredients"""
    conn = sqlite3.connect('shopping.db')
    conn.row_factory = sqlite3.Row  # To get column names returned with SQL query. Result of fetchone is now a dictionary

    db = conn.cursor()

    t = (user_id, )

    # Query database for ingredients in pantry
    c = db.execute("SELECT * FROM pantry WHERE id = ?", t)
    output = c.fetchall()
    conn.close()

    return output


def ingredients_lookup(user_id, meal):
    """Show ingredients"""
    conn = sqlite3.connect('shopping.db')
    conn.row_factory = sqlite3.Row  # To get column names returned with SQL query. Result of fetchone is now a dictionary

    db = conn.cursor()

    t = (user_id, meal)

    # Query database for ingredients in meal
    c = db.execute("SELECT * FROM recipes WHERE id = ? AND meal = ?", t)
    output = c.fetchall()
    conn.close()

    return output


@app.route("/meal", methods=["GET", "POST"])
@login_required
def meal():
    """Design your meal"""

    if request.method == "POST":

        session["meal_select"] = request.form.get("meal_select")
        ingredients = ingredients_lookup(user_id=session["user_id"], meal=session["meal_select"])

        return render_template("meal.html", meals=session["meals"], meal_selected=session["meal_select"],
                               ingredients=ingredients)
    else:
        meals = meals_lookup(session["user_id"])
        session["meals"] = meals

        return render_template("meal.html", meals=meals, meal_selected=None)


@app.route("/add_meal", methods=["POST"])
@login_required
def add_meal():
    """Design your meal"""
    new_meal = request.form.get("new_meal")

    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    # Query database to check if user has already created a meal with that name
    t = (session["user_id"], new_meal)

    c = db.execute("SELECT * FROM meals WHERE id = ? AND meal = ?", t)
    rows = c.fetchone()

    # Ensure meal does not already exist
    if rows is not None:
        conn.close()
        return apology("meal already exists", 400)

    db.execute("INSERT INTO meals(id, meal) VALUES(?, ?)", t)
    conn.commit()
    conn.close()

    return redirect("meal")


@app.route("/ingredients_delete", defaults={'ingredient': ''})  # If ingredient is blank, it can still be deleted.
@app.route("/ingredients_delete/<ingredient>")
@login_required
def ingredients_delete(ingredient):
    """Delete an ingredient from a meal"""

    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    t = (session["user_id"], session["meal_select"], ingredient)

    # Delete ingredient
    db.execute("DELETE FROM recipes WHERE id = ? AND meal = ? AND ingredient = ?", t)
    conn.commit()
    conn.close()

    ingredients = ingredients_lookup(user_id=session["user_id"], meal=session["meal_select"])

    return render_template("meal.html", meals=session["meals"], meal_selected=session["meal_select"],
                           ingredients=ingredients)


@app.route("/ingredients_add", methods=["GET", "POST"])
@login_required
def ingredients_add():
    """Add an ingredient to a meal"""

    ingredient = request.form.get("update_ingredients[1]")
    quantity = request.form.get("update_ingredients[2]")
    units = request.form.get("update_ingredients[3]")

    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    # Ensure a meal has been selected
    if session.get("meal_select") is None:
        return apology("must select a meal", 400)


    t = (session["user_id"], session["meal_select"], ingredient, quantity, units)

    # Add ingredient to database
    db.execute("INSERT INTO recipes VALUES(?, ?, ?, ?, ?)", t)
    conn.commit()
    conn.close()

    updated_ingredients = ingredients_lookup(user_id=session["user_id"], meal=session["meal_select"])

    return render_template("meal.html", meals=session["meals"], meal_selected=session["meal_select"],
                           ingredients=updated_ingredients)


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""

    username = request.form.get("username")

    conn = sqlite3.connect('shopping.db')
    db = conn.cursor()

    # Query database for usernames

    taken = db.execute("SELECT username FROM users").fetchone()

    conn.close()
    return apology(str(taken), 400)
    if not len(str(username)) > 0:
        return jsonify(False)
    for taken_username in taken:
        if username == taken_username["username"]:
            return jsonify(False), 400

    return jsonify(True), 200


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

        conn = sqlite3.connect('shopping.db')
        conn.row_factory = sqlite3.Row # To get column names returned with SQL query. Result of fetchone is now a dictionary
        db = conn.cursor()

        # Query database for username
        t = (request.form.get("username"),)
        c = db.execute("SELECT * FROM users WHERE username = ?", t)
        rows = c.fetchone()
        conn.close()

        # Ensure username exists and password is correct
        if rows is None or not check_password_hash(rows["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows["id"]

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


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password matches
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 400)

        conn = sqlite3.connect('shopping.db')
        db = conn.cursor()

        # Query database for username
        t = (request.form.get("username"),)

        c = db.execute("SELECT * FROM users WHERE username = ?", t)
        rows = c.fetchone()

        # Ensure username does not already exist
        check()

        # Ensure username does not already exist
        if rows is not None:
            return apology("username already exists", 400)

        # Add username and password to database
        else:
            username = request.form.get("username")
            hash = generate_password_hash(request.form.get("password"))
            user_hash = (username, hash)
            db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", user_hash)

        # Remember which user has logged in
        t = (request.form.get("username"),)
        c = db.execute("SELECT id FROM users WHERE username = ?", t)
        session["user_id"] = c.fetchone()[0]

        conn.commit()
        conn.close()
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
