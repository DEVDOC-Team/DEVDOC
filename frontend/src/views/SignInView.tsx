import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Panel } from '../components/ui/Panel';
import { Button } from '../components/ui/Button';
import { StatusPulse } from '../components/ui/StatusPulse';
import { KeyRound, ShieldAlert, ArrowRight, Lock } from 'lucide-react';

interface SignInViewProps {
  onSuccess?: () => void;
}

export const SignInView: React.FC<SignInViewProps> = ({ onSuccess }) => {
  const { signInWithToken, status, error, clearError } = useAuth();
  const [tokenInput, setTokenInput] = useState('');
  const [persistToken, setPersistToken] = useState(true);
  const [validationMsg, setValidationMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setValidationMsg(null);

    const cleanToken = tokenInput.trim();
    if (!cleanToken) {
      setValidationMsg('Please provide a valid Supabase JWT Bearer token.');
      return;
    }

    const res = await signInWithToken(cleanToken, persistToken);
    if (res.success && onSuccess) {
      onSuccess();
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
            Authenticate with DEVDOC
          </h1>
          <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            Enter your cryptographically signed Supabase access token to access autonomous DevOps operations.
          </p>
        </div>

        <Panel
          title="Session Authorization"
          meta={
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <StatusPulse status="ok" />
              <span style={{ fontSize: '10px', color: 'var(--devdoc-fg-muted)' }}>HS256 Verified</span>
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
                <strong>Authentication Rejected:</strong>
                <div style={{ marginTop: '2px', wordBreak: 'break-word' }}>
                  {error || validationMsg}
                </div>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit}>
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
                Supabase Bearer Token (JWT)
              </label>
              <textarea
                id="auth-token-input"
                rows={4}
                value={tokenInput}
                onChange={(e) => {
                  setTokenInput(e.target.value);
                  if (validationMsg) setValidationMsg(null);
                }}
                placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOi..."
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
                  checked={persistToken}
                  onChange={(e) => setPersistToken(e.target.checked)}
                  style={{ accentColor: 'var(--devdoc-accent)' }}
                />
                Remember session on this device
              </label>
            </div>

            <Button
              type="submit"
              variant="primary"
              style={{ width: '100%', padding: '10px' }}
              disabled={isLoading || !tokenInput.trim()}
              icon={<ArrowRight size={14} />}
            >
              {isLoading ? 'Verifying Credentials...' : 'Sign In to Platform'}
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
            Tokens are passed via <code>Authorization: Bearer</code> to verify <code>sub</code> claim against PostgreSQL RLS. Credentials are never logged or stored insecurely.
          </div>
        </Panel>
      </div>
    </div>
  );
};
