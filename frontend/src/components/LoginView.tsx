import BrandLockup from './brand/BrandLockup';

interface Props {
  error?: string | null;
}

export default function LoginView({ error }: Props) {
  return (
    <div className="min-h-dvh flex items-center justify-center px-4 sm:px-6 relative overflow-hidden bg-canvas">
      <img
        src="/brand/login-atmosphere.jpg"
        alt=""
        className="absolute inset-0 w-full h-full object-cover"
      />
      <div className="absolute inset-0 bg-canvas/40" aria-hidden />

      <div className="relative w-full max-w-sm nr-enter">
        <div className="mb-8 flex justify-center nr-enter nr-enter-delay-1">
          <BrandLockup size="md" />
        </div>

        <div className="bg-panel-elevated border border-border rounded-lg p-5 sm:p-6 shadow-sm nr-enter nr-enter-delay-2">
          <h1 className="text-[15px] font-semibold text-ink">Sign in to continue</h1>
          <p className="text-[13px] text-ink-secondary mt-1 mb-6">
            Use your Google account to save your companies, catalogs, and prospect queues — and pick up where you left off.
          </p>

          {error && (
            <p className="text-[13px] text-red-800 bg-red-50 border border-red-200 rounded-md px-3 py-2 mb-4">
              Sign-in failed. Check your Google OAuth settings and try again.
            </p>
          )}

          <a
            href="/api/auth/google"
            className="flex items-center justify-center gap-2.5 w-full px-4 py-2.5 bg-panel border border-border hover:border-ink-muted hover:bg-muted rounded-md text-[13.5px] font-medium text-ink transition-colors"
          >
            <GoogleIcon />
            Continue with Google
          </a>
        </div>

        <p className="text-[12px] text-ink-muted text-center mt-6 px-2">
          Turn products into qualified buyers.
        </p>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}
