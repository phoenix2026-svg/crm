from flask import Blueprint, render_template, request
from flask_login import login_required
from models import db, Project

commissions_bp = Blueprint('commissions', __name__, url_prefix='/commissions')


@commissions_bp.route('/')
@login_required
def commission_list():
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Project.query.filter(Project.commission_percent > 0)
    query = query.order_by(Project.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'commissions/list.html',
        projects=pagination.items,
        pagination=pagination,
    )


@commissions_bp.route('/<int:project_id>')
@login_required
def commission_detail(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        from flask import flash, redirect, url_for
        flash('Проект не найден.', 'danger')
        return redirect(url_for('commissions.commission_list'))

    cp = float(project.commission_percent or 0)

    contract_stages = []
    for item in project.payment_items.all():
        commission_amount = item.amount * cp / 100
        contract_stages.append({
            'title': item.title,
            'percent': float(item.percent),
            'amount': item.amount,
            'commission': commission_amount,
            'status': item.invoice_status,
            'status_label': item.status_label,
            'is_paid': item.invoice_status == 'paid',
        })

    variation_stages = []
    for v in project.variations.all():
        v_items = []
        for item in v.payment_items.all():
            commission_amount = item.amount * cp / 100
            v_items.append({
                'title': item.title,
                'percent': float(item.percent),
                'amount': item.amount,
                'commission': commission_amount,
                'status': item.invoice_status,
                'status_label': item.status_label,
                'is_paid': item.invoice_status == 'paid',
            })
        variation_stages.append({
            'variation_title': v.title,
            'extra_amount': float(v.extra_amount or 0),
            'stages': v_items,
        })

    total_commission = project.commission_total
    received = project.commission_received
    received_var = project.commission_received_from_variations
    total_received = received + received_var

    total_var_commission = 0
    for v in project.variations.all():
        for item in v.payment_items.all():
            total_var_commission += item.amount * cp / 100

    grand_total = total_commission + total_var_commission
    grand_pending = grand_total - total_received

    return render_template(
        'commissions/detail.html',
        project=project,
        cp=cp,
        contract_stages=contract_stages,
        variation_stages=variation_stages,
        total_commission=total_commission,
        received=received,
        total_var_commission=total_var_commission,
        received_var=received_var,
        grand_total=grand_total,
        total_received=total_received,
        grand_pending=grand_pending,
    )
