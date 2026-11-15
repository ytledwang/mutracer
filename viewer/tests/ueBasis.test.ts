import { describe, expect, it } from 'vitest';
import { cameraWorldThree, positionOf, ueLocalMatrix } from '../src/engine/ueBasis';

describe('UE stage basis (ported from blender_inner.py)', () => {
  it('places the M2 Front camera at the Three-Y-up world position', () => {
    const ue = ueLocalMatrix({
      position: [-0.04418734735240421, -5.921519541671659, 0.9732134751511868],
      rotation_euler: [0, 0, 90],
    }, false);
    const three = cameraWorldThree(ue);
    const pos = positionOf(three);
    expect(pos[0]).toBeCloseTo(-0.04418734735240421, 6);
    expect(pos[1]).toBeCloseTo(-5.921519541671659, 6);
    expect(pos[2]).toBeCloseTo(-0.9732134751511872, 6);
  });
});
