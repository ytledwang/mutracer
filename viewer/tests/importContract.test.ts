import { describe, expect, it } from 'vitest';
import { checkGltfJson, contractSummary } from '../src/engine/importContract';

const good = {
  nodes: [
    { name: 'Door_Pivot', children: [1] },
    { name: 'Fridge_Door', mesh: 0 },
    { name: 'Cam_Front', camera: 0 },
    { name: 'Product_Slot', extras: { replace_id: 'f1-named-pivot-placeholder' } },
  ],
  meshes: [{ name: 'Fridge_Door', primitives: [{ material: 0 }] }],
  materials: [{ name: 'Fridge_White' }],
  cameras: [{ name: 'Cam_Front' }],
};

describe('checkGltfJson', () => {
  it('passes a named-material + Pivot fixture', () => {
    const report = checkGltfJson(good);
    expect(report.errors).toEqual([]);
    expect(report.warnings).toEqual([]);
    expect(contractSummary(report)).toBeNull();
  });

  it('fails a flattened palette GLB', () => {
    const report = checkGltfJson({
      nodes: [
        { mesh: 0 },
        { camera: 0 },
      ],
      meshes: [{ primitives: [{ material: 0 }] }],
      materials: [{ name: 'PaletteMaterial001' }],
    });
    expect(report.errors.some((i) => i.code === 'node.unnamed')).toBe(true);
    expect(report.errors.some((i) => i.code === 'material.palette')).toBe(true);
    expect(report.infos.some((i) => i.code === 'pivot.absent')).toBe(true);
    const summary = contractSummary(report)!;
    expect(summary).toMatch(/unnamed/i);
    expect(summary).toMatch(/palette/i);
    expect(summary).toMatch(/Pivot/);
  });

  it('flags meshes with no materials', () => {
    const report = checkGltfJson({
      nodes: [{ name: 'Box', mesh: 0 }],
      meshes: [{ name: 'Box', primitives: [{}] }],
      materials: [],
    });
    expect(report.errors.some((i) => i.code === 'material.missing' || i.code === 'material.none')).toBe(true);
  });
});
