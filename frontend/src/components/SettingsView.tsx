import { useRef, useState, useEffect } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile } from '../types';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { apiFetch } from '../lib/api';

interface Props {
  businessInfo: BusinessInfo;
  products: Product[];
  icp: IdealCustomerProfile;
  initialSection?: SettingsTab;
  onSaveBusiness: (info: BusinessInfo) => void;
  onSaveProducts: (products: Product[]) => void;
  onSaveICP: (icp: IdealCustomerProfile) => void;
}

type SettingsTab = 'company' | 'catalog' | 'icp';

export default function SettingsView({
  businessInfo,
  products,
  icp,
  initialSection = 'company',
  onSaveBusiness,
  onSaveProducts,
  onSaveICP,
}: Props) {
  const [section, setSection] = useState<SettingsTab>(initialSection);

  useEffect(() => {
    setSection(initialSection);
  }, [initialSection]);

  return (
    <div className="max-w-3xl">
      <div className="mb-7">
        <h1 className="text-[15px] font-semibold text-ink tracking-tight">
          {section === 'catalog' ? 'Catalog' : 'Settings'}
        </h1>
        <p className="text-[13px] text-ink-secondary mt-0.5">
          Configure your workspace, product catalog, and targeting rules.
        </p>
      </div>

      <div className="flex space-x-6 border-b border-border mb-6">
        {([
          ['company', 'Company Profile'],
          ['catalog', 'Product Catalog'],
          ['icp', 'ICP & Signals'],
        ] as [SettingsTab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setSection(id)}
            className={`pb-2.5 text-[13px] border-b-2 -mb-px transition-colors ${
              section === id
                ? 'border-accent text-accent font-medium'
                : 'border-transparent text-ink-secondary hover:text-ink'
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

function CompanySection({ businessInfo, onSave }: { businessInfo: BusinessInfo; onSave: (b: BusinessInfo) => void }) {
  const [name, setName] = useState(businessInfo.name);
  const [website, setWebsite] = useState(businessInfo.website);
  const [description, setDescription] = useState(businessInfo.description);
  const [markets, setMarkets] = useState(businessInfo.targetMarkets.join(', '));
  const [categories, setCategories] = useState(businessInfo.primaryCategories.join(', '));
  const [extracting, setExtracting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  const handleExtract = async () => {
    if (!description.trim()) return;
    setExtracting(true);
    setError('');
    try {
      const resp = await apiFetch('/api/onboarding/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      });
      if (!resp.ok) throw new Error('Extract failed');
      const data = await resp.json();
      if (data.name) setName(data.name);
      if (data.website) setWebsite(data.website);
      if (Array.isArray(data.targetMarkets)) setMarkets(data.targetMarkets.join(', '));
      if (Array.isArray(data.primaryCategories)) setCategories(data.primaryCategories.join(', '));
    } catch (e) {
      console.warn(e);
      setError('Could not extract profile. Fill the fields manually.');
    } finally {
      setExtracting(false);
    }
  };

  const handleSave = () => {
    onSave({
      ...businessInfo,
      name,
      website,
      description,
      targetMarkets: markets.split(',').map(s => s.trim()).filter(Boolean),
      primaryCategories: categories.split(',').map(s => s.trim()).filter(Boolean),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-5 max-w-lg">
      <div>
        <label className="block text-[12px] font-medium text-ink-secondary mb-1">
          Business description <span className="text-ink-muted font-normal">(auto-fill from this)</span>
        </label>
        <div className="flex gap-2 items-start">
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={3}
            placeholder="We manufacture industrial valves in Italy and sell to water utilities in Germany and the UK..."
            className="flex-1 border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted resize-none"
          />
          <button
            onClick={handleExtract}
            disabled={extracting || !description.trim()}
            className="shrink-0 px-3 py-2 border border-border hover:border-ink-muted rounded-md text-[12px] text-ink-secondary hover:text-ink transition-colors disabled:opacity-40"
          >
            {extracting ? <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.75} /> : 'Auto-fill'}
          </button>
        </div>
        {error && <p className="text-[12px] text-amber-600 mt-1">{error}</p>}
      </div>

      <Field label="Business name" value={name} onChange={setName} placeholder="Acme Manufacturing" />
      <Field label="Website" value={website} onChange={setWebsite} placeholder="https://..." />
      <Field label="Target markets" value={markets} onChange={setMarkets} placeholder="Germany, United Kingdom, Netherlands" />
      <Field label="Product categories" value={categories} onChange={setCategories} placeholder="Industrial components, custom assemblies..." />

      <div className="pt-1">
        <button
          onClick={handleSave}
          className="px-4 py-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-medium rounded-md transition-colors"
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
      <label className="block text-[12px] font-medium text-ink-secondary mb-1">{label}</label>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted"
      />
    </div>
  );
}

function CatalogSection({ products, onSave }: { products: Product[]; onSave: (p: Product[]) => void }) {
  const [inputMode, setInputMode] = useState<'url' | 'file' | 'manual'>('url');
  const [url, setUrl] = useState('');
  const [scraping, setScraping] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const [manual, setManual] = useState({ name: '', category: '', description: '', price: '' });

  const mergeProducts = (incoming: Product[]) => {
    const byName = new Map(products.map(p => [p.name.toLowerCase(), p]));
    for (const item of incoming) {
      byName.set(item.name.toLowerCase(), item);
    }
    onSave(Array.from(byName.values()));
  };

  const handleScrape = async () => {
    if (!url.trim()) return;
    setScraping(true);
    setError('');
    try {
      const resp = await apiFetch('/api/products/extract-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      if (!resp.ok) throw new Error('Extract failed');
      const data = await resp.json();
      mergeProducts((data.products || []) as Product[]);
    } catch (e) {
      console.warn(e);
      setError('Could not extract products from that URL.');
    } finally {
      setScraping(false);
    }
  };

  const handleFile = async (file: File) => {
    setScraping(true);
    setError('');
    try {
      const body = new FormData();
      body.append('file', file);
      const resp = await apiFetch('/api/products/upload-file', { method: 'POST', body });
      if (!resp.ok) throw new Error('Upload failed');
      const data = await resp.json();
      mergeProducts((data.products || []) as Product[]);
    } catch (e) {
      console.warn(e);
      setError('Could not parse that file.');
    } finally {
      setScraping(false);
    }
  };

  const handleManualAdd = () => {
    if (!manual.name.trim()) return;
    mergeProducts([{
      id: `prod-manual-${Date.now()}`,
      name: manual.name.trim(),
      category: manual.category.trim() || 'Uncategorized',
      description: manual.description.trim(),
      price: manual.price.trim() || undefined,
      verifiedByUser: true,
      aiExtracted: false,
    }]);
    setManual({ name: '', category: '', description: '', price: '' });
  };

  const toggleVerified = (id: string) => {
    onSave(products.map(p => p.id === id ? { ...p, verifiedByUser: !p.verifiedByUser } : p));
  };

  const removeProduct = (id: string) => {
    onSave(products.filter(p => p.id !== id));
  };

  return (
    <div className="space-y-5 max-w-xl">
      <div>
        <label className="block text-[12px] font-medium text-ink-secondary mb-2">Import source</label>
        <div className="flex space-x-5">
          {(['url', 'file', 'manual'] as const).map(m => (
            <label key={m} className="flex items-center space-x-1.5 cursor-pointer text-[13px] text-ink-secondary">
              <input
                type="radio"
                name="import-mode"
                checked={inputMode === m}
                onChange={() => setInputMode(m)}
                className="accent-accent"
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
            className="flex-1 border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary placeholder-ink-muted"
          />
          <button
            onClick={handleScrape}
            disabled={scraping || !url.trim()}
            className="px-4 py-2 bg-accent hover:bg-accent-hover disabled:opacity-40 text-white text-[13px] font-medium rounded-md transition-colors shrink-0"
          >
            {scraping ? <Loader2 className="w-4 h-4 animate-spin inline" strokeWidth={1.75} /> : 'Extract'}
          </button>
        </div>
      )}

      {inputMode === 'file' && (
        <div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.csv,.xlsx,.xls"
            className="hidden"
            onChange={e => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
              e.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={scraping}
            className="w-full border border-dashed border-border rounded-md px-4 py-8 text-center hover:border-ink-muted transition-colors"
          >
            {scraping ? (
              <Loader2 className="w-4 h-4 animate-spin inline text-ink-muted" strokeWidth={1.75} />
            ) : (
              <>
                <p className="text-[13px] text-ink-secondary">Drop a PDF, CSV, or Excel file, or browse</p>
                <p className="text-[12px] text-ink-muted mt-1">Supports .pdf, .csv, .xlsx</p>
              </>
            )}
          </button>
        </div>
      )}

      {inputMode === 'manual' && (
        <div className="space-y-3 bg-panel border border-border rounded-lg p-4">
          <Field label="Product name" value={manual.name} onChange={v => setManual({ ...manual, name: v })} placeholder="Product name" />
          <Field label="Category" value={manual.category} onChange={v => setManual({ ...manual, category: v })} placeholder="Category" />
          <Field label="Price" value={manual.price} onChange={v => setManual({ ...manual, price: v })} placeholder="$1,850" />
          <div>
            <label className="block text-[12px] font-medium text-ink-secondary mb-1">Description</label>
            <textarea
              value={manual.description}
              onChange={e => setManual({ ...manual, description: e.target.value })}
              rows={2}
              className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary"
            />
          </div>
          <button
            onClick={handleManualAdd}
            disabled={!manual.name.trim()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-accent hover:bg-accent-hover disabled:opacity-40 text-white text-[13px] font-medium rounded-md"
          >
            <Plus className="w-3.5 h-3.5" strokeWidth={2} />
            Add product
          </button>
        </div>
      )}

      {error && <p className="text-[12px] text-amber-600">{error}</p>}

      {products.length > 0 && (
        <div className="pt-2">
          <p className="section-label mb-3">{products.length} Products in Catalog</p>
          <div className="bg-panel border border-border rounded-lg divide-y divide-border-subtle">
            {products.map(product => (
              <div key={product.id} className="px-4 py-3 flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-[13.5px] font-medium text-ink-secondary truncate">{product.name}</p>
                  <p className="text-[12px] text-ink-muted mt-0.5">
                    {product.category}
                    {product.price ? ` · ${product.price}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <button
                    onClick={() => toggleVerified(product.id)}
                    className={`text-[12px] ${product.verifiedByUser ? 'text-green-700' : 'text-ink-muted hover:text-ink-secondary'}`}
                  >
                    {product.verifiedByUser ? 'Verified' : 'Verify'}
                  </button>
                  <button
                    onClick={() => removeProduct(product.id)}
                    className="text-border hover:text-ink-secondary"
                    aria-label={`Remove ${product.name}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.75} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ICPSection({ icp, onSave }: { icp: IdealCustomerProfile; onSave: (i: IdealCustomerProfile) => void }) {
  const [buyerTypes, setBuyerTypes] = useState(icp.targetBuyerTypes.join(', '));
  const [countries, setCountries] = useState(icp.targetCountries.join(', '));
  const [companySize, setCompanySize] = useState(icp.companySize);
  const [minDealSize, setMinDealSize] = useState(icp.minDealSize || '');
  const [signals] = useState(icp.buyingSignals);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    onSave({
      ...icp,
      targetBuyerTypes: buyerTypes.split(',').map(s => s.trim()).filter(Boolean),
      targetCountries: countries.split(',').map(s => s.trim()).filter(Boolean),
      companySize,
      minDealSize: minDealSize || undefined,
      buyingSignals: signals,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-10 max-w-3xl">
      <div className="space-y-4">
        <p className="section-label">Target Buyer Criteria</p>
        <Field label="Buyer types" value={buyerTypes} onChange={setBuyerTypes} placeholder="Hospital groups, water utilities, OEMs" />
        <Field label="Target countries" value={countries} onChange={setCountries} placeholder="Germany, United Kingdom" />
        <div>
          <label className="block text-[12px] font-medium text-ink-secondary mb-1">Company size</label>
          <select
            value={companySize}
            onChange={e => setCompanySize(e.target.value as IdealCustomerProfile['companySize'])}
            className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary bg-panel"
          >
            {['Any', 'Small', 'Medium', 'Enterprise'].map(size => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </div>
        <Field label="Minimum deal size" value={minDealSize} onChange={setMinDealSize} placeholder="$15,000" />
        <div className="pt-2">
          <button
            onClick={handleSave}
            className="px-4 py-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-medium rounded-md transition-colors"
          >
            {saved ? 'Saved' : 'Save Changes'}
          </button>
        </div>
      </div>

      <div>
        <p className="section-label mb-3">Buying Signal Rules</p>
        <div className="space-y-4 divide-y divide-border-subtle">
          {signals.map((sig, i) => (
            <div key={sig.id || i} className="pt-3 first:pt-0">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[13.5px] font-medium text-ink-secondary">{sig.name}</p>
                <span className="text-[12px] text-ink-muted">+{sig.weight} pts</span>
              </div>
              <p className="text-[12px] text-ink-secondary mt-0.5 leading-relaxed">{sig.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
