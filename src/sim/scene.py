# SPDX-License-Identifier: GPL-3.0-or-later
"""The simulation scene: the robot from microban_model (walking forearms and feet, or climbing ones), a floor, a sky,
a light (as the former src/model/mjcf/scene.xml)."""
import mujoco
import microban_model


def build_scene(climb: bool = False) -> mujoco.MjModel:
    spec = mujoco.MjSpec.from_file(str(microban_model.mjcf(climb)))   # meshes found next to the robot's XML
    v = spec.visual
    v.headlight.diffuse, v.headlight.ambient, v.headlight.specular = [0.6] * 3, [0.3] * 3, [0.0] * 3
    v.rgba.haze = [0.15, 0.25, 0.35, 1.0]
    v.global_.azimuth, v.global_.elevation = 160, -20
    T, B = mujoco.mjtTexture, mujoco.mjtBuiltin
    sky = spec.add_texture()
    sky.name, sky.type, sky.builtin = "skybox", T.mjTEXTURE_SKYBOX, B.mjBUILTIN_GRADIENT
    sky.rgb1, sky.rgb2, sky.width, sky.height = [0.3, 0.5, 0.7], [0.0, 0.0, 0.0], 512, 3072
    tex = spec.add_texture()
    tex.name, tex.type, tex.builtin, tex.mark = "groundplane", T.mjTEXTURE_2D, B.mjBUILTIN_CHECKER, mujoco.mjtMark.mjMARK_EDGE
    tex.rgb1, tex.rgb2, tex.markrgb, tex.width, tex.height = [0.2, 0.3, 0.4], [0.1, 0.2, 0.3], [0.8, 0.8, 0.8], 300, 300
    mat = spec.add_material()
    mat.name, mat.texuniform, mat.texrepeat, mat.reflectance = "groundplane", True, [5, 5], 0.2
    mat.textures[mujoco.mjtTextureRole.mjTEXROLE_RGB] = "groundplane"
    spec.worldbody.add_light(pos=[0, 0, 3.5], dir=[0, 0, -1], type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)
    spec.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[0, 0, 0.05], material="groundplane")
    return spec.compile()
