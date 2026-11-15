/**
 * Viewer port of tools/dual-track/blender/blender_inner.py `material_override`
 * (calibrated defaults), so 实时查看 / 高质量预览 resolve the same albedo /
 * roughness / metalness as 提交渲染. Keep in sync with blender_inner.py.
 * Not ported: per-pixel flakes, textures, height-ramped emission (approximated).
 */
import type { StageMaterial } from './sceneJson';

export const FINAL_LOOK = {
  drawerPearlAlbedo: 0.88,
  charcoalAlbedo: 0.015,
  edgeLeft: { albedo: 0.22, roughness: 0.4, metalness: 0.3 },
  edgeRight: { albedo: 0, roughness: 0.45, metalness: 0 },
  interiorLift: 0.6,
  interiorLiftLow: 0.3,
  interiorEmit: 0.04,
  interiorSplitY: 0.3,
} as const;

const DOOR_EDGE_MESHES = new Set([
  '门体-51_Default', '门体-52_Default', '门体-53_Default', '门体-58_Default',
  '门体-62_Default', '门体-64_Default', '门体-76_Default', '门体-79_Default',
]);

export interface FinalLookParams {
  color: [number, number, number];
  roughness: number;
  metalness: number;
  glass: boolean;
  lacquer: boolean;
  emit: number;
}

export function isCadDebugName(name: string): boolean {
  return name.startsWith('solid_')
    || (name.length >= 3 && name.length <= 8 && /^[0-9a-fA-F]+$/.test(name))
    || (!!name && /^[0-9]+$/.test(name));
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** side / height: camera-space x / y of the instance bounding-box centre (view camera). */
export function finalLookMaterial(material: StageMaterial, meshName: string, side: number, height: number): FinalLookParams {
  const name = String(material.name ?? '');
  let master = String(material.master ?? '');
  const base = material.base_color_rgb;
  let color: [number, number, number] = Array.isArray(base) && base.length >= 3
    ? [base[0], base[1], base[2]] : [0.8, 0.8, 0.8];
  const isGlass = master.includes('Glass');
  const glassRough = num(material.glass_roughness_scalar);
  const roughScalar = num(material.roughness_scalar);
  const rMin = num(material.roughness_min_scalar);
  const rMax = num(material.roughness_max_scalar);
  let roughness: number;
  if (isGlass && glassRough !== null) roughness = clamp01(glassRough);
  else if (roughScalar !== null) roughness = clamp01(roughScalar);
  else if (master.startsWith('Haier_CMF') && rMin === null && rMax === null) roughness = 0.35;
  else roughness = clamp01(((rMin ?? 0.5) + (rMax ?? 0.5)) / 2);
  const metalScalar = num(material.metallic_scalar);
  let metalness = metalScalar !== null ? clamp01(metalScalar) : (master.includes('Metal') ? 0.85 : 0);
  if (isCadDebugName(name)) {
    const chroma = Math.max(...color) - Math.min(...color);
    if (chroma > 0.35) color = [0.97, 0.97, 0.97];
    roughness = 0.45;
    metalness = 0;
    master = 'Plastic';
  }
  const frosted = name.includes('Frosted') || master.includes('Frosted');
  if (isGlass && !frosted) roughness = Math.min(roughness, 0.1);
  else if (isGlass) roughness = Math.max(roughness, 0.3);
  let lacquer = false;
  if (master.startsWith('Haier_CMF')) {
    const lum = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2];
    const drawerFace = meshName.startsWith('门体-')
      && (name.includes('星蕴银') || name.includes('矿石银') || name.includes('珍珠米') || (lum >= 0.25 && lum < 0.75));
    if (drawerFace) {
      const a = FINAL_LOOK.drawerPearlAlbedo;
      color = [a, a, a * 0.995];
      metalness = 0.02;
      roughness = 0.35;
    } else if (lum < 0.35) {
      roughness = Math.max(roughness, 0.25);
    }
    lacquer = true;
    if (lum >= 0.5) metalness = Math.min(metalness, 0.3);
  }
  let charcoal = false;
  if (name.includes('钣金喷粉')) {
    const a = FINAL_LOOK.charcoalAlbedo;
    color = [a, a, a * 1.1];
    roughness = 0.45;
    metalness = 0.12;
    charcoal = true;
  }
  if (DOOR_EDGE_MESHES.has(meshName)
    && (name.includes('钣金喷粉') || name.includes('Plastic_Coated') || name.includes('Plastic_Rough') || name === '11')) {
    const e = side < 0 ? FINAL_LOOK.edgeLeft : FINAL_LOOK.edgeRight;
    color = [e.albedo, e.albedo, e.albedo * 1.1];
    roughness = e.roughness;
    metalness = e.metalness;
    charcoal = true;
  }
  if (charcoal) lacquer = false;
  const upper = height > FINAL_LOOK.interiorSplitY;
  const lift = upper ? FINAL_LOOK.interiorLift : FINAL_LOOK.interiorLiftLow;
  const interior = lift > 0 && !charcoal && !isGlass && !master.startsWith('Haier_CMF') && !DOOR_EDGE_MESHES.has(meshName);
  let emit = 0;
  if (interior) {
    color = color.map((c) => Math.min(1, c + lift * (1 - c))) as [number, number, number];
    if (upper) emit = FINAL_LOOK.interiorEmit;
  }
  return { color, roughness, metalness, glass: isGlass, lacquer, emit };
}
