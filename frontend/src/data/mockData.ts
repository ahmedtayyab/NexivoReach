import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog } from '../types';

export const initialBusinessInfo: BusinessInfo = {
  id: 'biz-apex-1',
  name: 'Apex Fitness Equipment',
  website: 'https://apexfitnessequipment.example.com',
  description: 'We manufacture commercial gym equipment in Sialkot, Pakistan and export heavy-duty strength and cardio solutions mainly to the Gulf Cooperation Council (GCC) markets. Our flagship line includes power racks, cable crossovers, olympic benches, commercial treadmills, and urethane dumbbell sets.',
  targetMarkets: ['United Arab Emirates', 'Saudi Arabia', 'Qatar', 'Kuwait', 'Oman'],
  primaryCategories: ['Commercial Strength', 'Free Weights', 'Cardio Equipment', 'Custom Facility Outfitting'],
  extractedByAi: true,
};

export const initialProducts: Product[] = [
  {
    id: 'prod-1',
    name: 'Commercial Heavy-Duty Power Rack',
    category: 'Commercial Strength',
    description: '3x3" 11-gauge steel uprights with laser-cut numbering, integrated multi-grip pull-up bar, and heavy-duty safety spotter arms.',
    price: '$1,850 - $2,400',
    moq: '5 Units',
    specs: ['11-gauge steel tube', '1000kg weight capacity', 'Custom powder coat finishing', 'Band pegs included'],
    targetBuyer: 'Commercial Gyms, University Sports Complexes, Hotel Fitness Centers',
    features: ['Modular expansion attachments', 'Integrated plate storage', 'Laser-cut pin holes'],
    productUrl: 'https://apexfitnessequipment.example.com/products/power-rack',
    aiExtracted: true,
    verifiedByUser: true,
  },
  {
    id: 'prod-2',
    name: 'Dual-Stack Cable Crossover',
    category: 'Commercial Strength',
    description: 'Selectorized dual-weight stack cable crossover with 18 vertical pulley positions and multi-angle grip station.',
    price: '$3,200',
    moq: '2 Units',
    specs: ['2x 100kg weight stacks', 'Aviation grade steel cables', 'Smooth sealed bearings'],
    targetBuyer: 'Commercial Gym Chains, Boutique Fitness Studios',
    features: ['360-degree swivel pulley heads', 'Quick-adjust pop pin system'],
    productUrl: 'https://apexfitnessequipment.example.com/products/cable-crossover',
    aiExtracted: true,
    verifiedByUser: true,
  },
  {
    id: 'prod-3',
    name: 'Pro Series Commercial Treadmill T9',
    category: 'Cardio Equipment',
    description: 'Heavy-duty 5.0 HP AC drive commercial treadmill with 21.5-inch HD touchscreen, self-lubricating belt, and 20% incline.',
    price: '$2,900',
    moq: '3 Units',
    specs: ['5.0 HP AC Commercial Motor', '22x60 inch running deck', 'Speed up to 24 km/h'],
    targetBuyer: 'Hotels, High-traffic Fitness Clubs',
    features: ['Impact absorption deck', 'Telemetry heart rate monitoring', 'Virtual run landscapes'],
    productUrl: 'https://apexfitnessequipment.example.com/products/treadmill-t9',
    aiExtracted: true,
    verifiedByUser: true,
  },
  {
    id: 'prod-4',
    name: 'Urethane Dumbbell Set (2.5kg - 50kg)',
    category: 'Free Weights',
    description: 'Solid steel CPU urethane coated dumbbells with hard chrome ergonomic handles and high-visibility laser embossed weight markings.',
    price: '$4,100 / full rack set',
    moq: '1 Complete Set',
    specs: ['CPU high-grade urethane', 'Welded single-piece construction', '5kg increments'],
    targetBuyer: 'Commercial Gyms, Crossfit Boxes, Luxury Hotel Gyms',
    features: ['Odorless CPU polyurethane', 'Anti-roll CPU endcap design'],
    productUrl: 'https://apexfitnessequipment.example.com/products/urethane-dumbbells',
    aiExtracted: true,
    verifiedByUser: true,
  }
];

