import { describe, expect, it } from 'vitest';
import { finalLookMaterial, isCadDebugName } from '../src/engine/finalLook';

// Mirrors tools/dual-track/blender/blender_inner.py material_override defaults.
describe('finalLookMaterial (viewer port of 提交渲染 material_override)', () => {
  it('turns saturated CAD debug solids into near-white plastic', () => {
    const look = finalLookMaterial({ name: 'solid_ff9900.006', master: 'M_Opaque_Master', base_color_rgb: [1, 0.6, 0] }, 'x', 0, 0);
    // 0.97 grey, then the low interior lift (0.30) like blender_inner.py: 0.97 + 0.3 * 0.03
    expect(look.color[0]).toBeCloseTo(0.979);
    expect(look.roughness).toBe(0.45);
    expect(look.metalness).toBe(0);
    expect(isCadDebugName('006')).toBe(true);
  });

  it('maps Haier CMF drawer faces to pearl albedo with lacquer', () => {
    const look = finalLookMaterial({ name: '01珍珠米', master: 'Haier_CMF_01', base_color_rgb: [0.3, 0.31, 0.28] }, '门体-13_Default', 0, -0.5);
    expect(look.color[0]).toBeCloseTo(0.88);
    expect(look.metalness).toBe(0.02);
    expect(look.lacquer).toBe(true);
  });

  it('lifts interior plastics more above the split height and adds emission', () => {
    const upper = finalLookMaterial({ name: 'Plastic', master: 'M_Opaque_Master', base_color_rgb: [0.5, 0.5, 0.5] }, 'x', 0, 0.5);
    const lower = finalLookMaterial({ name: 'Plastic', master: 'M_Opaque_Master', base_color_rgb: [0.5, 0.5, 0.5] }, 'x', 0, 0.1);
    expect(upper.color[0]).toBeCloseTo(0.8);
    expect(lower.color[0]).toBeCloseTo(0.65);
    expect(upper.emit).toBeCloseTo(0.04);
    expect(lower.emit).toBe(0);
  });

  it('uses side-specific door edge values', () => {
    const left = finalLookMaterial({ name: '11', master: 'M_Opaque_Master', base_color_rgb: [0.5, 0.5, 0.5] }, '门体-51_Default', -1, 0);
    const right = finalLookMaterial({ name: '11', master: 'M_Opaque_Master', base_color_rgb: [0.5, 0.5, 0.5] }, '门体-51_Default', 1, 0);
    expect(left.color[0]).toBeCloseTo(0.22);
    expect(right.color[0]).toBe(0);
  });

  it('metal masters default to 0.85 metalness, glass caps roughness', () => {
    expect(finalLookMaterial({ name: 'MI_Metal', master: 'M_Opaque_Metal_Parent', base_color_rgb: [0.3, 0.3, 0.3] }, 'x', 0, 0).metalness).toBe(0.85);
    const glass = finalLookMaterial({ name: 'Glass_Clear', master: 'M_Glass_Default_Parent' }, 'x', 0, 0);
    expect(glass.glass).toBe(true);
    expect(glass.roughness).toBeLessThanOrEqual(0.1);
  });
});
