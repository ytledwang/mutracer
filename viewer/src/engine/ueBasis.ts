/**
 * Stage scene.json transforms are stored in Unreal-style space.
 * These helpers port tools/dual-track/blender/blender_inner.py
 * (ue_rotation / swap_yz / gltf_to_ue / camera_basis_from_ue / mesh_basis_from_ue)
 * into Three.js Y-up, without touching blender_inner.py itself.
 */
import * as THREE from 'three';

export function matrixFromRows(rows: number[][]): THREE.Matrix4 {
  const r0 = rows[0], r1 = rows[1], r2 = rows[2], r3 = rows[3];
  return new THREE.Matrix4().set(
    r0[0], r0[1], r0[2], r0[3],
    r1[0], r1[1], r1[2], r1[3],
    r2[0], r2[1], r2[2], r2[3],
    r3[0], r3[1], r3[2], r3[3],
  );
}

export function swapYz(): THREE.Matrix4 {
  return matrixFromRows([
    [1, 0, 0, 0],
    [0, 0, 1, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1],
  ]);
}

export function gltfToUe(): THREE.Matrix4 {
  // Stage render default glTF→UE map, UE = (-z, x, y).
  return matrixFromRows([
    [0, 0, -1, 0],
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1],
  ]);
}

export function ueBasisFromView(): THREE.Matrix4 {
  return matrixFromRows([
    [0, 0, -1, 0],
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1],
  ]);
}

export function rotX(degrees: number): THREE.Matrix4 {
  return new THREE.Matrix4().makeRotationX(THREE.MathUtils.degToRad(degrees));
}

/** Blender Z-up world → Three Y-up world. */
export function blenderToThree(): THREE.Matrix4 {
  return rotX(-90);
}

export function ueRotation(eulerDeg?: number[]): THREE.Matrix4 {
  const [rx, ry, rz] = eulerDeg && eulerDeg.length >= 3 ? eulerDeg : [0, 0, 0];
  const roll = THREE.MathUtils.degToRad(rx);
  const pitch = THREE.MathUtils.degToRad(ry);
  const yaw = THREE.MathUtils.degToRad(rz);
  const sr = Math.sin(roll), cr = Math.cos(roll);
  const sp = Math.sin(pitch), cp = Math.cos(pitch);
  const sy = Math.sin(yaw), cy = Math.cos(yaw);
  const columns = [
    [cp * cy, cp * sy, sp],
    [sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp],
    [-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp],
  ];
  return matrixFromRows([
    [columns[0][0], columns[1][0], columns[2][0], 0],
    [columns[0][1], columns[1][1], columns[2][1], 0],
    [columns[0][2], columns[1][2], columns[2][2], 0],
    [0, 0, 0, 1],
  ]);
}

export type UeTransform = {
  position?: number[];
  rotation_euler?: number[];
  scale?: number[];
};

export function ueLocalMatrix(entity: UeTransform | undefined, withScale = true): THREE.Matrix4 {
  const translation = entity?.position && entity.position.length >= 3 ? entity.position : [0, 0, 0];
  const matrix = ueRotation(entity?.rotation_euler);
  const scale = withScale && entity?.scale && entity.scale.length >= 3 ? entity.scale : [1, 1, 1];
  const e = matrix.elements;
  // mathutils: scale columns 0..2, then write translation in the last column.
  for (let row = 0; row < 3; row++) {
    e[row] *= scale[0];
    e[4 + row] *= scale[1];
    e[8 + row] *= scale[2];
  }
  e[12] = translation[0];
  e[13] = translation[1];
  e[14] = translation[2];
  e[15] = 1;
  return matrix;
}

/** Three world matrix for a mesh holder whose children came from GLTFLoader (Y-up glTF). */
export function meshWorldThree(ueWorld: THREE.Matrix4): THREE.Matrix4 {
  return blenderToThree().multiply(swapYz()).multiply(ueWorld).multiply(gltfToUe());
}

/** Three world matrix for a non-mesh group / empty. */
export function groupWorldThree(ueWorld: THREE.Matrix4): THREE.Matrix4 {
  return blenderToThree().multiply(swapYz()).multiply(ueWorld);
}

/** Three world matrix for a stage camera (matches camera_basis_from_ue, then Blender→Three). */
export function cameraWorldThree(ueWorld: THREE.Matrix4): THREE.Matrix4 {
  return blenderToThree().multiply(swapYz()).multiply(ueWorld).multiply(ueBasisFromView());
}

/** Set an object's world matrix, deriving a compensating local matrix if it has a parent. */
export function applyThreeWorld(object: THREE.Object3D, world: THREE.Matrix4) {
  object.matrixAutoUpdate = false;
  if (object.parent) {
    object.parent.updateWorldMatrix(true, false);
    object.matrix.copy(object.parent.matrixWorld).invert().multiply(world);
  } else {
    object.matrix.copy(world);
  }
  object.matrixWorld.copy(world);
}

export function positionOf(matrix: THREE.Matrix4): [number, number, number] {
  const e = matrix.elements;
  return [e[12], e[13], e[14]];
}
