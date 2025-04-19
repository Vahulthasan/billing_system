from datetime import datetime
from models import db, Invoice, InvoicePDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from io import BytesIO
import qrcode
from PIL import Image as PILImage

class InvoiceGenerator:
    def __init__(self):
        self.company_info = {
            'company_name': 'Your Company Name',
            'company_address': '123 Business Street, City, State - 123456',
            'company_gstin': '12ABCDE1234F1Z5',
            'company_phone': '+91 9876543210',
            'company_email': 'contact@yourcompany.com',
            'company_website': 'www.yourcompany.com'
        }
        
    def _create_qr_code(self, invoice):
        """Generate QR code with invoice details"""
        qr_data = (
            f"Invoice: {invoice.invoice_number}\n"
            f"Date: {invoice.date.strftime('%d-%m-%Y')}\n"
            f"Amount: ₹{invoice.total_amount:.2f}\n"
            f"GSTIN: {invoice.customer_gstin}"
        )
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to bytes
        img_buffer = BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        return Image(img_buffer, width=1.5*inch, height=1.5*inch)

    def generate_invoice_pdf(self, invoice_id, include_qr=True):
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
                alignment=TA_CENTER,
            ))
            styles.add(ParagraphStyle(
                name='Right',
                parent=styles['Normal'],
                alignment=TA_RIGHT,
            ))

            # Add company header
            elements.append(Paragraph(self.company_info['company_name'], styles['Center']))
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(self.company_info['company_address'], styles['Center']))
            elements.append(Paragraph(f"GSTIN: {self.company_info['company_gstin']}", styles['Center']))
            elements.append(Paragraph(f"Phone: {self.company_info['company_phone']}", styles['Center']))
            elements.append(Paragraph(f"Email: {self.company_info['company_email']}", styles['Center']))
            elements.append(Spacer(1, 20))

            # Add invoice details and QR code in a table
            invoice_data = [[
                Paragraph(f"Invoice #{invoice.invoice_number}<br/>Date: {invoice.date.strftime('%d-%m-%Y')}", styles['Normal']),
                self._create_qr_code(invoice) if include_qr else Paragraph("", styles['Normal'])
            ]]
            invoice_table = Table(invoice_data, colWidths=[4*inch, 2*inch])
            invoice_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            elements.append(invoice_table)
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

            # Create the table with improved styling
            table = Table(table_data, colWidths=[2*inch, inch, 1.1*inch, inch, 1.2*inch, 1.2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -3), (-1, -1), colors.HexColor('#ecf0f1')),
                ('TEXTCOLOR', (0, -3), (-1, -1), colors.black),
                ('FONTNAME', (0, -3), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -3), (-1, -1), 10),
                ('ALIGN', (-2, -3), (-1, -1), 'RIGHT'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7'))
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))

            # Add payment information with improved styling
            payment_data = [
                ['Payment Method:', invoice.payment_method],
                ['Status:', invoice.status]
            ]
            payment_table = Table(payment_data, colWidths=[2*inch, 4*inch])
            payment_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50')),
            ]))
            elements.append(payment_table)
            elements.append(Spacer(1, 20))

            # Add footer
            elements.append(Paragraph("Thank you for your business!", styles['Center']))
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("This is a computer-generated invoice.", styles['Center']))

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
        results = {'success': [], 'failed': []}
        
        for invoice in invoices:
            try:
                self.generate_invoice_pdf(invoice.id)
                results['success'].append(invoice.invoice_number)
            except Exception as e:
                results['failed'].append({
                    'invoice_number': invoice.invoice_number,
                    'error': str(e)
                })
        
        return results

# Create an instance of the invoice generator
invoice_generator = InvoiceGenerator()
