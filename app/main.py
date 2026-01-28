import os
import secrets
import random
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

# =====================================================
# Paths
# =====================================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Duo")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "duo-change-me"),
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 24 * 7,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# =====================================================
# Configs
# =====================================================
DIARY_TAGS = {
    "hoje_tem": "😏 Hoje tem",
    "quero_filme": "🎬 Hoje quero um filme",
    "quero_massagem": "💆 Hoje quero massagem",
    "estressada": "😤 Hoje estou estressada",
    "saudades": "💋 Saudades, quero beijo",
}

QUESTION_SETS = {
    "divertidas": [
        "Se a gente fosse um filme, qual seria o gênero?",
        "Qual seria nosso nome de dupla?",
        "Qual mania minha você acha fofa?",
        "Que música tocaria se a gente entrasse numa festa?",
        "Se a gente pudesse viajar agora, pra onde iríamos?",
    ],
    "romanticas": [
        "O que você mais admira em mim?",
        "Quando você percebeu que era amor?",
        "Como posso te amar melhor?",
        "Qual gesto meu te faz se sentir seguro(a)?",
    ],
    "picantes_leves": [
        "Hoje eu te daria um beijo que é…",
        "De 0 a ‘vem cá’, quanto você tá com saudade?",
        "Qual meu ponto fraco?",
        "Beijo, abraço ou cafuné?",
    ],
}

# =====================================================
# Helpers
# =====================================================
def redirect_to(url: str):
    return RedirectResponse(url, status_code=303)

def current_user(request: Request, db: Session):
    uid = request.session.get("uid")
    return db.get(User, uid) if uid else None

def get_roles(db: Session, couple_id: int, my_user_id: int):
    users = (
        db.query(User)
        .filter(User.couple_id == couple_id)
        .order_by(User.id.asc())
        .all()
    )

    if len(users) < 2:
        return {"self_author": "me", "partner_author": "par", "partner_name": None}

    first, second = users[0], users[1]

    if my_user_id == first.id:
        return {"self_author": "me", "partner_author": "par", "partner_name": second.name}
    return {"self_author": "par", "partner_author": "me", "partner_name": first.name}

def split_tags(csv: str):
    return [t for t in (csv or "").split(",") if t.strip()]

def join_tags(tags: list[str]):
    seen = []
    for t in (tags or []):
        t = (t or "").strip()
        if not t:
            continue
        if t not in seen:
            seen.append(t)
    return ",".join(seen)

# =====================================================
# Auth
# =====================================================
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

    if not user or not verify_password(password, user.password_hash):
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
            {"request": request, "error": "E-mail já cadastrado."},
            status_code=400,
        )

    user = User(
        name=name_norm,
        email=email_norm,
        password_hash=hash_password(password),
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

# =====================================================
# Pair
# =====================================================
@app.get("/pair", response_class=HTMLResponse)
def pair_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    couple = db.get(Couple, u.couple_id) if u.couple_id else None
    partner_name = None
    if u.couple_id:
        partner_name = get_roles(db, u.couple_id, u.id)["partner_name"]

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

    # tenta gerar um código único
    code = None
    for _ in range(10):
        candidate = secrets.token_hex(4)
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
    db.commit()

    return redirect_to("/pair")

@app.post("/pair/join")
def pair_join(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if u.couple_id:
        return redirect_to("/")

    couple = db.query(Couple).filter(Couple.code == (code or "").strip()).first()
    if not couple:
        return templates.TemplateResponse(
            "pair.html",
            {"request": request, "user": u, "couple": None, "error": "Código inválido."},
            status_code=400,
        )

    u.couple_id = couple.id
    db.commit()
    return redirect_to("/")

# =====================================================
# Home
# =====================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    roles = get_roles(db, u.couple_id, u.id)

    entries = (
        db.query(Entry)
        .filter(Entry.couple_id == u.couple_id)
        .order_by(Entry.day.desc())
        .all()
    )

    by_day = {}
    for e in entries:
        d = by_day.setdefault(e.day, {"day": e.day, "me": None, "par": None, "created_at": ""})
        payload = {
            "mood": e.mood or "",
            "moment_special": e.moment_special or "",
            "love_action": e.love_action or "",
            "character": e.character or "",
            "music": e.music or "",
            "updated_at": e.updated_at or "",
            "tags": split_tags(getattr(e, "tags_csv", "") or ""),
        }

        if e.author == roles["self_author"]:
            d["me"] = payload
        elif e.author == roles["partner_author"]:
            d["par"] = payload

        d["created_at"] = d["created_at"] or (e.updated_at or "")

    days_sorted = sorted(by_day.keys(), reverse=True)
    rows = []
    for k in days_sorted:
        d = by_day[k]
        d["me"] = d["me"] or {
            "mood": "", "moment_special": "", "love_action": "", "character": "", "music": "", "updated_at": "", "tags": []
        }
        d["par"] = d["par"] or {
            "mood": "", "moment_special": "", "love_action": "", "character": "", "music": "", "updated_at": "", "tags": []
        }
        rows.append(d)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": u,
            "partner_name": roles["partner_name"],
            "entries": rows,
            "diary_tags": DIARY_TAGS,
        },
    )

# =====================================================
# Save side
# =====================================================
@app.post("/save_side")
def save_side(
    request: Request,
    side: str = Form(...),  # self ou partner
    mood: str = Form(""),
    moment_special: str = Form(""),
    love_action: str = Form(""),
    character: str = Form(""),
    music: str = Form(""),
    tags: list[str] = Form(default=[]),
    day: str = Form(""),  # opcional: permitir salvar outro dia
    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    roles = get_roles(db, u.couple_id, u.id)
    author = roles["self_author"] if side == "self" else roles["partner_author"]

    if not day:
        day = date.today().isoformat()

    entry = (
        db.query(Entry)
        .filter(Entry.couple_id == u.couple_id, Entry.day == day, Entry.author == author)
        .first()
    )

    if not entry:
        entry = Entry(couple_id=u.couple_id, day=day, author=author)
        db.add(entry)

    entry.mood = (mood or "").strip()
    entry.moment_special = (moment_special or "").strip()
    entry.love_action = (love_action or "").strip()
    entry.character = (character or "").strip()
    entry.music = (music or "").strip()
    entry.updated_at = datetime.now().strftime("%d/%m/%Y")

    # só salva tags válidas
    clean_tags = [t for t in (tags or []) if t in DIARY_TAGS]
    if hasattr(entry, "tags_csv"):
        entry.tags_csv = join_tags(clean_tags)

    db.commit()
    return redirect_to("/")

# =====================================================
# Puxa-papo
# =====================================================
@app.get("/puxa-papo", response_class=HTMLResponse)
def puxa_papo_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    roles = get_roles(db, u.couple_id, u.id)

    return templates.TemplateResponse(
        "puxa_papo.html",
        {
            "request": request,
            "user": u,
            "partner_name": roles["partner_name"],
            "modes": [
                ("divertidas", "😄 Divertidas"),
                ("romanticas", "💖 Românticas"),
                ("picantes_leves", "😏 Picantes (leve)"),
            ],
            "last": request.session.get("puxa_papo_last"),
        },
    )

@app.post("/puxa-papo/next")
def puxa_papo_next(request: Request, mode: str = Form("divertidas")):
    if mode not in QUESTION_SETS:
        mode = "divertidas"

    q = random.choice(QUESTION_SETS[mode])
    request.session["puxa_papo_last"] = {
        "mode": mode,
        "question": q,
        "at": datetime.now().strftime("%d/%m/%Y"),
    }
    return redirect_to("/puxa-papo")
