from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
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
    role = db.Column(db.String(20), default="EMPLOYEE")
    active = db.Column(db.Boolean, default=True)


class Tank(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    fuel_type = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Float, default=10000)
    current_stock = db.Column(db.Float, default=0)


class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    fuel_type = db.Column(db.String(20), nullable=False)
    opening_meter = db.Column(db.Float, default=0)
    active = db.Column(db.Boolean, default=True)


class DailyReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_date = db.Column(db.Date, nullable=False)
    machine_id = db.Column(
        db.Integer, db.ForeignKey("machine.id"), nullable=False
    )
    opening_meter = db.Column(db.Float, nullable=False)
    closing_meter = db.Column(db.Float)
    litres_sold = db.Column(db.Float)
    entered_by = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    machine = db.relationship("Machine")
    user = db.relationship("User")


class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_date = db.Column(db.Date, nullable=False)
    tank_id = db.Column(
        db.Integer, db.ForeignKey("tank.id"), nullable=False
    )
    quantity = db.Column(db.Float, nullable=False)
    supplier = db.Column(db.String(150))
    invoice_number = db.Column(db.String(100))
    tanker_number = db.Column(db.String(100))
    entered_by = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tank = db.relationship("Tank")
    user = db.relationship("User")


class CorrectionRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reading_id = db.Column(
        db.Integer, db.ForeignKey("daily_reading.id"), nullable=False
    )
    old_closing = db.Column(db.Float, nullable=False)
    new_closing = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    requested_by = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    approved_by = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(20), default="PENDING")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)

    reading = db.relationship("DailyReading")
    requester = db.relationship(
        "User", foreign_keys=[requested_by]
    )
    approver = db.relationship(
        "User", foreign_keys=[approved_by]
    )


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")


class CustomerDue(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    customer_name = db.Column(
        db.String(150), nullable=False
    )
    mobile_number = db.Column(db.String(20))
    vehicle_number = db.Column(db.String(30))

    fuel_type = db.Column(
        db.String(20), nullable=False
    )
    quantity = db.Column(
        db.Float, nullable=False
    )

    total_amount = db.Column(
        db.Float, nullable=False
    )
    paid_amount = db.Column(
        db.Float, default=0
    )
    remaining_amount = db.Column(
        db.Float, nullable=False
    )

    status = db.Column(
        db.String(20), default="PENDING"
    )
    business_date = db.Column(
        db.Date, default=date.today
    )

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )
    settled_at = db.Column(db.DateTime)

    entered_by = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )

    user = db.relationship("User")


def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "user_id" in session:
            return f(*a, **k)

        return redirect(url_for("login"))

    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if session.get("role") != "ADMIN":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))

        return f(*a, **k)

    return w


def log(action, details=""):
    db.session.add(
        AuditLog(
            user_id=session["user_id"],
            action=action,
            details=details
        )
    )
    db.session.commit()


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        u = User.query.filter_by(username=username).first()

        if (
            u
            and u.active
            and check_password_hash(u.password_hash, password)
        ):
            session["user_id"] = u.id
            session["name"] = u.name
            session["role"] = u.role

            log("LOGIN", f"{u.name} logged in")

            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user = User.query.get_or_404(session["user_id"])

    if request.method == "POST":
        current_password = request.form.get(
            "current_password", ""
        )
        new_password = request.form.get(
            "new_password", ""
        )
        confirm_password = request.form.get(
            "confirm_password", ""
        )

        if not check_password_hash(
            user.password_hash,
            current_password
        ):
            flash(
                "Current password is incorrect.",
                "error"
            )
            return redirect(
                url_for("change_password")
            )

        if len(new_password) < 6:
            flash(
                "New password must be at least 6 characters.",
                "error"
            )
            return redirect(
                url_for("change_password")
            )

        if new_password != confirm_password:
            flash(
                "New passwords do not match.",
                "error"
            )
            return redirect(
                url_for("change_password")
            )

        if current_password == new_password:
            flash(
                "New password must be different from the current password.",
                "error"
            )
            return redirect(
                url_for("change_password")
            )

        user.password_hash = generate_password_hash(
            new_password
        )

        db.session.commit()

        log(
            "PASSWORD_CHANGED",
            f"Password changed for user {user.username}"
        )

        flash(
            "Password changed successfully.",
            "success"
        )

        return redirect(url_for("dashboard"))

    return render_template("change_password.html")


