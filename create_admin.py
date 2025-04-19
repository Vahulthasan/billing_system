from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
import os

# Create a minimal Flask application
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///billing.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define minimal User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

def create_admin():
    with app.app_context():
        try:
            # Create tables if they don't exist
            db.create_all()
            
            # Check if admin exists
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                # Create new admin user
                admin = User(
                    username='admin',
                    password_hash=generate_password_hash('admin123')
                )
                db.session.add(admin)
            else:
                # Update existing admin's password
                admin.password_hash = generate_password_hash('admin123')
            
            db.session.commit()
            print("Admin user created/updated successfully!")
            print("Username: admin")
            print("Password: admin123")
            
        except Exception as e:
            print(f"Error: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    create_admin() 