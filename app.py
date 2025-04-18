# core_imports.py
import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from dotenv import load_dotenv
from datetime import datetime, timedelta
import io
import jwt
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
import sqlite3
from models import db, init_db, User, Product, Invoice, InvoiceItem, InvoicePDF

# email_imports.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask_mail import Mail, Message

# pdf_imports.py
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# utility_imports.py
import stripe
import requests
from functools import wraps
from io import BytesIO
import sqlite3

# Load environment variables
load_dotenv()

# Get GitHub token from environment
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# Ensure instance folder exists and build absolute path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_PATH = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_PATH, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///billing.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
init_db(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# Import models after db initialization
from models import User, Product, Invoice, InvoiceItem, InvoicePDF

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
        
        # Debug print
        print(f"Login attempt - Username: {username}")
        
        user = User.query.filter_by(username=username).first()
        if user is None:
            flash('Invalid username or password', 'danger')
            print(f"User not found: {username}")
            return render_template('login.html')
            
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            print(f"Successful login: {username}")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
            print(f"Invalid password for user: {username}")
    
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

from generate_invoice import InvoiceGenerator

# Initialize the invoice generator
invoice_generator = InvoiceGenerator()

@app.route('/generate_invoice', methods=['POST'])
@login_required
def generate_invoice():
    try:
        data = request.get_json()
        
        # Create new invoice
        invoice = Invoice(
            invoice_number=generate_invoice_number(),
            date=datetime.now(),
            customer_name=data['customer_name'],
            customer_address=data['customer_address'],
            customer_gstin=data.get('customer_gstin', ''),
            customer_phone=data.get('customer_phone', ''),
            payment_method=data['payment_method'],
            user_id=current_user.id,
            status='PENDING',
            total_amount=float(data['total_amount']),
            gst_amount=float(data['total_gst'])
        )
        db.session.add(invoice)
        db.session.flush()  # Get the invoice ID

        # Add invoice items
        for item in data['items']:
            invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=item['product_id'],
                product_name=item['name'],
                quantity=item['quantity'],
                unit_price=float(item['price']),
                gst_rate=float(item['gst_rate']),
                subtotal=float(item['subtotal']),
                gst_amount=float(item['gst_amount']),
                total=float(item['total'])
            )
            db.session.add(invoice_item)

            # Update product stock
            product = Product.query.get(item['product_id'])
            if product:
                product.quantity -= item['quantity']
                db.session.add(product)

        # Generate PDF
        invoice_generator.generate_invoice_pdf(invoice.id)

        # Commit all changes
        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Invoice generated successfully',
            'invoice_number': invoice.invoice_number
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/download_invoice/<invoice_number>')
@login_required
def download_invoice(invoice_number):
    try:
        invoice = Invoice.query.filter_by(invoice_number=invoice_number).first()
        if not invoice:
            return "Invoice not found", 404

        # Check if user has access to this invoice
        if invoice.user_id != current_user.id:
            return "Unauthorized access", 403

        # Get or generate PDF
        invoice_pdf = InvoicePDF.query.filter_by(invoice_id=invoice.id).first()
        if not invoice_pdf:
            # Generate new PDF if it doesn't exist
            pdf_data = invoice_generator.generate_invoice_pdf(invoice.id)
        else:
            pdf_data = invoice_pdf.pdf_data

        return send_file(
            BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"invoice_{invoice.invoice_number}.pdf"
        )

    except Exception as e:
        return str(e), 500

