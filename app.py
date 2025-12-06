from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# إعدادات قاعدة البيانات
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'WatchWinSecretKey2025'

db = SQLAlchemy(app)

# --- الجداول ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True) # Telegram ID
    name = db.Column(db.String(100))
    username = db.Column(db.String(100)) # اسم المستخدم للتواصل
    balance = db.Column(db.Integer, default=0)
    ads_watched = db.Column(db.Integer, default=0)
    referrer_id = db.Column(db.Integer, nullable=True)
    wallet = db.Column(db.String(150), nullable=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class Withdraw(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    username = db.Column(db.String(100)) # لتسهيل معرفة من سحب
    amount_coins = db.Column(db.Integer)
    ton_value = db.Column(db.Float)
    wallet = db.Column(db.String(150))
    status = db.Column(db.String(20), default='pending')
    date = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- إعدادات الأرباح ---
COINS_PER_AD = 100
REFERRAL_BONUS = 500
MIN_WITHDRAW = 50000
RATE = 0.00001 # 50,000 coins = 0.5 TON

# --- المسارات (Routes) ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('id')
    
    user = User.query.get(uid)
    if not user:
        # تسجيل مستخدم جديد
        user = User(
            id=uid, 
            name=data.get('name'), 
            username=data.get('username'),
            referrer_id=data.get('start_param')
        )
        db.session.add(user)
        
        # مكافأة الإحالة
        ref_id = data.get('start_param')
        if ref_id and str(ref_id) != str(uid):
            referrer = User.query.get(ref_id)
            if referrer:
                referrer.balance += REFERRAL_BONUS
        
        db.session.commit()
    else:
        # تحديث البيانات
        user.name = data.get('name')
        user.username = data.get('username')
        db.session.commit()

    return jsonify({
        "balance": user.balance,
        "wallet": user.wallet
    })

@app.route('/api/watch', methods=['POST'])
def watch():
    data = request.json
    user = User.query.get(data.get('user_id'))
    if user:
        user.balance += COINS_PER_AD
        user.ads_watched += 1
        db.session.commit()
        return jsonify({"new_balance": user.balance})
    return jsonify({"error": "User not found"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    uid = data.get('user_id')
    wallet = data.get('wallet')
    
    user = User.query.get(uid)
    if user and user.balance >= MIN_WITHDRAW:
        amount = user.balance
        ton_val = amount * RATE
        
        # حفظ الطلب وتصفير الرصيد
        user.wallet = wallet
        user.balance = 0
        wd = Withdraw(
            user_id=uid, 
            username=user.username,
            amount_coins=amount, 
            ton_value=ton_val, 
            wallet=wallet
        )
        db.session.add(wd)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

# --- لوحة الأدمن السرية ---
@app.route('/admin_panel_secret_key_99')
def admin():
    withdrawals = Withdraw.query.filter_by(status='pending').all()
    stats = {
        'total_users': User.query.count(),
        'total_ads': db.session.query(db.func.sum(User.ads_watched)).scalar() or 0
    }
    return render_template('admin.html', reqs=withdrawals, stats=stats)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
        
        db.session.add(new_req)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False, "msg": "Low Balance"})

# --- لوحة الأدمن المصغرة ---
@app.route('/admin_panel_secret_key_99') # غير هذا الرابط ليكون سرياً
def admin():
    reqs = Withdraw.query.filter_by(status='pending').all()
    stats = {
        'users': User.query.count(),
        'ads': db.session.query(db.func.sum(User.ads_watched)).scalar() or 0
    }
    return render_template('admin.html', reqs=reqs, stats=stats)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
