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
from .models import User, Couple, Entry, SpecialDate, Notification
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
# Configs (melhorias)
# =========================
DIARY_TAGS = {
    "hoje_tem": "😏 Hoje tem",
    "quero_filme": "🎬 Hoje quero um filme",
    "quero_massagem": "💆 Hoje quero massagem",
    "estressada": "😤 Hoje estou estressada",
    "saudades": "💋 Saudades, quero beijo",
}

SPECIAL_DATE_TYPES = [
    {"key": "primeiro_encontro", "label": "Primeiro encontro"},
    {"key": "primeiro_beijo", "label": "Primeiro beijo"},
    {"key": "primeira_vez", "label": "Primeira vez"},
    {"key": "casamento", "label": "Casamento / união"},
    {"key": "outro", "label": "Outro"},
]

QUESTION_SETS = {
    "divertidas": [
        "Se a gente fosse um filme, qual seria o gênero e por quê?",
        "Qual seria nosso nome de dupla de super-heróis?",
        "Qual mania minha você acha fofinha (mesmo quando te irrita)?",
        "Se eu fosse um emoji hoje, qual seria?",
        "Que música tocaria quando a gente entra numa festa juntos?",
        "Qual foi o momento mais aleatório e perfeito que já vivemos?",
        "Se a gente tivesse um restaurante, como ele se chamaria e qual seria o prato carro-chefe?",
        "Qual seria nosso “código secreto” pra pedir socorro em situações sociais?",
        "Qual apelido bobo você inventaria pra mim AGORA?",
        "Se a gente pudesse teleportar pra um lugar hoje, pra onde iríamos?",
    ],
    "romanticas": [
        "O que você mais admira em mim (além da aparência)?",
        "Qual foi o momento em que você percebeu: ‘é essa pessoa’?",
        "Como eu posso te amar melhor nos dias difíceis?",
        "Qual gesto meu te faz se sentir mais seguro(a) comigo?",
        "Qual sonho você quer que a gente realize juntos?",
        "Que lembrança nossa você queria reviver como se fosse a primeira vez?",
        "O que você sente que mudou em você depois que me conheceu?",
        "Qual foi um dia comum que virou especial só porque era comigo?",
        "Se você pudesse me escrever uma frase pra eu ler quando estiver triste, qual seria?",
        "Qual ‘ritual do casal’ você gostaria que fosse nosso (pequeno e constante)?",
    ],
    # ⚠️ Picantes aqui = leve/sugestivo (sem explícito)
    "picantes_leves": [
        "Hoje eu te daria um beijo que é… (complete em 3 palavras).",
        "De 0 a ‘vem cá’, quanto você tá com saudade de mim agora? 😏",
        "Qual é seu ‘ponto fraco’ em mim? (sorriso, voz, cheiro, olhar…)",
        "Qual seria um ‘encontro perfeito’ pra hoje à noite, do jeitinho que você gosta?",
        "Se eu te mandar uma mensagem com ‘🤭’, o que você acha que significa?",
        "Qual roupa minha te deixa mais ‘uau’?",
        "Escolhe: beijo demorado, abraço apertado ou cafuné — e por quê?",
        "Qual é a sua ‘cantada’ preferida (boba ou séria) pra usar comigo?",
        "Se a gente tivesse uma palavra-código pra ‘quero carinho AGORA’, qual seria?",
        "Qual é a coisa mais charmosa que eu faço sem perceber?",
    ],
}

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
        "tags": [],
    }

def split_tags(tags_csv: str) -> list[str]:
    if not tags_csv:
        return []
    return [t for t in (tags_csv or "").split(",") if t.strip()]

def join_tags(tags: list[str]) -> str:
    clean: list[str] = []
    seen = set()
    for t in tags or []:
        t = (t or "").strip()
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        clean.append(t)
    return ",".join(clean)

