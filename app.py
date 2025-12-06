from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import requests 

app = Flask(__name__)

# قاعدة البيانات
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users_pro_v6.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'DiamondSecretKey2025'

# 🔴 إعدادات البوت (توكنك وآيديك)
BOT_TOKEN = "8555461747:AAEQ_S9VDDPl6ICb-Nh1AC6BJ_05WDWUCB8"
ADMIN_ID = 1207530445

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
    
    # نظام الإحالة (التعقب)
    referrer_id = db.Column(db.Integer, nullable=True)   # من دعاني؟
    referral_bonus_paid = db.Column(db.Boolean, default=False) # هل دفعنا المكافأة؟
    
    wallet = db.Column(db.String(150), nullable=True)
    language = db.Column(db.String(10), default='ar')
    last_daily_bonus = db.Column(db.DateTime, nullable=True)
    last_ad_watched = db.Column(db.DateTime, nullable=True)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class Withdraw(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    username = db.Column(db.String(100))
    amount_coins = db.Column(db.Integer)
    ton_value = db.Column(db.Float)
    usd_value = db.Column(db.Float)
    wallet = db.Column(db.String(150))
    status = db.Column(db.String(20), default='pending')
    date = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- 📊 إعدادات الاقتصاد والربح ---
COINS_PER_AD = 250        # سعر الإعلان (جيد جداً)
REFERRAL_BONUS = 1000     # مكافأة الإحالة (بعد الشرط)
ADS_CONDITION = 20        # شرط الإحالة (مشاهدة 20 إعلان)
MIN_WITHDRAW = 100000     # الحد الأدنى للسحب
DOLLAR_RATE = 0.25        # 100 ألف نقطة = 0.25$
TON_PRICE = 6.5           # سعر التون التقريبي

# دالة إرسال الإشعارات
def send_telegram_msg(chat_id, text):
    if not BOT_TOKEN or not chat_id: return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': chat_id, 'text': text})
    except: pass

# --- API ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    uid = data.get('id')
    
    # 🔴 الحل لمشكلة تصفير النقاط:
    # نبحث عن المستخدم أولاً، إذا وجدناه لا نعدل رصيده
    user = User.query.get(uid)
    
    if not user:
        # مستخدم جديد فقط
        ref_id = data.get('start_param')
        final_ref = ref_id if (ref_id and str(ref_id) != str(uid)) else None
        
        user = User(
            id=uid, 
            name=data.get('name'), 
            username=data.get('username'),
            referrer_id=final_ref
        )
        db.session.add(user)
        
        # إشعار للمضيف (بدون دفع المكافأة الآن)
        if final_ref:
            referrer = User.query.get(final_ref)
            if referrer:
                referrer.referral_count += 1
                send_telegram_msg(final_ref, f"👤 انضم عضو جديد عبر رابطك: {data.get('name')}\n(ستحصل على {REFERRAL_BONUS} نقطة بعد مشاهدته {ADS_CONDITION} إعلانات)")
        
        db.session.commit()
    else:
        # مستخدم قديم: نحدث اسمه فقط، لا نلمس الرصيد
        user.name = data.get('name')
        user.username = data.get('username')
        db.session.commit()

    return jsonify({
        "balance": user.balance,
        "ads_watched": user.ads_watched,
        "referral_count": user.referral_count,
        "wallet": user.wallet,
        "language": user.language
    })

@app.route('/api/watch', methods=['POST'])
def watch():
    data = request.json
    uid = data.get('user_id')
    user = User.query.get(uid)
    
    if user:
        # حماية الوقت (10 ثواني)
        now = datetime.utcnow()
        if user.last_ad_watched and (now - user.last_ad_watched).total_seconds() < 10: 
            return jsonify({"error": "Too fast"}), 429
            
        user.balance += COINS_PER_AD
        user.ads_watched += 1
        user.last_ad_watched = now
        
        # 🔥 التحقق من شرط الإحالة (الجزئية التي طلبتها) 🔥
        if user.referrer_id and not user.referral_bonus_paid and user.ads_watched >= ADS_CONDITION:
            # الوصول للمضيف
            referrer = User.query.get(user.referrer_id)
            if referrer:
                referrer.balance += REFERRAL_BONUS
                user.referral_bonus_paid = True # تم الدفع، لن ندفع مرة أخرى
                send_telegram_msg(user.referrer_id, f"💰 مبروك! أحد أصدقائك أكمل {ADS_CONDITION} إعلانات.\nتمت إضافة {REFERRAL_BONUS} نقطة لرصيدك.")
        
        db.session.commit()
        return jsonify({"success": True, "new_balance": user.balance, "ads_watched": user.ads_watched})
    
    return jsonify({"error": "User not found"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    uid = data.get('user_id')
    wallet = data.get('wallet')
    amount = int(data.get('amount', 0))
    
    user = User.query.get(uid)
    
    if user and amount >= MIN_WITHDRAW and user.balance >= amount:
        # الحسابات
        usd_val = (amount / 100000) * DOLLAR_RATE
        ton_val = usd_val / TON_PRICE
        
        user.wallet = wallet
        user.balance -= amount
        user.total_withdrawn += amount
        
        wd = Withdraw(
            user_id=uid, username=user.username, amount_coins=amount,
            ton_value=ton_val, usd_value=usd_val, wallet=wallet
        )
        db.session.add(wd)
        db.session.commit()
        
        # إشعار لك (الأدمن)
        msg = f"🚨 <b>طلب سحب جديد!</b>\n👤 @{user.username}\n💰 {amount} نقطة\n💵 {usd_val:.2f} $\n💎 {ton_val:.4f} TON\n🏦 <code>{wallet}</code>"
        send_telegram_msg(ADMIN_ID, msg)
        
        return jsonify({"success": True, "new_balance": user.balance})
        
    return jsonify({"success": False, "message": "Low Balance"})

@app.route('/api/daily', methods=['POST'])
def daily():
    data = request.json
    user = User.query.get(data.get('user_id'))
    if user:
        now = datetime.utcnow()
        if user.last_daily_bonus and (now - user.last_daily_bonus) < timedelta(days=1):
            return jsonify({"success": False})
        user.balance += 50
        user.last_daily_bonus = now
        db.session.commit()
        return jsonify({"success": True, "new_balance": user.balance})
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

@app.route('/admin_panel_secret_key_99')
def admin():
    withdrawals = Withdraw.query.filter_by(status='pending').all()
    stats = {'users': User.query.count(), 'ads': db.session.query(db.func.sum(User.ads_watched)).scalar() or 0}
    return render_template('admin.html', reqs=withdrawals, stats=stats)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
        
