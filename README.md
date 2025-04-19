# Billing System

A comprehensive billing and invoice management system built with Flask.

## Features

### User Management
- Secure user authentication and authorization
- Admin and regular user roles
- Password hashing for security

### Product Management
- Add, edit, and delete products
- Product details include name, price, GST rate, and quantity
- Track product inventory
- Hide/Show products functionality

### Invoice Management
- Create professional invoices
- Add multiple products to invoice
- Automatic GST calculation
- Real-time total calculation
- PDF generation with QR codes
- Invoice history tracking
- Download invoices as PDF

### PDF Features
- Professional layout with company branding
- QR code generation for each invoice
- Detailed product listing
- GST breakdown
- Payment information
- Terms and conditions
- Modern color scheme and styling

### Email Integration
- Send invoices via email
- Professional email templates
- PDF attachments
- Configurable email settings

### Database Features
- SQLite database for data storage
- Efficient data relationships
- Transaction support
- Data integrity checks

### Security Features
- User authentication
- Session management
- CSRF protection
- Secure password storage

## Technical Stack
- Python 3.x
- Flask 2.0.1
- SQLAlchemy
- ReportLab 4.4.0 for PDF generation
- QR Code generation
- Flask-Login for authentication
- Bootstrap for frontend

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Vahulthasan/billing_system.git
cd billing_system
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Initialize the database:
```bash
python init_db.py
```

4. Run the application:
```bash
python app.py
```

## Default Login
- Username: admin
- Password: admin123

## Environment Variables
Create a `.env` file with the following:
```
SECRET_KEY=your-secret-key
EMAIL_USERNAME=your-email
EMAIL_PASSWORD=your-email-password
```

## Project Structure
```
billing_system/
├── app.py              # Main application file
├── models.py           # Database models
├── generate_invoice.py # Invoice generation logic
├── init_db.py         # Database initialization
├── requirements.txt    # Project dependencies
├── static/            # Static files (CSS, JS)
└── templates/         # HTML templates
```

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
This project is licensed under the MIT License.