export const initialICP: IdealCustomerProfile = {
  targetBuyerTypes: ['Commercial Gym Chains', 'Independent Fitness Clubs', 'Hotel & Resort Gyms', 'Sports Distributors'],
  targetCountries: ['United Arab Emirates', 'Saudi Arabia', 'Qatar'],
  companySize: 'Medium',
  minDealSize: '$15,000',
  shippingMarkets: ['GCC Sea Freight', 'Air Cargo'],
  salesConstraints: ['Requires direct manufacturer pricing', 'Prefers custom laser logo branding', 'Needs short lead time (<30 days)'],
  buyingSignals: [
    { id: 'sig-1', name: 'New Location Opening', description: 'Company announced a new facility or branch opening within the next 3-6 months.', weight: 20 },
    { id: 'sig-2', name: 'Facility Renovation', description: 'Mentions upgrading equipment, expanding floor space, or remodeling existing gym.', weight: 20 },
    { id: 'sig-3', name: 'Active Hiring for Trainers/Staff', description: 'Job posts for general managers, head fitness coaches, or facility directors.', weight: 15 },
    { id: 'sig-4', name: 'Supplier Transition Signal', description: 'Customer complaints or web updates indicating older gym equipment replacement.', weight: 15 }
  ]
};

export const initialProspects: Prospect[] = [
  {
    id: 'prospect-1',
    companyName: 'ABC Fitness Dubai',
    website: 'https://abcfitness-dubai.example.com',
    location: 'Business Bay, Dubai, UAE',
    industry: 'Commercial Fitness Club',
    companySize: '50-100 Employees (3 Locations)',
    fitScore: 94,
    fitBreakdown: {
      industryFit: 25,
      locationFit: 20,
      productMatch: 20,
      buyingSignals: 19,
      companyFit: 10,
    },
    whyThisProspect: 'ABC Fitness operates 3 high-volume commercial facilities in Dubai. They recently announced a 15,000 sq ft flagship expansion in Business Bay opening next quarter, creating immediate demand for heavy-duty power racks and dual cable stacks.',
    buyingSignals: [
      {
        signal: 'New Flagship Location Announced',
        whyItMatters: 'Indicates immediate need for new commercial equipment procurement prior to grand opening.',
        sourceUrl: 'https://gulfbusiness-news.example.com/abc-fitness-dubai-expansion',
        sourceExcerpt: 'ABC Fitness is investing AED 4.5 million into its new 15,000 sq ft flagship health club in Business Bay, set to open in Q4.'
      },
      {
        signal: 'Facility Equipment Upgrade Notice',
        whyItMatters: 'Existing locations are refreshing free weight areas with high-durability urethane dumbbells.',
        sourceUrl: 'https://abcfitness-dubai.example.com/blog/upgrades',
        sourceExcerpt: 'We are upgrading our strength zones across all branches with commercial-grade power racks and heavy dumbbells.'
      }
    ],
    productFit: [
      { productName: 'Commercial Heavy-Duty Power Rack', fitLevel: 'High', reasoning: 'New 15,000 sq ft facility requires 8-10 power racks for peak-hour member throughput.' },
      { productName: 'Dual-Stack Cable Crossover', fitLevel: 'High', reasoning: 'Key feature request for functional training area in new location.' },
      { productName: 'Urethane Dumbbell Set (2.5kg - 50kg)', fitLevel: 'High', reasoning: 'Matches their public commitment to upgrade strength zones.' },
      { productName: 'Pro Series Commercial Treadmill T9', fitLevel: 'Medium', reasoning: 'Cardio floor expansion planned for secondary phase.' }
    ],
    recommendedApproach: 'Lead with custom-branded heavy-duty Power Racks and direct factory pricing from Sialkot with short GCC transit times.',
    outreachDraft: {
      id: 'out-1',
      subject: 'Custom Power Racks for ABC Fitness Business Bay Opening',
      body: `Hi Marcus,

I saw the recent announcement regarding ABC Fitness's new 15,000 sq ft flagship facility in Business Bay — congratulations on the expansion!

Given your emphasis on premium strength zones across Dubai, I thought you might be interested in Apex Fitness Equipment. We manufacture heavy-duty 11-gauge commercial power racks and dual cable stacks directly for GCC commercial operators. 

Because we manufacture in-house and ship directly to Dubai, we deliver factory pricing with custom laser logo branding and quick 14-day GCC delivery times.

Would you be open to reviewing a quick spec sheet for your Business Bay floor plan?

Best regards,
Apex Sales Team`,
      personalizedReason: 'Personalized using ABC Fitness\'s recent Business Bay flagship expansion press release and their explicit emphasis on upgraded strength equipment.',
      status: 'Draft',
      createdAt: '2026-09-01T10:38:00Z'
    },
    stage: 'Qualified',
    discoveredAt: '2026-09-01T10:32:00Z',
    agentTimeline: [
      { time: '10:32', action: 'Discovered company via UAE commercial fitness search query' },
      { time: '10:34', action: 'Researched website and extracted Business Bay expansion announcement' },
      { time: '10:35', action: 'Identified 2 strong buying signals (New location + Equipment upgrade notice)' },
      { time: '10:36', action: 'Matched 4 catalog products (3 High Fit, 1 Medium Fit)' },
      { time: '10:37', action: 'Calculated fit score: 94/100 (Transparent Breakdown)' },
      { time: '10:38', action: 'Drafted personalized outreach (Pending Human Approval)' }
    ]
  },
  {
    id: 'prospect-2',
    companyName: 'PrimeFit UAE',
    website: 'https://primefit-uae.example.com',
    location: 'Abu Dhabi, UAE',
    industry: 'Independent Gym Chain',
    companySize: '20-50 Employees (2 Locations)',
    fitScore: 88,
    fitBreakdown: {
      industryFit: 25,
      locationFit: 20,
      productMatch: 18,
      buyingSignals: 15,
      companyFit: 10,
    },
    whyThisProspect: 'PrimeFit operates two high-end boutique performance centers in Abu Dhabi and has posted hiring ads for strength coaches, signalling facility capacity expansion.',
    buyingSignals: [
      {
        signal: 'Active Hiring for Head Strength Coach',
        whyItMatters: 'Indicates increased member registration and load on current strength stations.',
        sourceUrl: 'https://linkedin.com/jobs/primefit-strength-coach',
        sourceExcerpt: 'PrimeFit Abu Dhabi is hiring two Head Strength & Conditioning Coaches to manage growing athletic roster.'
      }
    ],
    productFit: [
      { productName: 'Commercial Heavy-Duty Power Rack', fitLevel: 'High', reasoning: 'Boutique strength coaching model relies on dedicated power rack stations.' },
      { productName: 'Urethane Dumbbell Set (2.5kg - 50kg)', fitLevel: 'High', reasoning: 'Replacing worn free weight sets in main Abu Dhabi branch.' }
    ],
    recommendedApproach: 'Offer custom powder-coat finishing matching PrimeFit\'s brand colors with low minimum order quantities.',
    outreachDraft: {
      id: 'out-2',
      subject: 'Custom Color Power Racks & Dumbbell Sets for PrimeFit Abu Dhabi',
      body: `Hi Tariq,

Noticed PrimeFit's recent growth and new strength coach additions in Abu Dhabi. 

At Apex Fitness, we specialize in supplying boutique fitness centers with custom-finished 11-gauge commercial power racks and CPU urethane dumbbells. We offer custom color powder-coating and laser logo engraving without long lead times.

Would it make sense to send over our product catalog for your Abu Dhabi facility?

Best regards,
Apex Sales Team`,
      personalizedReason: 'Personalized based on PrimeFit\'s active coach hiring in Abu Dhabi and focus on custom brand aesthetics.',
      status: 'Draft',
      createdAt: '2026-09-01T11:15:00Z'
    },
    stage: 'Researched',
    discoveredAt: '2026-09-01T11:00:00Z',
    agentTimeline: [
      { time: '11:00', action: 'Discovered company via Abu Dhabi performance gym query' },
      { time: '11:08', action: 'Researched website and job postings' },
      { time: '11:12', action: 'Calculated fit score: 88/100' },
      { time: '11:15', action: 'Drafted personalized outreach' }
    ]
  },
  {
    id: 'prospect-3',
    companyName: 'Elite Fitness Group Riyadh',
    website: 'https://elitefitness-sa.example.com',
    location: 'Riyadh, Saudi Arabia',
    industry: 'Commercial Health Club Chain',
    companySize: '100-250 Employees (6 Locations)',
    fitScore: 91,
    fitBreakdown: {
      industryFit: 25,
      locationFit: 20,
      productMatch: 20,
      buyingSignals: 16,
      companyFit: 10,
    },
    whyThisProspect: 'Major health club network in KSA opening 2 new women-only and men-only facilities in Riyadh as part of Saudi Vision 2030 sports initiatives.',
    buyingSignals: [
      {
        signal: 'Saudi Vision 2030 Sports Expansion Project',
        whyItMatters: 'Large capital allocation for multi-facility gym outfitting in Riyadh.',
        sourceUrl: 'https://saudibusiness.example.com/elite-fitness-riyadh-expansion',
        sourceExcerpt: 'Elite Fitness Group secures expansion funding for 2 new state-of-the-art wellness centers in Riyadh.'
      }
    ],
    productFit: [
      { productName: 'Pro Series Commercial Treadmill T9', fitLevel: 'High', reasoning: 'Large cardio floor layout requires 15+ heavy-duty commercial treadmills.' },
      { productName: 'Dual-Stack Cable Crossover', fitLevel: 'High', reasoning: 'Standard equipment package for both new Riyadh centers.' }
    ],
    recommendedApproach: 'Pitch bulk shipment package including AC commercial treadmills and cable stations with GCC warranty coverage.',
    outreachDraft: {
      id: 'out-3',
      subject: 'Direct Factory Equipment Package for Elite Fitness Riyadh Expansion',
      body: `Hi Faisal,

Congratulations on Elite Fitness Group's upcoming expansion project across Riyadh.

We supply top commercial operators in KSA with 5.0 HP AC commercial treadmills and dual cable stacks directly from our manufacturing facilities. By shipping directly to Riyadh, we provide significant cost savings and direct manufacturer warranty support.

Could I share our GCC commercial project portfolio with your procurement team?

Best regards,
Apex Sales Team`,
      personalizedReason: 'Personalized using Elite Fitness Group\'s funding announcement for two new wellness centers in Riyadh.',
      status: 'Draft',
      createdAt: '2026-09-01T12:05:00Z'
    },
    stage: 'New',
    discoveredAt: '2026-09-01T11:50:00Z',
    agentTimeline: [
      { time: '11:50', action: 'Discovered company via KSA health club expansion scan' },
      { time: '12:00', action: 'Researched Saudi Vision 2030 news mentions' },
      { time: '12:05', action: 'Drafted personalized outreach' }
    ]
  }
];

