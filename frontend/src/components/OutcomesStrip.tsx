import type { PipelineOutcomes } from '../lib/outcomes';

type Props = {
  outcomes: PipelineOutcomes;
  className?: string;
};

const CELLS: { key: keyof PipelineOutcomes; label: string; hint: string }[] = [
  { key: 'total', label: 'Leads', hint: 'In this company' },
  { key: 'withEmail', label: 'With email', hint: 'Ready to send' },
  { key: 'missingEmail', label: 'Need email', hint: 'Find on site' },
  { key: 'contacted', label: 'Contacted', hint: 'Sent or marked' },
  { key: 'replied', label: 'Replied', hint: 'Inbox or logged' },
  { key: 'dueFollowUp', label: 'Follow-up', hint: 'Due now' },
  { key: 'meeting', label: 'Meeting', hint: 'In pipeline' },
  { key: 'won', label: 'Won', hint: 'Closed' },
];

export default function OutcomesStrip({ outcomes, className = '' }: Props) {
  return (
    <div className={`outcomes-strip ${className}`.trim()} aria-label="Pipeline outcomes">
      {CELLS.map(cell => {
        const value = outcomes[cell.key];
        const hot = cell.key === 'dueFollowUp' && value > 0;
        const warn = cell.key === 'missingEmail' && value > 0;
        return (
          <div
            key={cell.key}
            className={`outcomes-strip__cell${hot ? ' is-hot' : ''}${warn ? ' is-warn' : ''}`}
          >
            <span className="outcomes-strip__value tabular-nums">{value}</span>
            <span className="outcomes-strip__label">{cell.label}</span>
            <span className="outcomes-strip__hint">{cell.hint}</span>
          </div>
        );
      })}
    </div>
  );
}
