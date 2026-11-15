"""Run blender_inner.py inside Blender with render.render replaced by a deterministic
fake: writes a fixed raw PNG and dumps a digest of the full scene state at render time.
Cycles Metal is not bit-deterministic run to run, so this proves the DEFAULT path
(no new flags) builds an identical scene and identical post output.
blender --background --factory-startup --python default_identity_probe.py -- INNER.py STATE.json <inner args...>"""
import bpy, json, sys, types, hashlib
import numpy

argv = sys.argv[sys.argv.index("--") + 1:]
inner, state_path, inner_args = argv[0], argv[1], argv[2:]
real_ops = bpy.ops


def digest_scene():
    sc = bpy.context.scene
    st = {"view": {k: getattr(sc.view_settings, k) for k in ("view_transform", "look", "exposure", "gamma")},
          "render": {k: getattr(sc.render, k) for k in ("resolution_x", "resolution_y", "film_transparent", "engine")},
          "image": {k: getattr(sc.render.image_settings, k) for k in ("file_format", "color_mode")},
          "cycles": {"samples": sc.cycles.samples, "denoise": sc.cycles.use_denoising, "device": sc.cycles.device},
          "objects": [], "lights": [], "world": [], "materials": []}
    for o in sorted(bpy.data.objects, key=lambda o: o.name):
        st["objects"].append([o.name, o.type, [round(v, 6) for row in o.matrix_world for v in row], o.hide_render,
                              o.data.name if o.data else None])
    for l in sorted(bpy.data.lights, key=lambda l: l.name):
        st["lights"].append([l.name, l.type, round(l.energy, 6), list(map(lambda v: round(v, 6), l.color)),
                             round(getattr(l, "size", 0), 6), round(getattr(l, "size_y", 0), 6)])
    w = sc.world
    for n in sorted(w.node_tree.nodes, key=lambda n: n.name):
        vals = [(i.name, list(i.default_value) if hasattr(i.default_value, "__len__") else i.default_value)
                for i in n.inputs if hasattr(i, "default_value") and not i.is_linked]
        st["world"].append([n.name, n.bl_idname, str(vals), getattr(getattr(n, "image", None), "filepath", None)])
    st["world_links"] = sorted(f"{l.from_node.name}.{l.from_socket.name}->{l.to_node.name}.{l.to_socket.name}" for l in w.node_tree.links)
    for m in sorted(bpy.data.materials, key=lambda m: m.name):
        if not m.use_nodes: continue
        sig = []
        for n in sorted(m.node_tree.nodes, key=lambda n: n.name):
            sig.append([n.name, n.bl_idname, str([(i.name, list(i.default_value) if hasattr(i.default_value, "__len__") else i.default_value)
                                                  for i in n.inputs if hasattr(i, "default_value") and not i.is_linked])])
        sig.append(sorted(f"{l.from_node.name}.{l.from_socket.name}->{l.to_node.name}.{l.to_socket.name}" for l in m.node_tree.links))
        st["materials"].append([m.name, hashlib.sha256(json.dumps(sig, default=str).encode()).hexdigest()])
    return st


calls = []


def fake_render(write_still=True, **kw):
    sc = bpy.context.scene
    calls.append(digest_scene())
    w, h = sc.render.resolution_x, sc.render.resolution_y
    img = bpy.data.images.new("fake_raw", w, h, alpha=True, float_buffer=False)
    yy, xx = numpy.mgrid[0:h, 0:w]
    px = numpy.stack([xx / w, yy / h, ((xx + yy) % 97) / 96.0, numpy.ones_like(xx, float)], -1).astype(numpy.float32)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = sc.render.filepath
    img.file_format = "PNG"
    img.save()


class Ops:
    def __getattr__(self, name):
        if name == "render":
            return types.SimpleNamespace(render=fake_render)
        return getattr(real_ops, name)


bpy.ops = Ops()
sys.argv = [sys.argv[0], "--"] + inner_args
code = compile(open(inner).read(), inner, "exec")
g = {"__name__": "__main__", "__file__": inner}
exec(code, g)
json.dump({"render_calls": calls}, open(state_path, "w"), indent=0, default=str)
print("[probe] wrote", state_path, "render calls", len(calls), flush=True)
