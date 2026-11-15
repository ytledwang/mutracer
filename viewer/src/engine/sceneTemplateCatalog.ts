/** Catalog rules for the scene-template panel (F2). */

/** Official RF kitchen shell — keep this id; mark 不可验收 when the GLB is absent. */
export const OFFICIAL_KITCHEN_REPLACE_ID = 'ccdaa114-cdb7-4ef5-af26-022938a780d5';

/** Local M2 fridge-kitchen fixture replace_id (never substitute for the official id). */
export const M2_REPLACE_ID = 'c83a2f4a-0a3d-4494-8da9-37e6ca6943a7';

export type TemplateAcceptance = 'ok' | 'unavailable' | 'unusable';

export interface CatalogTemplate {
  id: number;
  type: string;
  name: string;
  replace_id: string | null;
  data_bucket_url: string;
}

export function templateAcceptance(t: Pick<CatalogTemplate, 'replace_id'>): TemplateAcceptance {
  if (!t.replace_id) return 'unusable';
  if (t.replace_id === OFFICIAL_KITCHEN_REPLACE_ID) return 'unavailable';
  return 'ok';
}

export function templateBadge(state: TemplateAcceptance): string {
  if (state === 'ok') return 'replace_id';
  if (state === 'unavailable') return '不可验收';
  return '不可用';
}
