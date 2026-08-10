from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///petrol_pump.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="EMPLOYEE")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Tank(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    fuel_type = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Float, nullable=False, default=10000)
    current_stock = db.Column(db.Float, nullable=False, default=0)

class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    fuel_type = db.Column(db.String(20), nullable=False)
    opening_meter = db.Column(db.Float, default=0)
    active = db.Column(db.Boolean, default=True)

class DailyReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_date = db.Column(db.Date, nullable=False)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=False)
    opening_meter = db.Column(db.Float, nullable=False)
    closing_meter = db.Column(db.Float, nullable=True)
    litres_sold = db.Column(db.Float, nullable=True)
    entered_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    machine = db.relationship("Machine")
    user = db.relationship("User")

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_date = db.Column(db.Date, nullable=False)
    tank_id = db.Column(db.Integer, db.ForeignKey("tank.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    supplier = db.Column(db.String(150))
    invoice_number = db.Column(db.String(100))
    tanker_number = db.Column(db.String(100))
    entered_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tank = db.relationship("Tank")
    user = db.relationship("User")

class CorrectionRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(db.Integer, db.ForeignKey("daily_reading.id"), nullable=False)
    old_closing = db.Column(db.Float, nullable=False)
    new_closing = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(20), default="PENDING")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    reading = db.relationship("DailyReading")
    requester = db.relationship("User", foreign_keys=[requested_by])
    approver = db.relationship("User", foreign_keys=[approved_by])

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("role") != "ADMIN":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper

def log(action, details=""):
    db.session.add(AuditLog(user_id=session["user_id"], action=action, details=details))
    db.session.commit()

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["username"].strip()).first()
        if u and u.active and check_password_hash(u.password_hash, request.form["password"]):
            session["user_id"] = u.id
            session["name"] = u.name
            session["role"] = u.role
            log("LOGIN", f"{u.name} logged in")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    log("LOGOUT", f"{session.get('name')} logged out")
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    tanks = Tank.query.order_by(Tank.id).all()
    machines = Machine.query.order_by(Machine.id).all()
    pending = CorrectionRequest.query.filter_by(status="PENDING").count()
    today = date.today()
    readings = DailyReading.query.filter_by(business_date=today).all()
    diesel_sold = sum((r.litres_sold or 0) for r in readings if r.machine.fuel_type == "DIESEL")
    petrol_sold = sum((r.litres_sold or 0) for r in readings if r.machine.fuel_type == "PETROL")
    diesel_stock = sum(t.current_stock for t in tanks if t.fuel_type == "DIESEL")
    petrol_stock = sum(t.current_stock for t in tanks if t.fuel_type == "PETROL")
    return render_template("dashboard.html", tanks=tanks, machines=machines,
                           pending=pending, diesel_sold=diesel_sold,
                           petrol_sold=petrol_sold, diesel_stock=diesel_stock,
                           petrol_stock=petrol_stock, readings=readings)

@app.route("/daily", methods=["GET", "POST"])
@login_required
def daily():
    business_date = date.fromisoformat(request.form["business_date"]) if request.method == "POST" else date.today()
    if request.method == "POST":
        for machine in Machine.query.filter_by(active=True).all():
            key = f"closing_{machine.id}"
            if not request.form.get(key):
                continue
            closing = float(request.form[key])
            existing = DailyReading.query.filter_by(
                business_date=business_date, machine_id=machine.id
            ).first()
            if existing:
                flash(f"{machine.name} already has a closing entry. Use correction for mistakes.", "error")
                continue
            opening = machine.opening_meter or 0
            if closing < opening:
                flash(f"{machine.name}: closing meter cannot be below opening meter.", "error")
                continue
            sold = closing - opening
            db.session.add(DailyReading(
                business_date=business_date, machine_id=machine.id,
                opening_meter=opening, closing_meter=closing,
                litres_sold=sold, entered_by=session["user_id"]
            ))
            machine.opening_meter = closing
        db.session.commit()
        log("DAILY_CLOSING", f"Closing readings entered for {business_date}")
        flash("24-hour closing readings saved.", "success")
        return redirect(url_for("daily"))
    machines = Machine.query.filter_by(active=True).order_by(Machine.id).all()
    existing = {r.machine_id: r for r in DailyReading.query.filter_by(business_date=business_date).all()}
    diesel_total = sum((r.litres_sold or 0) for r in existing.values() if r.machine.fuel_type == "DIESEL")
    petrol_total = sum((r.litres_sold or 0) for r in existing.values() if r.machine.fuel_type == "PETROL")
    return render_template("daily.html", machines=machines, existing=existing,
                           business_date=business_date, diesel_total=diesel_total,
                           petrol_total=petrol_total)

