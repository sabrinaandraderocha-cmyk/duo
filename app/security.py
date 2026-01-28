from passlib.context import CryptContext
from passlib.exc import UnknownHashError

# MUDANÇA: Usando pbkdf2_sha256 que não precisa de instalação externa
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    """Verifica se a senha digitada bate com o hash salvo."""
    try:
        if not hashed_password:
            return False
        return pwd_context.verify(plain_password, hashed_password)
    except (UnknownHashError, ValueError):
        return False

def hash_password(password):
    """Transforma a senha em um hash seguro."""
    return pwd_context.hash(password)