@app.route("/logout")
@login_required
def logout():
    log(
        "LOGOUT",
        f"{session.get('name')} logged out"
    )

    session.clear()

    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    tanks = Tank.query.all()

    readings = DailyReading.query.filter_by(
        business_date=date.today()
    ).all()

    pending = CorrectionRequest.query.filter_by(
        status="PENDING"
    ).count()

    dues = CustomerDue.query.filter(
        CustomerDue.remaining_amount > 0
    ).all()

    return render_template(
        "dashboard.html",
        tanks=tanks,
        pending=pending,
        readings=readings,
        diesel_stock=sum(
            t.current_stock
            for t in tanks
            if t.fuel_type == "DIESEL"
        ),
        petrol_stock=sum(
            t.current_stock
            for t in tanks
            if t.fuel_type == "PETROL"
        ),
        diesel_sold=sum(
            (r.litres_sold or 0)
            for r in readings
            if r.machine.fuel_type == "DIESEL"
        ),
        petrol_sold=sum(
            (r.litres_sold or 0)
            for r in readings
            if r.machine.fuel_type == "PETROL"
        ),
        total_due_amount=sum(
            d.remaining_amount for d in dues
        ),
        pending_due_count=len(dues)
    )


@app.route("/daily", methods=["GET", "POST"])
@login_required
def daily():
    if request.method == "POST":
        d = date.fromisoformat(
            request.form["business_date"]
        )

        for m in Machine.query.filter_by(
            active=True
        ).all():

            v = request.form.get(
                f"closing_{m.id}"
            )

            if not v:
                continue

            if DailyReading.query.filter_by(
                business_date=d,
                machine_id=m.id
            ).first():
                continue

            closing = float(v)

            if closing < m.opening_meter:
                continue

            sold = closing - m.opening_meter

            db.session.add(
                DailyReading(
                    business_date=d,
                    machine_id=m.id,
                    opening_meter=m.opening_meter,
                    closing_meter=closing,
                    litres_sold=sold,
                    entered_by=session["user_id"]
                )
            )

            m.opening_meter = closing

        db.session.commit()

        log(
            "DAILY_CLOSING",
            f"Closing readings entered for {d}"
        )

        flash(
            "24-hour closing readings saved.",
            "success"
        )

        return redirect(url_for("daily"))

    d = date.today()

    machines = Machine.query.filter_by(
        active=True
    ).all()

    existing = {
        r.machine_id: r
        for r in DailyReading.query.filter_by(
            business_date=d
        ).all()
    }

    return render_template(
        "daily.html",
        machines=machines,
        existing=existing,
        business_date=d,
        diesel_total=sum(
            (r.litres_sold or 0)
            for r in existing.values()
            if r.machine.fuel_type == "DIESEL"
        ),
        petrol_total=sum(
            (r.litres_sold or 0)
            for r in existing.values()
            if r.machine.fuel_type == "PETROL"
        )
    )


@app.route("/purchase", methods=["GET", "POST"])
@login_required
def purchase():
    if request.method == "POST":
        t = Tank.query.get_or_404(
            int(request.form["tank_id"])
        )

        q = float(request.form["quantity"])

        if q <= 0 or t.current_stock + q > t.capacity:
            flash(
                "Invalid quantity or tank capacity exceeded.",
                "error"
            )
            return redirect(url_for("purchase"))

        db.session.add(
            Purchase(
                business_date=date.fromisoformat(
                    request.form["business_date"]
                ),
                tank_id=t.id,
                quantity=q,
                supplier=request.form.get("supplier"),
                invoice_number=request.form.get(
                    "invoice_number"
                ),
                tanker_number=request.form.get(
                    "tanker_number"
                ),
                entered_by=session["user_id"]
            )
        )

        t.current_stock += q

        db.session.commit()

        log(
            "FUEL_PURCHASE",
            f"{t.name}: +{q} L"
        )

        flash(
            "Fuel purchase saved.",
            "success"
        )

        return redirect(url_for("purchase"))

    return render_template(
        "purchase.html",
        tanks=Tank.query.all(),
        purchases=Purchase.query.order_by(
            Purchase.created_at.desc()
        ).limit(30).all(),
        today=date.today()
    )