def create_notification(db: Session, couple_id: int, title: str, body: str = ""):
    now = datetime.now().strftime("%d/%m/%Y")
    n = Notification(
        couple_id=couple_id,
        created_at=now,
        title=(title or "").strip()[:120],
        body=(body or "").strip(),
        is_read=0,
    )
    db.add(n)
    db.commit()

def get_today_special_dates(db: Session, couple_id: int):
    today_mmdd = date.today().strftime("%m-%d")
    rows = db.query(SpecialDate).filter(SpecialDate.couple_id == couple_id).all()
    today = []
    for r in rows:
        try:
            if (r.date or "")[5:] == today_mmdd:
                today.append(r)
        except Exception:
            pass
    return today

def get_roles(db: Session, couple_id: int, my_user_id: int) -> dict:
    """
    Define papéis dentro do casal:
    - O primeiro usuário (menor id) é o "A"
    - O segundo usuário é o "B"

    No banco, continuamos salvando Entry.author como "me" e "par".
    Mas para quem está logado, "me" deve significar "meu lado".

    Retorna:
      self_author: qual author do banco corresponde ao "meu lado" (me/par)
      partner_author: qual author do banco corresponde ao "lado do parceiro" (par/me)
      partner_name: nome do parceiro (se existir)
    """
    users = (
        db.query(User)
        .filter(User.couple_id == couple_id)
        .order_by(User.id.asc())
        .all()
    )

    if not users:
        return {"self_author": "me", "partner_author": "par", "partner_name": None}

    first = users[0]
    second = users[1] if len(users) > 1 else None

    if my_user_id == first.id:
        return {
            "self_author": "me",
            "partner_author": "par",
            "partner_name": second.name if second else None,
        }
    else:
        # Quem não é o primeiro usuário, enxerga invertido:
        return {
            "self_author": "par",
            "partner_author": "me",
            "partner_name": first.name,
        }

# =========================
# Auth
# =========================
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None})

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
            {"request": request, "user": None, "error": "E-mail ou senha inválidos."},
            status_code=400,
        )

    request.session["uid"] = user.id
    return redirect_to("/")

@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "user": None})

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
            {"request": request, "user": None, "error": "Esse e-mail já está cadastrado."},
            status_code=400,
        )

    try:
        pw_hash = hash_password(password)
    except ValueError as e:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "user": None, "error": str(e)},
            status_code=400,
        )
    except Exception:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "user": None, "error": "Não foi possível criar a senha. Tente uma senha menor."},
            status_code=400,
        )

    user = User(name=name_norm, email=email_norm, password_hash=pw_hash)
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
    partner_name = None
    if u.couple_id:
        roles = get_roles(db, u.couple_id, u.id)
        partner_name = roles["partner_name"]

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

    roles = get_roles(db, u.couple_id, u.id)
    partner_name = roles["partner_name"]
    self_author = roles["self_author"]
    partner_author = roles["partner_author"]

    # melhorias: datas especiais e banner
    special_today = get_today_special_dates(db, u.couple_id)

    # melhorias: notifs não lidas pro banner
    notifications_unread = (
        db.query(Notification)
        .filter(Notification.couple_id == u.couple_id, Notification.is_read == 0)
        .order_by(Notification.id.desc())
        .limit(5)
        .all()
    )

    entries = (
        db.query(Entry)
        .filter(Entry.couple_id == u.couple_id)
        .order_by(Entry.day.desc())
        .all()
    )

    by_day: dict[str, dict] = {}
    for e in entries:
        d = by_day.setdefault(e.day, {"day": e.day, "created_at": "", "me": None, "par": None})

        side_payload = {
            "mood": e.mood or "",
            "moment_special": e.moment_special or "",
            "love_action": e.love_action or "",
            "character": e.character or "",
            "music": e.music or "",
            "updated_at": e.updated_at or "",
            "tags": split_tags(getattr(e, "tags_csv", "") or ""),
        }

        if e.author == self_author:
            d["me"] = side_payload
        elif e.author == partner_author:
            d["par"] = side_payload

        d["created_at"] = d["created_at"] or (e.updated_at or "")

    days = sorted(by_day.keys(), reverse=True)
    rows = []
    for day_key in days:
        d = by_day[day_key]
        d["me"] = d["me"] or empty_side()
        d["par"] = d["par"] or empty_side()
        rows.append(d)

    # cria notificação simples 1x por sessão/dia quando for data especial
    if special_today:
        today_key = date.today().isoformat()
        flag = request.session.get("special_notified", "")
        if flag != today_key:
            request.session["special_notified"] = today_key
            first = special_today[0]
            create_notification(
                db,
                u.couple_id,
                f"💖 Hoje é {first.label}",
                (first.note or "").strip(),
            )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "entries": rows,
            "user": u,
            "partner_name": partner_name,
            # extras (se seu template usar, ótimo; se não usar, não quebra)
            "diary_tags": DIARY_TAGS,
            "special_today": special_today,
            "notifications_unread": notifications_unread,
        },
    )

