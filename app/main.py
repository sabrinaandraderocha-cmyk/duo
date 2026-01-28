import os
import secrets
import random
from datetime import date, datetime
from itertools import zip_longest

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import User, Couple, Entry
from .security import hash_password, verify_password

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Duo")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "duo-secret-key-change-me"),
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 24 * 7,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# =====================================================
# DADOS ESTÁTICOS
# =====================================================

DIARY_TAGS = {
    "hoje_tem": "😏 Hoje tem",
    "quero_filme": "🎬 Quero filme",
    "quero_massagem": "💆 Quero massagem",
    "estressada": "😤 Tô estressada(o)",
    "saudades": "💋 Quero beijo",
    "fofoca": "👀 Tenho fofoca",
}

PROMPTS_HUMOR = [
    "Ex: Leve e apaixonada...", "Ex: Cansada, mas feliz...", "Ex: Com saudade do fim de semana...",
    "Ex: Precisando de um abraço...", "Ex: Grata por ter você...", "Ex: Produtiva e focada...",
]

PROMPTS_MOMENTO = [
    "O que te fez sorrir hoje?", "Qual foi a melhor parte do dia?", "Teve alguma surpresa?",
    "Uma coisa simples que foi boa...", "Um detalhe que você não quer esquecer...",
]

QUESTION_SETS = {
    "divertidas": [
        "Se a gente fosse um filme, qual seria o gênero?", "Qual seria nosso nome de dupla criminosa?",
        "Qual mania minha você acha estranhamente fofa?", "Que música tocaria se a gente entrasse numa festa em câmera lenta?",
        "Se a gente ganhasse na loteria hoje, qual a primeira coisa que faríamos?",
    ],
    "romanticas": [
        "O que você mais admira em mim hoje?", "Qual foi o momento exato que você percebeu que me amava?",
        "Como posso fazer seu dia 1% melhor amanhã?", "Qual gesto meu te faz sentir mais segurança?",
    ],
    "picantes_leves": [
        "Hoje eu te daria um beijo com sabor de...", "De 0 a 10, quão perigoso está seu pensamento agora?",
        "Qual parte do meu corpo chamou sua atenção hoje?", "Se tivéssemos 1 hora sozinhos agora, o que faríamos?",
    ],
}

def redirect_to(url: str):
    return RedirectResponse(url, status_code=303)

def current_user(request: Request, db: Session):
    uid = request.session.get("uid")
    if not uid: return None
    return db.get(User, uid)

def get_couple_roles(db: Session, couple_id: int, my_user_id: int):
    users = db.query(User).filter(User.couple_id == couple_id).order_by(User.id.asc()).all()
    if len(users) < 2:
        return {"self_role": "me", "partner_role": "par", "partner_name": "Aguardando..."}
    first, second = users[0], users[1]
    if my_user_id == first.id:
        return {"self_role": "me", "partner_role": "par", "partner_name": second.name}
    return {"self_role": "par", "partner_role": "me", "partner_name": first.name}

def split_tags(csv: str):
    if not csv: return []
    return [t for t in csv.split(",") if t.strip()]

def join_tags(tags: list[str]):
    seen = []
    for t in (tags or []):
        t = (t or "").strip()
        if t and t not in seen: seen.append(t)
    return ",".join(seen)

