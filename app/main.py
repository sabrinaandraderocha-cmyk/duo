import os
import secrets
from datetime import date, datetime

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import User, Couple, Entry
from .security import hash_password, verify_password

# =========================
# Paths (robusto no Windows)
# =========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# cria tabelas
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Duo")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "duo-change-me"),
    same_site="lax",
    https_only=False,  # em produção (HTTPS) pode virar True
    max_age=60 * 60 * 24 * 7,  # 7 dias
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


# =========================
# Helpers
# =========================
def current_user(request: Request, db: Session) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    return db.get(User, uid)

def redirect_to(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)

def empty_side() -> dict:
    return {
        "mood": "",
        "moment_special": "",
        "love_action": "",
        "character": "",
        "music": "",
        "updated_at": "",
    }

def get_partner_name(db: Session, couple_id: int, my_user_id: int) -> str | None:
    partner = (
        db.query(User)
        .filter(User.couple_id == couple_id, User.id != my_user_id)
        .order_by(User.id.asc())
        .first()
    )
    return partner.name if partner else None


# =========================
# Auth
# =========================
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email_norm = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email_norm).first()

    ok = False
    if user:
        try:
            ok = verify_password(password, user.password_hash)
        except Exception:
            ok = False

    if not user or not ok:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "E-mail ou senha inválidos."},
            status_code=400,
        )

    request.session["uid"] = user.id
    return redirect_to("/")

@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
def signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    name_norm = (name or "").strip()
    email_norm = (email or "").strip().lower()

    if db.query(User).filter(User.email == email_norm).first():
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Esse e-mail já está cadastrado."},
            status_code=400,
        )

    try:
        pw_hash = hash_password(password)
    except ValueError as e:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": str(e)},
            status_code=400,
        )
    except Exception:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Não foi possível criar a senha. Tente uma senha menor."},
            status_code=400,
        )

    user = User(
        name=name_norm,
        email=email_norm,
        password_hash=pw_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["uid"] = user.id
    return redirect_to("/pair")

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect_to("/login")


# =========================
# Pairing (casal)
# =========================
@app.get("/pair", response_class=HTMLResponse)
def pair_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    couple = db.get(Couple, u.couple_id) if u.couple_id else None
    partner_name = get_partner_name(db, u.couple_id, u.id) if u.couple_id else None

    return templates.TemplateResponse(
        "pair.html",
        {"request": request, "user": u, "couple": couple, "partner_name": partner_name},
    )

@app.post("/pair/create")
def pair_create(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    if u.couple_id:
        return redirect_to("/")

    code = None
    for _ in range(10):
        candidate = secrets.token_hex(4)  # 8 chars
        exists = db.query(Couple).filter(Couple.code == candidate).first()
        if not exists:
            code = candidate
            break

    if not code:
        code = secrets.token_hex(6)

    couple = Couple(code=code)
    db.add(couple)
    db.commit()
    db.refresh(couple)

    u.couple_id = couple.id
    db.add(u)
    db.commit()

    return redirect_to("/pair")

@app.post("/pair/join")
def pair_join(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    if u.couple_id:
        return redirect_to("/")

    code_norm = (code or "").strip()
    couple = db.query(Couple).filter(Couple.code == code_norm).first()

    if not couple:
        return templates.TemplateResponse(
            "pair.html",
            {"request": request, "user": u, "couple": None, "error": "Código inválido."},
            status_code=400,
        )

    u.couple_id = couple.id
    db.add(u)
    db.commit()
    return redirect_to("/")


# =========================
# Home (timeline)
# =========================
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    if not u.couple_id:
        return redirect_to("/pair")

    partner_name = get_partner_name(db, u.couple_id, u.id)

    entries = (
        db.query(Entry)
        .filter(Entry.couple_id == u.couple_id)
        .order_by(Entry.day.desc())
        .all()
    )

    by_day: dict[str, dict] = {}
    for e in entries:
        d = by_day.setdefault(
            e.day,
            {"day": e.day, "created_at": "", "me": None, "par": None},
        )

        side_payload = {
            "mood": e.mood or "",
            "moment_special": e.moment_special or "",
            "love_action": e.love_action or "",
            "character": e.character or "",
            "music": e.music or "",
            "updated_at": e.updated_at or "",
        }

        if e.author == "me":
            d["me"] = side_payload
        elif e.author == "par":
            d["par"] = side_payload

        d["created_at"] = d["created_at"] or (e.updated_at or "")

    days = sorted(by_day.keys(), reverse=True)
    rows = []
    for day_key in days:
        d = by_day[day_key]
        d["me"] = d["me"] or empty_side()
        d["par"] = d["par"] or empty_side()
        rows.append(d)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "entries": rows, "user": u, "partner_name": partner_name},
    )


# =========================
# Save (upsert por dia+lado)
# =========================
@app.post("/save_side")
def save_side(
    request: Request,
    author: str = Form(...),  # "me" ou "par"
    mood: str = Form(""),
    moment_special: str = Form(""),
    love_action: str = Form(""),
    character: str = Form(""),
    music: str = Form(""),
    day: str = Form(""),
    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    if not u.couple_id:
        return redirect_to("/pair")

    if author not in ("me", "par"):
        return redirect_to("/")

    if not day:
        day = date.today().isoformat()

    # ✅ AGORA SEM HORA
    now = datetime.now().strftime("%d/%m/%Y")

    existing = (
        db.query(Entry)
        .filter(
            Entry.couple_id == u.couple_id,
            Entry.day == day,
            Entry.author == author,
        )
        .first()
    )

    if not existing:
        existing = Entry(couple_id=u.couple_id, day=day, author=author)
        db.add(existing)

    existing.mood = (mood or "").strip()
    existing.moment_special = (moment_special or "").strip()
    existing.love_action = (love_action or "").strip()
    existing.character = (character or "").strip()
    existing.music = (music or "").strip()
    existing.updated_at = now

    db.commit()
    return redirect_to("/")
