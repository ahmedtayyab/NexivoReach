/** Fit score triage badge — 90+ green, 70–89 amber, <70 red. */
export function fitBadgeClass(score: number | null | undefined): string {
  const n = Number(score) || 0;
  if (n >= 90) return 'fit-badge fit-badge--high';
  if (n >= 70) return 'fit-badge fit-badge--mid';
  return 'fit-badge fit-badge--low';
}

export function FitScoreBadge({ score }: { score: number | null | undefined }) {
  const n = Number(score) || 0;
  return (
    <span className={fitBadgeClass(n)} title={`Fit score ${n}`}>
      {n}
    </span>
  );
}
