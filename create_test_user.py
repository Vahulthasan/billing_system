from app import app, db
from models import User

def create_test_user():
    with app.app_context():
        # Check if test user exists
        test_user = User.query.filter_by(username='test').first()
        if not test_user:
            # Create test user if it doesn't exist
            test_user = User(username='test', password='test123')
            db.session.add(test_user)
            db.session.commit()
            print("Test user created successfully!")
        else:
            # Reset password if user exists
            test_user.set_password('test123')
            db.session.commit()
            print("Test user password reset successfully!")

if __name__ == '__main__':
    create_test_user() 