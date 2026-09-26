from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr
class TeamSummary(BaseModel):
 model_config=ConfigDict(from_attributes=True); id:int; name:str
class ClassificationSummary(BaseModel):
 model_config=ConfigDict(from_attributes=True); id:int; name:str
class UserRead(BaseModel):
 model_config=ConfigDict(from_attributes=True); id:int; name:str; email:EmailStr; created_at:datetime; is_active:bool; teams:list[TeamSummary]=[]
