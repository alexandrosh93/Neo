import React, { useState } from 'react';
import {
  Modal,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { checkPassword } from '../lib/password';

interface Props {
  visible: boolean;
  onSuccess: () => void;
  onCancel: () => void;
}

export default function PasswordModal({ visible, onSuccess, onCancel }: Props) {
  const [input, setInput] = useState('');
  const [error, setError] = useState('');

  async function handleSubmit() {
    const ok = await checkPassword(input);
    if (ok) {
      setInput('');
      setError('');
      onSuccess();
    } else {
      setError('Incorrect password. Try again.');
    }
  }

  function handleCancel() {
    setInput('');
    setError('');
    onCancel();
  }

  return (
    <Modal visible={visible} transparent animationType="fade">
      <KeyboardAvoidingView
        style={styles.overlay}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <View style={styles.card}>
          <Text style={styles.title}>Enter Password</Text>
          <TextInput
            style={styles.input}
            placeholder="Password"
            secureTextEntry
            value={input}
            onChangeText={setInput}
            onSubmitEditing={handleSubmit}
            autoFocus
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.buttons}>
            <TouchableOpacity style={styles.cancelBtn} onPress={handleCancel}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.submitBtn} onPress={handleSubmit}>
              <Text style={styles.submitText}>Unlock</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  card: {
    width: 300,
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 10,
    elevation: 8,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 16,
    color: '#1a1a2e',
    textAlign: 'center',
  },
  input: {
    borderWidth: 1,
    borderColor: '#d0d0d0',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    marginBottom: 8,
  },
  error: {
    color: '#e53e3e',
    fontSize: 13,
    marginBottom: 8,
    textAlign: 'center',
  },
  buttons: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  cancelBtn: {
    flex: 1,
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#d0d0d0',
    alignItems: 'center',
  },
  cancelText: {
    color: '#666',
    fontWeight: '600',
  },
  submitBtn: {
    flex: 1,
    padding: 12,
    borderRadius: 8,
    backgroundColor: '#2d6a4f',
    alignItems: 'center',
  },
  submitText: {
    color: '#fff',
    fontWeight: '700',
  },
});
