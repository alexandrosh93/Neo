import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Alert,
  Platform,
} from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { Ionicons } from '@expo/vector-icons';
import { supabase } from '../lib/supabase';
import { Visit, VisitResponse } from '../types';

const RESPONSES: VisitResponse[] = ['Yes', 'No', 'No Answer'];

const RESPONSE_COLORS: Record<VisitResponse, string> = {
  Yes: '#2d6a4f',
  No: '#c0392b',
  'No Answer': '#e67e22',
};

interface Props {
  navigation: any;
  route: any;
}

export default function EditVisitScreen({ navigation, route }: Props) {
  const { visit, onDone }: { visit: Visit; onDone: () => void } = route.params;
  const [date, setDate] = useState(new Date(visit.visited_at));
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [response, setResponse] = useState<VisitResponse>(visit.response);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    const { error } = await supabase
      .from('visits')
      .update({ visited_at: date.toISOString(), response })
      .eq('id', visit.id);
    setSaving(false);
    if (error) {
      Alert.alert('Error', error.message);
    } else {
      onDone();
      navigation.goBack();
    }
  }

  function formatDate(d: Date) {
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function formatTime(d: Date) {
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }

  return (
    <View style={styles.container}>
      <Text style={styles.sectionLabel}>Date & Time of Visit</Text>

      <View style={styles.row}>
        <TouchableOpacity style={styles.pickerBtn} onPress={() => setShowDatePicker(true)}>
          <Ionicons name="calendar-outline" size={18} color="#2d6a4f" />
          <Text style={styles.pickerText}>{formatDate(date)}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.pickerBtn} onPress={() => setShowTimePicker(true)}>
          <Ionicons name="time-outline" size={18} color="#2d6a4f" />
          <Text style={styles.pickerText}>{formatTime(date)}</Text>
        </TouchableOpacity>
      </View>

      {showDatePicker && (
        <DateTimePicker
          value={date}
          mode="date"
          display={Platform.OS === 'ios' ? 'spinner' : 'default'}
          onChange={(_, selected) => {
            setShowDatePicker(false);
            if (selected) {
              const updated = new Date(date);
              updated.setFullYear(selected.getFullYear(), selected.getMonth(), selected.getDate());
              setDate(updated);
            }
          }}
        />
      )}
      {showTimePicker && (
        <DateTimePicker
          value={date}
          mode="time"
          display={Platform.OS === 'ios' ? 'spinner' : 'default'}
          onChange={(_, selected) => {
            setShowTimePicker(false);
            if (selected) {
              const updated = new Date(date);
              updated.setHours(selected.getHours(), selected.getMinutes());
              setDate(updated);
            }
          }}
        />
      )}

      <Text style={[styles.sectionLabel, { marginTop: 24 }]}>Response</Text>
      <View style={styles.responseRow}>
        {RESPONSES.map((r) => (
          <TouchableOpacity
            key={r}
            style={[
              styles.responseBtn,
              response === r && { backgroundColor: RESPONSE_COLORS[r], borderColor: RESPONSE_COLORS[r] },
            ]}
            onPress={() => setResponse(r)}
          >
            <Text style={[styles.responseBtnText, response === r && { color: '#fff' }]}>{r}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity style={[styles.saveBtn, saving && { opacity: 0.6 }]} onPress={handleSave} disabled={saving}>
        <Text style={styles.saveBtnText}>{saving ? 'Saving…' : 'Update Visit'}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f7fa', padding: 20 },
  sectionLabel: { fontSize: 14, fontWeight: '700', color: '#555', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 10 },
  row: { flexDirection: 'row', gap: 12 },
  pickerBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 14,
    borderWidth: 1,
    borderColor: '#e0e0e0',
  },
  pickerText: { fontSize: 15, color: '#1a1a2e', fontWeight: '600' },
  responseRow: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  responseBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: '#d0d0d0',
    alignItems: 'center',
  },
  responseBtnText: { fontWeight: '700', fontSize: 14, color: '#555' },
  saveBtn: {
    marginTop: 36,
    backgroundColor: '#2d6a4f',
    borderRadius: 12,
    padding: 18,
    alignItems: 'center',
  },
  saveBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
