import os
import uuid
from datetime import datetime, date

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    current_app, send_from_directory, abort,
)
from flask_login import login_required
from werkzeug.utils import secure_filename

from models import (
    db, Project, PaymentPlanItem, Variation, ExtraPaymentPlanItem,
    ProjectTask, Document,
)

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')


def allowed_file(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']
    )


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def parse_decimal(s, default=0):
    if not s:
        return default
    try:
        return float(s.replace(',', '.'))
    except (ValueError, TypeError):
        return default


# ======================== PROJECT CRUD ========================

@projects_bp.route('/')
@login_required
def project_list():
    page = request.args.get('page', 1, type=int)
    per_page = 25
    status_filter = request.args.get('status', '')
    search = request.args.get('q', '').strip()
    overdue = request.args.get('overdue', '')

    query = Project.query

    if status_filter:
        query = query.filter(Project.status == status_filter)
    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(
                Project.project_name.ilike(like),
                Project.client_name.ilike(like),
            )
        )

    projects_all = query.order_by(Project.id.desc()).all()

    if overdue:
        today = date.today()
        projects_all = [
            p for p in projects_all
            if p.end_date and p.end_date < today and p.status not in ('completed', 'cancelled')
        ]

    total = len(projects_all)
    start = (page - 1) * per_page
    end = start + per_page
    projects_page = projects_all[start:end]

    class FakePagination:
        def __init__(self, items, total, page, per_page):
            self.items = items
            self.total = total
            self.page = page
            self.per_page = per_page
            self.pages = max(1, (total + per_page - 1) // per_page)
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1
            self.next_num = page + 1

        def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
            last = 0
            for num in range(1, self.pages + 1):
                if (
                    num <= left_edge
                    or (self.page - left_current <= num <= self.page + right_current)
                    or num > self.pages - right_edge
                ):
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    pagination = FakePagination(projects_page, total, page, per_page)

    return render_template(
        'projects/list.html',
        projects=projects_page,
        pagination=pagination,
        status_filter=status_filter,
        search=search,
        overdue=overdue,
        statuses=Project.STATUS_LABELS,
    )


@projects_bp.route('/create', methods=['GET', 'POST'])
@login_required
def project_create():
    if request.method == 'POST':
        project = Project(
            project_name=request.form.get('project_name', '').strip(),
            client_name=request.form.get('client_name', '').strip(),
            location_text=request.form.get('location_text', '').strip(),
            contract_amount=parse_decimal(request.form.get('contract_amount')),
            currency=request.form.get('currency', 'AED').strip(),
            start_date=parse_date(request.form.get('start_date')),
            duration_days=int(request.form.get('duration_days') or 0) or None,
            status=request.form.get('status', 'planned'),
        )
        if not project.project_name:
            flash('Название проекта обязательно.', 'danger')
            return render_template('projects/form.html', project=project, is_new=True)
        db.session.add(project)
        db.session.commit()
        flash('Проект создан.', 'success')
        return redirect(url_for('projects.project_detail', project_id=project.id))

    return render_template('projects/form.html', project=None, is_new=True)


@projects_bp.route('/<int:project_id>')
@login_required
def project_detail(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        flash('Проект не найден.', 'danger')
        return redirect(url_for('projects.project_list'))

    tab = request.args.get('tab', 'main')
    tasks_filter = request.args.get('tasks_filter', 'open')

    tasks_query = project.tasks
    if tasks_filter == 'open':
        tasks_query = tasks_query.filter(ProjectTask.status == 'open')
    tasks = tasks_query.order_by(
        db.case((ProjectTask.deadline_date.is_(None), 1), else_=0),
        ProjectTask.deadline_date.asc()
    ).all()

    return render_template(
        'projects/detail.html',
        project=project,
        tab=tab,
        tasks=tasks,
        tasks_filter=tasks_filter,
        today=date.today(),
    )


@projects_bp.route('/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def project_edit(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        flash('Проект не найден.', 'danger')
        return redirect(url_for('projects.project_list'))

    if request.method == 'POST':
        project.project_name = request.form.get('project_name', '').strip()
        project.client_name = request.form.get('client_name', '').strip()
        project.location_text = request.form.get('location_text', '').strip()
        project.contract_amount = parse_decimal(request.form.get('contract_amount'))
        project.currency = request.form.get('currency', 'AED').strip()
        project.start_date = parse_date(request.form.get('start_date'))
        project.duration_days = int(request.form.get('duration_days') or 0) or None
        project.status = request.form.get('status', 'planned')

        if not project.project_name:
            flash('Название проекта обязательно.', 'danger')
            return render_template('projects/form.html', project=project, is_new=False)

        db.session.commit()
        flash('Проект обновлён.', 'success')
        return redirect(url_for('projects.project_detail', project_id=project.id))

    return render_template('projects/form.html', project=project, is_new=False)


@projects_bp.route('/<int:project_id>/delete', methods=['POST'])
@login_required
def project_delete(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        flash('Проект не найден.', 'danger')
        return redirect(url_for('projects.project_list'))
    project.status = 'cancelled'
    db.session.commit()
    flash('Проект отменён (архивирован).', 'warning')
    return redirect(url_for('projects.project_list'))


# ======================== PAYMENT PLAN ========================

@projects_bp.route('/<int:project_id>/payments/add', methods=['POST'])
@login_required
def payment_add(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    item = PaymentPlanItem(
        project_id=project_id,
        title=request.form.get('title', '').strip() or 'Этап',
        percent=parse_decimal(request.form.get('percent'), 0),
        due_condition=request.form.get('due_condition', '').strip(),
    )
    db.session.add(item)
    db.session.commit()
    flash('Этап оплаты добавлен.', 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id, tab='payments'))


@projects_bp.route('/payments/<int:item_id>/edit', methods=['POST'])
@login_required
def payment_edit(item_id):
    item = db.session.get(PaymentPlanItem, item_id)
    if not item:
        abort(404)
    item.title = request.form.get('title', '').strip() or item.title
    item.percent = parse_decimal(request.form.get('percent'), float(item.percent))
    item.due_condition = request.form.get('due_condition', '').strip()
    db.session.commit()
    flash('Этап обновлён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=item.project_id, tab='payments'))


@projects_bp.route('/payments/<int:item_id>/delete', methods=['POST'])
@login_required
def payment_delete(item_id):
    item = db.session.get(PaymentPlanItem, item_id)
    if not item:
        abort(404)
    pid = item.project_id
    db.session.delete(item)
    db.session.commit()
    flash('Этап удалён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=pid, tab='payments'))


@projects_bp.route('/payments/<int:item_id>/status', methods=['POST'])
@login_required
def payment_status(item_id):
    item = db.session.get(PaymentPlanItem, item_id)
    if not item:
        abort(404)
    new_status = request.form.get('invoice_status', '')
    if new_status in PaymentPlanItem.STATUS_LABELS:
        item.invoice_status = new_status
        if new_status == 'invoiced' and not item.invoice_date:
            item.invoice_date = date.today()
        if new_status == 'paid' and not item.paid_date:
            item.paid_date = date.today()
        if new_status == 'not_invoiced':
            item.invoice_date = None
            item.paid_date = None
        db.session.commit()
        flash('Статус этапа обновлён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=item.project_id, tab='payments'))


# ======================== VARIATIONS ========================

@projects_bp.route('/<int:project_id>/variations/add', methods=['POST'])
@login_required
def variation_add(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    v = Variation(
        project_id=project_id,
        title=request.form.get('title', '').strip() or 'Доп. работа',
        extra_amount=parse_decimal(request.form.get('extra_amount'), 0),
        status=request.form.get('status', 'draft'),
    )
    db.session.add(v)
    db.session.commit()
    flash('Доп. работа добавлена.', 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id, tab='variations'))


@projects_bp.route('/variations/<int:var_id>/edit', methods=['POST'])
@login_required
def variation_edit(var_id):
    v = db.session.get(Variation, var_id)
    if not v:
        abort(404)
    v.title = request.form.get('title', '').strip() or v.title
    v.extra_amount = parse_decimal(request.form.get('extra_amount'), float(v.extra_amount))
    v.status = request.form.get('status', v.status)
    db.session.commit()
    flash('Доп. работа обновлена.', 'success')
    return redirect(url_for('projects.project_detail', project_id=v.project_id, tab='variations'))


@projects_bp.route('/variations/<int:var_id>/delete', methods=['POST'])
@login_required
def variation_delete(var_id):
    v = db.session.get(Variation, var_id)
    if not v:
        abort(404)
    pid = v.project_id
    db.session.delete(v)
    db.session.commit()
    flash('Доп. работа удалена.', 'success')
    return redirect(url_for('projects.project_detail', project_id=pid, tab='variations'))


# ======================== EXTRA PAYMENT PLAN ========================

@projects_bp.route('/variations/<int:var_id>/payments/add', methods=['POST'])
@login_required
def extra_payment_add(var_id):
    v = db.session.get(Variation, var_id)
    if not v:
        abort(404)
    item = ExtraPaymentPlanItem(
        variation_id=var_id,
        title=request.form.get('title', '').strip() or 'Этап',
        percent=parse_decimal(request.form.get('percent'), 0),
        due_condition=request.form.get('due_condition', '').strip(),
    )
    db.session.add(item)
    db.session.commit()
    flash('Этап оплаты (доп.) добавлен.', 'success')
    return redirect(url_for('projects.project_detail', project_id=v.project_id, tab='variations'))


@projects_bp.route('/extra-payments/<int:item_id>/edit', methods=['POST'])
@login_required
def extra_payment_edit(item_id):
    item = db.session.get(ExtraPaymentPlanItem, item_id)
    if not item:
        abort(404)
    item.title = request.form.get('title', '').strip() or item.title
    item.percent = parse_decimal(request.form.get('percent'), float(item.percent))
    item.due_condition = request.form.get('due_condition', '').strip()
    db.session.commit()
    flash('Этап (доп.) обновлён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=item.variation.project_id, tab='variations'))


@projects_bp.route('/extra-payments/<int:item_id>/delete', methods=['POST'])
@login_required
def extra_payment_delete(item_id):
    item = db.session.get(ExtraPaymentPlanItem, item_id)
    if not item:
        abort(404)
    pid = item.variation.project_id
    db.session.delete(item)
    db.session.commit()
    flash('Этап (доп.) удалён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=pid, tab='variations'))


@projects_bp.route('/extra-payments/<int:item_id>/status', methods=['POST'])
@login_required
def extra_payment_status(item_id):
    item = db.session.get(ExtraPaymentPlanItem, item_id)
    if not item:
        abort(404)
    new_status = request.form.get('invoice_status', '')
    if new_status in ExtraPaymentPlanItem.STATUS_LABELS:
        item.invoice_status = new_status
        if new_status == 'invoiced' and not item.invoice_date:
            item.invoice_date = date.today()
        if new_status == 'paid' and not item.paid_date:
            item.paid_date = date.today()
        if new_status == 'not_invoiced':
            item.invoice_date = None
            item.paid_date = None
        db.session.commit()
        flash('Статус этапа (доп.) обновлён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=item.variation.project_id, tab='variations'))


# ======================== TASKS ========================

@projects_bp.route('/<int:project_id>/tasks/add', methods=['POST'])
@login_required
def task_add(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    t = ProjectTask(
        project_id=project_id,
        title=request.form.get('title', '').strip() or 'Задача',
        description=request.form.get('description', '').strip(),
        deadline_date=parse_date(request.form.get('deadline_date')),
    )
    db.session.add(t)
    db.session.commit()
    flash('Задача добавлена.', 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id, tab='tasks'))


@projects_bp.route('/tasks/<int:task_id>/edit', methods=['POST'])
@login_required
def task_edit(task_id):
    t = db.session.get(ProjectTask, task_id)
    if not t:
        abort(404)
    t.title = request.form.get('title', '').strip() or t.title
    t.description = request.form.get('description', '').strip()
    t.deadline_date = parse_date(request.form.get('deadline_date'))
    db.session.commit()
    flash('Задача обновлена.', 'success')
    return redirect(url_for('projects.project_detail', project_id=t.project_id, tab='tasks'))


@projects_bp.route('/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def task_toggle(task_id):
    t = db.session.get(ProjectTask, task_id)
    if not t:
        abort(404)
    new_status = request.form.get('status', '')
    if new_status in ProjectTask.STATUS_LABELS:
        t.status = new_status
        if new_status == 'done':
            t.completed_at = datetime.utcnow()
        elif new_status == 'open':
            t.completed_at = None
        db.session.commit()
        flash('Статус задачи обновлён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=t.project_id, tab='tasks'))


@projects_bp.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def task_delete(task_id):
    t = db.session.get(ProjectTask, task_id)
    if not t:
        abort(404)
    pid = t.project_id
    db.session.delete(t)
    db.session.commit()
    flash('Задача удалена.', 'success')
    return redirect(url_for('projects.project_detail', project_id=pid, tab='tasks'))


# ======================== DOCUMENTS ========================

@projects_bp.route('/<int:project_id>/documents/upload', methods=['POST'])
@login_required
def document_upload(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)

    file = request.files.get('file')
    doc_type = request.form.get('doc_type', 'other')

    if not file or file.filename == '':
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('projects.project_detail', project_id=project_id, tab='documents'))

    if not allowed_file(file.filename):
        flash('Недопустимый тип файла.', 'danger')
        return redirect(url_for('projects.project_detail', project_id=project_id, tab='documents'))

    original = secure_filename(file.filename)
    if not original:
        original = 'document'
    ext = original.rsplit('.', 1)[1].lower() if '.' in original else 'bin'
    stored_name = f'{uuid.uuid4().hex}.{ext}'

    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], stored_name))

    doc = Document(
        project_id=project_id,
        doc_type=doc_type,
        file_name=stored_name,
        original_name=file.filename,
    )
    db.session.add(doc)
    db.session.commit()
    flash('Документ загружен.', 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id, tab='documents'))


@projects_bp.route('/documents/<int:doc_id>/download')
@login_required
def document_download(doc_id):
    doc = db.session.get(Document, doc_id)
    if not doc:
        abort(404)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        doc.file_name,
        as_attachment=True,
        download_name=doc.original_name,
    )


@projects_bp.route('/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def document_delete(doc_id):
    doc = db.session.get(Document, doc_id)
    if not doc:
        abort(404)
    pid = doc.project_id
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.file_name)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(doc)
    db.session.commit()
    flash('Документ удалён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=pid, tab='documents'))


# ======================== COMMISSION (set from project) ========================

@projects_bp.route('/<int:project_id>/commission', methods=['POST'])
@login_required
def project_commission_set(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        abort(404)
    project.commission_percent = parse_decimal(request.form.get('commission_percent'), 0)
    db.session.commit()
    flash('Процент комиссии обновлён.', 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id, tab='main'))
