import { useMemo, useState } from 'react';
import type { AgentRunLog } from '../types';
import type { AuthUser, Prospect } from '../types';
import { brandAssets } from '../lib/brandAssets';
import { computeOutcomes } from '../lib/outcomes';
import OutcomesStrip from './OutcomesStrip';
import PlanUsageCard from './PlanUsageCard';

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

  return (
    <div className="max-w-5xl">
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
          <div className="empty-state__art-wrap">
            <img src={brandAssets.emptyActivity} alt="" className="empty-state__art" loading="lazy" decoding="async" />
          </div>
          <p className="empty-state__title">No runs yet</p>
          <p className="empty-state__desc">Find buyers from Workspace to populate the operational log.</p>
          {onGoLeads && prospects.length > 0 && (
            <button type="button" className="btn btn-secondary mt-3" onClick={onGoLeads}>
              Open Leads
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 nr-enter nr-enter-delay-2 mt-6">
          <div className="lg:col-span-4 bg-panel border border-border rounded-lg p-3 space-y-1 nr-panel">
            <p className="section-label px-2 py-2">Runs ({agentLogs.length})</p>
            <div className="nr-stagger">
              {agentLogs.map(log => {
                const isSelected = log.id === selectedLog?.id;
                return (
                  <button
                    key={log.id}
                    onClick={() => setSelectedRunId(log.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-md transition-all duration-150 ${
                      isSelected ? 'bg-muted' : 'hover:bg-panel/80'
                    }`}
                  >
                    <div className="flex items-center justify-between text-[11px] text-ink-muted">
                      <span>{log.timestamp}</span>
                      <span className="tabular-nums">{(log.durationMs / 1000).toFixed(1)}s</span>
                    </div>
                    <p className="text-[13px] font-medium text-slate-800 mt-1 line-clamp-2">{log.task}</p>
                    <p className="text-[11px] text-ink-muted mt-1">
                      {log.toolsUsed.length} tools · {log.sourcesCount} sources · {log.status}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {selectedLog && (
            <div
              key={selectedLog.id}
              className="lg:col-span-8 bg-panel border border-border rounded-lg p-5 space-y-4 nr-panel nr-pop"
            >
              <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
                <div>
                  <p className="text-[11px] font-mono text-ink-muted">{selectedLog.id}</p>
                  <h3 className="text-[14px] font-semibold text-ink mt-1">{selectedLog.task}</h3>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-[13px] font-medium text-slate-800">{selectedLog.status}</p>
                  <p className="text-[11px] text-ink-muted">{(selectedLog.durationMs / 1000).toFixed(2)}s</p>
                </div>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {selectedLog.toolsUsed.map((tool, idx) => (
                  <span
                    key={idx}
                    className="text-[11px] bg-muted text-ink-secondary border border-border px-2 py-0.5 rounded nr-chip"
                  >
                    {tool}
                  </span>
                ))}
              </div>

              <div className="space-y-3 nr-stagger">
                {selectedLog.decisions.map((dec, idx) => (
                  <div key={idx} className="border border-border rounded-lg p-3.5 space-y-2 nr-panel">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-semibold text-slate-700">Step {dec.step}</span>
                      {dec.toolCalled && (
                        <span className="text-[11px] text-ink-secondary">{dec.toolCalled}</span>
                      )}
                    </div>
                    <p className="text-[13px] text-ink-secondary">
                      <span className="text-ink-muted">Observation · </span>
                      {dec.observation}
                    </p>
                    <p className="text-[13px] text-slate-800">
                      <span className="text-ink-muted">Decision · </span>
                      {dec.decision}
                    </p>
                    {dec.toolResultSnippet && (
                      <p className="text-[12px] text-ink-secondary bg-slate-50 rounded px-2.5 py-2">
                        {dec.toolResultSnippet}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
