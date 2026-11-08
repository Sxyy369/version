from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from .models import User
from .extensions import db
import random
import string

auth = Blueprint('auth', __name__)

def generate_captcha():
    """Generates a random 4-char alphanumeric captcha."""
    # Mix integers and upper-case letters
    chars = string.ascii_uppercase + string.digits
    # Exclude confusing chars like 0/O, 1/I
    chars = chars.replace('0', '').replace('O', '').replace('1', '').replace('I', '')
    
    code = ''.join(random.choices(chars, k=4))
    
    session['captcha_res'] = code
    return code

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        captcha_input = request.form.get('captcha')
        
        # Verify Captcha
        correct_code = session.get('captcha_res', '')
        # Case insensitive match
        if not captcha_input or captcha_input.upper() != correct_code:
            flash('验证码错误', 'error')
            # Regenerate on failure
            return render_template('login.html', captcha_code=generate_captcha())

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            session.pop('captcha_res', None)
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'error')

    return render_template('login.html', captcha_code=generate_captcha())

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role')
        captcha_input = request.form.get('captcha')

        # Verify Captcha
        correct_code = session.get('captcha_res', '')
        if not captcha_input or captcha_input.upper() != correct_code:
            flash('验证码错误', 'error')
            return render_template('register.html', captcha_code=generate_captcha())
            
        # Verify Password Match
        if password != confirm_password:
             flash('两次输入的密码不一致', 'error')
             return render_template('register.html', captcha_code=generate_captcha())

        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'error')
            return render_template('register.html', captcha_code=generate_captcha())
        else:
            new_user = User(username=username, role=role)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            session.pop('captcha_res', None)
            return redirect(url_for('index'))

    return render_template('register.html', captcha_code=generate_captcha())

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/api/bind', methods=['POST'])
@login_required
def bind_user():
    if current_user.role != 'guardian':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    target_username = data.get('target_username')
    
    target_user = User.query.filter_by(username=target_username, role='user').first()
    
    if target_user:
        current_user.linked_user_id = target_user.id
        db.session.commit()
        return jsonify({'status': 'ok', 'message': f'成功绑定用户: {target_username}'})
    else:
        return jsonify({'status': 'error', 'message': '找不到该盲人用户'}), 404
