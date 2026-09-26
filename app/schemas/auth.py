from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class AuthUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
    email: EmailStr
    is_active: bool


class LoginResponse(BaseModel):
    user: AuthUserRead
    csrf_token: str


class LogoutResponse(BaseModel):
    message: str


class CsrfRotationRequest(BaseModel):
    """An intentionally empty body that rejects client-supplied identity."""

    model_config = ConfigDict(extra="forbid")


class CsrfTokenResponse(BaseModel):
    csrf_token: str
