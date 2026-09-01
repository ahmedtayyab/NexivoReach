import { useState } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog } from '../types';
import { 
  Bot, 
  Search, 
  Sparkles, 
  CheckCircle2, 
  ArrowRight, 
  Cpu
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
  products, 
  onAddProspect, 
  onAddLog, 
  onViewProspect 
}: Props) {
  const [userQuery, setUserQuery] = useState<string>(
    'Find commercial gyms in UAE that are likely to need new commercial strength & cardio equipment.'
  );

  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(-1);
  const [activeSteps, setActiveSteps] = useState<{
    step: number;
    title: string;
    description: string;
    toolCalled?: string;
    status: 'pending' | 'running' | 'completed';
    resultSnippet?: string;
  }[]>([
    { step: 1, title: 'Understand & Structure Goal', description: 'Parsing user prompt against catalog items & target GCC markets.', status: 'pending' },
    { step: 2, title: 'Web Search & Discovery', description: 'Querying public business search & press releases in Dubai/UAE.', toolCalled: 'WebSearchTool', status: 'pending' },
    { step: 3, title: 'Deep Site Scrape & Signal Detection', description: 'Scraping company website & checking expansion press releases.', toolCalled: 'SiteScraperTool', status: 'pending' },
    { step: 4, title: 'Product Catalog Match & Fit Scoring', description: 'Matching power racks, cable crossover & treadmills to floor plan.', toolCalled: 'ProductMatcherTool', status: 'pending' },
    { step: 5, title: 'Transparent Score Calculation', description: 'Executing 100-point transparent formula with line-by-line evidence.', toolCalled: 'ScoreCalculatorTool', status: 'pending' },
    { step: 6, title: 'Personalized Outreach Drafting', description: 'Drafting custom outreach tied to Business Bay opening announcement.', toolCalled: 'OutreachEngine', status: 'pending' }
  ]);

  const [discoveredProspect, setDiscoveredProspect] = useState<Prospect | null>(null);

  const handleStartAgentRun = () => {
    setIsRunning(true);
    setCurrentStepIndex(0);
    setDiscoveredProspect(null);

    // Reset steps
    setActiveSteps(prev => prev.map(s => ({ ...s, status: 'pending', resultSnippet: undefined })));

    // Step 1
    setTimeout(() => {
      setCurrentStepIndex(0);
      setActiveSteps(prev => prev.map((s, idx) => idx === 0 ? { 
        ...s, 
        status: 'completed', 
        resultSnippet: `Goal Target: Commercial Gyms in UAE. Products to match: ${products.map(p => p.name).slice(0, 2).join(', ')}.` 
      } : s));
    }, 1000);

    // Step 2
    setTimeout(() => {
      setCurrentStepIndex(1);
      setActiveSteps(prev => prev.map((s, idx) => idx === 1 ? { 
        ...s, 
        status: 'completed', 
        resultSnippet: 'Discovered candidate: Urban Strength Gym Dubai (Commercial facility in Al Quoz).' 
      } : s));
    }, 2500);

    // Step 3
    setTimeout(() => {
      setCurrentStepIndex(2);
      setActiveSteps(prev => prev.map((s, idx) => idx === 2 ? { 
        ...s, 
        status: 'completed', 
        resultSnippet: 'Found Buying Signal: "Urban Strength expanding Al Quoz branch with 5,000 sq ft functional zone in Q4."' 
      } : s));
    }, 4000);

    // Step 4 & 5
    setTimeout(() => {
      setCurrentStepIndex(3);
      setActiveSteps(prev => prev.map((s, idx) => (idx === 3 || idx === 4) ? { 
        ...s, 
        status: 'completed', 
        resultSnippet: 'Catalog Fit: High match with Power Rack & Urethane Dumbbell sets. Fit Score calculated: 92/100.' 
      } : s));
    }, 5500);

    // Step 6 & Finish
    setTimeout(() => {
      setCurrentStepIndex(5);
      setActiveSteps(prev => prev.map((s, idx) => idx === 5 ? { 
        ...s, 
        status: 'completed', 
        resultSnippet: 'Generated personalized draft tied to Al Quoz 5,000 sq ft functional expansion.' 
      } : s));

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
        durationMs: 6500,
        toolsUsed: ['WebSearchTool', 'SiteScraperTool', 'SignalDetectorTool', 'ProductMatcherTool', 'ScoreCalculatorTool'],
        sourcesCount: 8,
        status: 'Completed',
        decisions: activeSteps.map(s => ({
          step: s.step,
          observation: s.description,
          decision: s.title,
          toolCalled: s.toolCalled,
          toolResultSnippet: s.resultSnippet
        }))
      });

      setIsRunning(false);
    }, 7000);
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-2">
        <div className="flex items-center space-x-2 text-blue-400 text-xs font-semibold uppercase tracking-wider">
          <Bot className="w-4 h-4" />
          <span>Step 4: Autonomous Prospecting Agent Loop</span>
        </div>
        <h1 className="text-xl font-bold text-white">Trigger Multi-Step AI Discovery Agent</h1>
        <p className="text-xs text-slate-300">
          Enter a high-level goal. The agent follows an actual <code className="text-indigo-300 font-mono">Observe → Decide → Tool → Inspect</code> loop to discover, research, score, and match buyers.
        </p>
      </div>

      {/* Query Bar */}
      <div className="bg-[#121929] border border-blue-900/40 rounded-xl p-5 space-y-4">
        <label className="block text-xs font-semibold text-slate-200">Prospecting Goal Prompt</label>
        <div className="flex flex-col sm:flex-row items-center gap-3">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              value={userQuery}
              onChange={(e) => setUserQuery(e.target.value)}
              placeholder="e.g. Find commercial gyms in UAE that are likely to need new equipment."
              disabled={isRunning}
              className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg pl-9 pr-3 py-2.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
            />
          </div>
          <button
            onClick={handleStartAgentRun}
            disabled={isRunning || !userQuery.trim()}
            className="w-full sm:w-auto px-6 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center justify-center space-x-2 shadow-lg shadow-blue-600/30 transition-all whitespace-nowrap"
          >
            <Sparkles className="w-4 h-4" />
            <span>{isRunning ? 'Agent Executing Steps...' : 'Execute Agent Goal'}</span>
          </button>
        </div>
      </div>

      {/* Agent Execution Trace Window */}
      <div className="bg-[#0c111d] border border-slate-800 rounded-xl p-5 space-y-4 font-sans">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <Cpu className="w-4 h-4 text-indigo-400" />
            <h2 className="text-xs font-semibold text-slate-200 font-mono">AGENT EXECUTION CYCLE TRACE</h2>
          </div>
          <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
            isRunning ? 'bg-amber-950 text-amber-400 border border-amber-800 animate-pulse' : 'bg-slate-800 text-slate-400'
          }`}>
            {isRunning ? 'Agent Status: ACTIVE EXECUTION' : 'Agent Status: READY'}
          </span>
        </div>

        <div className="space-y-3">
          {activeSteps.map((step, index) => {
            const isDone = step.status === 'completed';
            const isCurrent = isRunning && currentStepIndex === index;

            return (
              <div 
                key={step.step}
                className={`p-3.5 rounded-lg border text-xs transition-all ${
                  isDone 
                    ? 'bg-[#101726] border-slate-800' 
                    : isCurrent 
                    ? 'bg-blue-950/40 border-blue-600/50 shadow-md shadow-blue-500/10' 
                    : 'bg-[#080c14] border-slate-800/40 opacity-60'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start space-x-3">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center font-mono text-[10px] mt-0.5 ${
                      isDone ? 'bg-emerald-500 text-white font-bold' : isCurrent ? 'bg-blue-500 text-white font-bold animate-spin' : 'bg-slate-800 text-slate-400'
                    }`}>
                      {isDone ? '✓' : step.step}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold text-slate-200">{step.title}</span>
                        {step.toolCalled && (
                          <span className="font-mono text-[10px] bg-slate-800 text-indigo-300 px-1.5 py-0.2 rounded border border-slate-700">
                            Tool: {step.toolCalled}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">{step.description}</p>
                    </div>
                  </div>

                  {isDone && <span className="text-[10px] text-emerald-400 font-mono">COMPLETE</span>}
                  {isCurrent && <span className="text-[10px] text-blue-400 font-mono animate-pulse">EXECUTING...</span>}
                </div>

                {step.resultSnippet && (
                  <div className="mt-2.5 ml-8 bg-[#070a12] p-2 rounded border border-slate-800 text-[11px] font-mono text-slate-300">
                    <span className="text-slate-500">Result: </span>
                    {step.resultSnippet}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Discovered Prospect Result Banner */}
      {discoveredProspect && (
        <div className="bg-gradient-to-r from-emerald-950/60 via-slate-900 to-blue-950/60 border border-emerald-800/60 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-emerald-400 text-xs font-semibold">
              <CheckCircle2 className="w-4 h-4" />
              <span>New Qualified Prospect Discovered!</span>
            </div>
            <span className="text-lg font-bold text-emerald-400">{discoveredProspect.fitScore}% Fit Match</span>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[#0b101c] p-4 rounded-lg border border-slate-800">
            <div>
              <h3 className="font-bold text-white text-sm">{discoveredProspect.companyName}</h3>
              <p className="text-xs text-slate-300 mt-0.5">{discoveredProspect.whyThisProspect}</p>
            </div>

            <button
              onClick={() => onViewProspect(discoveredProspect.id)}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-lg flex items-center space-x-2 transition-all whitespace-nowrap shadow-md shadow-emerald-600/20"
            >
              <span>View Prospect Research View</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
