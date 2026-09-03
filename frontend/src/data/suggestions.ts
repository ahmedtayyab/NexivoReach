/** @deprecated Import from './taxonomy' instead. Kept for compatibility. */
export {
  MARKET_SUGGESTIONS,
  toggleCsvValue,
  csvIncludes,
} from './taxonomy';

import { suggestionsForField } from './taxonomy';

export const CATEGORY_SUGGESTIONS = suggestionsForField('categories', '');
export const BUYER_SUGGESTIONS = suggestionsForField('buyers', '');
