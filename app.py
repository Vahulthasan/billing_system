import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import stripe
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import requests
from flask_mail import Mail, Message
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from datetime import datetime, timedelta
import io
import jwt
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
import sqlite3
from dotenv import load_dotenv

from models import db, User, Product, Invoice, InvoiceItem

# Load environment variables
load_dotenv()

# Get GitHub token from environment
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# Ensure instance folder exists and build absolute path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_PATH, exist_ok=True)

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Database configuration
if os.getenv('RENDER'):
    # Use SQLite for Render deployment
    db_path = os.path.join(os.getcwd(), 'instance', 'billing_system.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
else:
    # Local development database
    db_path = os.path.join(INSTANCE_PATH, 'billing_system.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Stripe (Optional)
stripe.api_key = 'your_stripe_secret_key'

# Mailtrap (Optional)
app.config['MAIL_SERVER'] = 'smtp.mailtrap.io'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'your_username'
app.config['MAIL_PASSWORD'] = 'your_password'
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

# Login manager
login_manager = LoginManager(app)
login_manager.login_view = "login"

# Windsurf Token Configuration
WINDSURF_TOKEN = 'your-token-here'

# Fast2SMS Configuration
FAST2SMS_API_KEY = 'your-api-key-here'
FAST2SMS_URL = 'https://www.fast2sms.com/dev/bulkV2'

# Email Configuration
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
EMAIL_USERNAME = 'your-email@gmail.com'
EMAIL_PASSWORD = 'your-app-password'

# Initialize extensions
db.init_app(app)

# User loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    search_query = request.args.get('search', '')
    if search_query:
        products = Product.query.filter(Product.name.ilike(f'%{search_query}%')).all()
    else:
        products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

def send_sms(phone_number, message):
    try:
        payload = {
            'authorization': FAST2SMS_API_KEY,
            'message': message,
            'language': 'english',
            'route': 'q',
            'numbers': phone_number
        }
        headers = {
            'authorization': FAST2SMS_API_KEY,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        response = requests.post(FAST2SMS_URL, data=payload, headers=headers)
        return response.json()
    except Exception as e:
        print(f"Error sending SMS: {str(e)}")
        return None

def send_email(to_email, subject, body, attachment=None):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        if attachment:
            part = MIMEApplication(attachment, Name="invoice.pdf")
            part['Content-Disposition'] = f'attachment; filename="invoice.pdf"'
            msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

@app.route('/generate_bill', methods=['POST'])
@login_required
def generate_bill():
    if request.method == 'POST':
        try:
            product_ids = request.form.getlist('products')
            quantities = request.form.getlist('quantities')
            payment_method = request.form.get('payment_method')
            phone_number = request.form.get('phone_number')
            
            # Get customer details from form
            customer_name = request.form.get('customer_name')
            customer_address = request.form.get('customer_address')
            customer_gstin = request.form.get('customer_gstin')

            if not all([product_ids, quantities, payment_method, customer_name, customer_address]):
                flash('Please fill in all required fields', 'danger')
                return redirect(url_for('index'))

            # Generate invoice number
            last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
            invoice_number = f"INV{datetime.now().year}-{str(last_invoice.id + 1).zfill(3) if last_invoice else '001'}"

            # Calculate total amount
            total_amount = 0
            invoice_items = []

            for product_id, quantity in zip(product_ids, quantities):
                product = Product.query.get(product_id)
                if product and int(quantity) > 0:
                    if product.quantity < int(quantity):
                        flash(f'Not enough stock for {product.name}', 'danger')
                        return redirect(url_for('index'))
                    
                    total_amount += product.price * int(quantity)
                    invoice_items.append({
                        'product': product,
                        'quantity': int(quantity)
                    })

            # Create invoice
            invoice = Invoice(
                invoice_number=invoice_number,
                customer_name=customer_name,
                customer_address=customer_address,
                customer_gstin=customer_gstin,
                total_amount=total_amount,
                payment_method=payment_method,
                status='Pending',
                user_id=current_user.id
            )
            db.session.add(invoice)
            db.session.commit()

            # Create invoice items and update stock
            for item in invoice_items:
                invoice_item = InvoiceItem(
                    invoice_id=invoice.id,
                    product_id=item['product'].id,
                    quantity=item['quantity']
                )
                db.session.add(invoice_item)
                
                # Update product stock
                item['product'].quantity -= item['quantity']
                db.session.add(item['product'])

            db.session.commit()

            # Send notifications
            if phone_number:
                send_sms_notification(phone_number, invoice)
            
            send_email_notification(current_user.email, invoice)

            flash('Invoice generated successfully!', 'success')
            return redirect(url_for('view_invoice', invoice_id=invoice.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error generating invoice: {str(e)}', 'danger')
            return redirect(url_for('index'))

@app.route('/invoices')
@login_required
def view_invoices():
    invoices = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.date.desc()).all()
    return render_template('invoices.html', invoices=invoices)

@app.route('/invoice/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('index'))
    return render_template('invoice.html', invoice=invoice, timedelta=timedelta)

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        gst_rate = float(request.form['gst_rate'])
        new_product = Product(name=name, price=price, gst_rate=gst_rate)
        db.session.add(new_product)
        db.session.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('add_product.html')

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        product.name = request.form['name']
        product.price = float(request.form['price'])
        product.quantity = int(request.form['quantity'])
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('index'))

    return render_template('edit_product.html', product=product)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get(product_id)
    if product:
        db.session.delete(product)
        db.session.commit()
        flash('Product deleted successfully!', 'success')
    else:
        flash('Product not found!', 'danger')
    return redirect(url_for('index'))

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return {'message': 'Token is missing'}, 401
        try:
            data = jwt.decode(token, WINDSURF_TOKEN, algorithms=['RS256'])
            current_user = User.query.filter_by(email=data['email']).first()
            if not current_user:
                return {'message': 'User not found'}, 401
        except jwt.ExpiredSignatureError:
            return {'message': 'Token has expired'}, 401
        except jwt.InvalidTokenError:
            return {'message': 'Invalid token'}, 401
        return f(current_user, *args, **kwargs)
    return decorated

@app.route('/api/generate_token', methods=['POST'])
def generate_token():
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return {'message': 'Could not verify'}, 401
    
    user = User.query.filter_by(username=auth.username).first()
    if not user or user.password != auth.password:
        return {'message': 'Invalid credentials'}, 401
    
    token = jwt.encode({
        'email': user.username,  # Assuming username is email
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, WINDSURF_TOKEN, algorithm='RS256')
    
    return {'token': token}

@app.route('/api/invoices', methods=['GET'])
@token_required
def api_invoices(current_user):
    invoices = Invoice.query.filter_by(user_id=current_user.id).all()
    return {
        'invoices': [{
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'date': invoice.date.isoformat(),
            'total': invoice.total_amount,
            'payment_status': invoice.status,
            'payment_method': invoice.payment_method
        } for invoice in invoices]
    }

@app.route('/api/invoice/<int:invoice_id>', methods=['GET'])
@token_required
def api_invoice(current_user, invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.user_id != current_user.id:
        return {'message': 'Unauthorized access'}, 403
    
    return {
        'invoice': {
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'date': invoice.date.isoformat(),
            'total': invoice.total_amount,
            'payment_status': invoice.status,
            'payment_method': invoice.payment_method,
            'items': [{
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': item.price,
                'subtotal': item.subtotal
            } for item in invoice.items]
        }
    }

def send_email_notification(email, invoice):
    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USERNAME
        msg['To'] = email
        msg['Subject'] = f"Invoice #{invoice.invoice_number} - Your Store Name"

        # Create email body
        body = f"""
        Dear Customer,

        Thank you for your purchase! Please find below the details of your invoice:

        Invoice Number: {invoice.invoice_number}
        Date: {invoice.date.strftime('%d-%b-%Y')}
        Total Amount: ₹{invoice.total_amount * 1.18:.2f}
        Payment Method: {invoice.payment_method.title()}

        You can view and download your invoice from our system.

        Best regards,
        Your Store Name
        """

        msg.attach(MIMEText(body, 'plain'))

        # Generate PDF and attach
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer)
        
        # Add company header
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, 800, "Your Store Name")
        p.setFont("Helvetica", 12)
        p.drawString(50, 780, "123 Business Street")
        p.drawString(50, 760, "City, State - 123456")
        p.drawString(50, 740, "GSTIN: 12ABCDE1234F1Z5")
        p.drawString(50, 720, "Phone: +91 9876543210")

        # Add invoice details
        p.setFont("Helvetica-Bold", 14)
        p.drawString(400, 800, f"Invoice #{invoice.invoice_number}")
        p.setFont("Helvetica", 12)
        p.drawString(400, 780, f"Date: {invoice.date.strftime('%d-%m-%Y')}")

        # Add customer details
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, 680, "Bill To:")
        p.setFont("Helvetica", 12)
        p.drawString(50, 660, invoice.customer_name)
        p.drawString(50, 640, invoice.customer_address)
        p.drawString(50, 620, f"GSTIN: {invoice.customer_gstin}")
        p.drawString(50, 600, f"Phone: {invoice.customer_phone}")

        # Add items table
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, 560, "Item")
        p.drawString(200, 560, "Quantity")
        p.drawString(300, 560, "Unit Price")
        p.drawString(400, 560, "GST Rate")
        p.drawString(500, 560, "Total")

        y = 540
        for item in invoice.items:
            p.setFont("Helvetica", 12)
            p.drawString(50, y, item.product.name)
            p.drawString(200, y, str(item.quantity))
            p.drawString(300, y, f"₹{item.product.price}")
            p.drawString(400, y, f"{item.product.gst_rate}%")
            p.drawString(500, y, f"₹{item.quantity * item.product.price}")
            y -= 20

        # Add totals
        p.setFont("Helvetica-Bold", 12)
        p.drawString(400, y-20, f"Subtotal: ₹{invoice.subtotal:.2f}")
        p.drawString(400, y-40, f"GST: ₹{invoice.gst_amount:.2f}")
        p.drawString(400, y-60, f"Total: ₹{invoice.total:.2f}")

        # Add payment method and status
        p.drawString(50, y-100, f"Payment Method: {invoice.payment_method}")
        p.drawString(50, y-120, "Status: Paid")

        # Add terms and conditions
        p.setFont("Helvetica", 10)
        p.drawString(50, y-160, "Terms and Conditions:")
        p.drawString(50, y-180, "1. Payment is due within 30 days")
        p.drawString(50, y-200, "2. Please include invoice number in payment reference")
        p.drawString(50, y-220, "3. For any queries, contact accounts@company.com")

        p.save()
        buffer.seek(0)

        attachment = MIMEApplication(buffer.getvalue(), _subtype='pdf')
        attachment.add_header('Content-Disposition', 'attachment', 
                            filename=f"invoice_{invoice.invoice_number}.pdf")
        msg.attach(attachment)

        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True

    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

def send_sms_notification(phone_number, invoice):
    if not FAST2SMS_API_KEY:
        return False
    
    try:
        url = "https://www.fast2sms.com/dev/bulkV2"
        payload = {
            "route": "v3",
            "sender_id": "FTWSMS",
            "message": f"Thank you for your purchase! Invoice #{invoice.invoice_number} has been generated. Total amount: ₹{invoice.total_amount * 1.18:.2f}",
            "language": "english",
            "flash": 0,
            "numbers": phone_number
        }
        headers = {
            "authorization": FAST2SMS_API_KEY,
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers)
        return response.json().get('return', False)
    
    except Exception as e:
        print(f"Error sending SMS: {str(e)}")
        return False

def generate_invoice_pdf(invoice_id):
    """Generate a professional PDF invoice using SQLite data"""
    conn = sqlite3.connect('instance/billing_system.db')
    cursor = conn.cursor()

    # Fetch invoice details
    cursor.execute("""
        SELECT i.id, i.invoice_number, i.customer_name, i.customer_address, 
               i.customer_gstin, i.customer_phone, i.date, i.payment_method,
               i.subtotal, i.gst_amount, i.total
        FROM invoice i
        WHERE i.id = ?
    """, (invoice_id,))
    invoice = cursor.fetchone()

    if not invoice:
        print("Invoice not found")
        return None

    # Fetch invoice items
    cursor.execute("""
        SELECT p.name, ii.quantity, ii.unit_price, ii.gst_rate, ii.total
        FROM invoice_item ii
        JOIN product p ON ii.product_id = p.id
        WHERE ii.invoice_id = ?
    """, (invoice_id,))
    items = cursor.fetchall()

    conn.close()

    # Generate PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Add company header with logo
    p.setFont("Helvetica-Bold", 20)
    p.drawString(50, height - 50, "Your Company Name")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 70, "123 Business Street")
    p.drawString(50, height - 85, "City, State - 123456")
    p.drawString(50, height - 100, "GSTIN: 12ABCDE1234F1Z5")
    p.drawString(50, height - 115, "Phone: +91 9876543210")
    p.drawString(50, height - 130, "Email: contact@company.com")

    # Add invoice details box
    p.setFillColor(colors.lightgrey)
    p.rect(width - 200, height - 100, 150, 80, fill=1)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(width - 190, height - 50, f"Invoice #{invoice[1]}")
    p.setFont("Helvetica", 12)
    p.drawString(width - 190, height - 70, f"Date: {invoice[6].strftime('%d-%m-%Y')}")
    p.drawString(width - 190, height - 85, f"Status: Paid")

    # Add customer details
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 180, "Bill To:")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 200, invoice[2])
    p.drawString(50, height - 215, invoice[3])
    p.drawString(50, height - 230, f"GSTIN: {invoice[4]}")
    p.drawString(50, height - 245, f"Phone: {invoice[5]}")

    # Add items table header
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 300, "Item")
    p.drawString(200, height - 300, "Quantity")
    p.drawString(300, height - 300, "Unit Price")
    p.drawString(400, height - 300, "GST Rate")
    p.drawString(500, height - 300, "Total")

    # Draw table lines
    p.line(50, height - 310, width - 50, height - 310)
    p.line(50, height - 310, 50, height - 450)
    p.line(200, height - 310, 200, height - 450)
    p.line(300, height - 310, 300, height - 450)
    p.line(400, height - 310, 400, height - 450)
    p.line(500, height - 310, 500, height - 450)
    p.line(width - 50, height - 310, width - 50, height - 450)

    # Add items
    y = height - 330
    p.setFont("Helvetica", 12)
    for item in items:
        p.drawString(50, y, item[0])
        p.drawString(200, y, str(item[1]))
        p.drawString(300, y, f"₹{item[2]:.2f}")
        p.drawString(400, y, f"{item[3]}%")
        p.drawString(500, y, f"₹{item[4]:.2f}")
        y -= 20

    # Add totals
    p.setFont("Helvetica-Bold", 12)
    p.drawString(400, y - 40, f"Subtotal: ₹{invoice[8]:.2f}")
    p.drawString(400, y - 60, f"GST: ₹{invoice[9]:.2f}")
    p.drawString(400, y - 80, f"Total: ₹{invoice[10]:.2f}")

    # Add payment method
    p.drawString(50, y - 120, f"Payment Method: {invoice[7]}")

    # Add terms and conditions
    p.setFont("Helvetica", 10)
    p.drawString(50, y - 160, "Terms and Conditions:")
    p.drawString(50, y - 175, "1. Payment is due within 30 days")
    p.drawString(50, y - 190, "2. Please include invoice number in payment reference")
    p.drawString(50, y - 205, "3. For any queries, contact accounts@company.com")

    # Add footer
    p.setFont("Helvetica", 8)
    p.drawString(50, 50, "Thank you for your business!")
    p.drawString(50, 35, "This is a computer-generated invoice. No signature required.")

    p.save()
    buffer.seek(0)
    return buffer

