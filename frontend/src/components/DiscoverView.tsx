import { useState } from 'react';
import type { BusinessInfo, IdealCustomerProfile, Prospect, AgentRunLog } from '../types';
import { Loader2 } from 'lucide-react';

interface Props {
  businessInfo: BusinessInfo;
  icp: IdealCustomerProfile;
  onAddProspect: (prospect: Prospect) => void;
  onAddLog: (log: AgentRunLog) => void;
}

export default function DiscoverView({ onAddProspect, onAddLog }: Props) {
  const [query, setQuery] = useState(
    'Find commercial gyms expanding in the GCC region needing heavy-duty strength equipment.'
  );
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [runHistory, setRunHistory] = useState<
    Array<{ id: string; startedAt: Date; foundCount: number; durationSec: number }>
  >([
    { id: 'run-1', startedAt: new Date(Date.now() - 7200000), foundCount: 3, durationSec: 118 },
    { id: 'run-2', startedAt: new Date(Date.now() - 86400000 * 1.4), foundCount: 1, durationSec: 74 },
  ]);

  const handleRun = () => {
    if (!query.trim() || isRunning) return;
    setIsRunning(true);
    setStatusText('Scanning GCC market...');

    const runId = `run-${Date.now()}`;
    const startedAt = new Date();

    setTimeout(() => setStatusText('Reading company sites & press releases...'), 2000);
    setTimeout(() => setStatusText('Matching catalog items against facility specs...'), 4000);

    setTimeout(() => {
      const newProspect: Prospect = {
        id: `prospect-urban-${Date.now()}`,
        companyName: 'Urban Strength Gym Dubai',
        website: 'https://urbanstrength-dubai.example.com',
        location: 'Al Quoz, Dubai, UAE',
        industry: 'Commercial Fitness Club',
        companySize: '20–50 Employees',
        fitScore: 92,
        fitBreakdown: { industryFit: 25, locationFit: 20, productMatch: 19, buyingSignals: 18, companyFit: 10 },
        whyThisProspect:
          'Urban Strength is signing a lease for a 5,000 sq ft expansion zone in Al Quoz and is actively hiring a head strength coach. Their current equipment list shows only cardio machines — no strength rack inventory. They are the ideal first outreach for commercial power racks.',
        buyingSignals: [
          {
            signal: 'Al Quoz Facility Expansion (5,000 sq ft)',
            whyItMatters: 'New floor space requires immediate heavy equipment procurement.',
            sourceUrl: 'https://urbanstrength-dubai.example.com/expansion',
            sourceExcerpt: 'Adding 5,000 sq ft of dedicated strength equipment in our Al Quoz location opening Q4.',
          },
        ],
        productFit: [
          { productName: 'Apex Force Power Rack', fitLevel: 'High', reasoning: 'Anchor equipment for functional strength floor plan.' },
          { productName: 'Urethane Dumbbell Set (2.5–50 kg)', fitLevel: 'High', reasoning: 'Replaces rubber hex dumbbells in expanded area.' },
        ],
        recommendedApproach: 'Lead with Al Quoz expansion. Offer factory-direct GCC pricing with 14-day delivery.',
        outreachDraft: {
          id: `out-${Date.now()}`,
          subject: 'Power racks for Urban Strength Al Quoz expansion',
          body: `Hi Alex,\n\nSaw the news about Urban Strength's 5,000 sq ft expansion in Al Quoz — congrats on scaling.\n\nWe manufacture 11-gauge commercial power racks and urethane dumbbells directly for GCC strength clubs. We can ship custom-branded equipment to Dubai in 14 days at factory pricing.\n\nWould you be open to a quick call this week?\n\nBest,\nApex Fitness Equipment`,
          personalizedReason: "Urban Strength Al Quoz 5,000 sq ft expansion announcement.",
          status: 'Draft',
          createdAt: new Date().toISOString(),
        },
        stage: 'Researched',
        discoveredAt: new Date().toISOString(),
        agentTimeline: [],
      };

      const newLog: AgentRunLog = {
        id: runId,
        timestamp: startedAt.toISOString().replace('T', ' ').substring(0, 19),
        task: query,
        durationMs: 6000,
        toolsUsed: ['WebSearchTool', 'SiteScraperTool', 'ProductMatcherTool', 'ScoreCalculatorTool'],
        sourcesCount: 7,
        status: 'Completed',
        decisions: [],
      };

      onAddProspect(newProspect);
      onAddLog(newLog);

      setRunHistory(prev => [
        { id: runId, startedAt, foundCount: 1, durationSec: 6 },
        ...prev,
      ]);
      setIsRunning(false);
      setStatusText('');
    }, 6000);
  };

  const lastRun = runHistory[0];

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-slate-900">Discover</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Describe the type of buyer you are looking for. Results appear in your Queue.
        </p>
      </div>

      {/* Prompt area */}
      <div className="border border-slate-200 rounded-md p-4 space-y-3">
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          disabled={isRunning}
          rows={3}
          placeholder="Find commercial fitness centers expanding in the GCC region..."
          className="w-full text-sm text-slate-800 placeholder-slate-400 resize-none focus:outline-none border-none p-0 bg-transparent"
        />
        <div className="flex items-center justify-between pt-2 border-t border-slate-100">
          {isRunning ? (
            <span className="flex items-center space-x-2 text-sm text-slate-500">
              <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.75} />
              <span>{statusText}</span>
            </span>
          ) : (
            <span className="text-xs text-slate-400">
              {lastRun
                ? `Last run ${formatRelative(lastRun.startedAt)}`
                : 'No runs yet'}
            </span>
          )}
          <button
            onClick={handleRun}
            disabled={isRunning || !query.trim()}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-medium rounded-md transition-colors"
          >
            {isRunning ? 'Running...' : 'Run Scan'}
          </button>
        </div>
      </div>

      {/* Run history */}
      {runHistory.length > 0 && (
        <div className="mt-8">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-widest mb-3">Recent Runs</p>
          <div className="divide-y divide-slate-100">
            {runHistory.map(run => (
              <div key={run.id} className="py-2.5 flex items-center justify-between text-sm">
                <div>
                  <span className="text-slate-700">
                    {run.startedAt.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}
                    {' '}
                    {run.startedAt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span className="text-slate-400 ml-2">
                    · Found {run.foundCount} prospect{run.foundCount !== 1 ? 's' : ''}
                  </span>
                </div>
                <span className="text-slate-400 text-xs tabular-nums">
                  {run.durationSec < 60 ? `${run.durationSec}s` : `${Math.round(run.durationSec / 60)}m`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatRelative(date: Date): string {
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
