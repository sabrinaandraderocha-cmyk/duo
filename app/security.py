from passlib.context import CryptContext
from passlib.exc import UnknownHashError

# Configura o sistema de hash (Bcrypt é o padrão seguro)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    """Verifica se a senha digitada bate com o hash salvo."""
    try:
        # Se a senha no banco for nula ou vazia, nega
        if not hashed_password:
            return False
        return pwd_context.verify(plain_password, hashed_password)
    except (UnknownHashError, ValueError):
        # Se o hash estiver estragado, apenas nega o login (não derruba o site)
        return False

def hash_password(password):
    """Transforma a senha em um hash seguro."""
    return pwd_context.hash(password)
