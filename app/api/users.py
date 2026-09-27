from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.db.database import get_db
from app.db.models import Classification, Team, User, user_teams
from app.core.security import Principal, get_current_principal
from app.schemas.user import ClassificationSummary, TeamSummary, UserRead
router=APIRouter(tags=["users"])
@router.get("/users",response_model=list[UserRead])
def list_users(db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)): return list(db.scalars(select(User).options(selectinload(User.teams)).order_by(User.id)))
@router.get("/users/{user_id}",response_model=UserRead)
def get_user(user_id:int,db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)):
 user=db.scalar(select(User).options(selectinload(User.teams)).where(User.id==user_id))
 if not user: raise HTTPException(404,"User not found")
 return user
@router.get("/teams",response_model=list[TeamSummary],tags=["teams"])
def list_teams(db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)): return list(db.scalars(select(Team).join(user_teams,user_teams.c.team_id==Team.id).where(user_teams.c.user_id==principal.user_id).order_by(Team.name,Team.id)))
@router.get("/classifications",response_model=list[ClassificationSummary],tags=["classifications"])
def list_classifications(db:Session=Depends(get_db), principal:Principal=Depends(get_current_principal)): return list(db.scalars(select(Classification).order_by(Classification.name,Classification.id)))
