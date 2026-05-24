import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { supabase } from '../lib/supabase';
import { Visit } from '../types';
import PasswordModal from '../components/PasswordModal';

const RESPONSE_COLORS: Record<string, string> = {
  Yes: '#2d6a4f',
  No: '#c0392b',
  'No Answer': '#e67e22',
};

interface Props {
  navigation: any;
}

export default function VisitListScreen({ navigation }: Props) {
  const [visits, setVisits] = useState<Visit[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [passwordTarget, setPasswordTarget] = useState<'add' | 'edit' | 'delete' | null>(null);
  const [pendingVisit, setPendingVisit] = useState<Visit | null>(null);

  const fetchVisits = useCallback(async () => {
    const { data, error } = await supabase
      .from('visits')
      .select('*')
      .order('visited_at', { ascending: false });
    if (error) {
      Alert.alert('Error', error.message);
    } else {
      setVisits(data ?? []);
    }
  }, []);

  useEffect(() => {
    fetchVisits().finally(() => setLoading(false));
  }, [fetchVisits]);

  async function handleRefresh() {
    setRefreshing(true);
    await fetchVisits();
    setRefreshing(false);
  }

  function requestAdd() {
    setPasswordTarget('add');
  }

  function requestEdit(visit: Visit) {
    setPendingVisit(visit);
    setPasswordTarget('edit');
  }

  function requestDelete(visit: Visit) {
    setPendingVisit(visit);
    setPasswordTarget('delete');
  }

  async function onPasswordSuccess() {
    if (passwordTarget === 'add') {
      setPasswordTarget(null);
      navigation.navigate('AddVisit', { onDone: fetchVisits });
    } else if (passwordTarget === 'edit' && pendingVisit) {
      setPasswordTarget(null);
      navigation.navigate('EditVisit', { visit: pendingVisit, onDone: fetchVisits });
      setPendingVisit(null);
    } else if (passwordTarget === 'delete' && pendingVisit) {
      setPasswordTarget(null);
      await deleteVisit(pendingVisit.id);
      setPendingVisit(null);
    }
  }

  async function deleteVisit(id: string) {
    const { error } = await supabase.from('visits').delete().eq('id', id);
    if (error) {
      Alert.alert('Error', error.message);
    } else {
      await fetchVisits();
    }
  }

  function formatDate(iso: string) {
    const d = new Date(iso);
    return d.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  }

  function formatTime(iso: string) {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }

  function renderItem({ item }: { item: Visit }) {
    const color = RESPONSE_COLORS[item.response] ?? '#555';
    return (
      <View style={styles.card}>
        <View style={styles.cardLeft}>
          <Text style={styles.dateText}>{formatDate(item.visited_at)}</Text>
          <Text style={styles.timeText}>{formatTime(item.visited_at)}</Text>
        </View>
        <View style={[styles.badge, { backgroundColor: color }]}>
          <Text style={styles.badgeText}>{item.response}</Text>
        </View>
        <View style={styles.actions}>
          <TouchableOpacity onPress={() => requestEdit(item)} style={styles.iconBtn}>
            <Ionicons name="pencil" size={18} color="#2d6a4f" />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => requestDelete(item)} style={styles.iconBtn}>
            <Ionicons name="trash" size={18} color="#c0392b" />
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#2d6a4f" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={visits}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="calendar-outline" size={48} color="#ccc" />
            <Text style={styles.emptyText}>No visits recorded yet</Text>
          </View>
        }
        contentContainerStyle={visits.length === 0 ? styles.emptyContainer : styles.list}
      />
      <TouchableOpacity style={styles.fab} onPress={requestAdd}>
        <Ionicons name="add" size={28} color="#fff" />
      </TouchableOpacity>
      <PasswordModal
        visible={passwordTarget !== null}
        onSuccess={onPasswordSuccess}
        onCancel={() => {
          setPasswordTarget(null);
          setPendingVisit(null);
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f7fa' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: 16, gap: 12 },
  emptyContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  empty: { alignItems: 'center', gap: 8 },
  emptyText: { color: '#aaa', fontSize: 16 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.07,
    shadowRadius: 6,
    elevation: 3,
  },
  cardLeft: { flex: 1 },
  dateText: { fontSize: 15, fontWeight: '700', color: '#1a1a2e' },
  timeText: { fontSize: 13, color: '#777', marginTop: 2 },
  badge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    marginHorizontal: 10,
  },
  badgeText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  actions: { flexDirection: 'row', gap: 8 },
  iconBtn: { padding: 6 },
  fab: {
    position: 'absolute',
    bottom: 28,
    right: 24,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#2d6a4f',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 8,
  },
});