@app.route("/dues", methods=["GET", "POST"])
@login_required
def dues():
    if request.method == "POST":
        try:
            q = float(
                request.form["quantity"]
            )

            amount = float(
                request.form["total_amount"]
            )

            if q <= 0 or amount <= 0:
                raise ValueError

            due = CustomerDue(
                customer_name=request.form[
                    "customer_name"
                ].strip(),

                mobile_number=request.form.get(
                    "mobile_number",
                    ""
                ).strip(),

                vehicle_number=request.form.get(
                    "vehicle_number",
                    ""
                ).strip().upper(),

                fuel_type=request.form[
                    "fuel_type"
                ],

                quantity=q,

                total_amount=amount,

                paid_amount=0,

                remaining_amount=amount,

                business_date=date.fromisoformat(
                    request.form["business_date"]
                ),

                entered_by=session["user_id"]
            )

            db.session.add(due)
            db.session.commit()

            log(
                "CUSTOMER_DUE_CREATED",
                f"{due.customer_name}: Rs. {amount:.2f} due"
            )

            flash(
                "Customer due added successfully.",
                "success"
            )

        except:
            flash(
                "Please enter valid due details.",
                "error"
            )

        return redirect(url_for("dues"))

    pending = CustomerDue.query.filter(
        CustomerDue.remaining_amount > 0
    ).order_by(
        CustomerDue.created_at.desc()
    ).all()

    paid = CustomerDue.query.filter_by(
        status="PAID"
    ).order_by(
        CustomerDue.settled_at.desc()
    ).all()

    return render_template(
        "dues.html",
        pending_dues=pending,
        paid_history=paid,
        total_pending=sum(
            x.remaining_amount for x in pending
        ),
        today=date.today()
    )


@app.route("/dues/<int:due_id>/pay", methods=["POST"])
@login_required
def pay_due(due_id):
    due = CustomerDue.query.get_or_404(
        due_id
    )

    try:
        p = float(
            request.form["payment_amount"]
        )

        if p <= 0 or p > due.remaining_amount:
            raise ValueError

        due.paid_amount += p

        due.remaining_amount = max(
            0,
            due.remaining_amount - p
        )

        if due.remaining_amount <= 0.01:
            due.remaining_amount = 0
            due.status = "PAID"
            due.settled_at = datetime.utcnow()

        db.session.commit()

        log(
            "DUE_PAYMENT",
            f"{due.customer_name} paid Rs. {p:.2f}; "
            f"remaining Rs. {due.remaining_amount:.2f}"
        )

        flash(
            "Payment recorded successfully.",
            "success"
        )

    except:
        flash(
            "Invalid payment amount.",
            "error"
        )

    return redirect(url_for("dues"))


@app.route("/corrections", methods=["GET", "POST"])
@login_required
def corrections():
    if request.method == "POST":
        r = DailyReading.query.get_or_404(
            int(request.form["reading_id"])
        )

        db.session.add(
            CorrectionRequest(
                reading_id=r.id,
                old_closing=r.closing_meter,
                new_closing=float(
                    request.form["new_closing"]
                ),
                reason=request.form["reason"],
                requested_by=session["user_id"]
            )
        )

        db.session.commit()

        log(
            "CORRECTION_REQUEST",
            f"Reading #{r.id}"
        )

        flash(
            "Correction request sent.",
            "success"
        )

        return redirect(
            url_for("corrections")
        )

    return render_template(
        "corrections.html",
        readings=DailyReading.query.order_by(
            DailyReading.business_date.desc()
        ).limit(50).all(),

        requests=CorrectionRequest.query.order_by(
            CorrectionRequest.created_at.desc()
        ).limit(50).all()
    )


