# Billing System

A comprehensive billing and invoice management system built with Flask.

## Features

- Product Management
  - Add, edit, and delete products
  - Track product inventory
  - Set product prices and GST rates

- Invoice Generation
  - Create professional invoices
  - Add multiple products with quantities
  - Automatic GST calculation
  - PDF generation and download
  - Store invoice history

- User Management
  - Secure user authentication
  - Role-based access control
  - Password hashing

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Vahulthasan/billing_system.git
cd billing_system
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Initialize the database:
```bash
python app.py
# In another terminal:
curl http://localhost:5000/initialize
python create_test_user.py
```

## Usage

1. Start the application:
```bash
python app.py
```

2. Access the application:
- Open http://localhost:5000 in your browser
- Login with test credentials:
  - Username: test
  - Password: test123

3. Create an invoice:
- Go to "Create Invoice"
- Search and add products
- Fill customer details
- Generate and download PDF invoice

## Technologies Used

- Backend: Flask, SQLAlchemy
- Database: SQLite
- PDF Generation: ReportLab
- Frontend: HTML, CSS, JavaScript, Bootstrap
- Authentication: Flask-Login
- Deployment: Render

## Project Structure

```
billing_system/
├── app.py              # Main application file
├── models.py           # Database models
├── generate_invoice.py # Invoice generation logic
├── requirements.txt    # Project dependencies
├── static/            # Static files (CSS, JS)
├── templates/         # HTML templates
└── instance/         # Database and instance files
```

## Features in Detail

### Product Management
- Add new products with name, price, GST rate, and stock quantity
- Edit existing product details
- Delete products
- Search products by name
- Track product inventory

### Invoice Generation
- Select multiple products with quantities
- Real-time calculation of subtotal, GST, and total
- Professional PDF invoice generation
- Download generated invoices
- Store invoice history
- View and regenerate past invoices

### User Management
- Secure login system
- Password hashing for security
- Role-based access control
- Session management

## API Endpoints

### Authentication
- `/login` - User login
- `/logout` - User logout

### Products
- `/add_product` - Add new product
- `/edit_product/<id>` - Edit existing product
- `/delete_product/<id>` - Delete product

### Invoices
- `/create_invoice` - Create new invoice
- `/generate_invoice` - Generate invoice PDF
- `/download_invoice/<number>` - Download invoice
- `/invoices` - View all invoices
- `/invoice/<id>` - View specific invoice

## Contributing

1. Fork the repository
2. Create a new branch (`git checkout -b feature/improvement`)
3. Make your changes
4. Commit your changes (`git commit -am 'Add new feature'`)
5. Push to the branch (`git push origin feature/improvement`)
6. Create a Pull Request

## License

This project is licensed under the MIT License. 