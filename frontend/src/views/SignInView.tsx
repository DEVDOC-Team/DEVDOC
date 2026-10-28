import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { listOAuthProviders } from '../api/auth';
import type { OAuthProviderInfo } from '../api/types';
import { Panel } from '../components/ui/Panel';
import { Button } from '../components/ui/Button';
import { StatusPulse } from '../components/ui/StatusPulse';
import { KeyRound, ShieldAlert, ArrowRight, Lock, Mail, ChevronDown, ChevronRight } from 'lucide-react';

interface SignInViewProps {
  onSuccess?: () => void;
}

const GoogleIcon: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path
      fill="#4285F4"
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
    />
    <path
      fill="#34A853"
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
    />
    <path
      fill="#FBBC05"
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
    />
    <path
      fill="#EA4335"
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
    />
  </svg>
);

const GitHubIcon: React.FC<{ size?: number }> = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
    />
  </svg>
);

export const SignInView: React.FC<SignInViewProps> = ({ onSuccess }) => {
  const { signInWithCredentials, signInWithToken, signInWithOAuth, status, error, clearError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [persistSession, setPersistSession] = useState(true);
  const [validationMsg, setValidationMsg] = useState<string | null>(null);
  const [oauthLoadingProvider, setOauthLoadingProvider] = useState<'google' | 'github' | null>(null);
  const [providers, setProviders] = useState<OAuthProviderInfo[]>([
    { id: 'google', name: 'Google', enabled: true },
    { id: 'github', name: 'GitHub', enabled: true },
  ]);

  useEffect(() => {
    let active = true;
    listOAuthProviders()
      .then((data) => {
        if (active && Array.isArray(data) && data.length > 0) {
          setProviders(data);
        }
      })
      .catch(() => {
        // Fall back gracefully to standard providers without setting an error notice
      });
    return () => {
      active = false;
    };
  }, []);

  const googleEnabled = providers.find((p) => p.id === 'google')?.enabled ?? true;
  const githubEnabled = providers.find((p) => p.id === 'github')?.enabled ?? true;

  // Advanced direct token mode
  const [showDirectToken, setShowDirectToken] = useState(false);
  const [tokenInput, setTokenInput] = useState('');

  const handleOAuthSignIn = async (provider: 'google' | 'github') => {
    clearError();
    setValidationMsg(null);
    setOauthLoadingProvider(provider);
    const res = await signInWithOAuth(provider, persistSession);
    if (!res.success) {
      setOauthLoadingProvider(null);
    }
  };

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

  const isLoading = status === 'loading' || oauthLoadingProvider !== null;

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
            Authenticate with Google, GitHub, or your registered account to manage projects and run investigations.
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
                <strong>Authentication Notice:</strong>
                <div style={{ marginTop: '2px', wordBreak: 'break-word' }}>
                  {error || validationMsg}
                </div>
              </div>
            </div>
          )}

          {/* OAuth Provider Buttons */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '9px', marginBottom: '18px' }}>
            {googleEnabled && (
              <button
                id="oauth-google-button"
                type="button"
                onClick={() => handleOAuthSignIn('google')}
                disabled={isLoading}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  background: 'var(--devdoc-surface)',
                  border: '1px solid var(--devdoc-border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--devdoc-fg)',
                  fontSize: '13px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  cursor: isLoading ? 'not-allowed' : 'pointer',
                  opacity: isLoading && oauthLoadingProvider !== 'google' ? 0.6 : 1,
                  transition: 'background 0.15s ease, border-color 0.15s ease',
                }}
              >
                <GoogleIcon size={16} />
                <span>{oauthLoadingProvider === 'google' ? 'Connecting to Google...' : 'Continue with Google'}</span>
              </button>
            )}

            {githubEnabled && (
              <button
                id="oauth-github-button"
                type="button"
                onClick={() => handleOAuthSignIn('github')}
                disabled={isLoading}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  background: 'var(--devdoc-surface)',
                  border: '1px solid var(--devdoc-border)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--devdoc-fg)',
                  fontSize: '13px',
                  fontWeight: 500,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  cursor: isLoading ? 'not-allowed' : 'pointer',
                  opacity: isLoading && oauthLoadingProvider !== 'github' ? 0.6 : 1,
                  transition: 'background 0.15s ease, border-color 0.15s ease',
                }}
              >
                <GitHubIcon size={16} />
                <span>{oauthLoadingProvider === 'github' ? 'Connecting to GitHub...' : 'Continue with GitHub'}</span>
              </button>
            )}
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              marginBottom: '18px',
              color: 'var(--devdoc-fg-dim)',
            }}
          >
            <div style={{ flex: 1, height: '1px', background: 'var(--devdoc-border-subtle)' }} />
            <span
              style={{
                fontSize: '10px',
                fontFamily: 'var(--font-display)',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: 'var(--devdoc-fg-muted)',
              }}
            >
              or continue with email
            </span>
            <div style={{ flex: 1, height: '1px', background: 'var(--devdoc-border-subtle)' }} />
          </div>

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
            <div style={{ marginTop: '4px', color: 'var(--devdoc-fg-dim)' }}>
              Note: GitHub Sign-In authenticates your DEVDOC user identity. GitHub repository analysis access is managed and authorized independently per-project.
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
};
