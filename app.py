from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import requests # لإرسال الإشعارات

app = Flask(__name__)

# --- إعدادات هامة ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'MegaSecretKey2025'
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE" # 🔴 ضع توكن البوت هنا لإرسال الإشعارات

db = SQLAlchemy(app)

# --- الجداول المحدثة ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    username = db.Column(db.String(100))
    balance = db.Column(db.Integer, default=0)
    
    # إحصائيات مفصلة
    ads_watched = db.Column(db.Integer, default=0)       # عدد الإعلانات المشاهدة
    total_withdrawn = db.Column(db.Float, default=0.0)   # مجموع السحوبات (نقاط)
    referral_count = db.Column(db.Integer, default=0)    # عدد الأشخاص الذين دعوتهم
    
    # نظام الإحالة
    referrer_id = db.Column(db.Integer, nullable=True)   # من قام بدعوتي
    referral_bonus_paid = db.Column(db.Boolean, default=False) # هل دفعنا للمضيف مكافأة عني؟
    
    wallet = db.Column(db.String(150), nullable=True)
    language = db.Column(db.String(10), default='ar')
    last_daily_bonus = db.Column(db.DateTime, nullable=True)
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

# --- الثوابت المالية ---
COINS_PER_AD = 100
DAILY_BONUS = 50
REFERRAL_BONUS = 500
ADS_REQUIRED_FOR_REF = 20 # 🔴 عدد الإعلانات المطلوبة لاحتساب الإحالة
MIN_WITHDRAW = 50000

# سعر الصرف التقريبي (يمكن تحديثه)
# 100,000 نقطة = 0.5 دولار
USD_PER_100K = 0.5 
TON_PRICE_USD = 6.5 # سعر التون بالدولار (تقريبي)

# دالة إرسال إشعار عبر تيليجرام
def send_telegram_msg(chat_id, text):
    if not BOT_TOKEN or chat_id is None: return
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
        # مستخدم جديد
        ref_id = data.get('start_param')
        # تأكد أن المستخدم لا يدعو نفسه
        final_ref = ref_id if (ref_id and str(ref_id) != str(uid)) else None
        
        user = User(
            id=uid, 
            name=data.get('name'), 
            username=data.get('username'),
            referrer_id=final_ref
        )
        db.session.add(user)
        
        # إشعار للمضيف بأن شخصاً سجل عن طريقه
        if final_ref:
            referrer = User.query.get(final_ref)
            if referrer:
                referrer.referral_count += 1
                send_telegram_msg(final_ref, f"🎉 مستخدم جديد انضم عبر رابطك: {data.get('name')}\n(ستحصل على المكافأة بعد مشاهدته {ADS_REQUIRED_FOR_REF} إعلانات)")
        
        db.session.commit()
    else:
        # تحديث البيانات
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
        user.balance += COINS_PER_AD
        user.ads_watched += 1
        
        # --- التحقق من شرط الإحالة (20 إعلان) ---
        if user.referrer_id and not user.referral_bonus_paid and user.ads_watched >= ADS_REQUIRED_FOR_REF:
            referrer = User.query.get(user.referrer_id)
            if referrer:
                referrer.balance += REFERRAL_BONUS
                user.referral_bonus_paid = True
                send_telegram_msg(user.referrer_id, f"💰 مبروك! أحد مدعويك أكمل {ADS_REQUIRED_FOR_REF} إعلانات. تم إضافة {REFERRAL_BONUS} نقطة لرصيدك.")
        
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
        
        # الحسابات المالية
        usd_val = (amount / 100000) * USD_PER_100K
        ton_val = usd_val / TON_PRICE_USD
        
        user.wallet = wallet
        user.balance = 0
        user.total_withdrawn += amount # تحديث مجموع السحوبات
        
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

# لوحة الأدمن (مخفية)
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
