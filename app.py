from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import requests 

app = Flask(__name__)

# --- الإعدادات ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users_v3.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'MegaSecretKey2025'

# توكن البوت
BOT_TOKEN = "8555461747:AAEQ_S9VDDPl6ICb-Nh1AC6BJ_05WDWUCB8"

# 🔴 تم تحديث الآيدي الخاص بك هنا لاستقبال الإشعارات
ADMIN_TELEGRAM_ID = 1207530445

db = SQLAlchemy(app)

# --- الجداول ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    username = db.Column(db.String(100))
    balance = db.Column(db.Integer, default=0)
    
    # إحصائيات
    ads_watched = db.Column(db.Integer, default=0)       
    total_withdrawn = db.Column(db.Float, default=0.0)   
    referral_count = db.Column(db.Integer, default=0)    
    
    # الإحالات
    referrer_id = db.Column(db.Integer, nullable=True)   
    referral_bonus_paid = db.Column(db.Boolean, default=False) 
    
    wallet = db.Column(db.String(150), nullable=True)
    language = db.Column(db.String(10), default='ar')
    
    # التواريخ والوقت
    last_daily_bonus = db.Column(db.DateTime, nullable=True)
    last_ad_watched = db.Column(db.DateTime, nullable=True) # حماية من الغش
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class Withdraw(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    username = db.Column(db.String(100))
    amount_coins = db.Column(db.Integer)
    ton_value = db.Column(db.Float)
    wallet = db.Column(db.String(150))
    status = db.Column(db.String(20), default='pending')
    date = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- الثوابت ---
COINS_PER_AD = 100
DAILY_BONUS = 50
REFERRAL_BONUS = 500
ADS_REQUIRED_FOR_REF = 20 
MIN_WITHDRAW = 50000

# الأسعار
USD_PER_100K = 0.5 
TON_PRICE_USD = 6.5 

# دالة الإشعارات
def send_telegram_msg(chat_id, text):
    if not BOT_TOKEN or not chat_id: return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': chat_id, 'text': text})
    except:
        pass

# --- API Endpoints ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('id')
    
    user = User.query.get(uid)
    if not user:
        # تسجيل جديد
        ref_id = data.get('start_param')
        final_ref = ref_id if (ref_id and str(ref_id) != str(uid)) else None
        
        user = User(
            id=uid, 
            name=data.get('name'), 
            username=data.get('username'),
            referrer_id=final_ref
        )
        db.session.add(user)
        
        # إشعار للمضيف
        if final_ref:
            referrer = User.query.get(final_ref)
            if referrer:
                referrer.referral_count += 1
                send_telegram_msg(final_ref, f"👤 مستخدم جديد: {data.get('name')}\n(المكافأة معلقة حتى يشاهد {ADS_REQUIRED_FOR_REF} إعلانات)")
        
        db.session.commit()
    else:
        # تحديث بيانات
        user.name = data.get('name')
        user.username = data.get('username')
        db.session.commit()

    return jsonify({
        "balance": user.balance,
        "ads_watched": user.ads_watched,
        "referral_count": user.referral_count,
        "total_withdrawn": user.total_withdrawn,
        "wallet": user.wallet,
        "language": user.language
    })

@app.route('/api/watch', methods=['POST'])
def watch():
    data = request.json
    uid = data.get('user_id')
    user = User.query.get(uid)
    
    if user:
        # --- حماية أمنية (Anti-Cheat) ---
        now = datetime.utcnow()
        if user.last_ad_watched:
            seconds_diff = (now - user.last_ad_watched).total_seconds()
            if seconds_diff < 10: 
                return jsonify({"error": "Too fast"}), 429
        
        # تحديث الرصيد
        user.balance += COINS_PER_AD
        user.ads_watched += 1
        user.last_ad_watched = now 
        
        # شرط الإحالة
        if user.referrer_id and not user.referral_bonus_paid and user.ads_watched >= ADS_REQUIRED_FOR_REF:
            referrer = User.query.get(user.referrer_id)
            if referrer:
                referrer.balance += REFERRAL_BONUS
                user.referral_bonus_paid = True
                send_telegram_msg(user.referrer_id, f"💰 مبروك! أحد مدعويك أكمل المهام.\nتمت إضافة {REFERRAL_BONUS} نقطة لرصيدك.")
        
        db.session.commit()
        return jsonify({"new_balance": user.balance, "ads_watched": user.ads_watched})
    return jsonify({"error": "User not found"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    uid = data.get('user_id')
    wallet = data.get('wallet')
    
    user = User.query.get(uid)
    if user and user.balance >= MIN_WITHDRAW:
        amount = user.balance
        
        usd_val = (amount / 100000) * USD_PER_100K
        ton_val = usd_val / TON_PRICE_USD
        
        user.wallet = wallet
        user.balance = 0
        user.total_withdrawn += amount
        
        wd = Withdraw(
            user_id=uid, 
            username=user.username,
            amount_coins=amount, 
            ton_value=ton_val, 
            wallet=wallet
        )
        db.session.add(wd)
        db.session.commit()
        
        # إشعار للأدمن (لك أنت)
        msg = f"🚨 <b>طلب سحب جديد!</b>\n" \
              f"👤 المستخدم: @{user.username} ({user.name})\n" \
              f"💰 المبلغ: {amount} نقطة\n" \
              f"💎 القيمة: {ton_val:.4f} TON\n" \
              f"🏦 المحفظة:\n<code>{wallet}</code>"
        
        send_telegram_msg(ADMIN_TELEGRAM_ID, msg)

        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/api/set_language', methods=['POST'])
def set_language():
    data = request.json
    user = User.query.get(data.get('user_id'))
    if user:
        user.language = data.get('lang')
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/api/daily_bonus', methods=['POST'])
def daily_bonus():
    data = request.json
    user = User.query.get(data.get('user_id'))
    if user:
        now = datetime.utcnow()
        if user.last_daily_bonus and (now - user.last_daily_bonus) < timedelta(days=1):
            return jsonify({"success": False})
        user.balance += DAILY_BONUS
        user.last_daily_bonus = now
        db.session.commit()
        return jsonify({"success": True, "new_balance": user.balance})
    return jsonify({"success": False})

@app.route('/admin_panel_secret_key_99')
def admin():
    withdrawals = Withdraw.query.filter_by(status='pending').all()
    stats = {
        'users': User.query.count(),
        'ads': db.session.query(db.func.sum(User.ads_watched)).scalar() or 0
    }
    return render_template('admin.html', reqs=withdrawals, stats=stats)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
