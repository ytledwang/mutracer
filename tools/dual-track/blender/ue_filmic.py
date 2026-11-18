"""Opt-in approximation of UE's default post stack for the Blender final track.

Only used when blender_inner.py gets `--tonemap ue-filmic`; the default
(Standard + display_post) path never imports this module.

Order follows UE ColorCorrect + filmic tonemapper on scene-linear radiance:
  exposure (2**EV) -> white balance -> saturation (lerp from luma)
  -> contrast about 0.18: 0.18 * (x / 0.18) ** contrast
  -> pow(x, 1 / gamma) -> gain / offset
  -> ACES fitted filmic curve (Narkowicz) -> sRGB OETF.
Pixels whose alpha is 0 (camera ray hit the white backdrop) are composited
over `background` untouched by the tonemapper, like UE's white background.
"""
import numpy

LUMA = numpy.array([0.2126, 0.7152, 0.0722], dtype=numpy.float32)


def aces_fitted(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return numpy.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0)


def srgb_oetf(x):
    x = numpy.clip(x, 0.0, 1.0)
    return numpy.where(x <= 0.0031308, 12.92 * x, 1.055 * numpy.power(x, 1.0 / 2.4) - 0.055)


def ue_post(rgb, alpha, post, exposure_ev=0.0, background=1.0, scale=1.0):
    """rgb: (N,3) scene-linear float; alpha: (N,) in [0,1]. Returns (N,3) display [0,1]."""
    rgb = numpy.maximum(rgb.astype(numpy.float32) * float(scale) * float(2.0 ** exposure_ev), 0.0)
    temperature = float(post.get("temperature", 6500.0))
    shift = max(-0.5, min(0.5, (6500.0 - temperature) / 6500.0))
    rgb = rgb * numpy.array([1.0 - shift * 0.25, 1.0, 1.0 + shift * 0.25], dtype=numpy.float32)
    luma = (rgb * LUMA).sum(axis=1, keepdims=True)
    rgb = numpy.maximum(luma + (rgb - luma) * float(post.get("saturation", 1.0)), 0.0)
    rgb = 0.18 * numpy.power(rgb / 0.18, float(post.get("contrast", 1.0)))
    rgb = numpy.power(rgb, 1.0 / max(1e-4, float(post.get("gamma", 1.0))))
    rgb = rgb * float(post.get("gain", 1.0)) + float(post.get("offset", 0.0))
    display = srgb_oetf(aces_fitted(rgb))
    a = numpy.clip(alpha.astype(numpy.float32), 0.0, 1.0)[:, None]
    return display * a + float(background) * (1.0 - a)


# ---------------------------------------------------------------------------
# Opt-in `--tonemap ue55`: closer replica of UE 5.5 PostProcessCombineLUTs +
# TonemapCommon.ush FilmToneMap. DOC/RECOLLECTION-SOURCED (engine source is not
# local): constants are UE 5.5 defaults (slope .88, toe .55, shoulder .26,
# black clip 0, white clip .04, blue correction .6, expand gamut omitted,
# tonemapper sharpen omitted). Order:
#   linear sRGB * exposure -> AP1 -> ColorCorrect (AP1 luma, sat/contrast@0.18/
#   gamma/gain/offset) -> blue correct -> FilmToneMap -> inverse blue correct
#   -> AP1->sRGB -> clamp -> sRGB OETF.
_SRGB_2_XYZ = numpy.array([[0.4123907993, 0.3575843394, 0.1804807884],
                           [0.2126390059, 0.7151686788, 0.0721923054],
                           [0.0193308187, 0.1191947798, 0.9505321522]])
_D65_2_D60 = numpy.array([[1.01303, 0.00610531, -0.014971],
                          [0.00769823, 0.998165, -0.00503203],
                          [-0.00284131, 0.00468516, 0.924507]])
_AP1_2_XYZ = numpy.array([[0.6624541811, 0.1340042065, 0.1561876870],
                          [0.2722287168, 0.6740817658, 0.0536895174],
                          [-0.0055746495, 0.0040607335, 1.0103391003]])
_AP0_2_XYZ = numpy.array([[0.9525523959, 0.0, 0.0000936786],
                          [0.3439664498, 0.7281660966, -0.0721325464],
                          [0.0, 0.0, 1.0088251844]])
