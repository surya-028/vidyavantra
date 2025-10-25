# vidyavantra_backend/database.py

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def init_db(app):
    """Initializes the database with the Flask app."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
    print("Database initialized and tables created.")

