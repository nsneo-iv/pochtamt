// Авторизация: GET /auth/config, POST /auth/login, GET /auth/me
import { http } from './client'
import type { AuthConfig, LoginRequest, LoginResponse, User } from './types'

export function login(data: LoginRequest): Promise<LoginResponse> {
  return http.post<LoginResponse>('/auth/login', data)
}

export function me(): Promise<User> {
  return http.get<User>('/auth/me')
}

export function config(): Promise<AuthConfig> {
  return http.get<AuthConfig>('/auth/config')
}
