import type { Prospect } from '../../types';
import { X, ArrowLeft, ExternalLink, CheckCircle, Mail, Phone } from 'lucide-react';
import { useEffect, useState } from 'react';
import { recipientEmail } from '../../lib/leadTone';

interface Props {
  prospect: Prospect | null;
  onClose: () => void;
  onUpdateStatus: (id: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
  onSaveDraft: (id: string, subject: string, body: string, toEmail?: string) => void;
  onUpdateContactAgain?: (id: string, contactAgain: boolean) => void;
  onSaveReply?: (id: string, summary: string, contactAgain: boolean) => void;
  onSendViaEmail?: (
    id: string,
    overrides?: { subject?: string; body?: string; toEmail?: string },
  ) => void;
  onPrepareOutreach?: (id: string) => void;
  onPrepareFollowUp?: (id: string) => void;
  gmailConnected?: boolean;
}

export default function ReviewDrawer({
  prospect,
  onClose,
  onUpdateStatus,
  onSaveDraft,
  onUpdateContactAgain,
  onSaveReply,
  onSendViaEmail,
  onPrepareOutreach,
  onPrepareFollowUp,
  gmailConnected = false,
}: Props) {
  const [draftBody, setDraftBody] = useState('');
  const [draftSubject, setDraftSubject] = useState('');
  const [draftTo, setDraftTo] = useState('');
  const [replyNote, setReplyNote] = useState('');
  const [draftDirty, setDraftDirty] = useState(false);

  useEffect(() => {
    if (!prospect?.outreachDraft) {
      setDraftBody('');
      setDraftSubject('');
      setDraftTo('');
      setDraftDirty(false);
      return;
    }
    const d = prospect.outreachDraft;
    setDraftSubject(d.subject || '');
    setDraftBody(d.body || '');
    setDraftTo(d.toEmail || recipientEmail(prospect) || '');
    setDraftDirty(false);
    setReplyNote('');
  }, [
    prospect?.id,
    prospect?.outreachDraft?.subject,
    prospect?.outreachDraft?.body,
    prospect?.outreachDraft?.toEmail,
    prospect?.email,
  ]);

  if (!prospect) return null;

  const draft = prospect.outreachDraft;
  const alreadySent = draft?.status === 'Sent' || draft?.status === 'Replied';
  const breakdown = prospect.fitBreakdown;
  const scoreClass =
    prospect.fitScore >= 90 ? 'score-high'
    : prospect.fitScore >= 80 ? 'score-mid'
    : 'score-low';
  const contacts = prospect.contacts || [];

  const persistDraft = () => {
    if (!draft) return;
    onSaveDraft(prospect.id, draftSubject, draftBody, draftTo);
    setDraftDirty(false);
  };

  const openMailto = () => {
    if (!draft) return;
    const params = new URLSearchParams();
    if (draftSubject || draft.subject) params.set('subject', draftSubject || draft.subject);
    if (draftBody || draft.body) params.set('body', draftBody || draft.body);
    const qs = params.toString();
    const to = draftTo.trim() || recipientEmail(prospect);
    const href = to
      ? `mailto:${encodeURIComponent(to)}?${qs}`
      : `mailto:?${qs}`;
    window.open(href, '_blank');
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 drawer-overlay nr-fade" onClick={onClose} />

      <div className="relative w-full max-w-xl bg-panel-elevated border-l border-border h-full overflow-y-auto flex flex-col z-10 sm:max-w-xl nr-drawer-in">
        <div className="sticky top-0 bg-panel-elevated border-b border-border px-3 sm:px-5 py-3 flex items-center justify-between gap-2 z-20">
          <button
            onClick={onClose}
            className="flex items-center space-x-1.5 text-[13px] text-ink-secondary hover:text-ink transition-colors shrink-0"
          >
            <ArrowLeft className="w-4 h-4" strokeWidth={1.75} />
            <span className="hidden xs:inline sm:inline">Back</span>
          </button>

          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap justify-end">
            {!draft && onPrepareOutreach && (
              <button
                type="button"
                onClick={() => onPrepareOutreach(prospect.id)}
                className="px-2.5 sm:px-3.5 py-1.5 border border-border text-[12px] sm:text-[13px] rounded-md nr-btn-press"
              >
                Prepare outreach
              </button>
            )}
            {!alreadySent && draft && (
              <button
                type="button"
                onClick={() => {
                  if (draftDirty) persistDraft();
                  if (onSendViaEmail) {
                    onSendViaEmail(prospect.id, {
                      subject: draftSubject,
                      body: draftBody,
                      toEmail: draftTo,
                    });
                  } else {
                    openMailto();
                    onUpdateStatus(prospect.id, 'Sent');
                  }
                }}
                className="px-2.5 sm:px-3.5 py-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] sm:text-[13px] font-medium rounded-md nr-btn-press"
              >
                {gmailConnected ? 'Approve & send' : 'Approve & open email'}
              </button>
            )}
            {alreadySent && onPrepareFollowUp && (
              <button
                type="button"
                onClick={() => onPrepareFollowUp(prospect.id)}
                className="px-2.5 sm:px-3.5 py-1.5 border border-border text-[12px] sm:text-[13px] rounded-md nr-btn-press"
              >
                Draft follow-up
              </button>
            )}
            {alreadySent && (
              <span className="text-[13px] text-green-700 font-medium flex items-center space-x-1">
                <CheckCircle className="w-4 h-4" strokeWidth={1.75} />
                <span>{draft?.status === 'Replied' ? 'Replied' : 'Sent'}</span>
              </span>
            )}
            <button
              onClick={onClose}
              className="p-1 text-ink-muted hover:text-ink transition-colors"
              aria-label="Close"
            >
              <X className="w-4 h-4" strokeWidth={1.75} />
            </button>
          </div>
        </div>

        <div className="px-5 pt-5 pb-5 border-b border-border-subtle">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-[15px] font-semibold text-ink">{prospect.companyName}</h1>
              <p className="text-[13px] text-ink-muted mt-0.5">
                {[prospect.location?.trim() || 'Location not confirmed', prospect.industry].filter(Boolean).join(' · ')}
              </p>
            </div>
            <div className="text-right shrink-0">
              <span className={`text-base font-bold tabular-nums ${scoreClass}`}>{prospect.fitScore}</span>
              <p className="text-[11px] text-ink-muted mt-0.5">Fit (not intent)</p>
            </div>
          </div>
          {prospect.website && (
            <a
              href={prospect.website}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center space-x-1 text-[12px] text-accent hover:underline mt-2"
            >
              <span>{prospect.website}</span>
              <ExternalLink className="w-3 h-3" strokeWidth={1.75} />
            </a>
          )}
        </div>

        <div className="px-5 py-6 space-y-9 flex-1">
          <section>
            <h2 className="section-label mb-2.5">Location</h2>
            <div className="h-px bg-muted mb-4" />
            <p className="text-[13.5px] text-ink-secondary leading-relaxed">
              {prospect.location?.trim() || 'Not confirmed from public pages yet — verify before outreach.'}
            </p>
          </section>

          <section>
            <h2 className="section-label mb-2.5">Contacts</h2>
            <div className="h-px bg-muted mb-4" />
            {(() => {
              const seen = new Set<string>();
              const emails: string[] = [];
              const phones: string[] = [];
              const pages: { value: string; label?: string }[] = [];
              const pushEmail = (v?: string) => {
                const e = (v || '').trim().toLowerCase();
                if (!e || seen.has(`e:${e}`)) return;
                seen.add(`e:${e}`);
                emails.push(e);
              };
              const pushPhone = (v?: string) => {
                const p = (v || '').trim();
                if (!p || seen.has(`p:${p}`)) return;
                seen.add(`p:${p}`);
                phones.push(p);
              };
              pushEmail(prospect.email);
              pushPhone(prospect.phone);
              for (const c of contacts) {
                if (c.type === 'email') pushEmail(c.value);
                else if (c.type === 'phone') pushPhone(c.value);
                else if (c.type === 'url' && c.value && !seen.has(`u:${c.value}`)) {
                  seen.add(`u:${c.value}`);
                  pages.push({ value: c.value, label: c.label });
                }
              }
              if (!emails.length && !phones.length && !pages.length) {
                return (
                  <p className="text-[13px] text-ink-muted">
                    No public email on this company&apos;s site (homepage and contact pages were checked automatically).
                  </p>
                );
              }
              return (
                <div className="space-y-2.5 text-[13px]">
                  {emails.map(e => (
                    <a key={e} href={`mailto:${e}`} className="flex items-center gap-2 text-accent hover:underline">
                      <Mail className="w-3.5 h-3.5 shrink-0" strokeWidth={1.75} />
                      <span className="break-all">{e}</span>
                    </a>
                  ))}
                  {phones.map(p => (
                    <a key={p} href={`tel:${p}`} className="flex items-center gap-2 text-ink-secondary">
                      <Phone className="w-3.5 h-3.5 shrink-0" strokeWidth={1.75} />
                      {p}
                    </a>
                  ))}
                  {pages.slice(0, 3).map((c, i) => (
                    <a
                      key={`${c.value}-${i}`}
                      href={c.value}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 text-[12px] text-accent hover:underline"
                    >
                      {c.label || 'Contact page'}
                      <ExternalLink className="w-3 h-3" strokeWidth={1.5} />
                    </a>
                  ))}
                </div>
              );
            })()}
            <label className="mt-4 flex items-center gap-2 text-[13px] text-ink-secondary">
              <input
                type="checkbox"
                checked={prospect.contactAgain !== false}
                onChange={e => onUpdateContactAgain?.(prospect.id, e.target.checked)}
                className="rounded border-border"
              />
              Contact again (follow-up allowed)
            </label>
          </section>

          <section>
            <h2 className="section-label mb-2.5">Qualification</h2>
            <div className="h-px bg-muted mb-4" />
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[13px]">
              <LevelRow label="ICP fit" value={prospect.icpFit || breakdown?.icpFit} />
              <LevelRow label="Offer fit" value={prospect.offerFit || breakdown?.offerFit} />
              <LevelRow label="Motion fit" value={prospect.motionFit || breakdown?.motionFit} />
              <LevelRow label="Intent" value={prospect.intent || breakdown?.intent || 'none'} />
            </div>
            {prospect.priority && (
              <p className="text-[12px] text-ink-muted mt-3">Priority: {prospect.priority}</p>
            )}
          </section>

          <section>
            <h2 className="section-label mb-2.5">Why this prospect?</h2>
            <div className="h-px bg-muted mb-4" />
            <p className="text-[13.5px] text-ink-secondary leading-relaxed">
              {prospect.whyThisProspect}
            </p>
            {(prospect.evidence || prospect.fitBreakdown?.evidence || [])
              .filter(e => e.claim !== 'intent')
              .slice(0, 4)
              .map((e, i) => (
                <p key={i} className="source-quote mt-3">{e.quote || e.statement}</p>
              ))}
          </section>

          <section>
            <h2 className="section-label mb-2.5">Why now?</h2>
            <div className="h-px bg-muted mb-4" />
            <p className="text-[13.5px] text-ink-secondary leading-relaxed">
              {prospect.whyNow || breakdown?.whyNow || 'No timing evidence.'}
            </p>
            {(prospect.buyingSignals || []).map((sig, i) => (
              <div key={i} className="mt-4">
                <p className="text-[13px] font-medium text-ink-secondary">{sig.signal}</p>
                <p className="source-quote mt-1.5">{sig.sourceExcerpt || sig.whyItMatters}</p>
              </div>
            ))}
          </section>

          <section>
            <h2 className="section-label mb-2.5">Product Match</h2>
            <div className="h-px bg-muted mb-4" />
            <div className="space-y-4">
              {(prospect.productFit || []).map((item, i) => (
                <div key={i} className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[13.5px] font-medium text-ink-secondary">{i + 1}. {item.productName}</p>
                    <p className="text-[12px] text-ink-muted mt-1">{item.reasoning}</p>
                  </div>
                  <span className={`text-[12px] font-semibold shrink-0 mt-0.5 ${
                    item.fitLevel === 'High' ? 'text-green-700' : 'text-ink-muted'
                  }`}>
                    {item.fitLevel}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {draft && (
            <section>
              <div className="flex items-center justify-between mb-2.5 gap-3">
                <h2 className="section-label">Draft Outreach</h2>
                {!alreadySent && draftDirty && (
                  <button
                    type="button"
                    onClick={persistDraft}
                    className="px-2.5 py-1 text-[12px] bg-ink text-white rounded-md nr-btn-press"
                  >
                    Save changes
                  </button>
                )}
              </div>
              <div className="h-px bg-muted mb-4" />

              <div className="space-y-4">
                <div>
                  <label className="field-label" htmlFor={`review-to-${prospect.id}`}>To</label>
                  <input
                    id={`review-to-${prospect.id}`}
                    type="email"
                    value={draftTo}
                    disabled={alreadySent}
                    onChange={e => {
                      setDraftTo(e.target.value);
                      setDraftDirty(true);
                    }}
                    onBlur={() => {
                      if (draftDirty && !alreadySent) persistDraft();
                    }}
                    placeholder="buyer@company.com"
                    className="w-full border border-border rounded-md px-3 py-2.5 text-[13px] text-ink-secondary bg-panel disabled:opacity-60"
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor={`review-subject-${prospect.id}`}>Subject</label>
                  <input
                    id={`review-subject-${prospect.id}`}
                    value={draftSubject}
                    disabled={alreadySent}
                    onChange={e => {
                      setDraftSubject(e.target.value);
                      setDraftDirty(true);
                    }}
                    onBlur={() => {
                      if (draftDirty && !alreadySent) persistDraft();
                    }}
                    placeholder="Subject line…"
                    className="w-full border border-border rounded-md px-3 py-2.5 text-[13px] text-ink-secondary bg-panel disabled:opacity-60"
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor={`review-body-${prospect.id}`}>Body</label>
                  <textarea
                    id={`review-body-${prospect.id}`}
                    value={draftBody}
                    disabled={alreadySent}
                    onChange={e => {
                      setDraftBody(e.target.value);
                      setDraftDirty(true);
                    }}
                    onBlur={() => {
                      if (draftDirty && !alreadySent) persistDraft();
                    }}
                    rows={10}
                    className="w-full border border-border rounded-md px-3 py-2.5 text-[13px] text-ink-secondary resize-y min-h-[12rem] bg-panel disabled:opacity-60 leading-relaxed"
                  />
                </div>

                {draft.outreachRationale ? (
                  <div className="text-[12px] text-ink-muted border-t border-border-subtle pt-4 space-y-1.5">
                    <p className="font-medium text-ink-secondary">Outreach rationale</p>
                    {draft.outreachRationale.primary_signal && (
                      <p><span className="text-ink-muted">Signal:</span> {draft.outreachRationale.primary_signal}</p>
                    )}
                    {draft.outreachRationale.pain_hypothesis && (
                      <p><span className="text-ink-muted">Pain hypothesis:</span> {draft.outreachRationale.pain_hypothesis}</p>
                    )}
                    {draft.outreachRationale.matched_product && (
                      <p><span className="text-ink-muted">Matched product:</span> {draft.outreachRationale.matched_product}</p>
                    )}
                    <p>
                      {draft.outreachRationale.angle && (
                        <><span className="text-ink-muted">Approach:</span> {draft.outreachRationale.angle}</>
                      )}
                      {draft.outreachRationale.signal_confidence && (
                        <>
                          {draft.outreachRationale.angle ? ' · ' : null}
                          <span className="text-ink-muted">Confidence:</span> {draft.outreachRationale.signal_confidence}
                        </>
                      )}
                    </p>
                  </div>
                ) : draft.personalizedReason ? (
                  <p className="text-[12px] text-ink-muted border-t border-border-subtle pt-4">
                    Personalized using: {draft.personalizedReason}
                  </p>
                ) : null}
              </div>
            </section>
          )}

          <section>
            <h2 className="section-label mb-2.5">Reply / follow-up</h2>
            <div className="h-px bg-muted mb-4" />
            {prospect.replySummary && (
              <p className="text-[13px] text-ink-secondary mb-3">{prospect.replySummary}</p>
            )}
            {prospect.lastReplyAt && (
              <p className="text-[12px] text-ink-muted mb-3">Logged {prospect.lastReplyAt}</p>
            )}
            <textarea
              value={replyNote}
              onChange={e => setReplyNote(e.target.value)}
              rows={3}
              placeholder="Paste or summarize their reply…"
              className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary resize-none"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!replyNote.trim() || !onSaveReply}
                onClick={() => {
                  onSaveReply?.(prospect.id, replyNote.trim(), true);
                  setReplyNote('');
                }}
                className="px-3 py-1.5 text-[12px] bg-panel border border-border rounded-md hover:border-ink-muted disabled:opacity-40"
              >
                Log reply · re-contact
              </button>
              <button
                type="button"
                disabled={!replyNote.trim() || !onSaveReply}
                onClick={() => {
                  onSaveReply?.(prospect.id, replyNote.trim(), false);
                  setReplyNote('');
                }}
                className="px-3 py-1.5 text-[12px] bg-panel border border-border rounded-md hover:border-ink-muted disabled:opacity-40"
              >
                Log reply · do not contact
              </button>
              {onPrepareFollowUp && (prospect.replySummary || alreadySent) && (
                <button
                  type="button"
                  onClick={() => onPrepareFollowUp(prospect.id)}
                  className="px-3 py-1.5 text-[12px] bg-accent text-white font-medium rounded-md nr-btn-press"
                >
                  Draft follow-up email
                </button>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function LevelRow({ label, value }: { label: string; value?: string }) {
  const display = (value || 'unknown').toLowerCase();
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-muted">{label}</span>
      <span className="text-ink-secondary font-medium capitalize">{display}</span>
    </div>
  );
}
