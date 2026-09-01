import { Search, Sparkles } from 'lucide-react';

interface Props {
  businessName: string;
  onOpenDiscovery: () => void;
}

export default function TopHeader({ onOpenDiscovery }: Props) {
  return (
    <header className="h-14 border-b border-slate-800 bg-[#0c1220]/80 backdrop-blur sticky top-0 z-30 px-6 flex items-center justify-between">
      {/* Quick Search & Context */}
      <div className="flex items-center space-x-4 flex-1 max-w-md">
        <div className="relative w-full">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search prospects, companies, or buying signals..."
            className="w-full bg-[#121929] border border-slate-800 rounded-md pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-700"
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onOpenDiscovery}
          className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-md flex items-center space-x-1.5 transition-all shadow-sm"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Run Prospecting Search</span>
        </button>
      </div>
    </header>
  );
}
