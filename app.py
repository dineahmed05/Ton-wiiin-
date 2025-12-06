from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

# إعداد قاعدة البيانات
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'SuperSecretKey123' # غير هذا المفتاح

db = SQLAlchemy(app)

# --- جداول البيانات ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True) # Telegram ID
    name = db.Column(db.String(100))
    balance = db.Column(db.Integer, default=0) # الرصيد بالعملات
    ads_watched = db.Column(db.Integer, default=0)
    referrer_id = db.Column(db.Integer, nullable=True)
    wallet = db.Column(db.String(150), nullable=True)
    lang = db.Column(db.String(10), default='en') # اللغة

class Withdraw(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    amount_coins = db.Column(db.Integer)
    ton_value = db.Column(db.Float)
    wallet = db.Column(db.String(150))
    status = db.Column(db.String(20), default='pending') # pending, paid, rejected
    date = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- الإعدادات المالية ---
COINS_PER_AD = 100
REFERRAL_BONUS = 500 # مكافأة دعوة صديق
MIN_WITHDRAW_COINS = 50000 # الحد الأدنى للسحب (عملة)
COIN_TO_TON_RATE = 0.00001 # سعر تحويل العملة للتون

# --- الصفحات والـ API ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('id')
    name = data.get('first_name')
    lang = data.get('lang_code', 'en')
    ref_param = data.get('start_param')

    user = User.query.get(uid)
    if not user:
        # مستخدم جديد
        user = User(id=uid, name=name, lang=lang, referrer_id=ref_param)
        db.session.add(user)
        
        # احتساب مكافأة الإحالة
        if ref_param and str(ref_param) != str(uid):
            referrer = User.query.get(ref_param)
            if referrer:
                referrer.balance += REFERRAL_BONUS
        db.session.commit()
    else:
        # تحديث اللغة والاسم
        user.lang = lang
        user.name = name
        db.session.commit()

    return jsonify({
        "balance": user.balance,
        "ads": user.ads_watched,
        "wallet": user.wallet,
        "min_withdraw": MIN_WITHDRAW_COINS
    })

@app.route('/api/watch', methods=['POST'])
def watch_ad():
    data = request.json
    user = User.query.get(data.get('user_id'))
    if user:
        user.balance += COINS_PER_AD
        user.ads_watched += 1
        db.session.commit()
        return jsonify({"success": True, "new_balance": user.balance})
    return jsonify({"success": False})

@app.route('/api/withdraw', methods=['POST'])
def withdraw_request():
    data = request.json
    user_id = data.get('user_id')
    wallet = data.get('wallet')
    
    user = User.query.get(user_id)
    if user and user.balance >= MIN_WITHDRAW_COINS:
        amount = user.balance
        ton_val = amount * COIN_TO_TON_RATE
        
        # حفظ المحفظة وتصفير الرصيد وإنشاء طلب
        user.wallet = wallet
        user.balance = 0 
        new_req = Withdraw(user_id=user_id, amount_coins=amount, ton_value=ton_val, wallet=wallet)
        
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
