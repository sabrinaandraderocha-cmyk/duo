from passlib.context import CryptContext

# Configura o sistema de hash (Bcrypt é o padrão seguro)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    """Verifica se a senha digitada bate com o hash salvo."""
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password):
    """Transforma a senha em um hash seguro."""
    return pwd_context.hash(password)