@app.route(
    "/corrections/<int:req_id>/<action>",
    methods=["POST"]
)
@login_required
@admin_required
def correction_action(req_id, action):
    c = CorrectionRequest.query.get_or_404(
        req_id
    )

    if c.status == "PENDING":

        if action == "approve":
            r = c.reading

            if c.new_closing >= r.opening_meter:
                r.closing_meter = c.new_closing
                r.litres_sold = (
                    c.new_closing - r.opening_meter
                )
                r.machine.opening_meter = c.new_closing
                c.status = "APPROVED"

        elif action == "reject":
            c.status = "REJECTED"

        c.approved_by = session["user_id"]
        c.approved_at = datetime.utcnow()

        db.session.commit()

        log(
            "CORRECTION_" + c.status,
            f"Correction #{c.id}"
        )

    return redirect(
        url_for("corrections")
    )


@app.route("/admin/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    if request.method == "POST":
        username = request.form[
            "username"
        ].strip()

        if User.query.filter_by(
            username=username
        ).first():

            flash(
                "Username already exists.",
                "error"
            )

        else:
            db.session.add(
                User(
                    name=request.form[
                        "name"
                    ].strip(),

                    username=username,

                    password_hash=generate_password_hash(
                        request.form["password"]
                    ),

                    role=request.form["role"]
                )
            )

            db.session.commit()

            log(
                "USER_CREATED",
                username
            )

            flash(
                "User created.",
                "success"
            )

    return render_template(
        "users.html",
        users=User.query.all()
    )


@app.route("/admin/data")
@login_required
@admin_required
def admin_data():
    return render_template(
        "admin_data.html",
        users=User.query.order_by(User.id).all(),
        tanks=Tank.query.order_by(Tank.id).all(),
        machines=Machine.query.order_by(Machine.id).all(),
        readings=DailyReading.query.order_by(
            DailyReading.business_date.desc()
        ).all(),
        purchases=Purchase.query.order_by(
            Purchase.created_at.desc()
        ).all(),
        dues=CustomerDue.query.order_by(
            CustomerDue.created_at.desc()
        ).all(),
        corrections=CorrectionRequest.query.order_by(
            CorrectionRequest.created_at.desc()
        ).all(),
        logs=AuditLog.query.order_by(
            AuditLog.created_at.desc()
        ).all()
    )


@app.route("/audit")
@login_required
@admin_required
def audit():
    return render_template(
        "audit.html",
        logs=AuditLog.query.order_by(
            AuditLog.created_at.desc()
        ).limit(200).all()
    )


def seed():
    if not User.query.count():
        db.session.add(
            User(
                name="Main Admin",
                username="admin",
                password_hash=generate_password_hash(
                    "admin123"
                ),
                role="ADMIN"
            )
        )

    if not Tank.query.count():

        for i in range(1, 4):
            db.session.add(
                Tank(
                    name=f"Diesel Tank {i}",
                    fuel_type="DIESEL",
                    capacity=10000,
                    current_stock=5000
                )
            )

        for i in range(1, 3):
            db.session.add(
                Tank(
                    name=f"Petrol Tank {i}",
                    fuel_type="PETROL",
                    capacity=10000,
                    current_stock=5000
                )
            )

    if not Machine.query.count():

        for i in range(1, 6):
            db.session.add(
                Machine(
                    name=f"Diesel Machine {i}",
                    fuel_type="DIESEL"
                )
            )

        for i in range(1, 6):
            db.session.add(
                Machine(
                    name=f"Petrol Machine {i}",
                    fuel_type="PETROL"
                )
            )

    db.session.commit()


with app.app_context():
    db.create_all()
    seed()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
