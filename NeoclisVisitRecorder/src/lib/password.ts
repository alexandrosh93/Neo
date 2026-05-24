import * as SecureStore from 'expo-secure-store';

// Default password — user can change it in Settings
const DEFAULT_PASSWORD = 'neoclis2024';
const PASSWORD_KEY = 'app_password';

export async function getPassword(): Promise<string> {
  const stored = await SecureStore.getItemAsync(PASSWORD_KEY);
  return stored ?? DEFAULT_PASSWORD;
}

export async function setPassword(newPassword: string): Promise<void> {
  await SecureStore.setItemAsync(PASSWORD_KEY, newPassword);
}

export async function checkPassword(input: string): Promise<boolean> {
  const pw = await getPassword();
  return input === pw;
}
