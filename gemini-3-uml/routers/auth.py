from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import schemas, models, security
from database import get_db

router = APIRouter(tags=["auth"])

@router.post("/auth/register", response_model=schemas.RegisterRes, status_code=201)
def register(req: schemas.RegisterReq, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    user = models.User(email=req.email, password_hash=security.get_password_hash(req.password))
    db.add(user)
    db.flush()
    
    acc = models.Account(user_id=user.user_id, currency="GBP")
    db.add(acc)
    db.commit()
    
    return {"user_id": user.user_id, "email": user.email}

@router.post("/auth/login", response_model=schemas.LoginRes, status_code=200)
def login(req: schemas.LoginReq, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user or not security.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    return {"access_token": security.create_access_token({"sub": user.user_id})}
