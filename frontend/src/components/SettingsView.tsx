import { useState } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile } from '../types';
import { Loader2 } from 'lucide-react';

interface Props {
  businessInfo: BusinessInfo;
  products: Product[];
  icp: IdealCustomerProfile;
  onSaveBusiness: (info: BusinessInfo) => void;
  onSaveProducts: (products: Product[]) => void;
  onSaveICP: (icp: IdealCustomerProfile) => void;
}

type SettingsTab = 'company' | 'catalog' | 'icp';

export default function SettingsView({ businessInfo, products, icp, onSaveBusiness, onSaveProducts, onSaveICP }: Props) {
  const [section, setSection] = useState<SettingsTab>('company');

  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Configure your workspace, product catalog, and targeting rules.
        </p>
      </div>

      {/* Underline tabs — no pill backgrounds */}
      <div className="flex space-x-6 border-b border-slate-200 mb-6">
        {([
          ['company', 'Company Profile'],
          ['catalog', 'Product Catalog'],
          ['icp', 'ICP & Signals'],
        ] as [SettingsTab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setSection(id)}
            className={`pb-2.5 text-sm border-b-2 -mb-px transition-colors ${
              section === id
                ? 'border-blue-600 text-blue-600 font-medium'
                : 'border-transparent text-slate-500 hover:text-slate-900'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {section === 'company' && <CompanySection businessInfo={businessInfo} onSave={onSaveBusiness} />}
      {section === 'catalog' && <CatalogSection products={products} onSave={onSaveProducts} />}
      {section === 'icp' && <ICPSection icp={icp} onSave={onSaveICP} />}
    </div>
  );
}

/* ── Company Profile ────────────────────────────── */
function CompanySection({ businessInfo, onSave }: { businessInfo: BusinessInfo; onSave: (b: BusinessInfo) => void }) {
  const [name, setName] = useState(businessInfo.name);
  const [website, setWebsite] = useState(businessInfo.website);
  const [description, setDescription] = useState(businessInfo.description);
  const [markets, setMarkets] = useState(businessInfo.targetMarkets.join(', '));
  const [categories, setCategories] = useState(businessInfo.primaryCategories.join(', '));
  const [extracting, setExtracting] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleExtract = () => {
    setExtracting(true);
    setTimeout(() => {
      setName('Apex Fitness Equipment');
      setWebsite('https://apexfitnessequipment.example.com');
      setMarkets('United Arab Emirates, Saudi Arabia, Qatar, Kuwait, Oman');
      setCategories('Commercial Strength, Free Weights, Cardio Equipment, Custom Facility Outfitting');
      setExtracting(false);
    }, 1200);
  };

  const handleSave = () => {
    onSave({
      ...businessInfo,
      name, website, description,
      targetMarkets: markets.split(',').map(s => s.trim()).filter(Boolean),
      primaryCategories: categories.split(',').map(s => s.trim()).filter(Boolean),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-5 max-w-lg">
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">
          Business description <span className="text-slate-400 font-normal">(auto-fill from this)</span>
        </label>
        <div className="flex gap-2 items-start">
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={3}
            placeholder="We manufacture commercial gym equipment in Sialkot, Pakistan..."
            className="flex-1 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 placeholder-slate-400 resize-none focus:outline-none"
          />
          <button
            onClick={handleExtract}
            disabled={extracting}
            className="shrink-0 px-3 py-2 border border-slate-200 hover:border-slate-400 rounded-md text-xs text-slate-600 hover:text-slate-900 transition-colors"
          >
            {extracting ? <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.75} /> : 'Auto-fill'}
          </button>
        </div>
      </div>

      <Field label="Business name" value={name} onChange={setName} placeholder="Apex Fitness Equipment" />
      <Field label="Website" value={website} onChange={setWebsite} placeholder="https://..." />
      <Field label="Target markets" value={markets} onChange={setMarkets} placeholder="UAE, Saudi Arabia, Qatar" />
      <Field label="Product categories" value={categories} onChange={setCategories} placeholder="Commercial Strength, Free Weights..." />

      <div className="pt-1">
        <button
          onClick={handleSave}
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors"
        >
          {saved ? 'Saved' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1">{label}</label>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none"
      />
    </div>
  );
}

/* ── Product Catalog ────────────────────────────── */
function CatalogSection({ products, onSave: _onSave }: { products: Product[]; onSave: (p: Product[]) => void }) {
  const [inputMode, setInputMode] = useState<'url' | 'file' | 'manual'>('url');
  const [url, setUrl] = useState('https://apexfitnessequipment.example.com');
  const [scraping, setScraping] = useState(false);

  const handleScrape = () => {
    setScraping(true);
    setTimeout(() => setScraping(false), 1500);
  };

  return (
    <div className="space-y-5 max-w-xl">
      {/* Import mode toggle */}
      <div>
        <label className="block text-xs font-medium text-slate-700 mb-2">Import source</label>
        <div className="flex space-x-5">
          {(['url', 'file', 'manual'] as const).map(m => (
            <label key={m} className="flex items-center space-x-1.5 cursor-pointer text-sm text-slate-700">
              <input
                type="radio"
                name="import-mode"
                checked={inputMode === m}
                onChange={() => setInputMode(m)}
                className="accent-blue-600"
              />
              <span>{m === 'url' ? 'Website URL' : m === 'file' ? 'Upload file' : 'Manual entry'}</span>
            </label>
          ))}
        </div>
      </div>

      {inputMode === 'url' && (
        <div className="flex gap-2">
          <input
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://..."
            className="flex-1 border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none"
          />
          <button
            onClick={handleScrape}
            disabled={scraping}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-medium rounded-md transition-colors shrink-0"
          >
            {scraping ? <Loader2 className="w-4 h-4 animate-spin inline" strokeWidth={1.75} /> : 'Extract'}
          </button>
        </div>
      )}

      {inputMode === 'file' && (
        <div className="border border-dashed border-slate-300 rounded-md px-4 py-8 text-center">
          <p className="text-sm text-slate-500">Drop a PDF, CSV, or Excel file here, or <span className="text-blue-600 cursor-pointer">browse</span></p>
          <p className="text-xs text-slate-400 mt-1">Supports .pdf, .csv, .xlsx</p>
        </div>
      )}

      {/* Product list */}
      {products.length > 0 && (
        <div className="pt-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-widest mb-3">{products.length} Products in Catalog</p>
          <div className="border border-slate-200 rounded-md divide-y divide-slate-100">
            {products.map(product => (
              <div key={product.id} className="px-4 py-3 flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-slate-800">{product.name}</p>
                  <p className="text-xs text-slate-400 mt-0.5">{product.category} · {product.price}</p>
                </div>
                <span className={`text-xs shrink-0 mt-0.5 ${product.verifiedByUser ? 'text-green-700' : 'text-slate-400'}`}>
                  {product.verifiedByUser ? 'Verified' : 'Extracted'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── ICP & Signals ──────────────────────────────── */
function ICPSection({ icp, onSave }: { icp: IdealCustomerProfile; onSave: (i: IdealCustomerProfile) => void }) {
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    onSave(icp);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="grid grid-cols-2 gap-10 max-w-3xl">
      {/* Left: Target criteria */}
      <div className="space-y-4">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-widest">Target Buyer Criteria</p>

        <div>
          <p className="text-xs font-medium text-slate-700 mb-0.5">Buyer types</p>
          <p className="text-sm text-slate-600">{icp.targetBuyerTypes.join(', ')}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-slate-700 mb-0.5">Target countries</p>
          <p className="text-sm text-slate-600">{icp.targetCountries.join(', ')}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-slate-700 mb-0.5">Company size</p>
          <p className="text-sm text-slate-600">{icp.companySize}</p>
        </div>
        {icp.minDealSize && (
          <div>
            <p className="text-xs font-medium text-slate-700 mb-0.5">Minimum deal size</p>
            <p className="text-sm text-slate-600">{icp.minDealSize}</p>
          </div>
        )}

        <div className="pt-2">
          <button
            onClick={handleSave}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors"
          >
            {saved ? 'Saved' : 'Save Changes'}
          </button>
        </div>
      </div>

      {/* Right: Buying signal rules */}
      <div>
        <p className="text-xs font-medium text-slate-400 uppercase tracking-widest mb-3">Buying Signal Rules</p>
        <div className="space-y-4 divide-y divide-slate-100">
          {icp.buyingSignals.map((sig, i) => (
            <div key={i} className="pt-3 first:pt-0">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-slate-800">{sig.name}</p>
                <span className="text-xs text-slate-400">+{sig.weight} pts</span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{sig.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
