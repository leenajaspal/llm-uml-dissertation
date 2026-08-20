from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from schemas import UserRegister, UserLogin, TokenResponse, UserResponse
from services.auth_service import register_user, authenticate_user

router = APIRouter()

@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: UserRegister, db: Session = Depends(get_db)):
    try:
        user = register_user(db, request.email, request.password)
        return UserResponse(user_id=user.id, email=user.email)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/auth/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login(request: UserLogin, db: Session = Depends(get_db)):
    token = authenticate_user(db, request.email, request.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    return TokenResponse(access_token=token)