import { useState } from 'react';
import type { Prospect } from '../types';
import { 
  Search, 
  MapPin, 
  Plus
} from 'lucide-react';

interface Props {
  prospects: Prospect[];
  selectedProspectId: string;
  onSelectProspect: (id: string) => void;
  onUpdateStatus: (prospectId: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
  onNavigateToDiscovery: () => void;
}

export default function ProspectsView({ 
  prospects, 
  onSelectProspect, 
  onNavigateToDiscovery
}: Props) {
  const [searchTerm, setSearchTerm] = useState('');
  const [stageFilter, setStageFilter] = useState('All');

  const filteredProspects = prospects.filter(p => {
    const matchesSearch = p.companyName.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          p.location.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          p.industry.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStage = stageFilter === 'All' || p.stage === stageFilter;
    return matchesSearch && matchesStage;
  });

  return (
    <div className="space-y-6 font-sans text-slate-100">
      {/* Top Header & Search Bar */}
      <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-white tracking-tight">Discovered Prospect Intelligence</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {prospects.length} total qualified commercial leads matching Apex Fitness Equipment catalog specs.
          </p>
        </div>

        <button
          onClick={onNavigateToDiscovery}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-md flex items-center space-x-1.5 shadow-sm transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Prospecting Run</span>
        </button>
      </div>

      {/* Filter & Search Toolbar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-[#1e293b] border border-slate-800 rounded-lg p-3">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Filter by company name or city..."
            className="w-full bg-[#090d16] border border-slate-800 rounded-md pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-700"
          />
        </div>

        <div className="flex items-center space-x-2 w-full sm:w-auto">
          <span className="text-xs text-slate-400 font-medium">Stage:</span>
          <select
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className="bg-[#090d16] border border-slate-800 rounded-md px-3 py-1.5 text-xs text-slate-200 focus:outline-none"
          >
            <option value="All">All Stages</option>
            <option value="Qualified">Qualified</option>
            <option value="Researched">Researched</option>
            <option value="Contacted">Contacted</option>
            <option value="Replied">Replied</option>
          </select>
        </div>
      </div>

      {/* High-Density Data Table */}
      <div className="bg-[#1e293b] border border-slate-800 rounded-lg overflow-hidden">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-800 bg-[#090d16]/50 text-slate-400 text-[11px] font-semibold">
              <th className="py-3 px-4">Company Name</th>
              <th className="py-3 px-4">Location</th>
              <th className="py-3 px-4">Industry / Scale</th>
              <th className="py-3 px-4">Fit Score</th>
              <th className="py-3 px-4">Top Buying Signal</th>
              <th className="py-3 px-4">Stage</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {filteredProspects.map((prospect) => (
              <tr 
                key={prospect.id} 
                onClick={() => onSelectProspect(prospect.id)}
                className="hover:bg-slate-800/50 cursor-pointer transition-all"
              >
                <td className="py-3.5 px-4">
                  <span className="font-semibold text-white block">{prospect.companyName}</span>
                  <span className="text-[11px] text-slate-400 font-mono">{prospect.website}</span>
                </td>
                <td className="py-3.5 px-4 text-slate-300">
                  <span className="flex items-center space-x-1">
                    <MapPin className="w-3 h-3 text-slate-500" />
                    <span>{prospect.location}</span>
                  </span>
                </td>
                <td className="py-3.5 px-4 text-slate-300">
                  <span>{prospect.industry}</span>
                  <span className="text-[11px] text-slate-400 block">{prospect.companySize}</span>
                </td>
                <td className="py-3.5 px-4">
                  <span className={`font-bold text-xs ${
                    prospect.fitScore >= 90 ? 'text-emerald-400' : 'text-blue-400'
                  }`}>
                    {prospect.fitScore}% Match
                  </span>
                </td>
                <td className="py-3.5 px-4 text-slate-300">
                  <span className="text-[11px] font-medium text-slate-200">
                    ⚡ {prospect.buyingSignals[0]?.signal || 'Facility Expansion'}
                  </span>
                </td>
                <td className="py-3.5 px-4">
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
                    {prospect.stage}
                  </span>
                </td>
                <td className="py-3.5 px-4 text-right">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectProspect(prospect.id);
                    }}
                    className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] rounded font-medium transition-all"
                  >
                    Inspect Lead
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