_BLUE_CORRECT_AP0 = numpy.array([[0.9404372683, -0.0183068787, 0.0778696104],
                                 [0.0083786969, 0.8286599939, 0.1629613092],
                                 [0.0005471261, -0.0008833746, 1.0003362486]])
SRGB_2_AP1 = numpy.linalg.inv(_AP1_2_XYZ) @ _D65_2_D60 @ _SRGB_2_XYZ
AP1_2_SRGB = numpy.linalg.inv(SRGB_2_AP1)
AP1_2_AP0 = numpy.linalg.inv(_AP0_2_XYZ) @ _AP1_2_XYZ
AP0_2_AP1 = numpy.linalg.inv(AP1_2_AP0)
BLUE_CORRECT_AP1 = AP0_2_AP1 @ _BLUE_CORRECT_AP0 @ AP1_2_AP0
BLUE_CORRECT_INV_AP1 = numpy.linalg.inv(BLUE_CORRECT_AP1)
AP1_RGB2Y = _AP1_2_XYZ[1]


LM_PER_W = 683.0  # photometric conversion (CIE 555 nm assumption), matches blender_inner candela mode

# r13: live UE stove front fg 83.73, gold 80.33, r12 engine 126.82.
# Scaling gray by 80.33/126.82 (0.114) only reached displayed fg 101.48, because the
# film curve is not linear. One interpolation of those two points targets the UE frame.
# Provisional until the missing left grate is restored. Contrast pivot stays 0.18.
ENGINE_DISPLAY_GRAY = 0.06779987


def ue55_exposure_scale_engine(bias_ev):
    # Opt-in engine display. Source chain cancels 0.18 into GlobalExposure=2**bias,
    # which predicts ~8.8x over the stove gold and was rejected by the live UE frame.
    return ENGINE_DISPLAY_GRAY * LM_PER_W * (2.0 ** float(bias_ev))


def ue55_exposure_scale(bias_ev):
    # Manual exposure, ApplyPhysicalCameraExposure off: EV100 = -bias,
    # scale = 1 / EV100ToLuminance = 1 / (1.2 * 2**-bias).
    # NOTE (r12): legacy pre-engine-verification scale; superseded by
    # ue55_exposure_scale_engine when --display-units engine is passed.
    return float(2.0 ** float(bias_ev) / 1.2)


def _mul(m, x):
    return x @ m.T


def film_tonemap_ap1(c, slope=0.88, toe=0.55, shoulder=0.26, black=0.0, white=0.04):
    c = numpy.asarray(c, numpy.float64)
    ap0 = _mul(AP1_2_AP0, c)
    r, g, b = ap0[:, 0], ap0[:, 1], ap0[:, 2]
    mx, mn = ap0.max(1), ap0.min(1)
    sat = (numpy.maximum(mx, 1e-10) - numpy.maximum(mn, 1e-10)) / numpy.maximum(mx, 1e-2)
    chroma = numpy.sqrt(numpy.maximum(b * (b - g) + g * (g - r) + r * (r - b), 0.0))
    yc = (r + g + b + 1.75 * chroma) / 3.0
    xs = (sat - 0.4) / 0.2
    tt = numpy.maximum(1 - numpy.abs(0.5 * xs), 0)
    s = 0.5 * (1 + numpy.sign(xs) * (1 - tt * tt))
    gain = 0.05 * s
    mid = 0.08
    glow = numpy.where(yc <= 2.0 / 3.0 * mid, gain,
                       numpy.where(yc >= 2 * mid, 0.0, gain * (mid / numpy.maximum(yc, 1e-10) - 0.5)))
    ap0 = ap0 * (1 + glow)[:, None]
    r, g, b = ap0[:, 0], ap0[:, 1], ap0[:, 2]
    hue = numpy.degrees(numpy.arctan2(numpy.sqrt(3.0) * (g - b), 2 * r - g - b))
    hue = numpy.where((r == g) & (g == b), 0.0, numpy.where(hue < 0, hue + 360, hue))
    ch = numpy.where(hue > 180, hue - 360, hue)
    w = numpy.clip(1 - numpy.abs(2 * ch / 135.0), 0, 1)
    w = (w * w * (3 - 2 * w)) ** 2
    ap0[:, 0] = r + w * sat * (0.03 - r) * (1 - 0.82)
    work = numpy.maximum(_mul(AP0_2_AP1, ap0), 0.0)
    work = (work @ AP1_RGB2Y)[:, None] * (1 - 0.96) + work * 0.96
    toe_scale = 1 + black - toe
    shoulder_scale = 1 + white - shoulder
    in_match = out_match = 0.18
    if toe > 0.8:
        toe_match = (1 - toe - out_match) / slope + numpy.log10(in_match)
    else:
        bt = (out_match + black) / toe_scale - 1
        toe_match = numpy.log10(in_match) - 0.5 * numpy.log((1 + bt) / (1 - bt)) * (toe_scale / slope)
    straight_match = (1 - toe) / slope - toe_match
    shoulder_match = shoulder / slope - straight_match
    log_c = numpy.log10(numpy.maximum(work, 1e-10))
    straight = slope * (log_c + straight_match)
    toe_c = -black + (2 * toe_scale) / (1 + numpy.exp((-2 * slope / toe_scale) * (log_c - toe_match)))
    sh_c = (1 + white) - (2 * shoulder_scale) / (1 + numpy.exp((2 * slope / shoulder_scale) * (log_c - shoulder_match)))
    toe_c = numpy.where(log_c < toe_match, toe_c, straight)
    sh_c = numpy.where(log_c > shoulder_match, sh_c, straight)
    t = numpy.clip((log_c - toe_match) / (shoulder_match - toe_match), 0, 1)
    if shoulder_match < toe_match:
        t = 1 - t
    t = (3 - 2 * t) * t * t
    tone = toe_c + (sh_c - toe_c) * t
    tone = (tone @ AP1_RGB2Y)[:, None] * (1 - 0.93) + tone * 0.93
    return numpy.maximum(tone, 0.0)


