import os
import secrets
import random
from datetime import date, datetime
from itertools import zip_longest

from fastapi import FastAPI, Request, Form, Depends, Path
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
# CONTEÚDO (NOVAS PERGUNTAS E TEXTOS)
# =====================================================
DIARY_TAGS = {
    "hoje_tem": "😏 Hoje tem", "quero_filme": "🎬 Quero filme", "quero_massagem": "💆 Quero massagem",
    "estressada": "😤 Tô estressada(o)", "saudades": "💋 Quero beijo", "fofoca": "👀 Tenho fofoca",
    "orgulho": "🏆 Orgulho de nós", "cansada": "🔋 Bateria social baixa"
}

PROMPTS_HUMOR = [
    "Ex: Leve e apaixonada...", "Ex: Cansada, mas feliz...", "Ex: Com saudade do fim de semana...",
    "Ex: Precisando de um abraço...", "Ex: Grata por ter você...", "Ex: Produtiva e focada...",
    "Ex: Modo avião ativado...", "Ex: 100% nas nuvens..."
]

PROMPTS_MOMENTO = [
    "O que te fez sorrir hoje?", "Qual foi a melhor parte do dia?", "Teve alguma surpresa?",
    "Uma coisa simples que foi boa...", "Um detalhe que você não quer esquecer...",
    "O que você gostaria de ter feito diferente?", "Qual a cor do seu dia hoje?"
]

QUESTION_SETS = {
    "divertidas": [
        "Se a gente fosse um filme, qual seria o gênero?", "Qual seria nosso nome de dupla criminosa?",
        "Qual mania minha você acha estranhamente fofa?", "Que música tocaria se a gente entrasse numa festa em câmera lenta?",
        "Se a gente ganhasse na loteria hoje, qual a primeira coisa que faríamos?",
        "Qual meme define nosso relacionamento?", "Se fôssemos animais, quais seríamos?",
    ],
    "romanticas": [
        "O que você mais admira em mim hoje?", "Qual foi o momento exato que você percebeu que me amava?",
        "Como posso fazer seu dia 1% melhor amanhã?", "Qual gesto meu te faz sentir mais segurança?",
        "Qual sua memória favorita nossa deste ano?", "O que você sente quando eu te abraço?",
    ],
    "picantes_leves": [
        "Hoje eu te daria um beijo com sabor de...", "De 0 a 10, quão perigoso está seu pensamento agora?",
        "Qual parte do meu corpo chamou sua atenção hoje?", "Se tivéssemos 1 hora sozinhos agora, o que faríamos?",
        "Qual roupa minha você mais gosta de me ver usando (ou tirando)?",
    ],
    "profundas": [
        "Qual é o seu maior medo sobre o futuro?", "O que a gente precisa melhorar na nossa comunicação?",
        "Qual sonho seu você acha que eu poderia apoiar mais?", "O que significa 'lar' para você?"
    ]
}

# =====================================================
# HELPERS
# =====================================================
def redirect_to(url: str): return RedirectResponse(url, status_code=303)
def current_user(request: Request, db: Session):
    uid = request.session.get("uid")
    if not uid: return None
    return db.get(User, uid)
def get_couple_roles(db: Session, couple_id: int, my_user_id: int):
    users = db.query(User).filter(User.couple_id == couple_id).order_by(User.id.asc()).all()
    if len(users) < 2: return {"self_role": "me", "partner_role": "par", "partner_name": "Aguardando..."}
    first, second = users[0], users[1]
    if my_user_id == first.id: return {"self_role": "me", "partner_role": "par", "partner_name": second.name}
    return {"self_role": "par", "partner_role": "me", "partner_name": first.name}
def split_tags(csv: str): return [t.strip() for t in (csv or "").split(",") if t.strip()]
def join_tags(tags: list[str]): return ",".join(list(dict.fromkeys([t.strip() for t in (tags or []) if t.strip()])))

def get_own_entry(db: Session, user: User, entry_id: int):
    """Retorna apenas um registro que pertença ao casal e tenha sido criado pelo usuário logado."""
    if not user or not user.couple_id:
        return None

    entry = db.get(Entry, entry_id)
    if not entry or entry.couple_id != user.couple_id:
        return None

    roles = get_couple_roles(db, user.couple_id, user.id)
    if entry.author != roles["self_role"]:
        return None

    return entry