@app.route('/regenerate_invoice/<invoice_number>')
@login_required
def regenerate_invoice(invoice_number):
    try:
        invoice = Invoice.query.filter_by(invoice_number=invoice_number).first()
        if not invoice:
            return "Invoice not found", 404

        # Check if user has access to this invoice
        if invoice.user_id != current_user.id:
            return "Unauthorized access", 403

        # Regenerate PDF
        invoice_generator.generate_invoice_pdf(invoice.id)
        
        flash('Invoice regenerated successfully!', 'success')
        return redirect(url_for('view_invoice', invoice_id=invoice.id))

    except Exception as e:
        flash(f'Error regenerating invoice: {str(e)}', 'danger')
        return redirect(url_for('view_invoice', invoice_id=invoice.id))

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
        try:
            name = request.form['name']
            price = float(request.form['price'])
            gst_rate = float(request.form['gst_rate'])
            new_product = Product(name=name, price=price, gst_rate=gst_rate)
            db.session.add(new_product)
            db.session.commit()
            flash('Product added successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding product: {str(e)}', 'danger')
            return redirect(url_for('add_product'))
    return render_template('add_product.html')

@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        try:
            product.name = request.form['name']
            product.price = float(request.form['price'])
            product.gst_rate = float(request.form['gst_rate'])
            db.session.commit()
            flash('Product updated successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating product: {str(e)}', 'danger')
            return redirect(url_for('edit_product', product_id=product_id))

    return render_template('edit_product.html', product=product)

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        flash('Product deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting product: {str(e)}', 'danger')
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
        p.drawString(400, y - 40, f"Subtotal: ₹{invoice.subtotal:.2f}")
        p.drawString(400, y - 60, f"GST: ₹{invoice.gst_amount:.2f}")
        p.drawString(400, y - 80, f"Total: ₹{invoice.total:.2f}")

        # Add payment method and status
        p.drawString(50, y - 100, f"Payment Method: {invoice.payment_method}")
        p.drawString(50, y - 120, "Status: Paid")

        # Add terms and conditions
        p.setFont("Helvetica", 10)
        p.drawString(50, y - 160, "Terms and Conditions:")
        p.drawString(50, y - 180, "1. Payment is due within 30 days")
        p.drawString(50, y - 200, "2. Please include invoice number in payment reference")
        p.drawString(50, y - 220, "3. For any queries, contact accounts@company.com")

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