def ue55_post(rgb, alpha, post, exposure_bias_ev=None, background_linear=1.0, blue_correction=0.6,
              display_units="legacy"):
    """rgb: (N,3) linear sRGB radiance, alpha (N,): 0 = camera ray saw the
    backdrop, which is replaced by `background_linear` radiance (UE: White
    cubemap * HDRI_Brightness) BEFORE the same post chain. Returns display [0,1].

    display_units: "legacy" (pre-engine-verification: scale = 2**bias/1.2 applied
    directly to radiometric W) or "engine" (r12, UE 5.5.4 source-verified:
    radiometric W -> nits via 683, then scale = 0.18 * 2**bias; backdrop_linear
    is already in nits)."""
    rgb = numpy.asarray(rgb, numpy.float64)
    a = numpy.clip(numpy.asarray(alpha, numpy.float64), 0, 1)[:, None]
    bias = float(post.get("exposure", 0.0)) if exposure_bias_ev is None else float(exposure_bias_ev)
    if display_units == "engine":
        rgb = rgb * LM_PER_W  # radiometric W -> photometric nits; backdrop_linear already nits
        scale = ENGINE_DISPLAY_GRAY * (2.0 ** bias)
    else:
        scale = ue55_exposure_scale(bias)
    rgb = rgb + (1 - a) * float(background_linear)  # premultiplied film over backdrop
    if abs(float(post.get("temperature", 6500.0)) - 6500.0) > 1e-3:
        print("[ue55] warning: white balance != 6500K not implemented (identity used)", flush=True)
    c = _mul(SRGB_2_AP1, numpy.maximum(rgb, 0.0) * scale)
    luma = (c @ AP1_RGB2Y)[:, None]
    c = numpy.maximum(luma + (c - luma) * float(post.get("saturation", 1.0)), 0.0)
    c = numpy.power(c / 0.18, float(post.get("contrast", 1.0))) * 0.18
    c = numpy.power(c, 1.0 / max(1e-4, float(post.get("gamma", 1.0))))
    c = c * float(post.get("gain", 1.0)) + float(post.get("offset", 0.0))
    c = c + (_mul(BLUE_CORRECT_AP1, c) - c) * blue_correction
    f = film_tonemap_ap1(c)
    f = f + (_mul(BLUE_CORRECT_INV_AP1, f) - f) * blue_correction
    out = numpy.clip(_mul(AP1_2_SRGB, f), 0.0, 1.0)
    return srgb_oetf(out).astype(numpy.float32)
