from flask import Blueprint, render_template

views = Blueprint("views", __name__)


@views.get("/")
def dashboard():
    return render_template("dashboard.html")
