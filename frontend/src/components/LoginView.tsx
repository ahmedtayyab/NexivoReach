import BrandLockup from './brand/BrandLockup';

interface Props {
  error?: string | null;
}

export default function LoginView({ error }: Props) {
  return (
    <div className="min-h-dvh flex items-center justify-center px-4 sm:px-6 relative overflow-hidden">
      <img
        src="/brand/login-atmosphere.jpg"
        alt=""
        className="absolute inset-0 w-full h-full object-cover"
      />
      <div className="absolute inset-0 bg-canvas/55" aria-hidden />

      <div className="relative w-full max-w-md nr-enter">
        <div className="mb-10 flex justify-center nr-enter nr-enter-delay-1">
          <BrandLockup size="lg" className="scale-110 origin-center" />
        </div>

        <div className="nr-enter nr-enter-delay-2">
          <h1 className="font-display text-[1.75rem] sm:text-[2rem] font-bold text-ink leading-tight tracking-tight">
            Sign in
          </h1>
          <p className="text-[14px] text-ink-secondary mt-2 mb-7 leading-relaxed max-w-sm">
            Continue with Google to save companies, catalogs, and prospect queues.
          </p>

          {error && (
            <p className="ui-banner ui-banner--warn mb-4" role="alert">
              Sign-in failed. Check your Google OAuth settings and try again.
            </p>
          )}

          <a
            href="/api/auth/google"
            className="btn btn-primary w-full max-w-sm py-3 text-[14px]"
          >
            <GoogleIcon />
            Continue with Google
          </a>
        </div>

        <p className="text-[12px] text-ink-muted mt-10">
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
