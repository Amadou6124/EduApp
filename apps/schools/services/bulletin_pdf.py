"""
Générateur PDF de bulletins — WeasyPrint.
Template HTML → PDF haute qualité A4.

Supporte les formats :
- full_page : 1 bulletin par page A4
- two_per_page : 2 bulletins par page A4 (ligne pointillée de découpe)
"""
import io
import os
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML, CSS

from apps.schools.models import (
    Bulletin, BulletinConfig, BulletinFormat, BulletinLine,
    ClassSubject, NoteSystem,
)


def _get_config(school):
    """Récupère ou crée la configuration bulletin d'une école."""
    config, _ = BulletinConfig.objects.get_or_create(school=school)
    return config


def generate_bulletin_pdf(bulletin: Bulletin) -> bytes:
    """
    Génère un PDF à partir d'un Bulletin.
    Retourne les bytes du PDF.

    Si two_per_page → génère un seul bulletin en demi-page
    (la combinaison 2 par page se fait au niveau de generate_class_pdf).
    """
    config = _get_config(bulletin.student.school)
    lines = list(
        bulletin.lines.all()
        .select_related('class_subject__subject')
        .order_by('class_subject__order', 'class_subject__subject__name')
    )

    context = _build_context(bulletin, lines, config)
    context['is_half_page'] = (config.paper_format == BulletinFormat.TWO_PER_PAGE)

    html_str = render_to_string('bulletins/pdf/bulletin_template.html', context)

    if config.paper_format == BulletinFormat.TWO_PER_PAGE:
        # Demi-page A4 : 148mm de large, 210mm de hauteur (A5 paysage ≈ demi A4)
        pdf_bytes = HTML(string=html_str).write_pdf(
            presentational_hints=True,
        )
    else:
        pdf_bytes = HTML(string=html_str).write_pdf(
            presentational_hints=True,
        )

    return pdf_bytes


def generate_class_pdf(bulletins: list[Bulletin]) -> bytes:
    """
    Génère un PDF contenant tous les bulletins d'une classe.

    Si two_per_page → combine 2 bulletins par page A4 avec ligne de découpe.
    Si full_page → 1 bulletin par page.
    """
    if not bulletins:
        return b''

    config = _get_config(bulletins[0].student.school)

    if config.paper_format == BulletinFormat.TWO_PER_PAGE:
        return _generate_two_per_page_pdf(bulletins, config)
    else:
        return _generate_full_page_pdf(bulletins, config)


def _build_context(bulletin: Bulletin, lines: list[BulletinLine], config: BulletinConfig) -> dict:
    """Construit le contexte pour le template HTML du bulletin."""
    school = bulletin.student.school
    student = bulletin.student
    period = bulletin.period

    # Préparer les lignes matières
    subjects_rows = []
    for line in lines:
        cs = line.class_subject
        row = {
            'subject_name': cs.subject.name,
            'coefficient': cs.coefficient,
            'note_system': cs.note_system,
            'devoir_average': line.devoir_average,
            'compo_grade': line.compo_grade,
            'final_average': line.final_average,
            'weighted_grade': line.weighted_grade,
            'appreciation': line.appreciation,
            'max_grade': cs.max_grade,
        }
        subjects_rows.append(row)

    # Totaux
    total_coeff = sum(
        Decimal(str(line.class_subject.coefficient))
        for line in lines
    )
    total_weighted = sum(
        line.weighted_grade
        for line in lines
        if line.weighted_grade is not None
    ) if any(line.weighted_grade is not None for line in lines) else None

    return {
        'school': school,
        'student': student,
        'period': period,
        'bulletin': bulletin,
        'config': config,
        'subjects_rows': subjects_rows,
        'total_coeff': total_coeff,
        'total_weighted': total_weighted,
        'generated_at': bulletin.generated_at or datetime.now(),
    }


def _generate_full_page_pdf(bulletins: list[Bulletin], config: BulletinConfig) -> bytes:
    """1 bulletin par page A4."""
    all_html_parts = []
    for bulletin in bulletins:
        lines = list(
            bulletin.lines.all()
            .select_related('class_subject__subject')
            .order_by('class_subject__order', 'class_subject__subject__name')
        )
        context = _build_context(bulletin, lines, config)
        context['is_full_page'] = True
        html_part = render_to_string('bulletins/pdf/bulletin_template.html', context)
        all_html_parts.append(html_part)

    full_html = '\n<div class="page-break"></div>\n'.join(all_html_parts)

    pdf_bytes = HTML(string=full_html).write_pdf(presentational_hints=True)
    return pdf_bytes


def _generate_two_per_page_pdf(bulletins: list[Bulletin], config: BulletinConfig) -> bytes:
    """
    2 bulletins par page A4 avec ligne pointillée de découpe.

    Organisation : 
    ┌────────────────────┐
    │   Bulletin 1       │
    │                    │
    ├─ ─ ─ ─ ─ ─ ─ ─ ─ ─┤  ← ligne pointillée
    │   Bulletin 2       │
    │                    │
    └────────────────────┘
    """
    pages = []
    for i in range(0, len(bulletins), 2):
        pair = bulletins[i:i+2]

        html_parts = []
        for bulletin in pair:
            lines = list(
                bulletin.lines.all()
                .select_related('class_subject__subject')
                .order_by('class_subject__order', 'class_subject__subject__name')
            )
            context = _build_context(bulletin, lines, config)
            context['is_half_page'] = True
            html_part = render_to_string('bulletins/pdf/bulletin_template.html', context)
            html_parts.append(html_part)

        # Assembler les 2 bulletins avec ligne de découpe
        separator = '<div class="cut-line"></div>'
        page_html = separator.join(html_parts)

        # Wrapper pour une page A4 contenant les 2 bulletins
        pages.append(f'<div class="a4-page">{page_html}</div>')

    full_html = '\n'.join(pages)

    # CSS inline pour le format A4
    extra_css = CSS(string='''
        @page {
            size: A4;
            margin: 0;
        }
        .a4-page {
            width: 210mm;
            height: 297mm;
            display: flex;
            flex-direction: column;
            page-break-after: always;
        }
        .cut-line {
            border-top: 1px dashed #999;
            margin: 0 15mm;
            height: 0;
        }
        .bulletin-half {
            flex: 1;
            padding: 8mm 12mm;
            overflow: hidden;
        }
        @media print {
            .a4-page:last-child {
                page-break-after: avoid;
            }
        }
    ''')

    pdf_bytes = HTML(string=full_html).write_pdf(
        presentational_hints=True,
        stylesheets=[extra_css],
    )
    return pdf_bytes


def save_bulletin_pdf(bulletin: Bulletin) -> str:
    """
    Génère et sauvegarde le PDF d'un bulletin.
    Retourne le chemin relatif du fichier.
    """
    pdf_bytes = generate_bulletin_pdf(bulletin)

    filename = (
        f'bulletin_{bulletin.student.full_name.replace(" ", "_")}_'
        f'{bulletin.period.name.replace(" ", "_")}.pdf'
    )
    # Chemin : bulletins/YYYY/MM/filename
    now = datetime.now()
    rel_path = f'bulletins/{now.year}/{now.month:02d}/{filename}'
    full_path = os.path.join(settings.MEDIA_ROOT, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, 'wb') as f:
        f.write(pdf_bytes)

    bulletin.pdf_file.name = rel_path
    bulletin.save(update_fields=['pdf_file'])

    return rel_path