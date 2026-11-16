import React, { useEffect, useState } from 'react';
import { Camera, CheckCircle2, Info, Save, ShieldCheck, UserRound } from 'lucide-react';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Card from '../components/ui/Card';
import './ProfileSettings.css';
import TrustScorePanel from '../components/TrustScorePanel';

const ProfileSettings = () => {
  const { user, setUser } = useAuth();
  const [profile, setProfile] = useState({ name: '', username: '', email: '', phone: '', avatar_url: '' });
  const [emailCode, setEmailCode] = useState('');
  const [emailPending, setEmailPending] = useState('');
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '', confirm: '' });
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const syncProfile = (data) => setProfile({
    name: data?.name || '',
    username: data?.username || '',
    email: data?.email || '',
    phone: data?.phone || '',
    avatar_url: data?.avatar_url || '',
  });

  useEffect(() => {
    let active = true;
    if (user) syncProfile(user);
    api.get('/auth/me').then(({ data }) => {
      if (!active) return;
      setUser(data);
      syncProfile(data);
      setError('');
    }).catch((err) => {
      if (!active) return;
      if (user) setError('Showing your signed-in profile details. Refresh to retry loading the latest saved values.');
      else setError(err.response?.data?.detail || 'Could not load your profile. Please try again.');
    });
    return () => { active = false; };
  }, [setUser, user?.id]);

  const run = async (key, action, success) => {
    setBusy(key); setError(''); setNotice('');
    try { const result = await action(); if (success) success(result); else setNotice(result?.data?.message || 'Changes saved.'); }
    catch (err) { setError(err.response?.data?.detail || err.message || 'Could not save your changes.'); }
    finally { setBusy(''); }
  };

  const saveProfile = (event) => {
    event.preventDefault();
    run('profile', async () => {
      const { data } = await api.patch('/auth/me', { name: profile.name, username: profile.username, avatar_url: profile.avatar_url });
      setUser(data); setProfile((prev) => ({ ...prev, ...data }));
      return { data: { message: 'Profile updated successfully.' } };
    });
  };

  const uploadAvatar = async (event) => {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('image/')) { setError('Choose an image file.'); return; }
    if (file.size > 5 * 1024 * 1024) { setError('Profile pictures must be 5 MB or smaller.'); return; }
    await run('avatar', async () => {
      const form = new FormData(); form.append('file', file);
      const { data } = await api.post('/upload', form);
      setProfile((prev) => ({ ...prev, avatar_url: data.url }));
      setNotice('Picture uploaded. Save profile to apply it.');
      return { data: { message: 'Picture uploaded. Save profile to apply it.' } };
    });
  };

  const requestEmail = (event) => {
    event.preventDefault();
    run('email', async () => {
      const { data } = await api.post('/auth/me/email/request', { email: profile.email });
      setEmailPending(profile.email.trim().toLowerCase()); setEmailCode(''); return { data };
    });
  };
  const verifyEmail = (event) => {
    event.preventDefault();
    run('email', async () => {
      const { data } = await api.post('/auth/me/email/verify', { value: emailPending, code: emailCode });
      setUser(data); setProfile((prev) => ({ ...prev, email: data.email })); setEmailPending(''); return { data: { message: 'Email address verified and updated.' } };
    });
  };
  const savePhone = (event) => {
    event.preventDefault();
    run('phone', async () => {
      const phone = profile.phone.trim();
      const { data } = await api.patch('/auth/me', { phone: phone || null });
      setUser(data); setProfile((prev) => ({ ...prev, phone: data.phone || '' }));
      return { data: { message: 'Phone number updated.' } };
    });
  };
  const cancelContact = (kind) => run(kind, async () => {
    await api.delete('/auth/me/contact-change');
    setEmailPending(''); setEmailCode(''); setProfile((prev) => ({ ...prev, email: user.email }));
    return { data: { message: 'Verification request cancelled.' } };
  });
  const changePassword = (event) => {
    event.preventDefault();
    if (passwords.new_password !== passwords.confirm) { setError('New passwords do not match.'); return; }
    if (passwords.new_password.length < 8) { setError('Use at least 8 characters for your new password.'); return; }
    run('password', async () => {
      const { data } = await api.post('/auth/me/password', { current_password: passwords.current_password, new_password: passwords.new_password });
      setPasswords({ current_password: '', new_password: '', confirm: '' }); return { data };
    });
  };

  return <div className="profile-page app-page"><div className="wrap profile-wrap">
    <header className="profile-heading"><span className="profile-kicker"><ShieldCheck size={16} /> Account settings</span><h1 className="t-h2">Edit Profile</h1><p className="t-lead measure">Manage your details and keep your account information up to date.</p></header>
    {notice && <div className="profile-alert profile-success" role="status"><CheckCircle2 size={18} />{notice}</div>}
    {error && <div className="profile-alert profile-error" role="alert">{error}</div>}
    <TrustScorePanel userId="me" />

    <Card className="profile-card">
      <form onSubmit={saveProfile}>
        <h2 className="t-card">Personal details</h2>
        <div className="profile-avatar-row">
          <div className="profile-avatar">{profile.avatar_url ? <img src={profile.avatar_url} alt="Profile" /> : <UserRound size={32} />}</div>
          <label className="profile-upload btn btn--secondary"><Camera size={17} />{busy === 'avatar' ? 'Uploading…' : 'Change picture'}<input type="file" accept="image/*" onChange={uploadAvatar} disabled={Boolean(busy)} /></label>
          <span className="t-small muted">Image up to 5 MB</span>
        </div>
        <div className="profile-fields">
          <Input name="name" label="Full name" autoComplete="name" maxLength={120} required value={profile.name} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
          <Input name="username" label="Username" autoComplete="username" minLength={3} maxLength={50} pattern="[A-Za-z0-9_.-]+" required value={profile.username} onChange={(e) => setProfile({ ...profile, username: e.target.value })} />
        </div>
        <div className="profile-form-actions"><Button type="submit" disabled={Boolean(busy)} loading={busy === 'profile'}><Save size={17} /> Save profile</Button></div>
      </form>
    </Card>

    <Card className="profile-card"><form onSubmit={emailPending ? verifyEmail : requestEmail}>
      <h2 className="t-card">Email address</h2><p className="t-small muted">A code will be sent to the new address. Your current address stays active until you verify it.</p>
      <div className="profile-fields contact-fields"><Input name="email" type="email" label="Email" autoComplete="email" required value={profile.email} disabled={Boolean(emailPending)} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
        {emailPending && <Input name="email-code" label={`Code sent to ${emailPending}`} inputMode="numeric" autoComplete="one-time-code" maxLength={6} required value={emailCode} onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />}</div>
      <div className="profile-form-actions">{emailPending && <Button type="button" variant="secondary" disabled={Boolean(busy)} onClick={() => cancelContact('email')}>Cancel</Button>}<Button type="submit" disabled={Boolean(busy)} loading={busy === 'email'}>{emailPending ? 'Verify email' : 'Send verification code'}</Button></div>
    </form></Card>

    <Card className="profile-card"><form onSubmit={savePhone}>
      <h2 className="t-card">Phone number</h2><p className="t-small muted">Enter your phone number in international format. Phone number changes are saved immediately.</p>
      <div className="profile-fields contact-fields"><Input name="phone" type="tel" label="Phone" autoComplete="tel" placeholder="+14155552671" pattern="\+[1-9][0-9]{7,14}" value={profile.phone} onChange={(e) => setProfile({ ...profile, phone: e.target.value })} /></div>
      <div className="profile-form-actions"><Button type="submit" disabled={Boolean(busy)} loading={busy === 'phone'}>Save phone number</Button></div>
    </form></Card>

    <Card className="profile-card"><form onSubmit={changePassword}>
      <h2 className="t-card">Change password</h2><p className="t-small muted">Confirm your current password before setting a new one.</p>
      <div className="profile-fields"><Input name="current_password" type="password" label="Current password" autoComplete="current-password" required value={passwords.current_password} onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })} />
        <span /><Input name="new_password" type="password" label="New password" autoComplete="new-password" minLength={8} maxLength={72} required value={passwords.new_password} onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })} />
        <Input name="confirm_password" type="password" label="Confirm new password" autoComplete="new-password" minLength={8} maxLength={72} required value={passwords.confirm} onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} /></div>
      <div className="profile-form-actions"><Button type="submit" disabled={Boolean(busy)} loading={busy === 'password'}>Update password</Button></div>
    </form></Card>
    <p className="profile-footnote"><Info size={14} /> Email changes take effect only after verification. Phone number changes are saved immediately.</p>
  </div></div>;
};

export default ProfileSettings;
