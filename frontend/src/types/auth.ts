export interface AuthUser {
  id: number;
  name: string;
  email: string;
  is_active: boolean;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface LoginResponse {
  user: AuthUser;
  csrf_token: string;
}

export interface LogoutResponse {
  message: string;
}

export interface CsrfTokenResponse {
  csrf_token: string;
}
