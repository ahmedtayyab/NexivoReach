import React, { useState } from 'react';
import type { BusinessInfo } from '../types';
import { Building2, Sparkles, Check, ArrowRight, RefreshCw } from 'lucide-react';

interface Props {
  businessInfo: BusinessInfo;
  onSave: (info: BusinessInfo) => void;
  onNext: () => void;
}

export default function OnboardingView({ businessInfo, onSave, onNext }: Props) {
  const [naturalText, setNaturalText] = useState<string>(businessInfo.description || '');
  const [name, setName] = useState<string>(businessInfo.name || '');
  const [website, setWebsite] = useState<string>(businessInfo.website || '');
  const [markets, setMarkets] = useState<string>(businessInfo.targetMarkets.join(', ') || '');
  const [categories, setCategories] = useState<string>(businessInfo.primaryCategories.join(', ') || '');

  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [hasExtracted, setHasExtracted] = useState<boolean>(businessInfo.extractedByAi || false);

  const handleAiExtract = async () => {
    setIsExtracting(true);
    setTimeout(() => {
      setName('Apex Fitness Equipment');
      setWebsite('https://apexfitnessequipment.example.com');
      setMarkets('United Arab Emirates, Saudi Arabia, Qatar, Kuwait, Oman');
      setCategories('Commercial Strength, Free Weights, Cardio Equipment, Custom Outfitting');
      setHasExtracted(true);
      setIsExtracting(false);
    }, 1200);
  };

  const handleSaveAndContinue = (e: React.FormEvent) => {
    e.preventDefault();
    const updated: BusinessInfo = {
      name,
      website,
      description: naturalText,
      targetMarkets: markets.split(',').map(s => s.trim()).filter(Boolean),
      primaryCategories: categories.split(',').map(s => s.trim()).filter(Boolean),
      extractedByAi: hasExtracted,
    };
    onSave(updated);
    onNext();
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-2">
        <div className="flex items-center space-x-2 text-blue-400 text-xs font-semibold uppercase tracking-wider">
          <Building2 className="w-4 h-4" />
          <span>Step 1: Business Profile Setup</span>
        </div>
        <h1 className="text-xl font-bold text-white">Tell NexivoReach about your business</h1>
        <p className="text-xs text-slate-300">
          Describe what you sell naturally or enter your website. Our AI agent extracts your product category, export markets, and target buyer profile.
        </p>
      </div>

      <form onSubmit={handleSaveAndContinue} className="space-y-6">
        {/* Natural Language Prompt Box */}
        <div className="bg-[#121929] border border-blue-900/40 rounded-xl p-5 space-y-3">
          <label className="block text-xs font-semibold text-slate-200">
            Natural Business Description (AI Extraction Input)
          </label>
          <textarea
            value={naturalText}
            onChange={(e) => setNaturalText(e.target.value)}
            rows={4}
            placeholder="e.g. We manufacture commercial gym equipment in Sialkot, Pakistan and export heavy-duty strength equipment mainly to the Gulf (UAE, KSA, Qatar). Our main products are power racks, cable machines, and treadmills."
            className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-all"
          />

          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleAiExtract}
              disabled={isExtracting || !naturalText.trim()}
              className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white font-medium text-xs rounded-lg flex items-center space-x-2 shadow-md shadow-blue-600/20 transition-all"
            >
              {isExtracting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Extracting Business Structure...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5 text-blue-200" />
                  <span>Extract Profile with AI</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Structured Extracted Info Confirmation */}
        <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h2 className="text-xs font-semibold text-slate-200 flex items-center space-x-2">
              <span>Structured Business Information</span>
              {hasExtracted && (
                <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded font-medium flex items-center space-x-1">
                  <Check className="w-3 h-3" />
                  <span>AI Extracted & Verified</span>
                </span>
              )}
            </h2>
            <span className="text-[11px] text-slate-400">Review & edit prior to catalog step</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">Business Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">Website URL</label>
              <input
                type="url"
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
                required
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">Target Export Countries / Markets (Comma separated)</label>
              <input
                type="text"
                value={markets}
                onChange={(e) => setMarkets(e.target.value)}
                required
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-medium text-slate-300">Primary Product Categories (Comma separated)</label>
              <input
                type="text"
                value={categories}
                onChange={(e) => setCategories(e.target.value)}
                required
                className="w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg flex items-center space-x-2 shadow-lg shadow-blue-600/30 transition-all"
          >
            <span>Save Profile & Continue to Product Catalog</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