@app.route("/purchase", methods=["GET", "POST"])
@login_required
def purchase():
    if request.method == "POST":
        tank = Tank.query.get_or_404(int(request.form["tank_id"]))
        qty = float(request.form["quantity"])
        if qty <= 0 or tank.current_stock + qty > tank.capacity:
            flash("Invalid quantity or tank capacity exceeded.", "error")
            return redirect(url_for("purchase"))
        p = Purchase(
            business_date=date.fromisoformat(request.form["business_date"]),
            tank_id=tank.id, quantity=qty,
            supplier=request.form.get("supplier"),
            invoice_number=request.form.get("invoice_number"),
            tanker_number=request.form.get("tanker_number"),
            entered_by=session["user_id"]
        )
        tank.current_stock += qty
        db.session.add(p)
        db.session.commit()
        log("FUEL_PURCHASE", f"{tank.name}: +{qty} L")
        flash("Fuel purchase saved and stock updated.", "success")
        return redirect(url_for("purchase"))
    purchases = Purchase.query.order_by(Purchase.created_at.desc()).limit(30).all()
    return render_template("purchase.html", tanks=Tank.query.all(), purchases=purchases, today=date.today())

@app.route("/corrections", methods=["GET", "POST"])
@login_required
def corrections():
    if request.method == "POST":
        reading = DailyReading.query.get_or_404(int(request.form["reading_id"]))
        if CorrectionRequest.query.filter_by(reading_id=reading.id, status="PENDING").first():
            flash("A correction is already pending for this entry.", "error")
        else:
            db.session.add(CorrectionRequest(
                reading_id=reading.id,
                old_closing=reading.closing_meter,
                new_closing=float(request.form["new_closing"]),
                reason=request.form["reason"],
                requested_by=session["user_id"]
            ))
            db.session.commit()
            log("CORRECTION_REQUEST", f"Reading #{reading.id}")
            flash("Correction request sent to admin.", "success")
        return redirect(url_for("corrections"))
    readings = DailyReading.query.order_by(DailyReading.business_date.desc()).limit(50).all()
    requests = CorrectionRequest.query.order_by(CorrectionRequest.created_at.desc()).limit(50).all()
    return render_template("corrections.html", readings=readings, requests=requests)

@app.route("/corrections/<int:req_id>/<action>", methods=["POST"])
@login_required
@admin_required
def correction_action(req_id, action):
    cr = CorrectionRequest.query.get_or_404(req_id)
    if cr.status != "PENDING":
        flash("This request is already processed.", "error")
        return redirect(url_for("corrections"))
    if action == "approve":
        r = cr.reading
        old_sold = r.litres_sold or 0
        new_sold = cr.new_closing - r.opening_meter
        if cr.new_closing < r.opening_meter:
            flash("New closing meter is invalid.", "error")
            return redirect(url_for("corrections"))
        r.closing_meter = cr.new_closing
        r.litres_sold = new_sold
        r.machine.opening_meter = cr.new_closing
        cr.status = "APPROVED"
        cr.approved_by = session["user_id"]
        cr.approved_at = datetime.utcnow()
        db.session.commit()
        log("CORRECTION_APPROVED", f"Reading #{r.id}: {old_sold}L -> {new_sold}L")
        flash("Correction approved.", "success")
    elif action == "reject":
        cr.status = "REJECTED"
        cr.approved_by = session["user_id"]
        cr.approved_at = datetime.utcnow()
        db.session.commit()
        log("CORRECTION_REJECTED", f"Correction #{cr.id}")
        flash("Correction rejected.", "success")
    return redirect(url_for("corrections"))

@app.route("/admin/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    if request.method == "POST":
        username = request.form["username"].strip()
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
        else:
            db.session.add(User(
                name=request.form["name"].strip(), username=username,
                password_hash=generate_password_hash(request.form["password"]),
                role=request.form["role"]
            ))
            db.session.commit()
            log("USER_CREATED", username)
            flash("User created.", "success")
    return render_template("users.html", users=User.query.order_by(User.id).all())

@app.route("/audit")
@login_required
@admin_required
def audit():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return render_template("audit.html", logs=logs)

def seed():
    if User.query.count() == 0:
        db.session.add(User(name="Main Admin", username="admin",
                            password_hash=generate_password_hash("admin123"),
                            role="ADMIN"))
    if Tank.query.count() == 0:
        for i in range(1, 4):
            db.session.add(Tank(name=f"Diesel Tank {i}", fuel_type="DIESEL", capacity=10000, current_stock=5000))
        for i in range(1, 3):
            db.session.add(Tank(name=f"Petrol Tank {i}", fuel_type="PETROL", capacity=10000, current_stock=5000))
    if Machine.query.count() == 0:
        for i in range(1, 6):
            db.session.add(Machine(name=f"Diesel Machine {i}", fuel_type="DIESEL"))
        for i in range(1, 6):
            db.session.add(Machine(name=f"Petrol Machine {i}", fuel_type="PETROL"))
    db.session.commit()

with app.app_context():
    db.create_all()
    seed()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
