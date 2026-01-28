from passlib.context import CryptContext
from passlib.exc import UnknownHashError

# MUDANÇA: Forçamos o uso do bcrypt sem deixar 'auto' decidir
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