# =====================================================
# ROTAS DE AUTENTICAÇÃO (LOGIN / SIGNUP / FORGOT)
# =====================================================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email_norm = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email_norm).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "E-mail ou senha incorretos."}, status_code=400)
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
    recovery_key: str = Form(...), # NOVO
    db: Session = Depends(get_db)
):
    name_norm = (name or "").strip()
    email_norm = (email or "").strip().lower()
    recovery_norm = (recovery_key or "").strip().lower()

    if db.query(User).filter(User.email == email_norm).first():
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Este e-mail já tem conta."}, status_code=400)
    
    user = User(
        name=name_norm, 
        email=email_norm, 
        password_hash=hash_password(password),
        recovery_key=recovery_norm # SALVANDO
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["uid"] = user.id
    return redirect_to("/pair")

@app.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return templates.TemplateResponse("forgot.html", {"request": request})

@app.post("/forgot")
def forgot_submit(
    request: Request,
    email: str = Form(...),
    recovery_key: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    email_norm = (email or "").strip().lower()
    key_norm = (recovery_key or "").strip().lower()

    user = db.query(User).filter(User.email == email_norm).first()

    if not user or user.recovery_key != key_norm:
        return templates.TemplateResponse(
            "forgot.html",
            {"request": request, "error": "E-mail ou Palavra Secreta incorretos."},
            status_code=400,
        )

    user.password_hash = hash_password(new_password)
    db.commit()

    return templates.TemplateResponse(
        "login.html", 
        {"request": request, "success": "Senha alterada com sucesso! Faça login."}
    )

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect_to("/login")

# =====================================================
# PAREAMENTO
# =====================================================
@app.get("/pair", response_class=HTMLResponse)
def pair_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    couple = db.get(Couple, u.couple_id) if u.couple_id else None
    partner_name = None
    if u.couple_id:
        roles = get_couple_roles(db, u.couple_id, u.id)
        partner_name = roles["partner_name"]
    return templates.TemplateResponse("pair.html", {"request": request, "user": u, "couple": couple, "partner_name": partner_name})

@app.post("/pair/create")
def pair_create(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    if u.couple_id: return redirect_to("/")
    code = secrets.token_hex(4)
    couple = Couple(code=code)
    db.add(couple)
    db.commit()
    db.refresh(couple)
    u.couple_id = couple.id
    db.commit()
    return redirect_to("/pair")

@app.post("/pair/join")
def pair_join(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    if u.couple_id: return redirect_to("/")
    code_clean = (code or "").strip()
    couple = db.query(Couple).filter(Couple.code == code_clean).first()
    if not couple:
        return templates.TemplateResponse("pair.html", {"request": request, "user": u, "couple": None, "error": "Código não encontrado."}, status_code=400)
    u.couple_id = couple.id
    db.commit()
    return redirect_to("/")

# =====================================================
# HOME
# =====================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    if not u.couple_id: return redirect_to("/pair")

    roles = get_couple_roles(db, u.couple_id, u.id)

    entries = (
        db.query(Entry)
        .filter(Entry.couple_id == u.couple_id)
        .order_by(Entry.day.desc(), Entry.id.desc())
        .all()
    )

    by_day = {}
    for e in entries:
        if e.day not in by_day:
            by_day[e.day] = {
                "day": e.day,
                "display_date": datetime.strptime(e.day, "%Y-%m-%d").strftime("%d/%m") if "-" in e.day else e.day,
                "me_entries": [],
                "par_entries": []
            }
        
        data = {
            "mood": e.mood or "", "moment_special": e.moment_special or "", "love_action": e.love_action or "",
            "character": e.character or "", "music": e.music or "", "tags": split_tags(getattr(e, "tags_csv", "")),
        }

        if e.author == roles["self_role"]: by_day[e.day]["me_entries"].append(data)
        elif e.author == roles["partner_role"]: by_day[e.day]["par_entries"].append(data)

    timeline = []
    sorted_days = sorted(by_day.keys(), reverse=True)
    
    for day in sorted_days:
        day_obj = by_day[day]
        rows = list(zip_longest(day_obj["me_entries"], day_obj["par_entries"], fillvalue=None))
        day_obj["rows"] = rows
        timeline.append(day_obj)

    today_iso = date.today().isoformat()
    has_today = any(d['day'] == today_iso for d in timeline)
    
    synergy_percent = 0
    if has_today:
        today_data = next(d for d in timeline if d['day'] == today_iso)
        has_me = len(today_data["me_entries"]) > 0
        has_par = len(today_data["par_entries"]) > 0
        if has_me and has_par: synergy_percent = 100
        elif has_me or has_par: synergy_percent = 50

    hora = datetime.now().hour
    saudacao = "Bom dia" if 5 <= hora < 12 else "Boa tarde" if 12 <= hora < 18 else "Boa noite"

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, "user": u, "partner_name": roles["partner_name"], "timeline": timeline,
            "diary_tags": DIARY_TAGS, "today_iso": today_iso, "has_today": has_today, "synergy_percent": synergy_percent,
            "saudacao": saudacao, "ph_humor": random.choice(PROMPTS_HUMOR), "ph_momento": random.choice(PROMPTS_MOMENTO)
        },
    )

@app.post("/save_side")
def save_side(
    request: Request, side: str = Form(...), mood: str = Form(""), moment_special: str = Form(""),
    love_action: str = Form(""), character: str = Form(""), music: str = Form(""),
    tags: list[str] = Form(default=[]), day: str = Form(""), db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u or not u.couple_id: return redirect_to("/")

    roles = get_couple_roles(db, u.couple_id, u.id)
    author_role = roles["self_role"] if side == "self" else roles["partner_role"]

    if not day: day = date.today().isoformat()

    entry = Entry(couple_id=u.couple_id, day=day, author=author_role)
    db.add(entry)

    entry.mood = (mood or "").strip()
    entry.moment_special = (moment_special or "").strip()
    entry.love_action = (love_action or "").strip()
    entry.character = (character or "").strip()
    entry.music = (music or "").strip()
    entry.updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

    clean_tags = [t for t in (tags or []) if t in DIARY_TAGS]
    if hasattr(entry, "tags_csv"): entry.tags_csv = join_tags(clean_tags)

    db.commit()
    return redirect_to("/")

@app.get("/puxa-papo", response_class=HTMLResponse)
def puxa_papo_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u or not u.couple_id: return redirect_to("/")
    roles = get_couple_roles(db, u.couple_id, u.id)
    return templates.TemplateResponse("puxa_papo.html", {
        "request": request, "user": u, "partner_name": roles["partner_name"],
        "modes": [("divertidas", "😄 Divertidas"), ("romanticas", "💖 Românticas"), ("picantes_leves", "🔥 Picantes (leve)")],
        "last": request.session.get("puxa_papo_last"),
    })

@app.post("/puxa-papo/next")
def puxa_papo_next(request: Request, mode: str = Form("divertidas")):
    if mode not in QUESTION_SETS: mode = "divertidas"
    request.session["puxa_papo_last"] = {"mode": mode, "question": random.choice(QUESTION_SETS[mode])}
    return redirect_to("/puxa-papo")
    from sqlalchemy import text # <--- Adicione esse import no topo do arquivo se não tiver

# ... (resto do código) ...

# =====================================================
# ROTA DE EMERGÊNCIA (CORRIGIR BANCO)
# =====================================================
@app.get("/fix_db")
def fix_database_structure(db: Session = Depends(get_db)):
    try:
        # 1. Adiciona a coluna 'recovery_key' na tabela users se não existir
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_key VARCHAR(100) DEFAULT '';"))
        
        # 2. Remove a trava que impede salvar mais de uma vez por dia (uq_entry_side)
        # Nota: O nome da constraint pode variar, mas geralmente o SQLAlchemy nomeia assim ou como 'entries_couple_id_day_author_key'
        try:
            db.execute(text("ALTER TABLE entries DROP CONSTRAINT uq_entry_side;"))
        except Exception:
            pass # Se der erro é pq já foi removida ou tem outro nome, seguimos em frente
            
        try:
             # Tenta remover pelo nome automático do Postgres caso o de cima falhe
            db.execute(text("ALTER TABLE entries DROP CONSTRAINT entries_couple_id_day_author_key;"))
        except Exception:
            pass

        db.commit()
        return "SUCESSO! O banco foi atualizado. Agora você pode salvar registros e recuperar senha."
    except Exception as e:
        return f"Erro ao tentar corrigir: {e}"
