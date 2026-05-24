import { useEffect, useState } from 'react';
import { supabase } from './lib/supabase';
import { checkPassword, setPassword } from './lib/password';
import type { Visit, VisitResponse } from './types';

const RESPONSES: VisitResponse[] = ['Yes', 'No', 'No Answer'];

const RESPONSE_COLORS: Record<VisitResponse, string> = {
  Yes: '#2d6a4f',
  No: '#c0392b',
  'No Answer': '#e67e22',
};

type View = 'list' | 'add' | 'edit' | 'settings';

function toLocalDatetimeValue(iso: string) {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatDisplay(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function App() {
  const [visits, setVisits] = useState<Visit[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>('list');
  const [editTarget, setEditTarget] = useState<Visit | null>(null);

  // password gate
  const [pwModal, setPwModal] = useState<{ action: () => void } | null>(null);
  const [pwInput, setPwInput] = useState('');
  const [pwError, setPwError] = useState('');

  // form state
  const [formDatetime, setFormDatetime] = useState('');
  const [formResponse, setFormResponse] = useState<VisitResponse>('No Answer');
  const [formSaving, setFormSaving] = useState(false);

  // settings
  const [sCurrent, setSCurrent] = useState('');
  const [sNew, setSNew] = useState('');
  const [sConfirm, setSConfirm] = useState('');
  const [sMsg, setSMsg] = useState('');

  async function fetchVisits() {
    const { data } = await supabase
      .from('visits')
      .select('*')
      .order('visited_at', { ascending: false });
    setVisits(data ?? []);
    setLoading(false);
  }

  useEffect(() => { fetchVisits(); }, []);

  function requirePassword(action: () => void) {
    setPwInput('');
    setPwError('');
    setPwModal({ action });
  }

  function handlePwSubmit() {
    if (checkPassword(pwInput)) {
      const action = pwModal!.action;
      setPwModal(null);
      action();
    } else {
      setPwError('Incorrect password.');
    }
  }

  function openAdd() {
    requirePassword(() => {
      setFormDatetime(toLocalDatetimeValue(new Date().toISOString()));
      setFormResponse('No Answer');
      setView('add');
    });
  }

  function openEdit(v: Visit) {
    requirePassword(() => {
      setEditTarget(v);
      setFormDatetime(toLocalDatetimeValue(v.visited_at));
      setFormResponse(v.response);
      setView('edit');
    });
  }

  function openDelete(v: Visit) {
    requirePassword(async () => {
      await supabase.from('visits').delete().eq('id', v.id);
      await fetchVisits();
    });
  }

  async function handleAdd() {
    if (!formDatetime) return;
    setFormSaving(true);
    await supabase.from('visits').insert({
      visited_at: new Date(formDatetime).toISOString(),
      response: formResponse,
    });
    setFormSaving(false);
    await fetchVisits();
    setView('list');
  }

  async function handleEdit() {
    if (!formDatetime || !editTarget) return;
    setFormSaving(true);
    await supabase.from('visits').update({
      visited_at: new Date(formDatetime).toISOString(),
      response: formResponse,
    }).eq('id', editTarget.id);
    setFormSaving(false);
    await fetchVisits();
    setView('list');
  }

  function handleChangePassword() {
    if (!sCurrent || !sNew || !sConfirm) { setSMsg('Fill in all fields.'); return; }
    if (sNew !== sConfirm) { setSMsg('New passwords do not match.'); return; }
    if (sNew.length < 4) { setSMsg('Password must be at least 4 characters.'); return; }
    if (!checkPassword(sCurrent)) { setSMsg('Current password is incorrect.'); return; }
    setPassword(sNew);
    setSCurrent(''); setSNew(''); setSConfirm('');
    setSMsg('Password changed successfully!');
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f0f4f1', fontFamily: 'system-ui, sans-serif' }}>
      {/* Header */}
      <header style={{
        background: '#2d6a4f', color: '#fff', padding: '0 20px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        height: 56, boxShadow: '0 2px 8px rgba(0,0,0,.2)',
      }}>
        <span
          style={{ fontWeight: 700, fontSize: 17, cursor: 'pointer' }}
          onClick={() => setView('list')}
        >
          Neoclis Visit Recorder
        </span>
        <button
          onClick={() => { setSMsg(''); setView('settings'); }}
          style={{ background: 'none', border: 'none', color: '#fff', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}
          title="Settings"
        >⚙</button>
      </header>

      <main style={{ maxWidth: 560, margin: '0 auto', padding: '24px 16px' }}>

        {/* LIST VIEW */}
        {view === 'list' && (
          <>
            {loading ? (
              <p style={{ textAlign: 'center', color: '#888' }}>Loading…</p>
            ) : visits.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#aaa', marginTop: 60 }}>
                <div style={{ fontSize: 48 }}>📋</div>
                <p>No visits recorded yet</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {visits.map(v => (
                  <div key={v.id} style={{
                    background: '#fff', borderRadius: 12, padding: '14px 16px',
                    display: 'flex', alignItems: 'center', gap: 12,
                    boxShadow: '0 1px 4px rgba(0,0,0,.08)',
                  }}>
                    <span style={{ flex: 1, fontWeight: 600, color: '#1a1a2e', fontSize: 15 }}>
                      {formatDisplay(v.visited_at)}
                    </span>
                    <span style={{
                      background: RESPONSE_COLORS[v.response], color: '#fff',
                      borderRadius: 20, padding: '4px 12px', fontWeight: 700, fontSize: 13,
                      whiteSpace: 'nowrap',
                    }}>
                      {v.response}
                    </span>
                    <button onClick={() => openEdit(v)} style={iconBtn} title="Edit">✏️</button>
                    <button onClick={() => openDelete(v)} style={iconBtn} title="Delete">🗑️</button>
                  </div>
                ))}
              </div>
            )}

            <button onClick={openAdd} style={{
              position: 'fixed', bottom: 28, right: 24, width: 56, height: 56,
              borderRadius: '50%', background: '#2d6a4f', color: '#fff',
              border: 'none', fontSize: 28, cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(0,0,0,.25)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>+</button>
          </>
        )}

        {/* ADD / EDIT FORM */}
        {(view === 'add' || view === 'edit') && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <button onClick={() => setView('list')} style={backBtn}>← Back</button>
            <h2 style={{ margin: 0, color: '#1a1a2e' }}>
              {view === 'add' ? 'Add Visit' : 'Edit Visit'}
            </h2>

            <div>
              <label style={labelStyle}>Date & Time</label>
              <input
                type="datetime-local"
                value={formDatetime}
                onChange={e => setFormDatetime(e.target.value)}
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Response</label>
              <div style={{ display: 'flex', gap: 10 }}>
                {RESPONSES.map(r => (
                  <button
                    key={r}
                    onClick={() => setFormResponse(r)}
                    style={{
                      flex: 1, padding: '12px 0', borderRadius: 10, fontWeight: 700,
                      fontSize: 14, cursor: 'pointer', border: '2px solid',
                      borderColor: formResponse === r ? RESPONSE_COLORS[r] : '#d0d0d0',
                      background: formResponse === r ? RESPONSE_COLORS[r] : '#fff',
                      color: formResponse === r ? '#fff' : '#555',
                    }}
                  >{r}</button>
                ))}
              </div>
            </div>

            <button
              onClick={view === 'add' ? handleAdd : handleEdit}
              disabled={formSaving || !formDatetime}
              style={{ ...saveBtn, opacity: (formSaving || !formDatetime) ? 0.6 : 1 }}
            >
              {formSaving ? 'Saving…' : view === 'add' ? 'Save Visit' : 'Update Visit'}
            </button>
          </div>
        )}

        {/* SETTINGS */}
        {view === 'settings' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <button onClick={() => setView('list')} style={backBtn}>← Back</button>
            <h2 style={{ margin: 0, color: '#1a1a2e' }}>Settings</h2>

            <div style={{ background: '#fff', borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column', gap: 12, boxShadow: '0 1px 4px rgba(0,0,0,.08)' }}>
              <label style={labelStyle}>Change Password</label>
              <input style={inputStyle} type="password" placeholder="Current password" value={sCurrent} onChange={e => setSCurrent(e.target.value)} />
              <input style={inputStyle} type="password" placeholder="New password" value={sNew} onChange={e => setSNew(e.target.value)} />
              <input style={inputStyle} type="password" placeholder="Confirm new password" value={sConfirm} onChange={e => setSConfirm(e.target.value)} />
              {sMsg && <p style={{ margin: 0, color: sMsg.includes('success') ? '#2d6a4f' : '#c0392b', fontSize: 13 }}>{sMsg}</p>}
              <button onClick={handleChangePassword} style={saveBtn}>Change Password</button>
            </div>

            <div style={{ background: '#e8f5e9', borderRadius: 12, padding: 16, color: '#2d6a4f', fontSize: 14, lineHeight: 1.6 }}>
              <strong>Neoclis Visit Recorder</strong><br />
              Records visits to Koullis' Flat<br />
              Default password: neoclis2024
            </div>
          </div>
        )}
      </main>

      {/* PASSWORD MODAL */}
      {pwModal && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999,
        }}>
          <div style={{
            background: '#fff', borderRadius: 14, padding: 28, width: 300,
            boxShadow: '0 8px 32px rgba(0,0,0,.2)',
          }}>
            <h3 style={{ margin: '0 0 16px', textAlign: 'center', color: '#1a1a2e' }}>Enter Password</h3>
            <input
              autoFocus
              type="password"
              placeholder="Password"
              value={pwInput}
              onChange={e => setPwInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handlePwSubmit()}
              style={{ ...inputStyle, marginBottom: 8 }}
            />
            {pwError && <p style={{ margin: '0 0 8px', color: '#c0392b', fontSize: 13, textAlign: 'center' }}>{pwError}</p>}
            <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
              <button
                onClick={() => { setPwModal(null); setPwError(''); }}
                style={{ flex: 1, padding: 12, borderRadius: 8, border: '1px solid #d0d0d0', background: '#fff', cursor: 'pointer', fontWeight: 600, color: '#555' }}
              >Cancel</button>
              <button
                onClick={handlePwSubmit}
                style={{ flex: 1, padding: 12, borderRadius: 8, border: 'none', background: '#2d6a4f', color: '#fff', cursor: 'pointer', fontWeight: 700 }}
              >Unlock</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const iconBtn: React.CSSProperties = {
  background: 'none', border: 'none', cursor: 'pointer', fontSize: 16, padding: 4,
};
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 13, fontWeight: 700, color: '#555',
  textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8,
};
const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #d0d0d0',
  fontSize: 15, boxSizing: 'border-box',
};
const saveBtn: React.CSSProperties = {
  padding: '14px 0', background: '#2d6a4f', color: '#fff', border: 'none',
  borderRadius: 12, fontWeight: 700, fontSize: 16, cursor: 'pointer', width: '100%',
};
const backBtn: React.CSSProperties = {
  background: 'none', border: 'none', color: '#2d6a4f', fontWeight: 600,
  fontSize: 15, cursor: 'pointer', padding: 0, textAlign: 'left',
};
