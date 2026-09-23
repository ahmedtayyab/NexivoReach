import type { Prospect } from '../../types';
import { Printer } from 'lucide-react';
import { recipientEmail } from '../../lib/leadTone';

/** Printable one-pager: why this buyer, evidence, catalog match, suggested angle. */
export default function LeadBrief({ prospect }: { prospect: Prospect }) {
  const bd = prospect.fitBreakdown || ({} as Prospect['fitBreakdown']);
  const evidence = (prospect.evidence || bd.evidence || [])
    .filter(e => e.claim !== 'intent')
    .slice(0, 5);
  const products = (prospect.productFit || []).slice(0, 4);
  const approach = (prospect.recommendedApproach || '').trim();
  const angle = prospect.outreachDraft?.outreachRationale?.angle
    || prospect.outreachDraft?.outreachRationale?.value_proposition
    || '';
  const matched = prospect.outreachDraft?.outreachRationale?.matched_product
    || products[0]?.productName
    || '';
  const bestTo = recipientEmail(prospect) || prospect.email || '';
  const why = (prospect.whyThisProspect || '').trim();
  const whyNow = (prospect.whyNow || bd.whyNow || '').trim();

  const printBrief = () => {
    window.print();
  };

  return (
    <section className="lead-brief" id="lead-brief-print">
      <div className="lead-brief__head">
        <h2 className="section-label">Lead brief</h2>
        <button type="button" className="btn btn-ghost lead-brief__print" onClick={printBrief}>
          <Printer className="w-3.5 h-3.5" />
          Print brief
        </button>
      </div>
      <div className="h-px bg-muted mb-4" />

      <div className="lead-brief__meta">
        <p className="lead-brief__company">{prospect.companyName}</p>
        <p className="text-[12.5px] text-ink-muted">
          {[prospect.website, prospect.location, prospect.industry].filter(Boolean).join(' · ')}
        </p>
        <p className="text-[12.5px] text-ink-secondary mt-1.5">
          Fit {prospect.fitScore}
          {prospect.intent || bd.intent ? ` · Intent ${prospect.intent || bd.intent}` : ''}
          {prospect.priority ? ` · ${prospect.priority}` : ''}
          {bestTo ? ` · To ${bestTo}` : ''}
          {prospect.phone ? ` · ${prospect.phone}` : ''}
        </p>
      </div>

      {why && (
        <div className="lead-brief__block">
          <p className="lead-brief__label">Why this buyer</p>
          <p className="text-[13px] text-ink-secondary leading-relaxed">{why}</p>
        </div>
      )}

      {whyNow && whyNow !== 'No timing evidence.' && (
        <div className="lead-brief__block">
          <p className="lead-brief__label">Why now</p>
          <p className="text-[13px] text-ink-secondary leading-relaxed">{whyNow}</p>
        </div>
      )}

      {products.length > 0 && (
        <div className="lead-brief__block">
          <p className="lead-brief__label">Catalog match</p>
          <ul className="lead-brief__list">
            {products.map((p, i) => (
              <li key={i}>
                <strong>{p.productName}</strong>
                <span className="text-ink-muted"> · {p.fitLevel}</span>
                {p.reasoning ? <span className="block text-[12.5px] text-ink-muted mt-0.5">{p.reasoning}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      {evidence.length > 0 && (
        <div className="lead-brief__block">
          <p className="lead-brief__label">Evidence</p>
          {evidence.map((e, i) => (
            <p key={i} className="source-quote mt-2">{e.quote || e.statement}</p>
          ))}
        </div>
      )}

      {(approach || angle || matched) && (
        <div className="lead-brief__block">
          <p className="lead-brief__label">Suggested angle</p>
          {matched && (
            <p className="text-[12.5px] text-ink-muted mb-1">Matched product: {matched}</p>
          )}
          <p className="text-[13px] text-ink-secondary leading-relaxed">
            {angle || approach || 'Prepare outreach to generate a specific pitch.'}
          </p>
        </div>
      )}
    </section>
  );
}
