import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Panel } from '../components/ui/Panel';
import { Button } from '../components/ui/Button';
import { StatusPulse } from '../components/ui/StatusPulse';
import { KeyRound, ShieldAlert, ArrowRight, Lock, Mail, ChevronDown, ChevronRight } from 'lucide-react';

interface SignInViewProps {
  onSuccess?: () => void;
}

export const SignInView: React.FC<SignInViewProps> = ({ onSuccess }) => {
  const { signInWithCredentials, signInWithToken, status, error, clearError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [persistSession, setPersistSession] = useState(true);
  const [validationMsg, setValidationMsg] = useState<string | null>(null);

  // Advanced direct token mode
  const [showDirectToken, setShowDirectToken] = useState(false);
  const [tokenInput, setTokenInput] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setValidationMsg(null);

    if (showDirectToken) {
      const cleanToken = tokenInput.trim();
      if (!cleanToken) {
        setValidationMsg('Please provide a valid Supabase JWT Bearer token.');
        return;
      }
      const res = await signInWithToken(cleanToken, persistSession);
      if (res.success && onSuccess) {
        onSuccess();
      }
    } else {
      const cleanEmail = email.trim();
      if (!cleanEmail) {
        setValidationMsg('Please enter your email address.');
        return;
      }
      if (!password) {
        setValidationMsg('Please enter your password.');
        return;
      }

      const res = await signInWithCredentials(cleanEmail, password, persistSession);
      if (res.success && onSuccess) {
        onSuccess();
      }
    }
  };

  const isLoading = status === 'loading';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '75vh',
        padding: '24px 16px',
      }}
    >
      <div style={{ width: '100%', maxWidth: '460px' }}>
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '44px',
              height: '44px',
              borderRadius: 'var(--radius-md)',
              background: 'rgba(174, 184, 192, 0.1)',
              border: '1px solid rgba(174, 184, 192, 0.3)',
              color: 'var(--devdoc-accent)',
              marginBottom: '12px',
            }}
          >
            <KeyRound size={22} />
          </div>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '22px',
              fontWeight: 700,
              color: 'var(--devdoc-fg)',
              letterSpacing: '0.02em',
            }}
          >
            Sign In to DEVDOC
          </h1>
          <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            Sign in with your registered account to manage projects, connect GitHub repositories, and run AI investigations.
          </p>
        </div>

        <Panel
          title="Account Sign In"
          meta={
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <StatusPulse status="ok" />
              <span style={{ fontSize: '10px', color: 'var(--devdoc-fg-muted)' }}>Supabase Auth (ES256 / JWKS)</span>
            </div>
          }
        >
          {(error || validationMsg) && (
            <div
              style={{
                padding: '10px 12px',
                background: 'var(--devdoc-status-bad-bg)',
                border: '1px solid var(--devdoc-status-bad-border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--devdoc-status-bad)',
                fontSize: '12px',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '8px',
                marginBottom: '14px',
              }}
            >
              <ShieldAlert size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong>Authentication Failed:</strong>
                <div style={{ marginTop: '2px', wordBreak: 'break-word' }}>
                  {error || validationMsg}
                </div>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {!showDirectToken ? (
              <>
                <div style={{ marginBottom: '14px' }}>
                  <label
                    htmlFor="auth-email-input"
                    style={{
                      display: 'block',
                      fontSize: '11px',
                      fontFamily: 'var(--font-display)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      color: 'var(--devdoc-fg-muted)',
                      marginBottom: '6px',
                    }}
                  >
                    Email Address
                  </label>
                  <div style={{ position: 'relative' }}>
                    <input
                      id="auth-email-input"
                      type="email"
                      required
                      autoComplete="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        if (validationMsg) setValidationMsg(null);
                      }}
                      placeholder="engineer@company.com"
                      style={{
                        width: '100%',
                        background: 'var(--devdoc-surface-sunken)',
                        border: '1px solid var(--devdoc-border)',
                        color: 'var(--devdoc-fg)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '9px 12px 9px 34px',
                        fontSize: '13px',
                      }}
                      disabled={isLoading}
                    />
                    <Mail
                      size={15}
                      style={{
                        position: 'absolute',
                        left: '10px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        color: 'var(--devdoc-fg-dim)',
                        pointerEvents: 'none',
                      }}
                    />
                  </div>
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label
                    htmlFor="auth-password-input"
                    style={{
                      display: 'block',
                      fontSize: '11px',
                      fontFamily: 'var(--font-display)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      color: 'var(--devdoc-fg-muted)',
                      marginBottom: '6px',
                    }}
                  >
                    Password
                  </label>
                  <div style={{ position: 'relative' }}>
                    <input
                      id="auth-password-input"
                      type="password"
                      required
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        if (validationMsg) setValidationMsg(null);
                      }}
                      placeholder="••••••••"
                      style={{
                        width: '100%',
                        background: 'var(--devdoc-surface-sunken)',
                        border: '1px solid var(--devdoc-border)',
                        color: 'var(--devdoc-fg)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '9px 12px 9px 34px',
                        fontSize: '13px',
                      }}
                      disabled={isLoading}
                    />
                    <Lock
                      size={15}
                      style={{
                        position: 'absolute',
                        left: '10px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        color: 'var(--devdoc-fg-dim)',
                        pointerEvents: 'none',
                      }}
                    />
                  </div>
                </div>
              </>
            ) : (
              <div style={{ marginBottom: '14px' }}>
                <label
                  htmlFor="auth-token-input"
                  style={{
                    display: 'block',
                    fontSize: '11px',
                    fontFamily: 'var(--font-display)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    color: 'var(--devdoc-fg-muted)',
                    marginBottom: '6px',
                  }}
                >
                  Direct Supabase JWT Bearer Token
                </label>
                <textarea
                  id="auth-token-input"
                  rows={4}
                  value={tokenInput}
                  onChange={(e) => {
                    setTokenInput(e.target.value);
                    if (validationMsg) setValidationMsg(null);
                  }}
                  placeholder="eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOi..."
                  style={{
                    width: '100%',
                    background: 'var(--devdoc-surface-sunken)',
                    border: '1px solid var(--devdoc-border)',
                    color: 'var(--devdoc-fg)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 10px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    lineHeight: '1.4',
                    resize: 'vertical',
                  }}
                  disabled={isLoading}
                />
              </div>
            )}

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '16px',
                fontSize: '12px',
                color: 'var(--devdoc-fg-muted)',
              }}
            >
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={persistSession}
                  onChange={(e) => setPersistSession(e.target.checked)}
                  style={{ accentColor: 'var(--devdoc-accent)' }}
                />
                Remember session on this device
              </label>

              <button
                type="button"
                onClick={() => {
                  setShowDirectToken(!showDirectToken);
                  setValidationMsg(null);
                  clearError();
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--devdoc-accent)',
                  fontSize: '11px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: 0,
                }}
              >
                {showDirectToken ? (
                  <>
                    <ChevronDown size={13} />
                    Email / Password
                  </>
                ) : (
                  <>
                    <ChevronRight size={13} />
                    Direct Token
                  </>
                )}
              </button>
            </div>

            <Button
              type="submit"
              variant="primary"
              style={{ width: '100%', padding: '10px' }}
              disabled={isLoading || (!showDirectToken && (!email.trim() || !password)) || (showDirectToken && !tokenInput.trim())}
              icon={<ArrowRight size={14} />}
            >
              {isLoading ? 'Authenticating with Supabase...' : 'Sign In to Platform'}
            </Button>
          </form>

          <div
            style={{
              marginTop: '16px',
              paddingTop: '12px',
              borderTop: '1px solid var(--devdoc-border-subtle)',
              fontSize: '11px',
              color: 'var(--devdoc-fg-muted)',
              lineHeight: 1.5,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--devdoc-accent)', marginBottom: '4px' }}>
              <Lock size={12} />
              <span style={{ fontWeight: 600 }}>Security Protocol</span>
            </div>
            Sessions are validated by the FastAPI backend using Supabase Auth public keys via ES256/JWKS. User identifiers enforce PostgreSQL Row Level Security (RLS) on all workspace operations.
          </div>
        </Panel>
      </div>
    </div>
  );
};
