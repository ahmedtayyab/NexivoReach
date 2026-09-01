import { useState } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog } from '../types';
import { 
  Search, 
  Sparkles, 
  CheckCircle2, 
  ArrowRight,
  Loader2
} from 'lucide-react';

interface Props {
  businessInfo: BusinessInfo;
  products: Product[];
  icp: IdealCustomerProfile;
  onAddProspect: (prospect: Prospect) => void;
  onAddLog: (log: AgentRunLog) => void;
  onViewProspect: (id: string) => void;
}

export default function DiscoveryView({ 
  onAddProspect, 
  onAddLog, 
  onViewProspect 
}: Props) {
  const [userQuery, setUserQuery] = useState<string>(
    'Find commercial fitness centers expanding in Dubai and Riyadh needing heavy-duty strength equipment.'
  );

  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [statusText, setStatusText] = useState<string>('');
  const [discoveredProspect, setDiscoveredProspect] = useState<Prospect | null>(null);

  const handleStartAgentRun = () => {
    setIsRunning(true);
    setDiscoveredProspect(null);
    setStatusText('Searching GCC commercial fitness news & expansion press releases...');

    setTimeout(() => {
      setStatusText('Scraping public company web pages & detecting buying signals...');
    }, 2000);

    setTimeout(() => {
      setStatusText('Matching catalog items against expansion floor plans...');
    }, 4000);

    setTimeout(() => {
      const newProspectObj: Prospect = {
        id: `prospect-urban-${Date.now()}`,
        companyName: 'Urban Strength Gym Dubai',
        website: 'https://urbanstrength-dubai.example.com',
        location: 'Al Quoz, Dubai, UAE',
        industry: 'Commercial Fitness Club',
        companySize: '20-50 Employees (2 Locations)',
        fitScore: 92,
        fitBreakdown: {
          industryFit: 25,
          locationFit: 20,
          productMatch: 19,
          buyingSignals: 18,
          companyFit: 10,
        },
        whyThisProspect: 'Urban Strength operates a high-traffic functional performance club in Al Quoz and recently signed a lease for a 5,000 sq ft expansion zone, requiring heavy-duty power racks and free weights.',
        buyingSignals: [
          {
            signal: 'Al Quoz Facility 5,000 sq ft Expansion',
            whyItMatters: 'Requires immediate equipment outfitting for functional strength floor plan.',
            sourceUrl: 'https://urbanstrength-dubai.example.com/expansion',
            sourceExcerpt: 'Adding 5,000 sq ft of dedicated strength equipment area in our Al Quoz location opening Q4.'
          }
        ],
        productFit: [
          { productName: 'Commercial Heavy-Duty Power Rack', fitLevel: 'High', reasoning: 'Ideal anchor equipment for functional strength expansion floor.' },
          { productName: 'Urethane Dumbbell Set (2.5kg - 50kg)', fitLevel: 'High', reasoning: 'Replacing older rubber hex dumbbells for expanded area.' }
        ],
        recommendedApproach: 'Offer factory direct Sialkot pricing on power racks with quick 14-day GCC shipping.',
        outreachDraft: {
          id: `out-urban-${Date.now()}`,
          subject: 'Power Racks & Free Weights for Urban Strength Al Quoz Expansion',
          body: `Hi Alex,

Saw the announcement regarding Urban Strength's 5,000 sq ft expansion in Al Quoz — congratulations on scaling the facility!

We manufacture 11-gauge commercial power racks and CPU urethane dumbbells directly for GCC strength clubs. We can deliver custom branded equipment to Dubai within 14 days at direct factory pricing.

Would you be open to seeing a specs sheet for your new expansion floor plan?

Best regards,
Apex Sales Team`,
          personalizedReason: 'Personalized using Urban Strength\'s Al Quoz 5,000 sq ft facility expansion announcement.',
          status: 'Draft',
          createdAt: new Date().toISOString()
        },
        stage: 'Researched',
        discoveredAt: new Date().toISOString(),
        agentTimeline: [
          { time: 'Just now', action: 'Discovered company via UAE commercial strength search' },
          { time: 'Just now', action: 'Scraped website & extracted 5,000 sq ft expansion signal' },
          { time: 'Just now', action: 'Matched 2 high-fit products' },
          { time: 'Just now', action: 'Calculated 92% fit score' },
          { time: 'Just now', action: 'Generated personalized outreach draft' }
        ]
      };

      setDiscoveredProspect(newProspectObj);
      onAddProspect(newProspectObj);

      onAddLog({
        id: `run-${Date.now()}`,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        task: userQuery,
        durationMs: 5500,
        toolsUsed: ['WebSearchTool', 'SiteScraperTool', 'SignalDetectorTool', 'ProductMatcherTool', 'ScoreCalculatorTool'],
        sourcesCount: 8,
        status: 'Completed',
        decisions: []
      });

      setIsRunning(false);
      setStatusText('');
    }, 6000);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 font-sans text-slate-100">
      <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-6 space-y-2">
        <h1 className="text-lg font-bold text-white tracking-tight">Autonomous Prospecting Search</h1>
        <p className="text-xs text-slate-400">
          Enter a high-level buyer search prompt. NexivoReach scans public web sources, press releases, and buying signals to match against catalog items.
        </p>
      </div>

      {/* Query Bar */}
      <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-5 space-y-4">
        <label className="block text-xs font-semibold text-slate-300">Prospecting Goal Prompt</label>
        <div className="flex flex-col sm:flex-row items-center gap-3">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
            <input
              type="text"
              value={userQuery}
              onChange={(e) => setUserQuery(e.target.value)}
              placeholder="e.g. Find commercial fitness centers expanding in Dubai..."
              disabled={isRunning}
              className="w-full bg-[#090d16] border border-slate-800 rounded-md pl-9 pr-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-slate-700"
            />
          </div>
          <button
            onClick={handleStartAgentRun}
            disabled={isRunning || !userQuery.trim()}
            className="w-full sm:w-auto px-6 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold rounded-md flex items-center justify-center space-x-2 transition-all whitespace-nowrap shadow-sm"
          >
            <Sparkles className="w-4 h-4" />
            <span>{isRunning ? 'Searching Market...' : 'Run Prospecting Search'}</span>
          </button>
        </div>

        {isRunning && (
          <div className="flex items-center space-x-2 text-xs text-blue-400 pt-2 border-t border-slate-800">
            <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
            <span>{statusText}</span>
          </div>
        )}
      </div>

      {/* Discovered Prospect Result Banner */}
      {discoveredProspect && (
        <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center space-x-2 text-emerald-400 text-xs font-semibold">
              <CheckCircle2 className="w-4 h-4" />
              <span>Qualified Prospect Discovered</span>
            </div>
            <span className="text-lg font-bold text-emerald-400">{discoveredProspect.fitScore}% Fit Match</span>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[#090d16] p-4 rounded-md border border-slate-800">
            <div>
              <h3 className="font-bold text-white text-sm">{discoveredProspect.companyName}</h3>
              <p className="text-xs text-slate-300 mt-0.5">{discoveredProspect.whyThisProspect}</p>
            </div>

            <button
              onClick={() => onViewProspect(discoveredProspect.id)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-md flex items-center space-x-2 transition-all whitespace-nowrap shadow-sm"
            >
              <span>Inspect Prospect Details & Outreach</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
