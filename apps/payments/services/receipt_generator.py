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

from apps.payments.utils import amount_to_words_fr

_MOIS_FR = [
    '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
]


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


def _status_info(summary):
    """Statut affiché sur le reçu, depuis le résumé financier (helper central, lot 6bis-A).
    summary=None (élève sans fiche, cas legacy) → état neutre « indisponible »."""
    if summary is None:
        return {'label': 'Indisponible', 'emoji': '•', 'color': '#9ca3af'}
    if summary['balance'] <= 0:
        return {'label': 'Soldé', 'emoji': '✅', 'color': '#22c55e'}
    if summary['paid'] > 0:
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
    from apps.schools.models import SchoolYear

    student = payment.student

    logo_url = None
    if school.logo:
        logo_url = school.logo.path

    active_year = SchoolYear.objects.filter(school=school, is_active=True).first()
    school_year = active_year.name if active_year else ''

    d = payment.payment_date
    date_long = f'{d.day} {_MOIS_FR[d.month]} {d.year}'

    # Solde global du reçu — NOUVEAU modèle (lot 6bis-A) : 3 familles par allocation.
    # Repli « non disponible » si l'élève n'a pas de fiche (cas legacy résiduel). Le
    # DÉTAIL d'allocation (lot 5) ci-dessous reste calculé depuis le paiement lui-même.
    from apps.finance.services import student_fee_summary
    summary = student_fee_summary(student)
    if summary:
        total_due_fmt = _fmt_amount(summary['due'])
        total_paid_fmt = _fmt_amount(summary['paid'])
        balance_fmt = _fmt_amount(summary['balance'])
    else:
        total_due_fmt = total_paid_fmt = '—'
        balance_fmt = 'non disponible'

    ctx = {
        'payment':        payment,
        'school':         school,
        'student':        student,
        'class_name':     student.school_class.name,
        'amount_fmt':     _fmt_amount(payment.amount),
        'total_due_fmt':  total_due_fmt,
        'total_paid_fmt': total_paid_fmt,
        'balance_fmt':    balance_fmt,
        'date_fmt':       date_format(payment.payment_date, 'd/m/Y'),
        'date_long':      date_long,
        'method_label':   _payment_method_label(payment.payment_method),
        'status':         _status_info(summary),
        'logo_path':      logo_url,
        'school_year':    school_year,
        'amount_words':   amount_to_words_fr(int(payment.amount)),
        'signer_title':   school.receipt_signer_title or 'Le Caissier / Directeur',
        # Détail d'allocation (lot 5) : à quelle(s) tranche(s) ce paiement a été affecté.
        # Vide pour les paiements non alloués (anciens / hors guichet) → bloc masqué.
        'allocations': [
            {'label': a.installment.label,
             'debt':  a.installment.debt.label,
             'amount': _fmt_amount(a.amount)}
            for a in payment.allocations
                .select_related('installment__debt')
                .order_by('installment__debt__kind', 'installment__sequence')
        ],
    }

    html_string = render_to_string('payments/pdf/receipt_standard.html', ctx)
    base_url    = str(Path(settings.BASE_DIR))
    pdf_bytes   = HTML(string=html_string, base_url=base_url).write_pdf()
    return pdf_bytes


# ── Mode personnalisé (PyMuPDF) ───────────────────────────────────────────────

def _generate_custom(payment, school):
    import fitz  # PyMuPDF

    student   = payment.student
    # Solde — nouveau modèle (helper central) ; repli si pas de fiche (legacy).
    from apps.finance.services import student_fee_summary
    _summary = student_fee_summary(student)
    solde_str = (_fmt_amount(_summary['balance']) + ' FCFA') if _summary else 'non disponible'
    variables = {
        'nom_eleve':        student.full_name,
        'classe':           student.school_class.name,
        'montant':          _fmt_amount(payment.amount) + ' FCFA',
        'date':             date_format(payment.payment_date, 'd/m/Y'),
        'numero_recu':      payment.receipt_number,
        'solde':            solde_str,
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