def generate_invoice_pdf(invoice, items):
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
    """, (invoice.id,))
    invoice_details = cursor.fetchone()

    if not invoice_details:
        print("Invoice not found")
        return None

    # Fetch invoice items
    cursor.execute("""
        SELECT p.name, ii.quantity, ii.unit_price, ii.gst_rate, ii.total
        FROM invoice_item ii
        JOIN product p ON ii.product_id = p.id
        WHERE ii.invoice_id = ?
    """, (invoice.id,))
    existing_items = cursor.fetchall()

    conn.close()

    # Generate PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RightAlign', alignment=2))
    styles.add(ParagraphStyle(name='CenterAlign', alignment=1))
    styles.add(ParagraphStyle(
        name='CustomTitle',
        fontSize=24,
        spaceAfter=30,
        alignment=1
    ))
    
    # Add company logo/header
    elements.append(Paragraph("Your Store Name", styles['CustomTitle']))
    
    # Add company details
    company_info = [
        "123 Business Street, City, State - 123456",
        "GSTIN: 12ABCDE1234F1Z5",
        "Phone: +91 9876543210",
        "Email: contact@company.com",
        "Website: www.yourcompany.com"
    ]
    for info in company_info:
        elements.append(Paragraph(info, styles['CenterAlign']))
    
    elements.append(Spacer(1, 20))
    
    # Add invoice header
    invoice_header = [
        [Paragraph(f"<b>Invoice #{invoice_details[1]}</b>", styles['RightAlign']),
         Paragraph(f"<b>Date:</b> {invoice_details[6].strftime('%d-%m-%Y')}", styles['RightAlign'])],
    ]
    invoice_header_table = Table(invoice_header, colWidths=[doc.width/2]*2)
    invoice_header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 20),
    ]))
    elements.append(invoice_header_table)
    elements.append(Spacer(1, 20))
    
    # Add billing details
    billing_data = [
        ["BILL TO:", "SHIP TO:"],
        [invoice_details[2], invoice_details[2]],  # Customer name
        [invoice_details[3], invoice_details[3]],  # Address
        [f"GSTIN: {invoice_details[4]}", ""],
        [f"Phone: {invoice_details[5]}", ""],
    ]
    billing_table = Table(billing_data, colWidths=[doc.width/2]*2)
    billing_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    elements.append(billing_table)
    elements.append(Spacer(1, 20))
    
    # Add items table
    table_data = [["Item", "Quantity", "Unit Price", "GST Rate", "Total"]]
    for item in items:
        table_data.append([
            item['name'],
            str(item['quantity']),
            f"₹{item['price']:.2f}",
            f"{item['gst_rate']}%",
            f"₹{item['total']:.2f}"
        ])
    
    # Add totals
    table_data.extend([
        ["", "", "", "Subtotal:", f"₹{invoice_details[8]:.2f}"],
        ["", "", "", "GST:", f"₹{invoice_details[9]:.2f}"],
        ["", "", "", "Total:", f"₹{invoice_details[10]:.2f}"]
    ])
    
    # Create items table
    items_table = Table(table_data, colWidths=[doc.width/3, doc.width/6, doc.width/6, doc.width/6, doc.width/6])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -3), (-1, -1), colors.lightgrey),
        ('FONTNAME', (0, -3), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (-2, -3), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 20))
    
    # Add payment details
    payment_info = [
        [Paragraph("<b>Payment Method:</b>", styles['Normal']), invoice_details[7]],
        [Paragraph("<b>Payment Status:</b>", styles['Normal']), "Paid"],
    ]
    payment_table = Table(payment_info, colWidths=[doc.width/4, doc.width*3/4])
    payment_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(payment_table)
    elements.append(Spacer(1, 20))
    
    # Add terms and conditions
    elements.append(Paragraph("<b>Terms and Conditions:</b>", styles['Normal']))
    terms = [
        "1. Payment is due within 30 days",
        "2. Please include invoice number in payment reference",
        "3. For any queries, contact accounts@company.com",
        "4. Goods once sold cannot be returned",
        "5. All disputes are subject to local jurisdiction"
    ]
    for term in terms:
        elements.append(Paragraph(term, styles['Normal']))
    
    # Add footer
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("Thank you for your business!", styles['CenterAlign']))
    elements.append(Paragraph("This is a computer-generated invoice. No signature required.", styles['CenterAlign']))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

@app.route('/invoice_history')
@login_required
def invoice_history():
    # Get all invoices for the current user with their PDFs
    invoices = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.date.desc()).all()
    
    # Prepare data for template
    invoice_data = []
    for invoice in invoices:
        pdfs = InvoicePDF.query.filter_by(invoice_id=invoice.id).order_by(InvoicePDF.created_at.desc()).all()
        invoice_data.append({
            'invoice': invoice,
            'pdfs': pdfs
        })
    
    return render_template('invoice_history.html', invoice_data=invoice_data)

@app.route('/view_saved_pdf/<int:pdf_id>')
@login_required
def view_saved_pdf(pdf_id):
    invoice_pdf = InvoicePDF.query.get_or_404(pdf_id)
    
    # Check if the user has access to this invoice
    if invoice_pdf.invoice.user_id != current_user.id:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('invoice_history'))
    
    return send_file(
        BytesIO(invoice_pdf.pdf_data),
        download_name=invoice_pdf.file_name,
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

@app.route('/create_invoice')
@login_required
def create_invoice():
    products = Product.query.all()
    return render_template('create_invoice.html', products=products)

def create_tables():
    with app.app_context():
        db.create_all()

# Create tables before running the app
create_tables()

def generate_invoice_number():
    """Generate a unique invoice number based on the current year and a sequential number"""
    current_year = datetime.now().year
    last_invoice = Invoice.query.filter(
        Invoice.invoice_number.like(f'INV{current_year}-%')
    ).order_by(Invoice.id.desc()).first()

    if last_invoice:
        # Extract the sequential number from the last invoice number
        last_seq = int(last_invoice.invoice_number.split('-')[1])
        next_seq = last_seq + 1
    else:
        next_seq = 1

    return f'INV{current_year}-{str(next_seq).zfill(4)}'

@app.route('/test_invoice')
@login_required
def test_invoice():
    try:
        # Create a test product if it doesn't exist
        product = Product.query.filter_by(name='Test Product').first()
        if not product:
            product = Product(
                name='Test Product',
                price=1000.00,
                gst_rate=18.00,
                quantity=100
            )
            db.session.add(product)
            db.session.commit()

        # Create test invoice data
        invoice_data = {
            'customer_name': 'Test Customer',
            'customer_address': '123 Test Street, Test City - 123456',
            'customer_gstin': 'TEST1234567890',
            'customer_phone': '9876543210',
            'payment_method': 'Cash',
            'total_amount': 1180.00,  # 1000 + 18% GST
            'total_gst': 180.00,
            'items': [{
                'product_id': product.id,
                'name': product.name,
                'quantity': 1,
                'price': product.price,
                'gst_rate': product.gst_rate,
                'subtotal': product.price,
                'gst_amount': (product.price * product.gst_rate / 100),
                'total': product.price * (1 + product.gst_rate / 100)
            }]
        }

        # Create new invoice
        invoice = Invoice(
            invoice_number=generate_invoice_number(),
            date=datetime.now(),
            customer_name=invoice_data['customer_name'],
            customer_address=invoice_data['customer_address'],
            customer_gstin=invoice_data['customer_gstin'],
            customer_phone=invoice_data['customer_phone'],
            payment_method=invoice_data['payment_method'],
            user_id=current_user.id,
            status='PENDING',
            total_amount=invoice_data['total_amount'],
            gst_amount=invoice_data['total_gst']
        )
        db.session.add(invoice)
        db.session.flush()

        # Add invoice items
        for item in invoice_data['items']:
            invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=item['product_id'],
                product_name=item['name'],
                quantity=item['quantity'],
                unit_price=float(item['price']),
                gst_rate=float(item['gst_rate']),
                subtotal=float(item['subtotal']),
                gst_amount=float(item['gst_amount']),
                total=float(item['total'])
            )
            db.session.add(invoice_item)

        # Generate PDF
        pdf_data = invoice_generator.generate_invoice_pdf(invoice.id)
        
        # Commit all changes
        db.session.commit()

        # Return the PDF
        return send_file(
            BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"invoice_{invoice.invoice_number}.pdf"
        )

    except Exception as e:
        db.session.rollback()
        flash(f'Error generating test invoice: {str(e)}', 'danger')
        return redirect(url_for('index'))

def create_sample_products():
    with app.app_context():
        # Check if products already exist
        if Product.query.first() is None:
            # Create sample products
            products = [
                Product(name='Laptop', price=45000.00, gst_rate=18, quantity=10),
                Product(name='Mouse', price=500.00, gst_rate=18, quantity=50),
                Product(name='Keyboard', price=1000.00, gst_rate=18, quantity=30),
                Product(name='Monitor', price=15000.00, gst_rate=18, quantity=15),
                Product(name='Printer', price=12000.00, gst_rate=18, quantity=8),
                Product(name='USB Drive', price=800.00, gst_rate=18, quantity=100)
            ]
            db.session.add_all(products)
            db.session.commit()
            print("Sample products created successfully!")

@app.route('/initialize')
def initialize_db():
    try:
        create_tables()
        create_sample_products()
        return "Database initialized with sample products!"
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    if os.getenv('RENDER'):
        # Running on Render.com
        app.run(host='0.0.0.0', port=port)
    else:
        # Local development
        app.run(host='0.0.0.0', port=port, debug=True)

# Initialize database tables
with app.app_context():
    db.create_all()

