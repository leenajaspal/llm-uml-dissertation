from sqlalchemy.orm import Session
from models import User, Account
from auth import hash_password, verify_password, create_access_token

def register_user(db: Session, email: str, password: str) -> User:
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise ValueError("Email already registered")
    
    hashed_password, salt = hash_password(password)
    user = User(email=email, hashed_password=hashed_password, salt=salt)
    db.add(user)
    db.flush()
    
    account = Account(user_id=user.id, currency="GBP")
    db.add(account)
    db.commit()
    db.refresh(user)
    return user

def authenticate_user(db: Session, email: str, password: str) -> str | None:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    return create_access_token({"user_id": user.id})