@app.route('/download_invoice/<int:invoice_id>')
@login_required
def download_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('index'))

    buffer = generate_invoice_pdf(invoice_id)
    if not buffer:
        flash('Error generating invoice', 'danger')
        return redirect(url_for('view_invoice', invoice_id=invoice_id))

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"invoice_{invoice.invoice_number}.pdf",
        mimetype="application/pdf"
    )

def create_test_invoice():
    with app.app_context():
        # Create test user if not exists
        test_user = User.query.filter_by(username='test').first()
        if not test_user:
            test_user = User(username='test', password='test123')
            db.session.add(test_user)
            db.session.commit()

        # Create test products if not exists
        if not Product.query.first():
            products = [
                Product(name='Mouse', price=500, gst_rate=18),
                Product(name='Keyboard', price=1000, gst_rate=18),
                Product(name='Monitor', price=8000, gst_rate=18)
            ]
            db.session.add_all(products)
            db.session.commit()

        # Create test invoice with unique invoice number
        product = Product.query.filter_by(name='Mouse').first()
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        invoice = Invoice(
            invoice_number=f'TEST{timestamp}',
            customer_name='Test Customer',
            customer_address='Test Address',
            customer_gstin='TESTGSTIN123',
            customer_phone='1234567890',
            payment_method='Cash',
            user_id=test_user.id
        )
        db.session.add(invoice)
        db.session.commit()

        # Add invoice item
        invoice_item = InvoiceItem(
            invoice_id=invoice.id,
            product_id=product.id,
            quantity=2,
            unit_price=product.price,
            gst_rate=product.gst_rate
        )
        db.session.add(invoice_item)
        db.session.commit()

        # Generate PDF
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        
        # Add company header
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, 800, "Your Company Name")
        p.setFont("Helvetica", 12)
        p.drawString(50, 780, "123 Business Street")
        p.drawString(50, 760, "City, State - 123456")
        p.drawString(50, 740, "GSTIN: 12ABCDE1234F1Z5")
        p.drawString(50, 720, "Phone: +91 9876543210")

        # Add invoice details
        p.setFont("Helvetica-Bold", 14)
        p.drawString(400, 800, f"Invoice #{invoice.invoice_number}")
        p.setFont("Helvetica", 12)
        p.drawString(400, 780, f"Date: {invoice.date.strftime('%d-%m-%Y')}")

        # Add customer details
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, 680, "Bill To:")
        p.setFont("Helvetica", 12)
        p.drawString(50, 660, invoice.customer_name)
        p.drawString(50, 640, invoice.customer_address)
        p.drawString(50, 620, f"GSTIN: {invoice.customer_gstin}")
        p.drawString(50, 600, f"Phone: {invoice.customer_phone}")

        # Add items table
        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, 560, "Item")
        p.drawString(200, 560, "Quantity")
        p.drawString(300, 560, "Unit Price")
        p.drawString(400, 560, "GST Rate")
        p.drawString(500, 560, "Total")

        y = 540
        for item in invoice.items:
            p.setFont("Helvetica", 12)
            p.drawString(50, y, item.product.name)
            p.drawString(200, y, str(item.quantity))
            p.drawString(300, y, f"₹{item.unit_price}")
            p.drawString(400, y, f"{item.gst_rate}%")
            p.drawString(500, y, f"₹{item.total}")
            y -= 20

        # Add totals
        p.setFont("Helvetica-Bold", 12)
        p.drawString(400, y-20, f"Subtotal: ₹{invoice.subtotal:.2f}")
        p.drawString(400, y-40, f"GST: ₹{invoice.gst_amount:.2f}")
        p.drawString(400, y-60, f"Total: ₹{invoice.total:.2f}")

        # Add payment method and status
        p.drawString(50, y-100, f"Payment Method: {invoice.payment_method}")
        p.drawString(50, y-120, "Status: Paid")

        # Add terms and conditions
        p.setFont("Helvetica", 10)
        p.drawString(50, y-160, "Terms and Conditions:")
        p.drawString(50, y-180, "1. Payment is due within 30 days")
        p.drawString(50, y-200, "2. Please include invoice number in payment reference")
        p.drawString(50, y-220, "3. For any queries, contact accounts@company.com")

        p.save()
        buffer.seek(0)

        # Save PDF to file
        with open('test_invoice.pdf', 'wb') as f:
            f.write(buffer.getvalue())

        return 'Test invoice generated and saved as test_invoice.pdf'

# Initialize DB and seed data if not present
with app.app_context():
    db.create_all()

    if not User.query.first():
        test_user = User(username='admin', password='admin123')
        db.session.add(test_user)

    if not Product.query.first():
        products = [
            Product(name='Mouse', price=500, gst_rate=18),
            Product(name='Keyboard', price=1000, gst_rate=18),
            Product(name='Monitor', price=8000, gst_rate=18),
        ]
        db.session.add_all(products)

    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if os.getenv('RENDER'):
            # Create test data only in development
            print(create_test_invoice())
    # Use production server when deployed
    if os.getenv('RENDER'):
        app.run()
    else:
        app.run(host='0.0.0.0', port=5000, debug=True)

