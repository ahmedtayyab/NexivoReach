import React, { useState } from 'react';
import type { IdealCustomerProfile, BuyingSignalConfig } from '../types';
import { Target, Zap, Plus, Trash2, ArrowRight } from 'lucide-react';

interface Props {
  icp: IdealCustomerProfile;
  onSaveICP: (icp: IdealCustomerProfile) => void;
  onNext: () => void;
}

export default function ICPView({ icp, onSaveICP, onNext }: Props) {
  const [buyerTypesText, setBuyerTypesText] = useState(icp.targetBuyerTypes.join(', '));
  const [countriesText, setCountriesText] = useState(icp.targetCountries.join(', '));
  const [companySize, setCompanySize] = useState<IdealCustomerProfile['companySize']>(icp.companySize);
  const [minDealSize, setMinDealSize] = useState(icp.minDealSize || '');
  const [constraintsText, setConstraintsText] = useState(icp.salesConstraints?.join(', ') || '');
  const [buyingSignals, setBuyingSignals] = useState<BuyingSignalConfig[]>(icp.buyingSignals);

  // New Signal state
  const [newSignalName, setNewSignalName] = useState('');
  const [newSignalDesc, setNewSignalDesc] = useState('');
  const [newSignalWeight, setNewSignalWeight] = useState(15);

  const handleAddSignal = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSignalName.trim()) return;
    const newSig: BuyingSignalConfig = {
      id: `sig-custom-${Date.now()}`,
      name: newSignalName,
      description: newSignalDesc,
      weight: Number(newSignalWeight),
      isCustom: true,
    };
    setBuyingSignals([...buyingSignals, newSig]);
    setNewSignalName('');
    setNewSignalDesc('');
  };

  const handleRemoveSignal = (id: string) => {
    setBuyingSignals(buyingSignals.filter(s => s.id !== id));
  };

  const handleSaveAndContinue = (e: React.FormEvent) => {
    e.preventDefault();
    const updated: IdealCustomerProfile = {
      targetBuyerTypes: buyerTypesText.split(',').map(s => s.trim()).filter(Boolean),
      targetCountries: countriesText.split(',').map(s => s.trim()).filter(Boolean),
      companySize,
      minDealSize,
      salesConstraints: constraintsText.split(',').map(s => s.trim()).filter(Boolean),
      buyingSignals,
    };
    onSaveICP(updated);
    onNext();
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-2">
        <div className="flex items-center space-x-2 text-emerald-400 text-xs font-semibold uppercase tracking-wider">
          <Target className="w-4 h-4" />
          <span>Step 3: Ideal Customer Profile & Buying Signals</span>
        </div>
        <h1 className="text-xl font-bold text-white">Define Target Buyers & Qualification Triggers</h1>
        <p className="text-xs text-slate-300">
          Specify who you sell to, target markets, minimum deal sizes, and the exact buying signals that trigger AI prospect qualification.
        </p>
      </div>

      <form onSubmit={handleSaveAndContinue} className="space-y-6">
        {/* ICP Parameters Box */}
        <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-4">
          <h2 className="text-xs font-semibold text-slate-200 border-b border-slate-800 pb-3">
            Target Audience & Market Criteria
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">
                Target Buyer Categories (Comma separated)
              </label>
              <input
                type="text"
                value={buyerTypesText}
                onChange={e => setBuyerTypesText(e.target.value)}
                placeholder="e.g. Commercial Gym Chains, Independent Gyms, Hotels, Sports Retailers"
                required
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">
                Target Geographic Markets (Comma separated)
              </label>
              <input
                type="text"
                value={countriesText}
                onChange={e => setCountriesText(e.target.value)}
                placeholder="e.g. United Arab Emirates, Saudi Arabia, Qatar"
                required
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">Company Size Preference</label>
              <select
                value={companySize}
                onChange={e => setCompanySize(e.target.value as any)}
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                <option value="Any">Any Company Size</option>
                <option value="Small">Small (1-20 Employees / Single location)</option>
                <option value="Medium">Medium (20-100 Employees / 2-5 locations)</option>
                <option value="Enterprise">Enterprise (100+ Employees / Large Chains)</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">Minimum Deal Size / Order Target</label>
              <input
                type="text"
                value={minDealSize}
                onChange={e => setMinDealSize(e.target.value)}
                placeholder="e.g. $15,000"
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div className="col-span-1 md:col-span-2 space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">Sales Constraints / Requirements</label>
              <input
                type="text"
                value={constraintsText}
                onChange={e => setConstraintsText(e.target.value)}
                placeholder="e.g. Requires direct factory pricing, Custom laser branding, Short lead time (<30 days)"
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>
        </div>

        {/* Buying Signals Box */}
        <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h2 className="text-xs font-semibold text-slate-200 flex items-center space-x-2">
                <Zap className="w-4 h-4 text-emerald-400" />
                <span>Buying Signal Detection Rules ({buyingSignals.length})</span>
              </h2>
              <p className="text-[11px] text-slate-400 mt-0.5">
                The AI agent searches for these specific indicators when evaluating potential buyers.
              </p>
            </div>
          </div>

          <div className="space-y-3">
            {buyingSignals.map(sig => (
              <div key={sig.id} className="bg-[#0b101c] border border-slate-800 rounded-lg p-3 flex items-center justify-between gap-3">
                <div className="space-y-0.5">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-slate-200 text-xs">⚡ {sig.name}</span>
                    <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800/60 px-1.5 py-0.2 rounded font-mono">
                      Weight: +{sig.weight} pts
                    </span>
                    {sig.isCustom && (
                      <span className="text-[10px] bg-blue-950 text-blue-300 border border-blue-800/60 px-1 py-0.2 rounded">
                        Custom
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400">{sig.description}</p>
                </div>

                <button
                  type="button"
                  onClick={() => handleRemoveSignal(sig.id)}
                  className="text-slate-500 hover:text-rose-400 p-1"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          {/* Add Custom Buying Signal */}
          <div className="bg-[#0b101c] border border-slate-800/80 rounded-lg p-4 space-y-3">
            <span className="text-xs font-semibold text-slate-300 block">Add Custom Buying Signal</span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <input
                type="text"
                value={newSignalName}
                onChange={e => setNewSignalName(e.target.value)}
                placeholder="Signal Name (e.g. Funding Raised)"
                className="bg-[#121929] border border-slate-700/80 rounded p-2 text-xs text-slate-200"
              />
              <input
                type="text"
                value={newSignalDesc}
                onChange={e => setNewSignalDesc(e.target.value)}
                placeholder="Description / Trigger Keyword"
                className="bg-[#121929] border border-slate-700/80 rounded p-2 text-xs text-slate-200"
              />
              <div className="flex items-center space-x-2">
                <input
                  type="number"
                  value={newSignalWeight}
                  onChange={e => setNewSignalWeight(Number(e.target.value))}
                  min={5}
                  max={30}
                  className="w-20 bg-[#121929] border border-slate-700/80 rounded p-2 text-xs text-slate-200"
                />
                <button
                  type="button"
                  onClick={handleAddSignal}
                  className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded flex items-center justify-center space-x-1"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Signal</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Continue to Agent */}
        <div className="flex justify-end">
          <button
            type="submit"
            className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg flex items-center space-x-2 shadow-lg shadow-emerald-600/30 transition-all"
          >
            <span>Save Profile & Launch Discovery Agent</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
