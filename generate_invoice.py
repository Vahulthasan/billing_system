from datetime import datetime
from models import db, Invoice, InvoicePDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from io import BytesIO

class InvoiceGenerator:
    def __init__(self):
        self.company_info = {
            'company_name': 'Your Company Name',
            'company_address': '123 Business Street, City, State - 123456',
            'company_gstin': '12ABCDE1234F1Z5',
            'company_phone': '+91 9876543210',
            'company_email': 'contact@yourcompany.com'
        }

    def generate_invoice_pdf(self, invoice_id):
        """Generate PDF for a given invoice ID"""
        try:
            # Get invoice from database
            invoice = Invoice.query.get_or_404(invoice_id)
            
            # Create PDF buffer
            buffer = BytesIO()
            
            # Create the PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )

            # Container for the 'Flowable' objects
            elements = []
            
            # Styles
            styles = getSampleStyleSheet()
            styles.add(ParagraphStyle(
                name='Center',
                parent=styles['Heading1'],
                alignment=1,
            ))

            # Add company header
            elements.append(Paragraph(self.company_info['company_name'], styles['Center']))
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(self.company_info['company_address'], styles['Center']))
            elements.append(Paragraph(f"GSTIN: {self.company_info['company_gstin']}", styles['Center']))
            elements.append(Paragraph(f"Phone: {self.company_info['company_phone']}", styles['Center']))
            elements.append(Spacer(1, 20))

            # Add invoice details
            elements.append(Paragraph(f"Invoice #{invoice.invoice_number}", styles['Heading2']))
            elements.append(Paragraph(f"Date: {invoice.date.strftime('%d-%m-%Y')}", styles['Normal']))
            elements.append(Spacer(1, 12))

            # Add customer details
            elements.append(Paragraph("Bill To:", styles['Heading3']))
            elements.append(Paragraph(invoice.customer_name, styles['Normal']))
            elements.append(Paragraph(invoice.customer_address, styles['Normal']))
            if invoice.customer_gstin:
                elements.append(Paragraph(f"GSTIN: {invoice.customer_gstin}", styles['Normal']))
            if invoice.customer_phone:
                elements.append(Paragraph(f"Phone: {invoice.customer_phone}", styles['Normal']))
            elements.append(Spacer(1, 20))

            # Add items table
            table_data = [
                ['Item', 'Quantity', 'Unit Price', 'GST Rate', 'GST Amount', 'Total']
            ]
            
            for item in invoice.items:
                table_data.append([
                    item.product_name,
                    str(item.quantity),
                    f"₹{item.unit_price:.2f}",
                    f"{item.gst_rate}%",
                    f"₹{item.gst_amount:.2f}",
                    f"₹{item.total:.2f}"
                ])

            # Add totals
            table_data.extend([
                ['', '', '', '', 'Subtotal:', f"₹{(invoice.total_amount - invoice.gst_amount):.2f}"],
                ['', '', '', '', 'GST Total:', f"₹{invoice.gst_amount:.2f}"],
                ['', '', '', '', 'Total:', f"₹{invoice.total_amount:.2f}"]
            ])

            # Create the table
            table = Table(table_data, colWidths=[2*inch, inch, 1.1*inch, inch, 1.2*inch, 1.2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -3), (-1, -1), colors.lightgrey),
                ('TEXTCOLOR', (0, -3), (-1, -1), colors.black),
                ('FONTNAME', (0, -3), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -3), (-1, -1), 10),
                ('ALIGN', (-2, -3), (-1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))

            # Add payment information
            elements.append(Paragraph("Payment Information", styles['Heading3']))
            elements.append(Paragraph(f"Payment Method: {invoice.payment_method}", styles['Normal']))
            elements.append(Paragraph(f"Status: {invoice.status}", styles['Normal']))
            elements.append(Spacer(1, 20))

            # Add footer
            elements.append(Paragraph("Thank you for your business!", styles['Center']))
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("This is a computer-generated invoice and does not require a signature.", styles['Center']))

            # Build PDF
            doc.build(elements)
            pdf_data = buffer.getvalue()
            buffer.close()

            # Create or update InvoicePDF record
            invoice_pdf = InvoicePDF.query.filter_by(invoice_id=invoice.id).first()
            if not invoice_pdf:
                invoice_pdf = InvoicePDF(
                    invoice_id=invoice.id,
                    pdf_data=pdf_data,
                    file_name=f"invoice_{invoice.invoice_number}.pdf",
                    file_size=len(pdf_data)
                )
                db.session.add(invoice_pdf)
            else:
                invoice_pdf.pdf_data = pdf_data
                invoice_pdf.file_size = len(pdf_data)
                invoice_pdf.created_at = datetime.utcnow()

            db.session.commit()
            return pdf_data

        except Exception as e:
            db.session.rollback()
            raise Exception(f"Failed to generate invoice PDF: {str(e)}")

    def regenerate_all_invoices(self):
        """Regenerate PDFs for all invoices"""
        invoices = Invoice.query.all()
        for invoice in invoices:
            try:
                self.generate_invoice_pdf(invoice.id)
                print(f"Successfully regenerated PDF for invoice {invoice.invoice_number}")
            except Exception as e:
                print(f"Failed to regenerate PDF for invoice {invoice.invoice_number}: {str(e)}")

# Create an instance of the invoice generator
invoice_generator = InvoiceGenerator()
