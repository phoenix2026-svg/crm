import os
from datetime import timedelta

import bcrypt
from flask import Flask, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from config import Config
from models import db, User

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(seconds=app.config['PERMANENT_SESSION_LIFETIME'])

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth_login'
    login_manager.login_message = 'Пожалуйста, войдите в систему.'
    login_manager.login_message_category = 'warning'

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    from routes_leads import leads_bp
    from routes_projects import projects_bp
    from routes_commissions import commissions_bp

    app.register_blueprint(leads_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(commissions_bp)

    # --- Auth routes ---

    from flask import render_template, session

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    @app.before_request
    def check_must_change_password():
        if current_user.is_authenticated and current_user.must_change_password:
            allowed = {'auth_change_password', 'auth_logout', 'static'}
            if request.endpoint and request.endpoint not in allowed:
                return redirect(url_for('auth_change_password'))

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.route('/')
    @login_required
    def index():
        return redirect(url_for('leads.lead_list'))

    @app.route('/login', methods=['GET', 'POST'])
    def auth_login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            user = User.query.filter_by(username=username).first()
            if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
                login_user(user)
                if user.must_change_password:
                    return redirect(url_for('auth_change_password'))
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            flash('Неверный логин или пароль.', 'danger')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def auth_logout():
        logout_user()
        flash('Вы вышли из системы.', 'info')
        return redirect(url_for('auth_login'))

    @app.route('/change-password', methods=['GET', 'POST'])
    @login_required
    def auth_change_password():
        if request.method == 'POST':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            if not bcrypt.checkpw(current_pw.encode('utf-8'), current_user.password_hash.encode('utf-8')):
                flash('Текущий пароль неверен.', 'danger')
                return render_template('change_password.html')

            if len(new_pw) < 4:
                flash('Новый пароль должен содержать минимум 4 символа.', 'danger')
                return render_template('change_password.html')

            if new_pw != confirm_pw:
                flash('Пароли не совпадают.', 'danger')
                return render_template('change_password.html')

            hashed = bcrypt.hashpw(new_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            current_user.password_hash = hashed
            current_user.must_change_password = False
            db.session.commit()
            flash('Пароль успешно изменён.', 'success')
            return redirect(url_for('index'))

        return render_template('change_password.html')

    # --- Initialize database and default admin ---

    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            hashed = bcrypt.hashpw(b'admin', bcrypt.gensalt()).decode('utf-8')
            admin = User(username='admin', password_hash=hashed, must_change_password=True)
            db.session.add(admin)
            db.session.commit()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
