import { useState } from 'react';
import type { AgentRunLog } from '../types';
import { Activity } from 'lucide-react';

interface Props {
  agentLogs: AgentRunLog[];
}

export default function ActivityView({ agentLogs }: Props) {
  const [selectedRunId, setSelectedRunId] = useState<string>(agentLogs[0]?.id || '');
  const selectedLog = agentLogs.find(l => l.id === selectedRunId) || agentLogs[0];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-2">
        <div className="flex items-center space-x-2 text-indigo-400 text-xs font-semibold uppercase tracking-wider">
          <Activity className="w-4 h-4" />
          <span>Step 7: Agent Operational Activity & Audit Log</span>
        </div>
        <h1 className="text-xl font-bold text-white">Inspect Agent Decisions & Tool Traces</h1>
        <p className="text-xs text-slate-300">
          Full operational execution transparency. Review tools invoked, sources inspected, buying signal triggers detected, and execution duration.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left List of Agent Runs */}
        <div className="lg:col-span-4 bg-[#121929] border border-slate-800 rounded-xl p-4 space-y-3">
          <h2 className="text-xs font-semibold text-slate-200 border-b border-slate-800 pb-2">
            Execution Runs ({agentLogs.length})
          </h2>

          <div className="space-y-2">
            {agentLogs.map(log => {
              const isSelected = log.id === selectedRunId;
              return (
                <div
                  key={log.id}
                  onClick={() => setSelectedRunId(log.id)}
                  className={`p-3 rounded-lg border text-xs cursor-pointer transition-all space-y-1 ${
                    isSelected 
                      ? 'bg-indigo-950/60 border-indigo-500/50' 
                      : 'bg-[#0b101c] border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                    <span>{log.timestamp}</span>
                    <span className="text-emerald-400 font-bold">{(log.durationMs / 1000).toFixed(1)}s</span>
                  </div>
                  <p className="font-medium text-slate-200 line-clamp-2">{log.task}</p>
                  <div className="flex items-center space-x-2 text-[10px] text-slate-400 pt-1">
                    <span>{log.toolsUsed.length} Tools</span>
                    <span>•</span>
                    <span>{log.sourcesCount} Sources</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Run Trace Detail */}
        {selectedLog && (
          <div className="lg:col-span-8 bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
              <div>
                <span className="text-[10px] font-mono text-indigo-400 bg-indigo-950 px-2 py-0.5 rounded border border-indigo-800">
                  RUN ID: {selectedLog.id}
                </span>
                <h3 className="font-bold text-white text-sm mt-1">{selectedLog.task}</h3>
              </div>

              <div className="text-right">
                <span className="text-xs text-emerald-400 font-bold font-mono">STATUS: {selectedLog.status}</span>
                <span className="block text-[10px] text-slate-400">Duration: {(selectedLog.durationMs / 1000).toFixed(2)}s</span>
              </div>
            </div>

            {/* Tools Used Badge Pills */}
            <div className="space-y-1.5">
              <span className="text-[11px] text-slate-400 font-medium block">Tools Executed:</span>
              <div className="flex flex-wrap gap-1.5">
                {selectedLog.toolsUsed.map((tool, idx) => (
                  <span key={idx} className="text-[10px] font-mono bg-[#0b101c] text-indigo-300 border border-slate-700 px-2 py-0.5 rounded">
                    {tool}
                  </span>
                ))}
              </div>
            </div>

            {/* Decision Steps Trace */}
            <div className="space-y-3 pt-2">
              <h4 className="text-xs font-semibold text-slate-200">Execution Decision Sequence</h4>
              
              <div className="space-y-3 font-sans">
                {selectedLog.decisions.map((dec, idx) => (
                  <div key={idx} className="bg-[#0b101c] border border-slate-800 rounded-lg p-3.5 space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-blue-400 font-bold">Step {dec.step}</span>
                      {dec.toolCalled && (
                        <span className="font-mono text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
                          Invoked: {dec.toolCalled}
                        </span>
                      )}
                    </div>

                    <div className="space-y-1">
                      <p className="text-slate-300">
                        <strong className="text-slate-400">Observation: </strong>{dec.observation}
                      </p>
                      <p className="text-white font-medium">
                        <strong className="text-slate-400">Decision: </strong>{dec.decision}
                      </p>
                    </div>

                    {dec.toolResultSnippet && (
                      <div className="bg-[#070a12] p-2.5 rounded border border-slate-800 font-mono text-[11px] text-slate-300">
                        <span className="text-slate-500 block mb-0.5">Tool Output Snippet:</span>
                        {dec.toolResultSnippet}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
