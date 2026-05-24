const KEY = 'neoclis_password';
const DEFAULT = 'neoclis2024';

export function getPassword(): string {
  return localStorage.getItem(KEY) ?? DEFAULT;
}

export function setPassword(pw: string): void {
  localStorage.setItem(KEY, pw);
}

export function checkPassword(input: string): boolean {
  return input === getPassword();
}
