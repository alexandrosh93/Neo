import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { checkPassword, setPassword } from '../lib/password';

export default function SettingsScreen() {
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleChangePassword() {
    if (!currentPw || !newPw || !confirmPw) {
      Alert.alert('Validation', 'Please fill in all fields.');
      return;
    }
    if (newPw !== confirmPw) {
      Alert.alert('Validation', 'New passwords do not match.');
      return;
    }
    if (newPw.length < 4) {
      Alert.alert('Validation', 'Password must be at least 4 characters.');
      return;
    }
    const ok = await checkPassword(currentPw);
    if (!ok) {
      Alert.alert('Error', 'Current password is incorrect.');
      return;
    }
    setSaving(true);
    await setPassword(newPw);
    setSaving(false);
    setCurrentPw('');
    setNewPw('');
    setConfirmPw('');
    Alert.alert('Success', 'Password changed successfully.');
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Text style={styles.sectionLabel}>Change Password</Text>
        <View style={styles.card}>
          <TextInput
            style={styles.input}
            placeholder="Current password"
            secureTextEntry
            value={currentPw}
            onChangeText={setCurrentPw}
          />
          <TextInput
            style={styles.input}
            placeholder="New password"
            secureTextEntry
            value={newPw}
            onChangeText={setNewPw}
          />
          <TextInput
            style={[styles.input, { marginBottom: 0 }]}
            placeholder="Confirm new password"
            secureTextEntry
            value={confirmPw}
            onChangeText={setConfirmPw}
          />
        </View>
        <TouchableOpacity
          style={[styles.saveBtn, saving && { opacity: 0.6 }]}
          onPress={handleChangePassword}
          disabled={saving}
        >
          <Text style={styles.saveBtnText}>{saving ? 'Saving…' : 'Change Password'}</Text>
        </TouchableOpacity>

        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>Neoclis Visit Recorder</Text>
          <Text style={styles.infoText}>Records visits to Koullis' Flat</Text>
          <Text style={styles.infoText}>Default password: neoclis2024</Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f7fa' },
  content: { padding: 20, gap: 16 },
  sectionLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: '#555',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e8e8e8',
  },
  input: {
    borderWidth: 1,
    borderColor: '#d0d0d0',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    marginBottom: 12,
  },
  saveBtn: {
    backgroundColor: '#2d6a4f',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  saveBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  infoCard: {
    marginTop: 16,
    backgroundColor: '#e8f5e9',
    borderRadius: 12,
    padding: 16,
    gap: 4,
  },
  infoTitle: { fontWeight: '700', fontSize: 15, color: '#2d6a4f' },
  infoText: { color: '#4a7c59', fontSize: 13 },
});
