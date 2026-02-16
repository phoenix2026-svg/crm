from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Lead

leads_bp = Blueprint('leads', __name__, url_prefix='/leads')


@leads_bp.route('/')
@login_required
def lead_list():
    page = request.args.get('page', 1, type=int)
    per_page = 25
    status_filter = request.args.get('status', '')
    source_filter = request.args.get('source', '')
    search = request.args.get('q', '').strip()

    query = Lead.query

    if status_filter:
        query = query.filter(Lead.status == status_filter)
    if source_filter:
        query = query.filter(Lead.source == source_filter)
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Lead.client_name.ilike(like),
                Lead.phone.ilike(like),
            )
        )

    query = query.order_by(Lead.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    sources = db.session.query(Lead.source).filter(Lead.source != '').distinct().all()
    sources = sorted(set(s[0] for s in sources if s[0]))

    return render_template(
        'leads/list.html',
        leads=pagination.items,
        pagination=pagination,
        status_filter=status_filter,
        source_filter=source_filter,
        search=search,
        sources=sources,
        statuses=Lead.STATUS_LABELS,
    )


@leads_bp.route('/create', methods=['GET', 'POST'])
@login_required
def lead_create():
    if request.method == 'POST':
        lead = Lead(
            client_name=request.form.get('client_name', '').strip(),
            phone=request.form.get('phone', '').strip(),
            location_text=request.form.get('location_text', '').strip(),
            request_description=request.form.get('request_description', '').strip(),
            source=request.form.get('source', '').strip(),
            status=request.form.get('status', 'new'),
            comment=request.form.get('comment', '').strip(),
        )
        if not lead.client_name:
            flash('Имя клиента обязательно.', 'danger')
            return render_template('leads/form.html', lead=lead, is_new=True)
        db.session.add(lead)
        db.session.commit()
        flash('Лид создан.', 'success')
        return redirect(url_for('leads.lead_list'))

    return render_template('leads/form.html', lead=None, is_new=True)


@leads_bp.route('/<int:lead_id>/edit', methods=['GET', 'POST'])
@login_required
def lead_edit(lead_id):
    lead = db.session.get(Lead, lead_id)
    if not lead:
        flash('Лид не найден.', 'danger')
        return redirect(url_for('leads.lead_list'))

    if request.method == 'POST':
        lead.client_name = request.form.get('client_name', '').strip()
        lead.phone = request.form.get('phone', '').strip()
        lead.location_text = request.form.get('location_text', '').strip()
        lead.request_description = request.form.get('request_description', '').strip()
        lead.source = request.form.get('source', '').strip()
        lead.status = request.form.get('status', 'new')
        lead.comment = request.form.get('comment', '').strip()

        if not lead.client_name:
            flash('Имя клиента обязательно.', 'danger')
            return render_template('leads/form.html', lead=lead, is_new=False)

        db.session.commit()
        flash('Лид обновлён.', 'success')
        return redirect(url_for('leads.lead_list'))

    return render_template('leads/form.html', lead=lead, is_new=False)


@leads_bp.route('/<int:lead_id>/delete', methods=['POST'])
@login_required
def lead_delete(lead_id):
    lead = db.session.get(Lead, lead_id)
    if lead:
        db.session.delete(lead)
        db.session.commit()
        flash('Лид удалён.', 'success')
    return redirect(url_for('leads.lead_list'))


@leads_bp.route('/<int:lead_id>/status', methods=['POST'])
@login_required
def lead_status(lead_id):
    lead = db.session.get(Lead, lead_id)
    if lead:
        new_status = request.form.get('status', '')
        if new_status in Lead.STATUS_LABELS:
            lead.status = new_status
            db.session.commit()
            flash('Статус обновлён.', 'success')
    return redirect(url_for('leads.lead_list'))