# =====================================================
# ROTAS GERAIS
# =====================================================
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request): return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email_norm = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email_norm).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "E-mail ou senha incorretos."}, status_code=400)
    request.session["uid"] = user.id
    return redirect_to("/")

@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request): return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/signup")
def signup(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    name_norm = (name or "").strip()
    email_norm = (email or "").strip().lower()
    if db.query(User).filter(User.email == email_norm).first():
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Este e-mail já tem conta."}, status_code=400)
    user = User(name=name_norm, email=email_norm, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["uid"] = user.id
    return redirect_to("/pair")

@app.get("/logout")
def logout(request: Request): request.session.clear(); return redirect_to("/login")

# =====================================================
# PERFIL & SENHA (NOVO)
# =====================================================
@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    return templates.TemplateResponse("profile.html", {"request": request, "user": u})

@app.post("/profile/update_password")
def update_password(request: Request, new_password: str = Form(...), db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    
    if len(new_password) < 4:
        return templates.TemplateResponse("profile.html", {"request": request, "user": u, "error": "Senha muito curta!"})
        
    u.password_hash = hash_password(new_password)
    db.commit()
    return templates.TemplateResponse("profile.html", {"request": request, "user": u, "success": "Senha alterada com sucesso!"})

# =====================================================
# PAREAMENTO
# =====================================================
@app.get("/pair", response_class=HTMLResponse)
def pair_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    roles = get_couple_roles(db, u.couple_id, u.id) if u.couple_id else {}
    return templates.TemplateResponse("pair.html", {"request": request, "user": u, "couple": db.get(Couple, u.couple_id) if u.couple_id else None, "partner_name": roles.get("partner_name")})

@app.post("/pair/create")
def pair_create(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u or u.couple_id: return redirect_to("/")
    couple = Couple(code=secrets.token_hex(4))
    db.add(couple); db.commit(); db.refresh(couple)
    u.couple_id = couple.id; db.commit()
    return redirect_to("/pair")

@app.post("/pair/join")
def pair_join(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u or u.couple_id: return redirect_to("/")
    couple = db.query(Couple).filter(Couple.code == (code or "").strip()).first()
    if not couple: return templates.TemplateResponse("pair.html", {"request": request, "user": u, "error": "Código não encontrado."}, status_code=400)
    u.couple_id = couple.id; db.commit()
    return redirect_to("/")

# =====================================================
# HOME & DIÁRIO
# =====================================================
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    if not u.couple_id: return redirect_to("/pair")

    roles = get_couple_roles(db, u.couple_id, u.id)
    entries = db.query(Entry).filter(Entry.couple_id == u.couple_id).order_by(Entry.day.desc(), Entry.id.desc()).all()
    
    by_day = {}
    for e in entries:
        if e.day not in by_day:
            by_day[e.day] = {"day": e.day, "display_date": datetime.strptime(e.day, "%Y-%m-%d").strftime("%d/%m") if "-" in e.day else e.day, "me_entries": [], "par_entries": []}
        data = {
            "id": e.id,
            "mood": e.mood, "moment_special": e.moment_special, "love_action": e.love_action,
            "character": e.character, "music": e.music, "tags": split_tags(e.tags_csv),
            "time": e.updated_at.split(" ")[1] if e.updated_at and " " in e.updated_at else "",
            "can_edit": e.author == roles["self_role"]
        }
        if e.author == roles["self_role"]: by_day[e.day]["me_entries"].append(data)
        elif e.author == roles["partner_role"]: by_day[e.day]["par_entries"].append(data)

    timeline = []
    for day in sorted(by_day.keys(), reverse=True):
        obj = by_day[day]
        obj["rows"] = list(zip_longest(obj["me_entries"], obj["par_entries"], fillvalue=None))
        timeline.append(obj)

    has_today = any(d['day'] == date.today().isoformat() for d in timeline)
    syn = 0
    if has_today:
        td = next(d for d in timeline if d['day'] == date.today().isoformat())
        if td["me_entries"] and td["par_entries"]: syn = 100
        elif td["me_entries"] or td["par_entries"]: syn = 50

    h = datetime.now().hour
    saudacao = "Bom dia" if 5<=h<12 else "Boa tarde" if 12<=h<18 else "Boa noite"
    return templates.TemplateResponse("index.html", {
        "request": request, "user": u, "partner_name": roles["partner_name"], "timeline": timeline, "diary_tags": DIARY_TAGS,
        "has_today": has_today, "synergy_percent": syn, "saudacao": saudacao, "ph_humor": random.choice(PROMPTS_HUMOR), "ph_momento": random.choice(PROMPTS_MOMENTO)
    })

@app.post("/save_side")
def save_side(request: Request, side: str = Form("self"), mood: str = Form(""), moment_special: str = Form(""), love_action: str = Form(""), character: str = Form(""), music: str = Form(""), tags: list[str] = Form(default=[]), db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u or not u.couple_id: return redirect_to("/")

    # O autor sempre é definido pelo usuário logado.
    # Não confiamos no valor enviado pelo formulário para evitar registros em nome do par.
    roles = get_couple_roles(db, u.couple_id, u.id)
    entry = Entry(couple_id=u.couple_id, day=date.today().isoformat(), author=roles["self_role"])
    entry.mood = (mood or "").strip()
    entry.moment_special = (moment_special or "").strip()
    entry.love_action = (love_action or "").strip()
    entry.character = (character or "").strip()
    entry.music = (music or "").strip()
    entry.updated_at = datetime.now().strftime("%d/%m %H:%M")
    entry.tags_csv = join_tags([t for t in tags if t in DIARY_TAGS])
    db.add(entry)
    db.commit()
    return redirect_to("/")

@app.get("/entry/{entry_id}/edit", response_class=HTMLResponse)
def edit_entry_page(entry_id: int, request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    entry = get_own_entry(db, u, entry_id)
    if not entry:
        return redirect_to("/")

    return templates.TemplateResponse("edit_entry.html", {
        "request": request,
        "user": u,
        "entry": entry,
        "entry_tags": split_tags(entry.tags_csv),
        "diary_tags": DIARY_TAGS,
    })

@app.post("/entry/{entry_id}/edit")
def update_entry(
    entry_id: int,
    request: Request,
    mood: str = Form(""),
    moment_special: str = Form(""),
    love_action: str = Form(""),
    character: str = Form(""),
    music: str = Form(""),
    tags: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    entry = get_own_entry(db, u, entry_id)
    if not entry:
        return redirect_to("/")

    entry.mood = (mood or "").strip()
    entry.moment_special = (moment_special or "").strip()
    entry.love_action = (love_action or "").strip()
    entry.character = (character or "").strip()
    entry.music = (music or "").strip()
    entry.tags_csv = join_tags([t for t in tags if t in DIARY_TAGS])
    entry.updated_at = datetime.now().strftime("%d/%m %H:%M")

    db.commit()
    return redirect_to(f"/?edited=1#entry-{entry.id}")

@app.post("/delete_entry/{entry_id}")
def delete_entry(entry_id: int, request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")

    # Cada pessoa só pode excluir os próprios registros.
    entry = get_own_entry(db, u, entry_id)
    if entry:
        db.delete(entry)
        db.commit()

    return redirect_to("/")

# =====================================================
# PUXA-PAPO
# =====================================================
@app.get("/puxa-papo", response_class=HTMLResponse)
def puxa_papo(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u: return redirect_to("/login")
    
    modes = [("divertidas", "😄 Divertidas"), ("romanticas", "💖 Românticas"), ("picantes_leves", "🔥 Picantes"), ("profundas", "🧠 Profundas")]
    
    return templates.TemplateResponse("puxa_papo.html", {
        "request": request, "user": u, "partner_name": "", 
        "modes": modes, 
        "last": request.session.get("puxa_papo_last")
    })

@app.post("/puxa-papo/next")
def puxa_next(request: Request, mode: str = Form("divertidas")):
    request.session["puxa_papo_last"] = {"mode": mode, "question": random.choice(QUESTION_SETS.get(mode, QUESTION_SETS["divertidas"]))}
    return redirect_to("/puxa-papo")
