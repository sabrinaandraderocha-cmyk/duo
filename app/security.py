from passlib.context import CryptContext

# ✅ Seguro e sem limite de 72 bytes como bcrypt
pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

MIN_LEN = 6
MAX_LEN = 256  # limite prático pra evitar abuso (pode ajustar)

def hash_password(password: str) -> str:
    password = (password or "").strip()

    if len(password) < MIN_LEN:
        raise ValueError(f"A senha deve ter pelo menos {MIN_LEN} caracteres.")
    if len(password) > MAX_LEN:
        raise ValueError(f"A senha deve ter no máximo {MAX_LEN} caracteres.")

    return pwd.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd.verify((password or ""), hashed)
