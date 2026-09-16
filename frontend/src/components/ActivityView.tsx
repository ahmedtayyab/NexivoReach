import { useEffect, useMemo, useState } from 'react';
import type { AgentRunLog } from '../types';
import type { AuthUser, Prospect } from '../types';
import { brandAssets } from '../lib/brandAssets';
import { computeOutcomes } from '../lib/outcomes';
import OutcomesStrip from './OutcomesStrip';
import PlanUsageCard from './PlanUsageCard';
import PageAmbient from './brand/PageAmbient';

interface Props {
  agentLogs: AgentRunLog[];
  prospects?: Prospect[];
  user?: AuthUser | null;
  onAskSupport?: () => void;
  onGoLeads?: () => void;
}

export default function ActivityView({
  agentLogs,
  prospects = [],
  user = null,
  onAskSupport,
  onGoLeads,
}: Props) {
  const [selectedRunId, setSelectedRunId] = useState<string>(agentLogs[0]?.id || '');
  const selectedLog = agentLogs.find(l => l.id === selectedRunId) || agentLogs[0];
  const outcomes = useMemo(() => computeOutcomes(prospects), [prospects]);

  useEffect(() => {
    if (!agentLogs.length) {
      setSelectedRunId('');
      return;
    }
    if (!agentLogs.some(l => l.id === selectedRunId)) {
      setSelectedRunId(agentLogs[0].id);
    }
  }, [agentLogs, selectedRunId]);

  return (
    <div className="activity-desk page-shell">
      {agentLogs.length > 0 && <PageAmbient variant="activity" tone="whisper" />}
      <div className="page-header">
        <h1 className="page-header__title">Activity</h1>
        <p className="page-header__desc">
          Pipeline outcomes for this company, today’s plan usage, and hunt decision traces.
        </p>
      </div>

      <OutcomesStrip outcomes={outcomes} className="mb-4 nr-enter" />
      <PlanUsageCard user={user} compact onAskSupport={onAskSupport} />

      {agentLogs.length === 0 ? (
        <div className="empty-state nr-enter mt-6">
          <img src={brandAssets.emptyActivity} alt="" className="empty-state__art" loading="lazy" decoding="async" />
          <div className="empty-state__content">
            <p className="empty-state__title">No runs yet</p>
            <p className="empty-state__desc">Find buyers from Workspace to populate the operational log.</p>
            {onGoLeads && prospects.length > 0 && (
              <button type="button" className="btn btn-secondary" onClick={onGoLeads}>
                Open Leads
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="activity-layout nr-enter nr-enter-delay-2">
          <aside className="activity-runs" aria-label="Hunt runs">
            <p className="section-label activity-runs__label">Runs ({agentLogs.length})</p>
            <div className="activity-runs__list nr-stagger">
              {agentLogs.map(log => {
                const isSelected = log.id === selectedLog?.id;
                return (
                  <button
                    key={log.id}
                    type="button"
                    onClick={() => setSelectedRunId(log.id)}
                    className={`activity-run${isSelected ? ' is-selected' : ''}`}
                  >
                    <div className="activity-run__meta">
                      <span>{log.timestamp}</span>
                      <span className="tabular-nums">{(log.durationMs / 1000).toFixed(1)}s</span>
                    </div>
                    <p className="activity-run__title">{log.task}</p>
                    <p className="activity-run__foot">
                      {log.toolsUsed.length} tools · {log.sourcesCount} sources · {log.status}
                    </p>
                  </button>
                );
              })}
            </div>
          </aside>

          {selectedLog && (
            <section key={selectedLog.id} className="activity-detail nr-panel nr-pop" aria-label="Run detail">
              <header className="activity-detail__head">
                <div>
                  <p className="activity-detail__id">{selectedLog.id}</p>
                  <h2 className="activity-detail__title">{selectedLog.task}</h2>
                </div>
                <div className="activity-detail__status">
                  <span className={`activity-status is-${(selectedLog.status || '').toLowerCase()}`}>
                    {selectedLog.status}
                  </span>
                  <span className="activity-detail__duration tabular-nums">
                    {(selectedLog.durationMs / 1000).toFixed(2)}s
                  </span>
                </div>
              </header>

              {selectedLog.toolsUsed.length > 0 && (
                <div className="activity-tools">
                  {selectedLog.toolsUsed.map((tool, idx) => (
                    <span key={idx} className="activity-chip">
                      {tool}
                    </span>
                  ))}
                </div>
              )}

              <div className="activity-steps nr-stagger">
                {selectedLog.decisions.map((dec, idx) => (
                  <article key={idx} className="activity-step">
                    <div className="activity-step__head">
                      <span className="activity-step__n">Step {dec.step}</span>
                      {dec.toolCalled && <span className="activity-step__tool">{dec.toolCalled}</span>}
                    </div>
                    <p className="activity-step__line">
                      <span className="activity-step__k">Observation</span>
                      <span className="activity-step__v">{dec.observation}</span>
                    </p>
                    <p className="activity-step__line">
                      <span className="activity-step__k">Decision</span>
                      <span className="activity-step__v activity-step__v--emph">{dec.decision}</span>
                    </p>
                    {dec.toolResultSnippet && (
                      <pre className="activity-step__snippet">{dec.toolResultSnippet}</pre>
                    )}
                  </article>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
