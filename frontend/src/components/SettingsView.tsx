import { useEffect, useMemo, useRef, useState } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect } from '../types';
import { CheckCircle2, ExternalLink, Loader2, Plus, Trash2, XCircle } from 'lucide-react';
import { apiFetch } from '../lib/api';
import PredictiveField from './PredictiveField';
import {
  categoriesFromProducts,
  suggestionsForField,
} from '../data/taxonomy';

import type { SettingsSection } from '../lib/navigation';

interface Props {
  businessInfo: BusinessInfo;
  products: Product[];
  icp: IdealCustomerProfile;
  section: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
  onSaveBusiness: (info: BusinessInfo) => void;
  onSaveProducts: (products: Product[]) => void;
  onSaveICP: (icp: IdealCustomerProfile) => void;
  onRestoredFromSheets?: (payload: {
    company?: BusinessInfo;
    products?: Product[];
    prospects?: Prospect[];
    activeBusinessId?: string;
  }) => void | Promise<void>;
}

export default function SettingsView({
  businessInfo,
  products,
  icp,
  section,
  onSectionChange,
  onSaveBusiness,
  onSaveProducts,
  onSaveICP,
  onRestoredFromSheets,
}: Props) {
  const titles: Record<SettingsSection, string> = {
    company: 'Company Profile',
    catalog: 'Product Catalog',
    icp: 'ICP & Signals',
    integrations: 'Integrations',
  };
  const descriptions: Record<SettingsSection, string> = {
    company:
      'Describe this selling company: what it offers, how it sells (private label, wholesale, direct, SaaS, local services), and which markets it wants. Discover uses this to choose search strategies and to judge business-model fit — not just category keywords.',
    catalog:
      'The products or services this company actually sells. Offer fit is checked against this catalog, so keep names and categories accurate.',
    icp:
      'The ideal customer is who should buy — not who you are. Set buyer types (brands, distributors, hospitals, plants, etc.), countries, and size. Fit is scored against this. Buying-signal rules are optional timing clues; they do not turn a keyword match into intent.',
    integrations:
      'Connect Google Sheets and other destinations so qualified leads and catalog rows sync out of NexivoReach.',
  };

  return (
    <div className="max-w-3xl">
      <div className="mb-7">
        <h1 className="text-[15px] font-semibold text-ink tracking-tight">
          {titles[section]}
        </h1>
        <p className="text-[13px] text-ink-secondary mt-1.5 leading-relaxed max-w-2xl">
          {descriptions[section]}
        </p>
      </div>

      <div className="flex gap-4 sm:gap-6 border-b border-border mb-6 overflow-x-auto scrollbar-none -mx-4 px-4 sm:mx-0 sm:px-0">
        {([
          ['company', 'Company Profile'],
          ['catalog', 'Product Catalog'],
          ['icp', 'ICP & Signals'],
          ['integrations', 'Integrations'],
        ] as [SettingsSection, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => onSectionChange(id)}
            className={`shrink-0 pb-2.5 text-[13px] border-b-2 -mb-px transition-colors ${
              section === id
                ? 'border-accent text-accent font-medium'
                : 'border-transparent text-ink-secondary hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {section === 'company' && (
        <CompanySection
          key={businessInfo.id ?? 'company'}
          businessInfo={businessInfo}
          products={products}
          onSave={onSaveBusiness}
        />
      )}
      {section === 'catalog' && <CatalogSection products={products} onSave={onSaveProducts} />}
      {section === 'icp' && (
        <ICPSection
          key={icp.companySize + icp.targetCountries.join('|')}
          icp={icp}
          businessInfo={businessInfo}
          products={products}
          onSave={onSaveICP}
        />
      )}
      {section === 'integrations' && (
        <IntegrationsSection onRestoredFromSheets={onRestoredFromSheets} />
      )}
    </div>
  );
}

function CompanySection({
  businessInfo,
  products,
  onSave,
}: {
  businessInfo: BusinessInfo;
  products: Product[];
  onSave: (b: BusinessInfo) => void;
}) {
  const [name, setName] = useState(businessInfo.name ?? '');
  const [website, setWebsite] = useState(businessInfo.website ?? '');
  const [description, setDescription] = useState(businessInfo.description ?? '');
  const [markets, setMarkets] = useState((businessInfo.targetMarkets ?? []).join(', '));
  const [categories, setCategories] = useState((businessInfo.primaryCategories ?? []).join(', '));
  const [extracting, setExtracting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  const catalogCats = useMemo(() => categoriesFromProducts(products), [products]);
  const context = `${description} ${categories} ${catalogCats.join(' ')}`;
  const marketSuggestions = useMemo(
    () => suggestionsForField('markets', context, catalogCats),
    [context, catalogCats],
  );
  const categorySuggestions = useMemo(
    () => suggestionsForField('categories', context, catalogCats),
    [context, catalogCats],
  );

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
      <p className="text-[13px] text-ink-muted leading-relaxed">
        Write the description the way you would brief a new salesperson: product, manufacturing vs brand, export vs local, and who you refuse to sell to if that matters.
      </p>
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
        {catalogCats.length > 0 && (
          <p className="text-[12px] text-ink-muted mt-2">
            From your catalog: {catalogCats.slice(0, 5).join(', ')}
            {catalogCats.length > 5 ? '…' : ''} — used to refine suggestions below.
          </p>
        )}
      </div>

      <Field label="Business name" value={name} onChange={setName} placeholder="Acme Manufacturing" />
      <Field label="Website" value={website} onChange={setWebsite} placeholder="https://..." />
      <PredictiveField
        label="Target markets"
        hint="Start typing a country — matching options appear. Or click a chip."
        value={markets}
        onChange={setMarkets}
        suggestions={marketSuggestions}
        placeholder="United States, United Kingdom, UAE"
        aiContext={{
          field: 'markets',
          description,
          catalogCategories: catalogCats,
        }}
      />
      <PredictiveField
        label="Product categories"
        hint="Type a word like “gym” or “industrial” — related categories appear instantly."
        value={categories}
        onChange={setCategories}
        suggestions={categorySuggestions}
        placeholder="e.g. Sportswear, Industrial Equipment, SaaS"
        aiContext={{
          field: 'categories',
          description,
          catalogCategories: catalogCats,
        }}
      />

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
  const [status, setStatus] = useState('');
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
    setStatus('Reading the website and looking for products...');
    try {
      const resp = await apiFetch('/api/products/extract-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      if (!resp.ok) throw new Error('Extract failed');
      const data = await resp.json();
      const found = (data.products || []) as Product[];
      mergeProducts(found);
      setStatus(
        found.length
          ? data.message || `Added ${found.length} product${found.length === 1 ? '' : 's'} from the website.`
          : data.message || 'No products were found. Try a product page URL or add items manually.'
      );
    } catch (e) {
      console.warn(e);
      setStatus('');
      setError('Could not extract products from that URL. Try a product or catalog page, or add items manually.');
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
    }]);
    setManual({ name: '', category: '', description: '', price: '' });
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
            placeholder="https://www.alwasi-ent.com"
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
      {status && <p className="text-[12px] text-ink-secondary">{status}</p>}

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
              <div key={product.id} className="px-4 py-3 flex items-start gap-3">
                {/* Thumbnail */}
                {product.imageUrl ? (
                  <img
                    src={product.imageUrl}
                    alt={product.name}
                    className="w-12 h-12 rounded object-cover shrink-0 border border-border bg-canvas"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                ) : (
                  <div className="w-12 h-12 rounded border border-border bg-canvas shrink-0 flex items-center justify-center text-[10px] text-ink-muted">
                    No img
                  </div>
                )}
                {/* Info */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[13.5px] font-medium text-ink-secondary truncate">{product.name}</p>
                      <p className="text-[12px] text-ink-muted mt-0.5">
                        {product.category}
                        {product.price ? ` · ${product.price}` : ''}
                        {product.moq ? ` · MOQ: ${product.moq}` : ''}
                      </p>
                      {product.description && (
                        <p className="text-[11.5px] text-ink-muted mt-0.5 line-clamp-2 leading-relaxed">{product.description}</p>
                      )}
                      <div className="flex items-center gap-3 mt-1">
                        {product.productUrl && (
                          <a href={product.productUrl} target="_blank" rel="noopener noreferrer"
                            className="text-[11px] text-accent hover:underline">
                            View product ↗
                          </a>
                        )}
                        {product.inStock === true && <span className="text-[11px] text-emerald-600">In stock</span>}
                        {product.inStock === false && <span className="text-[11px] text-amber-600">Out of stock</span>}
                      </div>
                    </div>
                    <button
                      onClick={() => removeProduct(product.id)}
                      className="text-border hover:text-ink-secondary shrink-0 mt-0.5"
                      aria-label={`Remove ${product.name}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" strokeWidth={1.75} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ICPSection({
  icp,
  businessInfo,
  products,
  onSave,
}: {
  icp: IdealCustomerProfile;
  businessInfo: BusinessInfo;
  products: Product[];
  onSave: (i: IdealCustomerProfile) => void;
}) {
  const [buyerTypes, setBuyerTypes] = useState((icp.targetBuyerTypes ?? []).join(', '));
  const [countries, setCountries] = useState((icp.targetCountries ?? []).join(', '));
  const [companySize, setCompanySize] = useState(icp.companySize ?? 'Any');
  const [minDealSize, setMinDealSize] = useState(icp.minDealSize || '');
  const [signals] = useState(icp.buyingSignals ?? []);
  const [saved, setSaved] = useState(false);

  const catalogCats = useMemo(() => categoriesFromProducts(products), [products]);
  const context = useMemo(
    () =>
      [
        businessInfo.description,
        ...(businessInfo.primaryCategories ?? []),
        ...(businessInfo.targetMarkets ?? []),
        buyerTypes,
        ...catalogCats,
      ].join(' '),
    [businessInfo, buyerTypes, catalogCats],
  );
  const buyerSuggestions = useMemo(
    () => suggestionsForField('buyers', context, catalogCats),
    [context, catalogCats],
  );
  const countrySuggestions = useMemo(
    () => suggestionsForField('markets', context, catalogCats),
    [context, catalogCats],
  );

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
        <p className="text-[13px] text-ink-muted leading-relaxed">
          Name the companies you want in the pipeline. A Pakistani factory selling private-label apparel should list brands and importers — not other factories. Geography here is a hard filter when the agent can confirm it.
        </p>
        <PredictiveField
          label="Buyer types"
          hint="Type who you sell to (e.g. “gym”, “hospital”, “distributor”) — options appear as you type."
          value={buyerTypes}
          onChange={setBuyerTypes}
          suggestions={buyerSuggestions}
          placeholder="Distributors, Retailers, Hospitals…"
          aiContext={{
            field: 'buyers',
            description: businessInfo.description,
            catalogCategories: catalogCats.length ? catalogCats : businessInfo.primaryCategories,
          }}
        />
        <PredictiveField
          label="Target countries"
          hint="Start typing a country name — matching markets appear."
          value={countries}
          onChange={setCountries}
          suggestions={countrySuggestions}
          placeholder="United Arab Emirates, Germany"
          aiContext={{
            field: 'markets',
            description: businessInfo.description,
            catalogCategories: catalogCats,
          }}
        />
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
        <p className="section-label mb-1.5">Buying Signal Rules</p>
        <p className="text-[13px] text-ink-muted leading-relaxed mb-3">
          Optional. These are examples of timing the agent may look for on a qualified site (expansion, sourcing, a new line). A company is not a hot lead just because it matches a product keyword.
        </p>
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

// ── Integrations Section ─────────────────────────────────────────────────────

type SheetsStatus =
  | { connected: true; spreadsheet_title: string; url: string }
  | { connected: false; reason: string };

function IntegrationsSection({
  onRestoredFromSheets,
}: {
  onRestoredFromSheets?: (payload: {
    company?: BusinessInfo;
    products?: Product[];
    prospects?: Prospect[];
    activeBusinessId?: string;
  }) => void | Promise<void>;
}) {
  const [status, setStatus] = useState<SheetsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [restoreOptions, setRestoreOptions] = useState<
    Array<{ companyName: string; productsTab?: string; leadsTab?: string }>
  >([]);
  const [restoreCompany, setRestoreCompany] = useState('');
  const [includeLeads, setIncludeLeads] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreMsg, setRestoreMsg] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch('/api/sheets/status');
      if (r.ok) {
        const data = await r.json();
        setStatus(data);
        if (data.connected) {
          const opts = await apiFetch('/api/sheets/restore-options');
          if (opts.ok) {
            const body = await opts.json();
            const companies = Array.isArray(body.companies) ? body.companies : [];
            setRestoreOptions(companies);
            if (companies.length && !restoreCompany) {
              setRestoreCompany(companies[0].companyName);
            }
          }
        }
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleRestore = async () => {
    if (!restoreCompany || restoring) return;
    const ok = window.confirm(
      includeLeads
        ? `Restore catalog and leads for “${restoreCompany}” from Google Sheets into this company?`
        : `Restore the product catalog for “${restoreCompany}” from Google Sheets into this company?`,
    );
    if (!ok) return;
    setRestoring(true);
    setRestoreMsg('');
    try {
      const resp = await apiFetch('/api/sheets/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: restoreCompany,
          include_products: true,
          include_leads: includeLeads,
          replace_products: true,
          replace_leads: includeLeads,
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || `Restore failed (${resp.status})`);
      }
      const data = await resp.json();
      setRestoreMsg(
        `Restored company “${data.company?.name || restoreCompany}” with ${data.productsRestored || 0} products`
        + (includeLeads ? ` and ${data.leadsRestored || 0} leads` : '')
        + `.`,
      );
      if (onRestoredFromSheets) {
        await onRestoredFromSheets({
          company: data.company,
          products: data.products,
          prospects: data.prospects,
          activeBusinessId: data.activeBusinessId,
        });
      }
    } catch (e) {
      setRestoreMsg(e instanceof Error ? e.message : 'Restore failed');
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Google Sheets card */}
      <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-[14px] font-semibold text-ink">Google Sheets</h3>
            <p className="text-[12.5px] text-ink-secondary mt-0.5">
              Optional export of catalog and leads. The live product database is Postgres in production — Sheets is backup, not the source of truth.
            </p>
          </div>
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-ink-secondary" />
          ) : status?.connected ? (
            <span className="flex items-center gap-1.5 text-[12px] text-emerald-600 font-medium">
              <CheckCircle2 className="w-4 h-4" /> Connected
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[12px] text-amber-600 font-medium">
              <XCircle className="w-4 h-4" /> Not connected
            </span>
          )}
        </div>

        {status?.connected && (
          <a
            href={status.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[12.5px] text-accent hover:underline"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            {status.spreadsheet_title}
          </a>
        )}

        {!status?.connected && !loading && (
          <div className="space-y-3 pt-1">
            <p className="text-[12.5px] text-ink-secondary leading-relaxed">
              To connect, add these two variables to your <code className="bg-canvas px-1 rounded text-[11.5px]">backend/.env</code> file and restart the server:
            </p>
            <div className="rounded-lg bg-canvas border border-border p-3 font-mono text-[11.5px] text-ink-secondary space-y-1 select-all">
              <div>GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON={"<paste service-account JSON>"}</div>
              <div>GOOGLE_SHEETS_SPREADSHEET_ID={"<your spreadsheet ID>"}</div>
            </div>
            <ol className="text-[12px] text-ink-secondary space-y-1 list-decimal list-inside leading-relaxed">
              <li>Go to <a href="https://console.cloud.google.com/" target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">Google Cloud Console</a> → Create a service account → Download JSON key.</li>
              <li>Enable the <strong>Google Sheets API</strong> and <strong>Google Drive API</strong> in your project.</li>
              <li>Create a new Google Sheet, then share it with the service account email (<em>Editor</em> access).</li>
              <li>Copy the spreadsheet ID from the URL (the long string between <code>/d/</code> and <code>/edit</code>).</li>
              <li>Paste the JSON (as a single line) and the ID into your <code>.env</code>, then restart.</li>
            </ol>
            <button
              onClick={load}
              className="btn-secondary text-[12.5px] py-1.5 px-4"
            >
              Refresh status
            </button>
          </div>
        )}
      </div>

      {status?.connected && restoreOptions.length > 0 && (
        <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
          <div>
            <h3 className="text-[14px] font-semibold text-ink">Restore company from Sheets</h3>
            <p className="text-[12.5px] text-ink-secondary mt-0.5 leading-relaxed">
              Recreates the company in the app (name, website, catalog) from your Sheets tabs. Pick Alwasi Enterprises to bring it back into the sidebar.
            </p>
          </div>
          <div>
            <label className="block text-[12px] font-medium text-ink-secondary mb-1">Company tab</label>
            <select
              value={restoreCompany}
              onChange={e => setRestoreCompany(e.target.value)}
              className="w-full max-w-md border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary bg-panel"
            >
              {restoreOptions.map(opt => (
                <option key={opt.companyName} value={opt.companyName}>
                  {opt.companyName}
                  {opt.productsTab ? ' (products)' : ''}
                  {opt.leadsTab ? ' (leads)' : ''}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-[13px] text-ink-secondary">
            <input
              type="checkbox"
              checked={includeLeads}
              onChange={e => setIncludeLeads(e.target.checked)}
            />
            Also restore leads (usually skip — re-run Discover instead)
          </label>
          <button
            type="button"
            onClick={handleRestore}
            disabled={restoring || !restoreCompany}
            className="px-4 py-1.5 bg-accent hover:bg-accent-hover disabled:opacity-40 text-white text-[13px] font-medium rounded-md transition-colors"
          >
            {restoring ? 'Restoring…' : 'Restore company'}
          </button>
          {restoreMsg && (
            <p className="text-[12.5px] text-ink-secondary">{restoreMsg}</p>
          )}
        </div>
      )}

      {/* What syncs */}
      <div className="rounded-xl border border-border bg-surface p-6">
        <h4 className="text-[13px] font-semibold text-ink mb-3">What gets synced</h4>
        <ul className="space-y-2 text-[12.5px] text-ink-secondary">
          <li className="flex gap-2">
            <span className="text-accent font-bold mt-0.5">→</span>
            <span><strong className="text-ink">Product Catalog</strong> — every time you save your catalog, all products are upserted into a per-company tab (e.g. <em>"Acme — Products"</em>).</span>
          </li>
          <li className="flex gap-2">
            <span className="text-accent font-bold mt-0.5">→</span>
            <span><strong className="text-ink">Prospects</strong> — written to a shared <em>Prospects</em> tab (keyed on website). Stage changes (Qualified → Contacted → Replied, etc.) are recorded in a <em>Timeline</em> tab.</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
