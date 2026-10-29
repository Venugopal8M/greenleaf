"""GreenLeaf Grocers - Inventory & Sales Management System (Flask application factory)."""
import os

from flask import Flask, flash, redirect, render_template, url_for

import database
from routes import bp

BASE = os.path.dirname(os.path.abspath(__file__))


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
        DATABASE=os.path.join(BASE, "greenleaf.db"),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    database.init_db(app.config["DATABASE"])
    app.teardown_appcontext(database.close_db)
    app.register_blueprint(bp)

    @app.errorhandler(404)
    def not_found(_e):
        flash("That page does not exist.", "error")
        return redirect(url_for("main.home"))

    @app.errorhandler(413)
    def too_big(_e):
        flash("That file is too large (2 MB maximum).", "error")
        return redirect(url_for("main.products"))

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("login.html", fatal=True), 500

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