export const initialAgentLogs: AgentRunLog[] = [
  {
    id: 'run-101',
    timestamp: '2026-09-01 10:32:00',
    task: 'Find commercial gyms in UAE that are likely to need new equipment',
    durationMs: 4250,
    toolsUsed: ['WebSearchTool', 'SiteScraperTool', 'SignalDetectorTool', 'ProductMatcherTool', 'ScoreCalculatorTool'],
    sourcesCount: 12,
    status: 'Completed',
    decisions: [
      {
        step: 1,
        observation: 'Received target request: Commercial gyms in UAE needing new equipment.',
        decision: 'Query web search API for recent gym openings, renovations, and commercial fitness clubs in Dubai and Abu Dhabi.',
        toolCalled: 'WebSearchTool',
        toolResultSnippet: 'Discovered 12 candidate companies including ABC Fitness Dubai, PrimeFit UAE, and Urban Strength.'
      },
      {
        step: 2,
        observation: '12 companies discovered. Need deeper site inspection for buying signals.',
        decision: 'Scrape public press release pages and website about pages for ABC Fitness Dubai.',
        toolCalled: 'SiteScraperTool',
        toolResultSnippet: 'Retrieved press release: "ABC Fitness announces 15,000 sq ft flagship health club in Business Bay opening Q4."'
      },
      {
        step: 3,
        observation: 'Extracted text content from ABC Fitness press release.',
        decision: 'Analyze text against ICP buying signal definitions.',
        toolCalled: 'SignalDetectorTool',
        toolResultSnippet: 'Detected 2 signals: "New Location Opening" (Score +20) and "Equipment Upgrade Notice" (Score +20).'
      },
      {
        step: 4,
        observation: 'Company requires heavy-duty strength equipment for 15,000 sq ft space.',
        decision: 'Match catalog items from Apex Fitness Equipment against buyer profile.',
        toolCalled: 'ProductMatcherTool',
        toolResultSnippet: 'Matched 3 High-Fit products (Power Rack, Cable Crossover, Urethane Dumbbells) and 1 Medium-Fit product (Treadmill T9).'
      },
      {
        step: 5,
        observation: 'Product match and signal evidence assembled.',
        decision: 'Run transparent fit scoring formula.',
        toolCalled: 'ScoreCalculatorTool',
        toolResultSnippet: 'Calculated 94/100 (Industry: 25/25, Location: 20/20, Product: 20/20, Signals: 19/20, Company Fit: 10/15).'
      }
    ]
  }
];
