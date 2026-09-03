import React, { useState } from 'react';
import type { Product } from '../types';
import { 
  Package, 
  Globe, 
  Upload, 
  Plus, 
  Sparkles, 
  Edit3, 
  Trash2, 
  ArrowRight,
  FileText,
  FileSpreadsheet
} from 'lucide-react';

interface Props {
  products: Product[];
  onSaveProducts: (products: Product[]) => void;
  onNext: () => void;
}

export default function CatalogView({ products, onSaveProducts, onNext }: Props) {
  const [activeInputMethod, setActiveInputMethod] = useState<'url' | 'file' | 'manual'>('url');
  
  // URL state
  const [urlInput, setUrlInput] = useState<string>('');
  const [isUrlExtracting, setIsUrlExtracting] = useState<boolean>(false);

  // File state
  const [fileName, setFileName] = useState<string>('');
  const [isFileParsing, setIsFileParsing] = useState<boolean>(false);

  // Manual modal / form state
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [showFormModal, setShowFormModal] = useState<boolean>(false);

  // Form fields
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [moq, setMoq] = useState('');
  const [productUrl, setProductUrl] = useState('');
  const [imageUrl, setImageUrl] = useState('');

  const handleUrlExtract = () => {
    if (!urlInput.trim()) return;
    setIsUrlExtracting(true);
    setTimeout(() => {
      const newProduct: Product = {
        id: `prod-url-${Date.now()}`,
        name: 'Sample Product from URL',
        category: 'Uncategorized',
        description: 'Replace this with a real extraction from your catalog URL.',
        productUrl: urlInput,
        sourceUrl: urlInput,
      };
      onSaveProducts([newProduct, ...products]);
      setIsUrlExtracting(false);
    }, 1500);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setIsFileParsing(true);
    setTimeout(() => {
      const newProduct: Product = {
        id: `prod-file-${Date.now()}`,
        name: 'Sample Product from File',
        category: 'Uncategorized',
        description: 'Replace this with a real extraction from your uploaded catalog.',
      };
      onSaveProducts([newProduct, ...products]);
      setIsFileParsing(false);
    }, 1500);
  };

  const handleOpenAddManual = () => {
    setEditingProduct(null);
    setName('');
    setCategory('');
    setDescription('');
    setPrice('');
    setMoq('');
    setProductUrl('');
    setImageUrl('');
    setShowFormModal(true);
  };

  const handleEditProduct = (p: Product) => {
    setEditingProduct(p);
    setName(p.name);
    setCategory(p.category);
    setDescription(p.description);
    setPrice(p.price || '');
    setMoq(p.moq || '');
    setProductUrl(p.productUrl || '');
    setImageUrl(p.imageUrl || '');
    setShowFormModal(true);
  };

  const handleDeleteProduct = (id: string) => {
    onSaveProducts(products.filter(p => p.id !== id));
  };

  const handleSaveForm = (e: React.FormEvent) => {
    e.preventDefault();
    const productData: Product = {
      id: editingProduct ? editingProduct.id : `prod-${Date.now()}`,
      name,
      category,
      description,
      price,
      moq,
      productUrl: productUrl || undefined,
      imageUrl: imageUrl || undefined,
    };

    if (editingProduct) {
      onSaveProducts(products.map(p => p.id === editingProduct.id ? productData : p));
    } else {
      onSaveProducts([productData, ...products]);
    }
    setShowFormModal(false);
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-2">
        <div className="flex items-center space-x-2 text-indigo-400 text-xs font-semibold uppercase tracking-wider">
          <Package className="w-4 h-4" />
          <span>Step 2: Product Catalog & Specifications</span>
        </div>
        <h1 className="text-xl font-bold text-white">Import and Manage Catalog Products</h1>
        <p className="text-xs text-slate-300">
          Provide your products via Website URL, PDF/CSV/Excel upload, or manual entry. AI extracts specs, MOQ, and target buyer profiles for prospect matching.
        </p>
      </div>

      {/* 3 Input Methods Tabs */}
      <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex border-b border-slate-800 space-x-2 pb-3">
          <button
            onClick={() => setActiveInputMethod('url')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
              activeInputMethod === 'url' ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Globe className="w-4 h-4" />
            <span>A. Website URL Scraper</span>
          </button>
          <button
            onClick={() => setActiveInputMethod('file')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
              activeInputMethod === 'file' ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Upload className="w-4 h-4" />
            <span>B. Upload (PDF / CSV / Excel)</span>
          </button>
          <button
            onClick={() => setActiveInputMethod('manual')}
            className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
              activeInputMethod === 'manual' ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Plus className="w-4 h-4" />
            <span>C. Manual Product Entry</span>
          </button>
        </div>

        {/* Input Method Content */}
        {activeInputMethod === 'url' && (
          <div className="flex flex-col sm:flex-row items-center gap-3">
            <input
              type="url"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              placeholder="https://yourcompany.com/products"
              className="flex-1 w-full bg-[#0b101c] border border-slate-700/80 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            />
            <button
              onClick={handleUrlExtract}
              disabled={isUrlExtracting}
              className="w-full sm:w-auto px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center justify-center space-x-2 transition-all whitespace-nowrap shadow-md shadow-indigo-600/20"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{isUrlExtracting ? 'Analyzing Web Page...' : 'Extract Products from URL'}</span>
            </button>
          </div>
        )}

        {activeInputMethod === 'file' && (
          <div className="border-2 border-dashed border-slate-800 hover:border-indigo-500/50 rounded-xl p-6 text-center space-y-3 transition-all bg-[#0b101c]">
            <div className="flex justify-center space-x-3 text-slate-400">
              <FileText className="w-6 h-6 text-rose-400" />
              <FileSpreadsheet className="w-6 h-6 text-emerald-400" />
            </div>
            <p className="text-xs text-slate-300 font-medium">Upload PDF catalog, CSV, or Excel file</p>
            <p className="text-[11px] text-slate-400">NexivoReach automatically extracts product names, specs, MOQ, and pricing.</p>
            <label className="inline-flex items-center space-x-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs font-semibold text-slate-200 cursor-pointer transition-all">
              <Upload className="w-4 h-4 text-indigo-400" />
              <span>{fileName ? fileName : 'Choose PDF/CSV/Excel File'}</span>
              <input type="file" accept=".pdf,.csv,.xlsx,.xls" onChange={handleFileUpload} className="hidden" />
            </label>
            {isFileParsing && <p className="text-xs text-indigo-400 animate-pulse">Parsing document & running AI spec extraction...</p>}
          </div>
        )}

        {activeInputMethod === 'manual' && (
          <div className="flex justify-between items-center bg-[#0b101c] p-4 rounded-lg border border-slate-800">
            <div>
              <p className="text-xs font-medium text-slate-200">Manually Add Catalog Items</p>
              <p className="text-[11px] text-slate-400">Enter custom product details directly</p>
            </div>
            <button
              onClick={handleOpenAddManual}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg flex items-center space-x-2 transition-all shadow-md shadow-indigo-600/20"
            >
              <Plus className="w-4 h-4" />
              <span>Add Product</span>
            </button>
          </div>
        )}
      </div>

      {/* Product List */}
      <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-xs font-semibold text-slate-200 flex items-center space-x-2">
            <span>Product Catalog Items ({products.length})</span>
          </h2>
          <span className="text-[11px] text-slate-400">Products will be matched against target buyer needs</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {products.map((product) => (
            <div key={product.id} className="bg-[#0b101c] border border-slate-800 hover:border-slate-700 rounded-xl p-4 space-y-3 transition-all relative">
              <div className="flex items-start gap-3">
                {product.imageUrl ? (
                  <img
                    src={product.imageUrl}
                    alt={product.name}
                    className="w-14 h-14 rounded object-cover border border-slate-700 shrink-0"
                  />
                ) : (
                  <div className="w-14 h-14 rounded border border-slate-700 bg-slate-900 shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-400 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-800/40">
                    {product.category}
                  </span>
                  <h3 className="font-semibold text-white text-sm mt-1">{product.name}</h3>
                </div>
              </div>

              <p className="text-xs text-slate-300 line-clamp-2">{product.description}</p>

              <div className="grid grid-cols-2 gap-2 text-[11px] bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                <div>
                  <span className="text-slate-400">Price:</span>{' '}
                  <span className="text-slate-200 font-medium">{product.price || 'Contact for Quote'}</span>
                </div>
                <div>
                  <span className="text-slate-400">MOQ:</span>{' '}
                  <span className="text-slate-200 font-medium">{product.moq || 'N/A'}</span>
                </div>
                {product.productUrl && (
                  <div className="col-span-2">
                    <a
                      href={product.productUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-300 hover:underline"
                    >
                      View product page
                    </a>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800/60">
                <button
                  onClick={() => handleEditProduct(product)}
                  className="text-xs text-slate-400 hover:text-slate-200 flex items-center space-x-1 px-2 py-1 rounded hover:bg-slate-800"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  <span>Edit</span>
                </button>
                <button
                  onClick={() => handleDeleteProduct(product.id)}
                  className="text-xs text-rose-400 hover:text-rose-300 flex items-center space-x-1 px-2 py-1 rounded hover:bg-rose-950/40"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Remove</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Continue Button */}
      <div className="flex justify-end">
        <button
          onClick={onNext}
          className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg flex items-center space-x-2 shadow-lg shadow-indigo-600/30 transition-all"
        >
          <span>Save Catalog & Configure Ideal Customer Profile</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {/* Manual / Edit Modal */}
      {showFormModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#121929] border border-slate-700 rounded-xl p-6 max-w-lg w-full space-y-4">
            <h3 className="font-bold text-white text-sm">
              {editingProduct ? 'Edit Catalog Product' : 'Add New Product Manually'}
            </h3>
            <form onSubmit={handleSaveForm} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-300 mb-1">Product Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  required
                  className="w-full bg-[#0b101c] border border-slate-700 rounded p-2 text-slate-200"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-slate-300 mb-1">Category</label>
                  <input
                    type="text"
                    value={category}
                    onChange={e => setCategory(e.target.value)}
                    required
                    className="w-full bg-[#0b101c] border border-slate-700 rounded p-2 text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 mb-1">Price / Range</label>
                  <input
                    type="text"
                    value={price}
                    onChange={e => setPrice(e.target.value)}
                    className="w-full bg-[#0b101c] border border-slate-700 rounded p-2 text-slate-200"
                  />
                </div>
              </div>
              <div>
                <label className="block text-slate-300 mb-1">Description</label>
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  rows={3}
                  required
                  className="w-full bg-[#0b101c] border border-slate-700 rounded p-2 text-slate-200"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-slate-300 mb-1">Minimum Order (MOQ)</label>
                  <input
                    type="text"
                    value={moq}
                    onChange={e => setMoq(e.target.value)}
                    className="w-full bg-[#0b101c] border border-slate-700 rounded p-2 text-slate-200"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 mb-1">Product URL</label>
                  <input
                    type="url"
                    value={productUrl}
                    onChange={e => setProductUrl(e.target.value)}
                    className="w-full bg-[#0b101c] border border-slate-700 rounded p-2 text-slate-200"
                  />
                </div>
              </div>
              <div>
                <label className="block text-slate-300 mb-1">Image URL</label>
                <input
                  type="url"
                  value={imageUrl}
                  onChange={e => setImageUrl(e.target.value)}
                  className="w-full bg-[#0b101c] border border-slate-700 rounded p-2 text-slate-200"
                />
              </div>
              <div className="flex justify-end space-x-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowFormModal(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 text-white rounded font-medium hover:bg-indigo-500"
                >
                  Save Product
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
