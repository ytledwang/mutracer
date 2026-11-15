// Import contract for glTF/GLB: names are the contract.
// Pure JSON checks, no Three.js, so tests can run without a renderer.

export type ContractSeverity = 'error' | 'warning' | 'info';

export interface ContractIssue {
  code: string;
  severity: ContractSeverity;
  message: string;
}

export interface ContractReport {
  errors: ContractIssue[];
  warnings: ContractIssue[];
  infos: ContractIssue[];
}

const GENERIC_NODE = /^(Node|Mesh|Object|Empty|Cube|Cylinder|Sphere|Icosphere)([._\s-]?\d+)?$/i;
const GENERIC_MESH = /^(Mesh|Geometry)([._\s-]?\d+)?$/i;
const GENERIC_MAT = /^(Material|DefaultMaterial|Default)([._\s-]?\d+)?$/i;
const PALETTE_MAT = /^PaletteMaterial/i;
const PIVOT = /pivot/i;

type GltfNode = {
  name?: string;
  mesh?: number;
  camera?: number;
  children?: number[];
  extras?: { replace_id?: string; replaceId?: string };
};
type GltfMesh = { name?: string; primitives?: { material?: number }[] };
type GltfMaterial = { name?: string };
type GltfDoc = {
  nodes?: GltfNode[];
  meshes?: GltfMesh[];
  materials?: GltfMaterial[];
  cameras?: { name?: string }[];
};

const nameOf = (item?: { name?: string }) => (item?.name ?? '').trim();

function push(report: ContractReport, severity: ContractSeverity, code: string, message: string) {
  report[severity === 'error' ? 'errors' : severity === 'warning' ? 'warnings' : 'infos']
    .push({ code, severity, message });
}

/** Structural contract checks used by the viewer after a GLB/glTF parse. */
export function checkGltfJson(json: GltfDoc): ContractReport {
  const report: ContractReport = { errors: [], warnings: [], infos: [] };
  const nodes = json.nodes ?? [];
  const meshes = json.meshes ?? [];
  const materials = json.materials ?? [];

  let pivots = 0;
  const seen = new Map<string, number>();
  nodes.forEach((node, i) => {
    const name = nameOf(node);
    const hasPayload = node.mesh !== undefined || node.camera !== undefined;
    if (hasPayload && !name) push(report, 'error', 'node.unnamed', `node[${i}] has a mesh/camera but no name`);
    else if (!name && (node.children?.length || hasPayload)) push(report, 'warning', 'node.unnamed', `node[${i}] has no name`);
    if (name && hasPayload && GENERIC_NODE.test(name)) push(report, 'warning', 'node.generic', `node[${i}] has generic name "${name}"`);
    if (name) seen.set(name, (seen.get(name) ?? 0) + 1);
    if (name && PIVOT.test(name)) {
      pivots += 1;
      if (!(node.children && node.children.length) && node.mesh === undefined) {
        push(report, 'error', 'pivot.empty', `pivot node "${name}" has no children and no mesh`);
      }
    }
  });
  for (const [name, count] of seen) {
    if (count > 1) push(report, 'warning', 'node.duplicate', `duplicate node name "${name}" appears ${count} times`);
  }

  meshes.forEach((mesh, i) => {
    const name = nameOf(mesh);
    if (!name) push(report, 'warning', 'mesh.unnamed', `mesh[${i}] has no name`);
    else if (GENERIC_MESH.test(name)) push(report, 'warning', 'mesh.generic', `mesh[${i}] has generic name "${name}"`);
    (mesh.primitives ?? []).forEach((prim, p) => {
      if (prim.material === undefined) {
        push(report, 'error', 'material.missing', `mesh[${i}] primitive[${p}] has no material`);
      }
    });
  });

  let genericOnly = true;
  materials.forEach((mat, i) => {
    const name = nameOf(mat);
    if (!name) {
      push(report, 'error', 'material.unnamed', `material[${i}] has no name`);
      genericOnly = false;
      return;
    }
    if (PALETTE_MAT.test(name)) {
      push(report, 'error', 'material.palette', `material[${i}] name "${name}" looks like a palette merge`);
      genericOnly = false;
    } else if (GENERIC_MAT.test(name)) {
      push(report, 'warning', 'material.generic', `material[${i}] has generic name "${name}"`);
    } else genericOnly = false;
  });
  if (materials.length && genericOnly) {
    push(report, 'warning', 'material.default_only', 'every material uses a generic default name');
  }
  if (!materials.length && meshes.length) {
    push(report, 'error', 'material.none', 'file has meshes but no materials');
  }
  if (!pivots) {
    push(report, 'info', 'pivot.absent', 'no node name contains Pivot');
  }
  return report;
}

export function contractSummary(report: ContractReport): string | null {
  const parts: string[] = [];
  const unnamed = report.errors.filter((i) => i.code === 'node.unnamed').length
    + report.warnings.filter((i) => i.code === 'node.unnamed').length;
  if (unnamed) parts.push(`${unnamed} unnamed mesh/camera node${unnamed === 1 ? '' : 's'}`);
  if (report.errors.some((i) => i.code === 'material.palette')) parts.push('palette material merge');
  if (report.errors.some((i) => i.code === 'material.none' || i.code === 'material.missing')) parts.push('missing materials');
  if (report.warnings.some((i) => i.code === 'material.default_only')) parts.push('all materials are defaults');
  if (report.infos.some((i) => i.code === 'pivot.absent')) parts.push('no Pivot node');
  const leftoverErrors = report.errors.length;
  if (!parts.length && leftoverErrors) parts.push(`${leftoverErrors} contract error${leftoverErrors === 1 ? '' : 's'}`);
  if (!parts.length && report.warnings.length) parts.push(`${report.warnings.length} contract warning${report.warnings.length === 1 ? '' : 's'}`);
  if (!parts.length) return null;
  return `Import contract: ${parts.join(', ')}`;
}
