const ACCESS_KEY = "stock_access_token";
const REFRESH_KEY = "stock_refresh_token";

export function getAccessToken(): string {
  return localStorage.getItem(ACCESS_KEY) ?? "";
}

export function getRefreshToken(): string {
  return localStorage.getItem(REFRESH_KEY) ?? "";
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_KEY, accessToken);
  localStorage.setItem(REFRESH_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken());
}
