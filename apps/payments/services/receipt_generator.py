"""
Génération des reçus PDF.

Deux modes selon school.receipt_mode :
  - 'standard' : WeasyPrint à partir d'un template HTML
  - 'custom'   : PyMuPDF injection de variables dans le PDF template uploadé
"""
import io
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.formats import date_format


def _fmt_amount(amount):
    """Formate un montant FCFA avec séparateur de milliers."""
    try:
        return f'{int(amount):,}'.replace(',', ' ')
    except (TypeError, ValueError):
        return str(amount)


def _payment_method_label(code):
    labels = {
        'cash':         'Espèces',
        'orange_money': 'Orange Money',
        'wave':         'Wave',
        'other':        'Autre',
    }
    return labels.get(code, code)


def _status_info(payment):
    student   = payment.student
    balance   = student.get_balance_due()
    total_paid = student.get_total_paid()
    if balance <= 0:
        return {'label': 'Soldé', 'emoji': '✅', 'color': '#22c55e'}
    if total_paid > 0:
        return {'label': 'Partiel', 'emoji': '⏳', 'color': '#f59e0b'}
    return {'label': 'Impayé', 'emoji': '❌', 'color': '#ef4444'}


def generate_receipt(payment, school):
    """Point d'entrée principal. Retourne les bytes PDF."""
    if school.receipt_mode == 'custom' and school.receipt_template_pdf and school.receipt_mapping:
        return _generate_custom(payment, school)
    return _generate_standard(payment, school)


# ── Mode standard (WeasyPrint) ────────────────────────────────────────────────

def _generate_standard(payment, school):
    from weasyprint import HTML, CSS

    student = payment.student

    logo_url = None
    if school.logo:
        logo_url = school.logo.path

    ctx = {
        'payment':        payment,
        'school':         school,
        'student':        student,
        'class_name':     student.school_class.name,
        'amount_fmt':     _fmt_amount(payment.amount),
        'total_due_fmt':  _fmt_amount(student.tuition_fee),
        'total_paid_fmt': _fmt_amount(student.get_total_paid()),
        'balance_fmt':    _fmt_amount(student.get_balance_due()),
        'date_fmt':       date_format(payment.payment_date, 'd/m/Y'),
        'method_label':   _payment_method_label(payment.payment_method),
        'status':         _status_info(payment),
        'logo_path':      logo_url,
        'primary_color':  school.primary_color or '#1E3A5F',
    }

    html_string = render_to_string('payments/pdf/receipt_standard.html', ctx)
    base_url    = str(Path(settings.BASE_DIR))
    pdf_bytes   = HTML(string=html_string, base_url=base_url).write_pdf()
    return pdf_bytes


# ── Mode personnalisé (PyMuPDF) ───────────────────────────────────────────────

def _generate_custom(payment, school):
    import fitz  # PyMuPDF

    student   = payment.student
    variables = {
        'nom_eleve':        student.full_name,
        'classe':           student.school_class.name,
        'montant':          _fmt_amount(payment.amount) + ' FCFA',
        'date':             date_format(payment.payment_date, 'd/m/Y'),
        'numero_recu':      payment.receipt_number,
        'solde':            _fmt_amount(student.get_balance_due()) + ' FCFA',
        'nom_ecole':        school.name,
        'telephone_ecole':  school.phone_number or '',
        'mode_paiement':    _payment_method_label(payment.payment_method),
    }

    mapping  = school.receipt_mapping or {}
    pdf_path = school.receipt_template_pdf.path

    doc = fitz.open(pdf_path)
    for page in doc:
        for zone_key, var_key in mapping.items():
            if var_key == 'ignore':
                continue
            value = variables.get(var_key, '')
            placeholder = '{{' + var_key + '}}'
            areas = page.search_for(placeholder)
            for area in areas:
                page.add_redact_annot(area, fill=(1, 1, 1))
            page.apply_redactions()
            for area in page.search_for(placeholder):
                page.insert_text(area.tl, value, fontsize=10)

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()