# =========================
# Save (upsert por dia+lado) + TAGS
# =========================
@app.post("/save_side")
def save_side(
    request: Request,

    # compatível com seu index atual (author=me/par)
    author: str = Form(""),

    # compatível com versão melhor (side=self/partner)
    side: str = Form(""),  # "self" ou "partner"

    mood: str = Form(""),
    moment_special: str = Form(""),
    love_action: str = Form(""),
    character: str = Form(""),
    music: str = Form(""),
    day: str = Form(""),

    # ✅ novo (não quebra seu form antigo)
    tags: list[str] = Form(default=[]),

    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    roles = get_roles(db, u.couple_id, u.id)
    self_author = roles["self_author"]
    partner_author = roles["partner_author"]

    # determina author real do banco
    if side:
        if side == "self":
            author_db = self_author
        elif side == "partner":
            author_db = partner_author
        else:
            return redirect_to("/")
    else:
        if author == "me":
            author_db = self_author
        elif author == "par":
            author_db = partner_author
        else:
            return redirect_to("/")

    if not day:
        day = date.today().isoformat()

    # sem hora
    now = datetime.now().strftime("%d/%m/%Y")

    existing = (
        db.query(Entry)
        .filter(
            Entry.couple_id == u.couple_id,
            Entry.day == day,
            Entry.author == author_db,
        )
        .first()
    )

    if not existing:
        existing = Entry(couple_id=u.couple_id, day=day, author=author_db)
        db.add(existing)

    existing.mood = (mood or "").strip()
    existing.moment_special = (moment_special or "").strip()
    existing.love_action = (love_action or "").strip()
    existing.character = (character or "").strip()
    existing.music = (music or "").strip()
    existing.updated_at = now

    # tags (só guarda as tags que existem no dicionário)
    clean_tags = [t for t in (tags or []) if t in DIARY_TAGS]
    if hasattr(existing, "tags_csv"):
        existing.tags_csv = join_tags(clean_tags)

    db.commit()

    # notificação leve baseada nas tags
    if clean_tags:
        msg = []
        if "hoje_tem" in clean_tags:
            msg.append("😏 Sinais no ar…")
        if "quero_filme" in clean_tags:
            msg.append("🎬 Pedido de filme!")
        if "quero_massagem" in clean_tags:
            msg.append("💆 Pedido de massagem.")
        if "estressada" in clean_tags:
            msg.append("😤 Dia tenso — carinho pode ajudar.")
        if "saudades" in clean_tags:
            msg.append("💋 Saudade declarada.")

        create_notification(db, u.couple_id, "📌 Tags do dia", " | ".join(msg)[:400])

    return redirect_to("/")

# =========================
# Datas especiais
# =========================
@app.get("/special-dates", response_class=HTMLResponse)
def special_dates_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    roles = get_roles(db, u.couple_id, u.id)
    partner_name = roles["partner_name"]

    dates = (
        db.query(SpecialDate)
        .filter(SpecialDate.couple_id == u.couple_id)
        .order_by(SpecialDate.date.asc())
        .all()
    )

    return templates.TemplateResponse(
        "special_dates.html",
        {
            "request": request,
            "user": u,
            "partner_name": partner_name,
            "types": SPECIAL_DATE_TYPES,
            "dates": dates,
        },
    )

@app.post("/special-dates/add")
def special_dates_add(
    request: Request,
    type: str = Form(...),
    date_str: str = Form(..., alias="date"),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    t = next((x for x in SPECIAL_DATE_TYPES if x["key"] == type), None)
    if not t:
        return redirect_to("/special-dates")

    # valida date
    try:
        _ = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        roles = get_roles(db, u.couple_id, u.id)
        partner_name = roles["partner_name"]
        dates = db.query(SpecialDate).filter(SpecialDate.couple_id == u.couple_id).all()
        return templates.TemplateResponse(
            "special_dates.html",
            {
                "request": request,
                "user": u,
                "partner_name": partner_name,
                "types": SPECIAL_DATE_TYPES,
                "dates": dates,
                "error": "Data inválida.",
            },
            status_code=400,
        )

    item = SpecialDate(
        couple_id=u.couple_id,
        type=t["key"],
        label=t["label"],
        date=date_str,
        note=(note or "").strip(),
    )
    db.add(item)
    db.commit()

    create_notification(db, u.couple_id, "💖 Data especial salva", f"{t['label']} — {date_str}")
    return redirect_to("/special-dates")

@app.post("/special-dates/delete")
def special_dates_delete(
    request: Request,
    id: int = Form(...),
    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    item = db.get(SpecialDate, id)
    if item and item.couple_id == u.couple_id:
        db.delete(item)
        db.commit()
        create_notification(db, u.couple_id, "🗑️ Data removida", item.label)
    return redirect_to("/special-dates")

# =========================
# Notificações
# =========================
@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    roles = get_roles(db, u.couple_id, u.id)
    partner_name = roles["partner_name"]

    items = (
        db.query(Notification)
        .filter(Notification.couple_id == u.couple_id)
        .order_by(Notification.id.desc())
        .limit(50)
        .all()
    )

    return templates.TemplateResponse(
        "notifications.html",
        {"request": request, "user": u, "partner_name": partner_name, "items": items},
    )

@app.post("/notifications/read")
def notifications_read(
    request: Request,
    id: int = Form(...),
    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    n = db.get(Notification, id)
    if n and n.couple_id == u.couple_id:
        n.is_read = 1
        db.add(n)
        db.commit()

    return redirect_to("/notifications")

# =========================
# Puxa-papo (compatível com seu template)
# =========================
@app.get("/puxa-papo", response_class=HTMLResponse)
def puxa_papo_page(request: Request, db: Session = Depends(get_db)):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    roles = get_roles(db, u.couple_id, u.id)
    partner_name = roles["partner_name"]

    last = request.session.get("puxa_papo_last", None)

    return templates.TemplateResponse(
        "puxa_papo.html",
        {
            "request": request,
            "user": u,
            "partner_name": partner_name,
            "last": last,
            "modes": [
                ("divertidas", "😄 Divertidas"),
                ("romanticas", "💖 Românticas"),
                ("picantes_leves", "😏 Picantes (leve)"),
            ],
        },
    )

@app.post("/puxa-papo/next")
def puxa_papo_next(
    request: Request,
    mode: str = Form("divertidas"),
    db: Session = Depends(get_db),
):
    u = current_user(request, db)
    if not u:
        return redirect_to("/login")
    if not u.couple_id:
        return redirect_to("/pair")

    if mode not in QUESTION_SETS:
        mode = "divertidas"

    q = random.choice(QUESTION_SETS[mode])

    request.session["puxa_papo_last"] = {
        "mode": mode,
        "question": q,
        "at": datetime.now().strftime("%d/%m/%Y"),
    }

    return redirect_to("/puxa-papo")
