from app import app, db, User

def reset_admin_password():
    with app.app_context():
        try:
            # Find admin user or create new one
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(username='admin')
                db.session.add(admin)
            
            # Set new password
            admin.set_password('admin123')
            db.session.commit()
            print("Admin password has been reset successfully!")
            print("Username: admin")
            print("Password: admin123")
            
        except Exception as e:
            print(f"Error resetting password: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    reset_admin_password() 