use glam::{EulerRot, Mat4, Quat};
use mutracer_native_probe::api::{
    Camera, ConvergeOptions, DisplaySettings, Engine, EngineOptions, Render, RenderSettings,
    RenderSize, ToneMapping,
};
use mutracer_native_probe::scene_api::{ImportedScene, Light, Scene, Texture, TexturePixels};
use serde_json::{Map, Value};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};

type Result<T> = std::result::Result<T, String>;

static CAD_OVERRIDE_LOGGED: AtomicUsize = AtomicUsize::new(0);

fn stage_to_render() -> Mat4 {
    Mat4::from_cols(
        glam::Vec4::new(1., 0., 0., 0.),
        glam::Vec4::new(0., 0., -1., 0.),
        glam::Vec4::new(0., 1., 0., 0.),
        glam::Vec4::new(0., 0., 0., 1.),
    )
}

fn map_stage_point(p: glam::Vec3) -> glam::Vec3 {
    glam::Vec3::new(p.x, p.z, -p.y)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum StageBasis {
    Stage2Y,
    None,
}

impl StageBasis {
    fn apply_transform(self, transform: Mat4) -> Mat4 {
        match self {
            StageBasis::Stage2Y => stage_to_render() * transform,
            StageBasis::None => transform,
        }
    }

    fn apply_point(self, point: glam::Vec3) -> glam::Vec3 {
        match self {
            StageBasis::Stage2Y => map_stage_point(point),
            StageBasis::None => point,
        }
    }

    fn up(self) -> glam::Vec3 {
        match self {
            StageBasis::Stage2Y => glam::Vec3::Y,
            StageBasis::None => glam::Vec3::Z,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CameraMode {
    Matrix,
    LookAt,
}

struct MaterialOverride {
    name: String,
    master: String,
    color: Option<[f32; 3]>,
    roughness: Option<f32>,
    metalness: Option<f32>,
    normal_scale: Option<f32>,
    roughness_texture: Option<PathBuf>,
    normal_texture: Option<PathBuf>,
    basecolor_texture: Option<PathBuf>,
}

fn is_cad_debug_name(name: &str) -> bool {
    name.starts_with("solid_")
        || ((3..=8).contains(&name.len()) && name.chars().all(|char| char.is_ascii_hexdigit()))
        || (!name.is_empty() && name.chars().all(|char| char.is_ascii_digit()))
}

#[derive(Clone, Copy, Debug)]
struct RenderJob {
    width: u32,
    height: u32,
    samples: u32,
    bounces: u32,
    denoise: bool,
    light_scale: f32,
    timeout_ms: u64,
}

#[derive(Clone, Debug)]
struct StageCamera {
    camera: Camera,
    display: DisplaySettings,
}

fn parse_args() -> Result<(Args, RenderJob)> {
    let mut args = Args {
        scene: PathBuf::new(),
        out: PathBuf::new(),
        view: None,
        asset_map: None,
        camera_target: "0,0,0".into(),
        tone_mapping: "agx".into(),
        camera_mode: CameraMode::LookAt,
        basis: StageBasis::None,
    };
    let mut job = RenderJob {
        width: 0,
        height: 0,
        samples: 32,
        bounces: 3,
        denoise: true,
        light_scale: 1.,
        timeout_ms: 600_000,
    };
    let values = std::env::args().skip(1).collect::<Vec<_>>();
    let mut i = 0;
    while i < values.len() {
        let key = values[i].as_str();
        let value = values.get(i + 1).map(String::as_str);
        let next_value = value.ok_or_else(|| format!("{key} requires a value"))?;
        i += 1;
        match key {
            "--scene" => args.scene = PathBuf::from(next_value),
            "--out" => args.out = PathBuf::from(next_value),
            "--view" => args.view = Some(next_value.to_string()),
            "--asset-map" => args.asset_map = Some(PathBuf::from(next_value)),
            "--camera-target" => args.camera_target = next_value.to_string(),
            "--camera-mode" => {
                args.camera_mode = match next_value {
                    "matrix" => CameraMode::Matrix,
                    "lookat" => CameraMode::LookAt,
                    _ => return Err("--camera-mode must be matrix or lookat".into()),
                }
            }
            "--basis" => {
                args.basis = match next_value {
                    "stage2y" => StageBasis::Stage2Y,
                    "none" => StageBasis::None,
                    _ => return Err("--basis must be stage2y or none".into()),
                }
            }
            "--tone-mapping" => args.tone_mapping = next_value.to_string(),
            "--width" => job.width = parse_u32(value, "--width")?,
            "--height" => job.height = parse_u32(value, "--height")?,
            "--samples" => job.samples = parse_u32(value, "--samples")?,
            "--bounces" => job.bounces = parse_u32(value, "--bounces")?,
            "--denoise" => job.denoise = parse_bool(value, "--denoise")?,
            "--light-scale" => job.light_scale = parse_f32(value, "--light-scale")?,
            "--timeout-ms" => job.timeout_ms = parse_u64(value, "--timeout-ms")?,
            _ => return Err(format!("unknown option {key}")),
        }
        i += 1;
    }
    if !args.scene.as_os_str().is_empty() && !args.out.as_os_str().is_empty() {
        Ok((args, job))
    } else {
        Err("usage: mutracer-render --scene <task.json> --out <render.png> [options]".into())
    }
}

struct Args {
    scene: PathBuf,
    out: PathBuf,
    view: Option<String>,
    asset_map: Option<PathBuf>,
    camera_target: String,
    camera_mode: CameraMode,
    basis: StageBasis,
    tone_mapping: String,
}

fn parse_u32(value: Option<&str>, name: &'static str) -> Result<u32> {
    value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be an integer"))
}

fn parse_u64(value: Option<&str>, name: &'static str) -> Result<u64> {
    value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be an integer"))
}

fn parse_f32(value: Option<&str>, name: &'static str) -> Result<f32> {
    let value: f32 = value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be a number"))?;
    value
        .is_finite()
        .then_some(value)
        .ok_or_else(|| format!("{name} must be finite"))
}

fn parse_bool(value: Option<&str>, name: &'static str) -> Result<bool> {
    match value.ok_or_else(|| format!("{name} requires a value"))? {
        "1" | "true" => Ok(true),
        "0" | "false" => Ok(false),
        _ => Err(format!("{name} must be 0, 1, true or false")),
    }
}

fn number(value: Option<&Value>, default: f32) -> f32 {
    value
        .and_then(Value::as_f64)
        .map(|v| v as f32)
        .unwrap_or(default)
}

fn vector(value: Option<&Value>, default: [f32; 3]) -> [f32; 3] {
    let mut result = default;
    if let Some(Value::Array(items)) = value {
        for (slot, item) in result.iter_mut().zip(items) {
            if let Some(number) = item.as_f64() {
                *slot = number as f32;
            }
        }
    }
    result
}

fn local_matrix(entity: Option<&Value>) -> Mat4 {
    let Some(entity) = entity else {
        return Mat4::IDENTITY;
    };
    let translation = vector(entity.get("position"), [0.; 3]);
    let scale = vector(entity.get("scale"), [1.; 3]);
    let degrees = vector(entity.get("rotation_euler"), [0.; 3]);
    let rotation = Quat::from_euler(
        EulerRot::XYZ,
        degrees[0].to_radians(),
        degrees[1].to_radians(),
        degrees[2].to_radians(),
    );
    Mat4::from_scale_rotation_translation(scale.into(), rotation, translation.into())
}

fn visible_mesh_transforms(scene: &Value, basis: StageBasis) -> Vec<(String, Mat4)> {
    let models = scene
        .get("models")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let roots = models
        .iter()
        .filter(|(_, entity)| entity.get("type").and_then(Value::as_str) == Some("root"))
        .map(|(id, _)| id.clone())
        .collect::<Vec<_>>();
    let mut transforms = Vec::new();
    let mut visited = std::collections::BTreeSet::new();
    for root in roots {
        walk_model(
            scene,
            &models,
            &root,
            Mat4::IDENTITY,
            &mut visited,
            &mut transforms,
        );
    }
    transforms
        .into_iter()
        .map(|(mesh_id, transform)| (mesh_id, basis.apply_transform(transform)))
        .collect()
}

fn walk_model(
    scene: &Value,
    models: &Map<String, Value>,
    id: &str,
    parent: Mat4,
    visited: &mut std::collections::BTreeSet<String>,
    output: &mut Vec<(String, Mat4)>,
) {
    if !visited.insert(id.into()) {
        return;
    }
    let Some(entity) = models.get(id) else { return };
    if entity.get("is_visible").and_then(Value::as_bool) == Some(false) {
        return;
    }
    let transform = parent * local_matrix(Some(entity));
    if entity.get("type").and_then(Value::as_str) == Some("model") {
        if let Some(mesh) = entity.get("mesh").and_then(Value::as_str) {
            output.push((mesh.into(), transform));
        }
    }
    for child in entity
        .get("children")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(child) = child.as_str() {
            walk_model(scene, models, child, transform, visited, output);
        }
    }
}

fn mesh_url<'a>(scene: &'a Value, mesh_id: &'a str) -> Option<&'a str> {
    scene
        .get("meshes")
        .and_then(Value::as_object)
        .and_then(|meshes| meshes.get(mesh_id))
        .and_then(|mesh| mesh.get("url"))
        .and_then(Value::as_str)
}

fn load_texture(path: &Path, rgba32f: bool) -> Result<Texture> {
    let image = image::open(path).map_err(|e| format!("Loading {}: {e}", path.display()))?;
    if rgba32f {
        let rgba = image.into_rgba32f();
        let pixels: Vec<f32> = rgba
            .pixels()
            .flat_map(|pixel| [pixel.0[0], pixel.0[1], pixel.0[2], pixel.0[3]])
            .collect();
        Ok(Texture {
            pixels: TexturePixels::Rgba32F(pixels.into()),
            width: rgba.width(),
            height: rgba.height(),
            ..Texture::rgba8(1, 1, [0; 4])
        })
    } else {
        let rgba8 = image.into_rgba8();
        let pixels = rgba8.pixels().flat_map(|p| p.0).collect::<Vec<_>>();
        Ok(Texture::rgba8(rgba8.width(), rgba8.height(), pixels))
    }
}

fn merge_imported(
    target: &mut Scene,
    imported: ImportedScene,
    transform: Mat4,
    mesh_id: &str,
    override_materials: Option<&[MaterialOverride]>,
    log_count: &mut usize,
) -> Result<usize> {
    let mut textures = HashMap::new();
    let mut geometries = HashMap::new();
    let mut materials = HashMap::new();

    for ids in imported.names.geometries.values() {
        for id in ids {
            let geometry = imported
                .scene
                .geometry(*id)
                .map_err(|e| e.to_string())?
                .clone();
            let new = target.add_geometry(geometry).map_err(|e| e.to_string())?;
            geometries.insert(*id, new);
        }
    }
    let mut imported_materials = imported
        .names
        .materials
        .values()
        .flatten()
        .copied()
        .collect::<Vec<_>>();
    imported_materials.sort_unstable();
    for (material_index, id) in imported_materials.into_iter().enumerate() {
        let mut material = imported
            .scene
            .material(id)
            .map_err(|e| e.to_string())?
            .clone();
        for slot in material.textures.iter_mut() {
            if let Some(old) = *slot {
                let new = match textures.get(&old) {
                    Some(&new) => new,
                    None => {
                        let texture = imported
                            .scene
                            .texture(old)
                            .map_err(|e| e.to_string())?
                            .clone();
                        let new = target.add_texture(texture).map_err(|e| e.to_string())?;
                        textures.insert(old, new);
                        new
                    }
                };
                *slot = Some(new);
            }
        }
        let new = target.add_material(material).map_err(|e| e.to_string())?;
        materials.insert(id, new);
        if let Some(override_material) = override_materials.and_then(|overrides| {
            if overrides.is_empty() {
                None
            } else {
                Some(&overrides[material_index.min(overrides.len() - 1)])
            }
        }) {
            override_imported_material(target, new, override_material, mesh_id, log_count)?;
        }
    }
    let mut mesh_count = 0;
    for ids in imported.names.meshes.values() {
        for id in ids {
            let mut mesh = imported.scene.mesh(*id).map_err(|e| e.to_string())?.clone();
            let geometry = geometries
                .get(&mesh.geometry)
                .ok_or("Imported geometry missing")?;
            mesh.geometry = *geometry;
            mesh.material = *materials
                .get(&mesh.material)
                .ok_or("Imported material missing")?;
            for material in mesh.materials.iter_mut() {
                *material = *materials.get(material).ok_or("Imported material missing")?;
            }
            mesh.transform = transform * mesh.transform;
            target.add_mesh(mesh).map_err(|e| e.to_string())?;
            mesh_count += 1;
        }
    }
    Ok(mesh_count)
}

fn override_imported_material(
    target: &mut Scene,
    id: mutracer_native_probe::scene_api::MaterialId,
    override_material: &MaterialOverride,
    mesh_id: &str,
    log_count: &mut usize,
) -> Result<()> {
    let material = target.material_mut(id).map_err(|e| e.to_string())?;
    material.values.name = override_material.name.clone();
    if let Some(color) = override_material.color {
        material.values.color = color;
    }
    if let Some(roughness) = override_material.roughness {
        material.values.roughness = roughness;
    }
    if let Some(metalness) = override_material.metalness {
        material.values.metalness = metalness;
    }
    if let Some(normal_scale) = override_material.normal_scale {
        material.values.normal_scale = normal_scale;
    }
    if override_material.master.contains("Glass") {
        material.values.transmission = 0.9;
        material.values.roughness = material.values.roughness.min(0.1);
    }
    material.textures = [None; 9];
    let load = |target: &mut Scene, path: Option<&PathBuf>| -> Result<Option<_>> {
        let Some(path) = path else { return Ok(None) };
        let rgba32f = path
            .extension()
            .and_then(|extension| extension.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("exr"));
        let texture = load_texture(path, rgba32f)?;
        Ok(Some(
            target.add_texture(texture).map_err(|e| e.to_string())?,
        ))
    };
    let basecolor = load(target, override_material.basecolor_texture.as_ref())?;
    let normal = load(target, override_material.normal_texture.as_ref())?;
    let roughness = load(target, override_material.roughness_texture.as_ref())?;
    let material = target.material_mut(id).map_err(|e| e.to_string())?;
    material.textures[0] = basecolor;
    material.textures[1] = normal;
    material.textures[4] = roughness;
    let is_frosted = override_material.master.contains("Frosted")
        || override_material.master.contains("MetalFingerprints");
    if is_frosted && *log_count < 5 {
        *log_count += 1;
        eprintln!(
            "frosted override: mesh={mesh_id} material={} color={:?} rough={:.3} metal={:.3} normal={} roughness_map={}",
            material.values.name,
            material.values.color,
            material.values.roughness,
            material.values.metalness,
            material.textures[1].is_some(),
            material.textures[4].is_some(),
        );
    }
    Ok(())
}

fn texture_url<'a>(scene: &'a Value, texture_id: &str) -> Option<&'a str> {
    scene
        .get("textures")
        .and_then(Value::as_object)
        .and_then(|textures| textures.get(texture_id))
        .and_then(|texture| texture.get("urls").or(texture.get("url")))
        .and_then(Value::as_str)
}

fn material_override(
    scene: &Value,
    assets: &HashMap<String, String>,
    material_id: &str,
) -> Result<Option<MaterialOverride>> {
    let Some(entity) = scene
        .get("materials")
        .and_then(Value::as_object)
        .and_then(|materials| materials.get(material_id))
    else {
        return Ok(None);
    };
    let master = entity
        .get("master")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let name = entity
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let mut color = entity
        .get("base_color_rgb")
        .and_then(Value::as_array)
        .map(|rgb| vector(Some(&Value::Array(rgb.clone())), [0.8; 3]));
    let mut roughness = if entity.get("roughness_scalar").is_some() {
        Some(number(entity.get("roughness_scalar"), 0.5).clamp(0., 1.))
    } else if master.contains("Haier_CMF")
        && entity.get("roughness_min_scalar").is_none()
        && entity.get("roughness_max_scalar").is_none()
    {
        Some(0.35)
    } else {
        Some(
            ((number(entity.get("roughness_min_scalar"), 0.5)
                + number(entity.get("roughness_max_scalar"), 0.5))
                / 2.)
                .clamp(0., 1.),
        )
    };
    let mut metalness = if entity.get("metallic_scalar").is_some() {
        Some(number(entity.get("metallic_scalar"), 0.).clamp(0., 1.))
    } else {
        Some(if master.contains("Metal") { 0.85 } else { 0. })
    };
    let mut override_master = master.clone();
    if is_cad_debug_name(&name) {
        color = color.filter(|rgb| {
            let [red, green, blue] = *rgb;
            red.max(green).max(blue) - red.min(green).min(blue) <= 0.35
        });
        color.get_or_insert([0.92, 0.92, 0.92]);
        roughness = Some(0.45);
        metalness = Some(0.);
        override_master = "Plastic".into();
        let logged = CAD_OVERRIDE_LOGGED.fetch_add(1, Ordering::Relaxed);
        if logged < 3 {
            eprintln!(
                "cad debug override: material={name} master={master} color={:?}",
                color.unwrap()
            );
        }
    }
    let normal_scale = entity
        .get("normal_intensity_scalar")
        .map(|_| number(entity.get("normal_intensity_scalar"), 1.));
    let texture_path = |field: &str| -> Result<Option<PathBuf>> {
        let Some(texture_id) = entity.get(field).and_then(Value::as_str) else {
            return Ok(None);
        };
        if texture_id.is_empty() {
            return Ok(None);
        }
        let Some(url) = texture_url(scene, texture_id) else {
            return Ok(None);
        };
        let path = assets
            .get(url)
            .ok_or_else(|| format!("Missing asset for {url}"))?;
        Ok(Some(PathBuf::from(path)))
    };
    Ok(Some(MaterialOverride {
        name,
        master: override_master,
        color,
        roughness,
        metalness,
        normal_scale,
        roughness_texture: texture_path("roughness_tex")?,
        normal_texture: texture_path("normal_tex")?,
        basecolor_texture: texture_path("basecolor_tex")?,
    }))
}

fn override_material(
    scene: &Value,
    mesh_id: &str,
    assets: &HashMap<String, String>,
) -> Result<Option<Vec<MaterialOverride>>> {
    let material_ids = scene
        .get("meshes")
        .and_then(Value::as_object)
        .and_then(|meshes| meshes.get(mesh_id))
        .and_then(|mesh| mesh.get("materials"))
        .and_then(Value::as_array)
        .map(|materials| {
            materials
                .iter()
                .filter_map(Value::as_str)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if material_ids.is_empty() {
        return Ok(None);
    }
    let mut overrides = Vec::new();
    for material_id in material_ids {
        overrides.extend(material_override(scene, assets, material_id)?);
    }
    Ok((!overrides.is_empty()).then_some(overrides))
}

fn stage_camera(
    scene: &Value,
    view: Option<&Value>,
    camera_target: glam::Vec3,
    camera_mode: CameraMode,
    basis: StageBasis,
) -> Result<StageCamera> {
    let cameras = scene.get("cameras").and_then(Value::as_object);
    let active = view
        .and_then(|view| view.get("active_camera"))
        .and_then(Value::as_str);
    let entity = cameras
        .and_then(|cameras| active.and_then(|id| cameras.get(id)))
        .or_else(|| {
            cameras.and_then(|cameras| {
                cameras
                    .values()
                    .find(|c| c.get("type").and_then(Value::as_str) == Some("camera"))
            })
        });
    let entity = entity.ok_or("No camera entity found")?;
    let settings = entity.get("camera").ok_or("Camera settings missing")?;
    let width = entity
        .get("frame_size")
        .and_then(Value::as_array)
        .and_then(|v| v.first())
        .and_then(Value::as_f64)
        .unwrap_or(1920.) as f32;
    let height = entity
        .get("frame_size")
        .and_then(Value::as_array)
        .and_then(|v| v.get(1))
        .and_then(Value::as_f64)
        .unwrap_or(1080.) as f32;
    let fov_horizontal = number(settings.get("fov"), 45.).to_radians();
    let fov_vertical = 2. * ((fov_horizontal / 2.).tan() * height / width).atan();
    let mut camera = Camera::default();
    camera.fov = fov_vertical.to_degrees();
    camera.f_stop = if settings.get("dof").and_then(Value::as_bool) == Some(true) {
        number(settings.get("aperture_fstop"), 0.)
    } else {
        0.
    };
    camera.focus_distance = number(settings.get("focal_distance"), 1.).max(0.1);
    camera.world_matrix = match camera_mode {
        CameraMode::Matrix => basis.apply_transform(local_matrix(Some(entity))),
        CameraMode::LookAt => {
            let p = vector(entity.get("position"), [0.; 3]);
            let eye = basis.apply_point(glam::Vec3::from(p));
            let target = basis.apply_point(camera_target);
            Mat4::look_at_rh(eye, target, basis.up()).inverse()
        }
    }
    .to_cols_array();

    let post = settings.get("post_processing_settings");
    let mut display = DisplaySettings::default();
    display.tone_mapping = ToneMapping::Agx;
    display.tone_mapping_exposure = number(post.and_then(|p| p.get("exposure")), 1.);
    display.contrast = number(post.and_then(|p| p.get("contrast")), 1.);
    display.saturation = number(post.and_then(|p| p.get("saturation")), 1.);
    display.vignette = number(post.and_then(|p| p.get("vignette")), 0.).clamp(0., 1.);
    Ok(StageCamera { camera, display })
}

fn add_environment(
    scene: &mut Scene,
    source: &Value,
    view: Option<&Value>,
    assets: &HashMap<String, String>,
) -> Result<()> {
    let env_id = view
        .and_then(|v| v.get("active_environment"))
        .and_then(Value::as_str);
    let env = env_id.and_then(|id| {
        source
            .get("environments")
            .and_then(Value::as_object)
            .and_then(|map| map.get(id))
    });
    let settings = env.and_then(|e| e.get("settings"));
    let intensity = number(settings.and_then(|s| s.get("hdri_brightness")), 1.);
    let hdri_angle = number(settings.and_then(|s| s.get("hdri_angle")), 0.).to_radians();
    let background_type = settings
        .and_then(|s| s.get("background_type"))
        .and_then(Value::as_str)
        .unwrap_or("white");
    let texture_id = settings
        .and_then(|s| s.get("image"))
        .and_then(Value::as_str);
    let url = texture_id
        .and_then(|id| {
            source
                .get("textures")
                .and_then(Value::as_object)
                .and_then(|map| map.get(id))
        })
        .and_then(|texture| texture.get("urls").or(texture.get("url")))
        .and_then(Value::as_str);
    let mut environment_settings = mutracer_native_probe::scene_api::EnvironmentSettings::default();
    let mut environment = mutracer_native_probe::scene_api::Environment::default();
    if background_type == "white" {
        if let Some(path) = url.and_then(|u| assets.get(u).map(String::as_str)) {
            let texture = load_texture(Path::new(path), true)?;
            let id = scene.add_texture(texture).map_err(|e| e.to_string())?;
            environment.texture = Some(id);
        }
        let mut texture = Texture::rgba8(1, 1, [255, 255, 255, 255]);
        texture.pixels = TexturePixels::Rgba32F([1., 1., 1., 1.].into());
        let id = scene.add_texture(texture).map_err(|e| e.to_string())?;
        environment.background = Some(id);
        environment_settings.background_intensity = 1.;
    } else if let Some(path) = url.and_then(|u| assets.get(u).map(String::as_str)) {
        let texture = load_texture(Path::new(path), true)?;
        let id = scene.add_texture(texture).map_err(|e| e.to_string())?;
        environment.texture = Some(id);
        environment.background = Some(id);
    } else {
        let mut texture = Texture::rgba8(1, 1, [231, 231, 231, 255]);
        texture.pixels = TexturePixels::Rgba32F([0.9, 0.9, 0.9, 1.].into());
        let id = scene.add_texture(texture).map_err(|e| e.to_string())?;
        environment.texture = Some(id);
        environment.background = Some(id);
    }
    environment_settings.intensity = intensity;
    if background_type != "white" {
        environment_settings.background_intensity = intensity;
    }
    environment_settings.rotation = -hdri_angle;
    environment_settings.background_rotation = -hdri_angle;
    scene
        .set_environment(environment)
        .map_err(|e| e.to_string())?;
    scene
        .set_environment_settings(environment_settings)
        .map_err(|e| e.to_string())
}

fn add_lights(
    scene: &mut Scene,
    source: &Value,
    view: Option<&Value>,
    job: RenderJob,
    basis: StageBasis,
) -> Result<()> {
    let lights = source
        .get("lights")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let roots = lights
        .iter()
        .filter(|(_, entity)| entity.get("type").and_then(Value::as_str) == Some("root"))
        .map(|(id, _)| id.clone())
        .collect::<Vec<_>>();
    let mut visited = std::collections::BTreeSet::new();
    for root in roots {
        walk_light(
            scene,
            &lights,
            &root,
            Mat4::IDENTITY,
            view,
            job,
            basis,
            &mut visited,
        )?;
    }
    Ok(())
}

fn walk_light(
    scene: &mut Scene,
    lights: &Map<String, Value>,
    id: &str,
    parent: Mat4,
    view: Option<&Value>,
    job: RenderJob,
    basis: StageBasis,
    visited: &mut std::collections::BTreeSet<String>,
) -> Result<()> {
    if !visited.insert(id.into()) {
        return Ok(());
    }
    let Some(entity) = lights.get(id) else {
        return Ok(());
    };
    if entity.get("is_visible").and_then(Value::as_bool) == Some(false) {
        return Ok(());
    }
    let transform = parent * local_matrix(Some(entity));
    if entity.get("type").and_then(Value::as_str) == Some("light") {
        let data = entity.get("light").ok_or("Light settings missing")?;
        let color = vector(data.get("color"), [1.; 3]);
        let intensity = number(data.get("power"), 0.) * job.light_scale;
        let light = match data.get("type").and_then(Value::as_str) {
            Some("area_light") => Light::Rect {
                color,
                intensity,
                width: number(data.get("size_x"), 0.) / 100.,
                height: number(data.get("size_z"), 0.) / 100.,
                spread: 0.,
                transform: basis.apply_transform(transform),
                texture: None,
            },
            Some("point_light") => Light::Sphere {
                color,
                intensity,
                radius: (number(data.get("radius"), 0.) / 100.).max(0.01),
                transform: basis.apply_transform(transform),
            },
            Some("directional_light") => Light::Directional {
                color,
                intensity,
                transform: basis.apply_transform(transform),
            },
            Some("spot_light") => {
                let outer = number(data.get("spot_size"), 45.).clamp(0.1, 89.9);
                let blend = number(data.get("blend"), 0.).clamp(0., 1.);
                Light::Spot {
                    color,
                    intensity,
                    inner: outer * blend,
                    outer,
                    transform: basis.apply_transform(transform),
                    ies: Vec::new().into(),
                }
            }
            _ => {
                return Err(format!(
                    "Unsupported light type {}",
                    data.get("type").unwrap_or(&Value::Null)
                ));
            }
        };
        scene.add_light(light).map_err(|e| e.to_string())?;
    }
    for child in entity
        .get("children")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(child) = child.as_str() {
            walk_light(scene, lights, child, transform, view, job, basis, visited)?;
        }
    }
    Ok(())
}

fn build_scene(
    source: &Value,
    assets: &HashMap<String, String>,
    basis: StageBasis,
) -> Result<Scene> {
    let mut scene = Scene::new();
    let mut mesh_count = 0;
    let mut log_count = 0;
    for (mesh_id, transform) in visible_mesh_transforms(source, basis) {
        let url = mesh_url(source, &mesh_id).ok_or_else(|| format!("Mesh {mesh_id} has no URL"))?;
        let path = assets
            .get(url)
            .ok_or_else(|| format!("Missing asset for {url}"))?;
        let imported =
            Scene::import_gltf(path).map_err(|e| format!("Importing {url}: {}", e.message))?;
        let override_material = override_material(source, &mesh_id, assets)?;
        mesh_count += merge_imported(
            &mut scene,
            imported,
            transform,
            &mesh_id,
            override_material.as_ref().map(|v| &**v),
            &mut log_count,
        )?;
    }
    if mesh_count == 0 {
        return Err("No visible meshes were imported".into());
    }
    Ok(scene)
}

fn selected_view(scene: &Value, view: Option<&str>) -> Result<Option<Value>> {
    let Some(view) = view else { return Ok(None) };
    scene
        .get("views")
        .and_then(Value::as_object)
        .and_then(|views| views.get(view))
        .cloned()
        .map(Some)
        .ok_or_else(|| format!("View {view} not found"))
}

fn tone_mapping_from_arg(arg: &str) -> Result<ToneMapping> {
    match arg {
        "agx" => Ok(ToneMapping::Agx),
        "aces" => Ok(ToneMapping::Aces),
        "cineon" => Ok(ToneMapping::Cineon),
        "reinhard" => Ok(ToneMapping::Reinhard),
        "linear" => Ok(ToneMapping::Linear),
        _ => Err(format!("Unsupported tone mapping {arg}")),
    }
}

fn main() -> Result<()> {
    let (args, job) = parse_args()?;
    let raw =
        fs::read(&args.scene).map_err(|e| format!("Reading {}: {e}", args.scene.display()))?;
    let data: Value =
        serde_json::from_slice(&raw).map_err(|e| format!("Parsing scene JSON: {e}"))?;
    let source = data.get("scene_json").unwrap_or(&data);
    let assets = match args.asset_map.as_ref() {
        Some(path) => {
            let raw = fs::read(path).map_err(|e| format!("Reading asset map: {e}"))?;
            serde_json::from_slice(&raw).map_err(|e| format!("Parsing asset map: {e}"))?
        }
        None => HashMap::new(),
    };
    let target_parts = args
        .camera_target
        .split(',')
        .map(|part| part.trim().parse::<f32>())
        .collect::<std::result::Result<Vec<_>, _>>()
        .map_err(|_| "--camera-target must be x,y,z")?;
    let camera_target = match target_parts[..] {
        [x, y, z] => glam::Vec3::new(x, y, z),
        _ => return Err("--camera-target must contain three numbers".into()),
    };
    let view = selected_view(source, args.view.as_deref())?;
    let mut camera = stage_camera(
        source,
        view.as_ref(),
        camera_target,
        args.camera_mode,
        args.basis,
    )?;
    camera.display.tone_mapping = tone_mapping_from_arg(&args.tone_mapping)?;
    let mut scene = build_scene(source, &assets, args.basis)?;
    add_environment(&mut scene, source, view.as_ref(), &assets)?;
    add_lights(&mut scene, source, view.as_ref(), job, args.basis)?;

    let engine = Engine::new(EngineOptions::default()).map_err(|e| e.to_string())?;
    engine
        .display()
        .set_settings(camera.display)
        .map_err(|e| e.to_string())?;
    engine.set_scene_object(&scene).map_err(|e| e.to_string())?;
    engine.update().map_err(|e| e.to_string())?;
    let render = Render::new(
        &engine,
        RenderSettings {
            size: RenderSize::Fixed {
                width: job.width,
                height: job.height,
            },
            max_samples: job.samples,
            bounces: job.bounces.clamp(1, 20),
            ..Default::default()
        },
    )
    .map_err(|e| e.to_string())?;
    if job.denoise {
        render
            .set_denoiser(Default::default())
            .map_err(|e| e.to_string())?;
    }
    let options = ConvergeOptions {
        camera: Some(camera.camera),
        timeout_ms: job.timeout_ms,
        ..ConvergeOptions::new(job.samples)
    };
    render.converge(options).map_err(|e| e.to_string())?;
    let png = engine
        .display()
        .encode_png(&render)
        .map_err(|e| e.to_string())?;
    if let Some(parent) = args.out.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Creating {}: {e}", parent.display()))?;
    }
    fs::write(&args.out, png).map_err(|e| format!("Writing {}: {e}", args.out.display()))?;
    println!(
        "rendered {}x{} {} spp -> {}",
        job.width,
        job.height,
        job.samples,
        args.out.display()
    );
    Ok(())
}
