from datetime import datetime, date, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    must_change_password = db.Column(db.Boolean, default=False)


class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    client_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), default='')
    location_text = db.Column(db.String(300), default='')
    request_description = db.Column(db.Text, default='')
    source = db.Column(db.String(200), default='')
    status = db.Column(db.String(20), default='new')
    comment = db.Column(db.Text, default='')

    STATUS_LABELS = {
        'new': 'Новый',
        'in_progress': 'В работе',
        'closed': 'Закрыт',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(300), nullable=False)
    client_name = db.Column(db.String(200), default='')
    location_text = db.Column(db.String(300), default='')
    contract_amount = db.Column(db.Numeric(15, 2), default=0)
    currency = db.Column(db.String(10), default='AED')
    start_date = db.Column(db.Date, nullable=True)
    duration_days = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='planned')
    commission_percent = db.Column(db.Numeric(5, 2), default=0)

    payment_items = db.relationship(
        'PaymentPlanItem', backref='project', lazy='dynamic',
        cascade='all, delete-orphan'
    )
    variations = db.relationship(
        'Variation', backref='project', lazy='dynamic',
        cascade='all, delete-orphan'
    )
    tasks = db.relationship(
        'ProjectTask', backref='project', lazy='dynamic',
        cascade='all, delete-orphan'
    )
    documents = db.relationship(
        'Document', backref='project', lazy='dynamic',
        cascade='all, delete-orphan'
    )

    STATUS_LABELS = {
        'planned': 'Запланирован',
        'active': 'В работе',
        'on_hold': 'Пауза',
        'completed': 'Завершён',
        'cancelled': 'Отменён',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def end_date(self):
        if self.start_date and self.duration_days:
            return self.start_date + timedelta(days=self.duration_days)
        return None

    @property
    def days_left(self):
        ed = self.end_date
        if ed:
            return (ed - date.today()).days
        return None

    @property
    def days_elapsed(self):
        if self.start_date:
            return (date.today() - self.start_date).days
        return None

    @property
    def payment_percent_total(self):
        items = self.payment_items.all()
        return sum(float(i.percent) for i in items)

    @property
    def paid_percent(self):
        items = self.payment_items.filter_by(invoice_status='paid').all()
        return sum(float(i.percent) for i in items)

    @property
    def paid_amount(self):
        items = self.payment_items.filter_by(invoice_status='paid').all()
        return sum(i.amount for i in items)

    @property
    def total_variations_amount(self):
        return sum(float(v.extra_amount or 0) for v in self.variations.all())

    @property
    def commission_total(self):
        cp = float(self.commission_percent or 0)
        ca = float(self.contract_amount or 0)
        return ca * cp / 100

    @property
    def commission_received(self):
        cp = float(self.commission_percent or 0)
        if cp == 0:
            return 0
        total = 0.0
        for item in self.payment_items.filter_by(invoice_status='paid').all():
            total += item.amount * cp / 100
        return total

    @property
    def commission_pending(self):
        return self.commission_total - self.commission_received

    @property
    def commission_total_with_variations(self):
        cp = float(self.commission_percent or 0)
        base = self.commission_total
        extra = 0.0
        for v in self.variations.all():
            for item in v.payment_items.all():
                extra += item.amount * cp / 100
        return base + extra - self.commission_received_from_variations

    @property
    def commission_received_from_variations(self):
        cp = float(self.commission_percent or 0)
        if cp == 0:
            return 0
        total = 0.0
        for v in self.variations.all():
            for item in v.payment_items.filter_by(invoice_status='paid').all():
                total += item.amount * cp / 100
        return total


class PaymentPlanItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    percent = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    due_condition = db.Column(db.String(300), default='')
    invoice_status = db.Column(db.String(20), default='not_invoiced')
    invoice_date = db.Column(db.Date, nullable=True)
    paid_date = db.Column(db.Date, nullable=True)

    STATUS_LABELS = {
        'not_invoiced': 'Не выставлен',
        'invoiced': 'Выставлен',
        'paid': 'Оплачен',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.invoice_status, self.invoice_status)

    @property
    def amount(self):
        if self.project and self.project.contract_amount:
            return float(self.project.contract_amount) * float(self.percent) / 100
        return 0.0


class Variation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    extra_amount = db.Column(db.Numeric(15, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='draft')

    payment_items = db.relationship(
        'ExtraPaymentPlanItem', backref='variation', lazy='dynamic',
        cascade='all, delete-orphan'
    )

    STATUS_LABELS = {
        'draft': 'Черновик',
        'approved': 'Утверждено',
        'invoiced': 'Выставлен счёт',
        'paid': 'Оплачено',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def payment_percent_total(self):
        items = self.payment_items.all()
        return sum(float(i.percent) for i in items)

    @property
    def paid_percent(self):
        items = self.payment_items.filter_by(invoice_status='paid').all()
        return sum(float(i.percent) for i in items)

    @property
    def paid_amount(self):
        items = self.payment_items.filter_by(invoice_status='paid').all()
        return sum(i.amount for i in items)


class ExtraPaymentPlanItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    variation_id = db.Column(db.Integer, db.ForeignKey('variation.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    percent = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    due_condition = db.Column(db.String(300), default='')
    invoice_status = db.Column(db.String(20), default='not_invoiced')
    invoice_date = db.Column(db.Date, nullable=True)
    paid_date = db.Column(db.Date, nullable=True)

    STATUS_LABELS = {
        'not_invoiced': 'Не выставлен',
        'invoiced': 'Выставлен',
        'paid': 'Оплачен',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.invoice_status, self.invoice_status)

    @property
    def amount(self):
        if self.variation and self.variation.extra_amount:
            return float(self.variation.extra_amount) * float(self.percent) / 100
        return 0.0


class ProjectTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default='')
    deadline_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    STATUS_LABELS = {
        'open': 'Открыта',
        'done': 'Выполнена',
        'cancelled': 'Отменена',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def is_overdue(self):
        if self.deadline_date and self.status == 'open':
            return self.deadline_date < date.today()
        return False


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    doc_type = db.Column(db.String(20), nullable=False)
    file_name = db.Column(db.String(300), nullable=False)
    original_name = db.Column(db.String(300), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    TYPE_LABELS = {
        'contract': 'Договор',
        'estimate': 'Смета',
        'other': 'Прочее',
    }

    @property
    def type_label(self):
        return self.TYPE_LABELS.get(self.doc_type, self.doc_type)
