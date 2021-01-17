# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# ---------------------------- ADAPTIVE DUPLIFACES --------------------------- #
# ------------------------------- version 0.84 ------------------------------- #
#                                                                              #
# Creates duplicates of selected mesh to active morphing the shape according   #
# to target faces.                                                             #
#                                                                              #
#                    (c)  Alessandro Zomparelli                                #
#                             (2017)                                           #
#                                                                              #
# http://www.co-de-it.com/                                                     #
#                                                                              #
# ############################################################################ #


import bpy
from bpy.types import (
        Operator,
        Panel,
        PropertyGroup,
        )
from bpy.props import (
        BoolProperty,
        EnumProperty,
        FloatProperty,
        IntProperty,
        StringProperty,
        PointerProperty
        )
from mathutils import Vector, Quaternion, Matrix
import numpy as np
from math import *
import random, time, copy
import bmesh
from .utils import *
from .weight_tools import *
from .numba_functions import *
from .tissue_properties import *
import os
from pathlib import Path

from . import config

def tessellate_patch(props):
    tt = time.time()

    ob = props['self']
    _ob0 = props['generator']
    components = props['component']
    offset = props['offset']
    zscale = props['zscale']
    gen_modifiers = props['gen_modifiers']
    com_modifiers = props['com_modifiers']
    mode = props['mode']
    fill_mode = props['fill_mode']
    scale_mode = props['scale_mode']
    rotation_mode = props['rotation_mode']
    rotation_shift = props['rotation_shift']
    rand_seed = props['rand_seed']
    rand_step = props['rand_step']
    bool_vertex_group = props['bool_vertex_group']
    bool_selection = props['bool_selection']
    bool_shapekeys = props['bool_shapekeys']
    bool_material_id = props['bool_material_id']
    material_id = props['material_id']
    normals_mode = props['normals_mode']
    bounds_x = props['bounds_x']
    bounds_y = props['bounds_y']
    use_origin_offset = props['use_origin_offset']
    vertex_group_thickness = props['vertex_group_thickness']
    invert_vertex_group_thickness = props['invert_vertex_group_thickness']
    vertex_group_thickness_factor = props['vertex_group_thickness_factor']
    vertex_group_cap_owner = props['vertex_group_cap_owner']
    vertex_group_cap = props['vertex_group_cap']
    invert_vertex_group_cap = props['invert_vertex_group_cap']
    vertex_group_bridge_owner = props['vertex_group_bridge_owner']
    vertex_group_bridge = props['vertex_group_bridge']
    invert_vertex_group_bridge = props['invert_vertex_group_bridge']
    vertex_group_rotation = props['vertex_group_rotation']
    invert_vertex_group_rotation = props['invert_vertex_group_rotation']
    rotation_direction = props['rotation_direction']
    target = props['target']
    smooth_normals = props['smooth_normals']
    smooth_normals_iter = props['smooth_normals_iter']
    smooth_normals_uv = props['smooth_normals_uv']
    vertex_group_smooth_normals = props['vertex_group_smooth_normals']
    invert_vertex_group_smooth_normals = props['invert_vertex_group_smooth_normals']
    bool_multi_components = props['bool_multi_components']

    # reset messages
    ob.tissue_tessellate.warning_message_thickness = ''

    if normals_mode == 'SHAPEKEYS':
        if _ob0.data.shape_keys != None:
            target = _ob0
        else:
            normals_mode = 'VERTS'
            message = "Base mesh doesn't have Shape Keys"
            ob.tissue_tessellate.warning_message_thickness = message
            print("Tissue: " + message)
    if normals_mode == 'OBJECT' and target == None:
        normals_mode = 'VERTS'
        message = "Please select a target object"
        ob.tissue_tessellate.warning_message_thickness = message
        print("Tissue: " + message)

    random.seed(rand_seed)
    if len(_ob0.modifiers) == 0: gen_modifiers = False

    # Target mesh used for normals
    if normals_mode in ('SHAPEKEYS', 'OBJECT'):
        if fill_mode == 'PATCH':
            ob0_sk = convert_object_to_mesh(target, True, True)
        else:
            use_modifiers = gen_modifiers
            if normals_mode == 'SHAPEKEYS' and not gen_modifiers:
                target = _ob0
                for m in target.modifiers:
                    m.show_viewport = False
                use_modifiers = True
            if fill_mode == 'FAN': ob0_sk = convert_to_fan(target, use_modifiers)
            elif fill_mode == 'FRAME': ob0_sk = convert_to_frame(target, props, use_modifiers)
            elif fill_mode == 'TRI': ob0_sk = convert_to_triangles(target, use_modifiers)
            elif fill_mode == 'QUAD': ob0_sk = reduce_to_quads(target, use_modifiers)
        me0_sk = ob0_sk.data
        normals_target = get_vertices_numpy(me0_sk)
        bpy.data.objects.remove(ob0_sk)
        if normals_mode == 'SHAPEKEYS':
            key_values0 = [sk.value for sk in _ob0.data.shape_keys.key_blocks]
            for sk in _ob0.data.shape_keys.key_blocks: sk.value = 0
    # Base mesh
    if fill_mode == 'PATCH':
        ob0 = convert_object_to_mesh(_ob0)
    else:
        if fill_mode == 'FAN': ob0 = convert_to_fan(_ob0, gen_modifiers)
        elif fill_mode == 'FRAME': ob0 = convert_to_frame(_ob0, props, gen_modifiers)
        elif fill_mode == 'TRI': ob0 = convert_to_triangles(_ob0, gen_modifiers)
        elif fill_mode == 'QUAD': ob0 = reduce_to_quads(_ob0, gen_modifiers)
    ob0.name = "_tissue_tmp_ob0"
    me0 = ob0.data
    n_verts0 = len(me0.vertices)

    # read vertices coordinates
    verts0_co = get_vertices_numpy(me0)

    # base normals
    if normals_mode in ('SHAPEKEYS','OBJECT'):
        if len(normals_target) != len(me0.vertices):
            normals_mode = 'VERTS'
            message = "Base mesh and Target mesh don't match"
            ob.tissue_tessellate.warning_message_thickness = message
            print("Tissue: " + message)
        else:
            if normals_mode == 'SHAPEKEYS':
                for sk, val in zip(_ob0.data.shape_keys.key_blocks, key_values0): sk.value = val
            verts0_normal = normals_target - verts0_co
            '''
            While in Relative thickness method the components are built
            between the two surfaces, in Constant mode the thickness is uniform.
            '''
            if scale_mode == 'CONSTANT':
                # Normalize vectors
                verts0_normal /= np.linalg.norm(verts0_normal, axis=1).reshape((-1,1))
                original_normals = get_normals_numpy(me0)
                verts0_normal /= np.multiply(verts0_normal, original_normals).sum(1)[:,None]
    elif normals_mode in ('VERTS','FACES'):
        verts0_normal = get_normals_numpy(me0)

    _me0 = _ob0.data

    levels = 0
    not_allowed  = ['FLUID_SIMULATION', 'ARRAY', 'BEVEL', 'BOOLEAN', 'BUILD',
                    'DECIMATE', 'EDGE_SPLIT', 'MASK', 'MIRROR', 'REMESH',
                    'SCREW', 'SOLIDIFY', 'TRIANGULATE', 'WIREFRAME', 'SKIN',
                    'EXPLODE', 'PARTICLE_INSTANCE', 'PARTICLE_SYSTEM', 'SMOKE']
    modifiers0 = list(_ob0.modifiers)
    if len(modifiers0) == 0 or fill_mode != 'PATCH':
        before_subsurf = me0
        if fill_mode == 'PATCH':
            fill_mode = 'QUAD'
    else:
        show_modifiers = [m.show_viewport for m in _ob0.modifiers]
        show_modifiers.reverse()
        modifiers0.reverse()
        for m in modifiers0:
            visible = m.show_viewport
            if not visible: continue
            #m.show_viewport = False
            if m.type in ('SUBSURF', 'MULTIRES') and visible:
                levels = m.levels
                break
            elif m.type in not_allowed:
                bpy.data.meshes.remove(ob0.data)
                #bpy.data.meshes.remove(me0)
                return "modifiers_error"

        before = _ob0.copy()
        before.name = _ob0.name + "_before_subs"
        bpy.context.collection.objects.link(before)
        #if ob0.type == 'MESH': before.data = me0
        before_mod = list(before.modifiers)
        before_mod.reverse()
        for m in before_mod:
            if m.type in ('SUBSURF', 'MULTIRES') and m.show_viewport:
                before.modifiers.remove(m)
                break
            else: before.modifiers.remove(m)

        before_subsurf = simple_to_mesh(before)
        bpy.data.objects.remove(before)

    tt = tissue_time(tt, "Meshes preparation", levels=2)

    ### PATCHES ###

    patch_faces = 4**levels
    sides = int(sqrt(patch_faces))
    step = 1/sides
    sides0 = sides-2
    patch_faces0 = int((sides-2)**2)

    if fill_mode == 'PATCH':
        all_verts, mask, materials = get_patches(before_subsurf, me0, 4, levels, bool_selection)
    else:
        all_verts, mask, materials = get_quads(me0, bool_selection)
    n_patches = len(all_verts)

    tt = tissue_time(tt, "Indexing", levels=2)

    ### WEIGHT ###

    # Check if possible to use Weight Rotation
    if rotation_mode == 'WEIGHT':
        if not vertex_group_rotation in ob0.vertex_groups.keys():
            rotation_mode = 'DEFAULT'

    bool_weight_smooth_normals = vertex_group_smooth_normals in ob0.vertex_groups.keys()
    bool_weight_thickness = vertex_group_thickness in ob0.vertex_groups.keys()
    bool_weight_cap = vertex_group_cap_owner == 'BASE' and vertex_group_cap in ob0.vertex_groups.keys()
    bool_weight_bridge = vertex_group_bridge_owner == 'BASE' and vertex_group_bridge in ob0.vertex_groups.keys()

    read_vertex_groups = bool_vertex_group or rotation_mode == 'WEIGHT' or bool_weight_thickness or bool_weight_cap or bool_weight_bridge or bool_weight_smooth_normals
    weight = weight_thickness = weight_rotation = None
    if read_vertex_groups:
        if bool_vertex_group:
            weight = [get_weight(vg, n_verts0) for vg in ob0.vertex_groups]
            weight = np.array(weight)
            n_vg = len(ob0.vertex_groups)
            if rotation_mode == 'WEIGHT':
                vg_id = ob0.vertex_groups[vertex_group_rotation].index
                weight_rotation =  weight[vg_id]
            if bool_weight_smooth_normals:
                vg_id = ob0.vertex_groups[bool_weight_smooth_normals].index
                weight_rotation =  weight[vg_id]
        else:
            if rotation_mode == 'WEIGHT':
                vg = ob0.vertex_groups[vertex_group_rotation]
                weight_rotation = get_weight_numpy(vg, n_verts0)
            if bool_weight_smooth_normals:
                vg = ob0.vertex_groups[vertex_group_smooth_normals]
                weight_smooth_normals = get_weight_numpy(vg, n_verts0)

    random.seed(rand_seed)
    bool_correct = False

    tt = tissue_time(tt, "Reading Vertex Groups", levels=2)

    ### SMOOTH NORMALS
    if smooth_normals:
        weight_smooth_normals = 0.2
        weight_smooth_normals0 = 0.2
        if vertex_group_smooth_normals in ob0.vertex_groups.keys():
            vg = ob0.vertex_groups[vertex_group_smooth_normals]
            weight_smooth_normals0 = get_weight_numpy(vg, n_verts0)
            if invert_vertex_group_smooth_normals:
                weight_smooth_normals0 = 1-weight_smooth_normals0
            weight_smooth_normals0 *= 0.2

        verts0_normal = mesh_diffusion_vector(me0, verts0_normal, smooth_normals_iter, weight_smooth_normals0, smooth_normals_uv)
        '''
        While in Relative thickness method the components are built
        between the two surfaces, in Constant mode the thickness is uniform.
        '''
        if scale_mode == 'CONSTANT':
            # Normalize vectors
            verts0_normal /= np.linalg.norm(verts0_normal, axis=1).reshape((-1,1))
            # Compare to the original normals direction
            original_normals = get_normals_numpy(me0)
            verts0_normal /= np.multiply(verts0_normal, original_normals).sum(1)[:,None]

        tt = tissue_time(tt, "Smooth Normals", levels=2)

    ### ROTATE PATCHES ###

    if rotation_mode != 'DEFAULT' or rotation_shift != 0:

        # Weight rotation
        weight_shift = 0
        if rotation_mode == 'WEIGHT':
            corners_id = np.array(((0,0,-1,-1),(0,-1,-1,0)))
            corners = all_verts[:,corners_id[0],corners_id[1]]
            corners_weight = weight_rotation[corners]
            if invert_vertex_group_rotation:
                corners_weight = 1-corners_weight
            ids4 = np.arange(4)
            if rotation_direction == 'DIAG':
                c0 = corners_weight[:,ids4]
                c3 = corners_weight[:,(ids4+2)%4]
                differential = c3 - c0
            else:
                c0 = corners_weight[:,ids4]
                c1 = corners_weight[:,(ids4+1)%4]
                c2 = corners_weight[:,(ids4+2)%4]
                c3 = corners_weight[:,(ids4+3)%4]
                differential = - c0 + c1 + c2 - c3
            weight_shift = np.argmax(differential, axis=1)

        # Random rotation
        random_shift = 0
        if rotation_mode == 'RANDOM':
            np.random.seed(rand_seed)
            random_shift = np.random.randint(0,4,size=n_patches)*rand_step

        # UV rotation
        UV_shift = 0
        if rotation_mode == 'UV' and ob0.type == 'MESH':
            bm = bmesh.new()
            bm.from_mesh(before_subsurf)
            uv_lay = bm.loops.layers.uv.active
            UV_shift = [0]*len(mask)
            for f in bm.faces:
                ll = f.loops
                if len(ll) == 4:
                    uv0 = ll[0][uv_lay].uv
                    uv1 = ll[3][uv_lay].uv
                    uv2 = ll[2][uv_lay].uv
                    uv3 = ll[1][uv_lay].uv

                    v01 = (uv0 + uv1)   # not necessary to divide by 2
                    v32 = (uv3 + uv2)
                    v0132 = v32 - v01   # axis vector 1
                    v0132.normalize()   # based on the rotation not on the size
                    v12 = (uv1 + uv2)
                    v03 = (uv0 + uv3)
                    v1203 = v03 - v12   # axis vector 2
                    v1203.normalize()   # based on the rotation not on the size

                    dot1203 = v1203.x
                    dot0132 = v0132.x
                    if(abs(dot1203) < abs(dot0132)):    # already vertical
                        if (dot0132 > 0): shift = 0
                        else: shift = 2                 # rotate 180°
                    else:                               # horizontal
                        if(dot1203 < 0): shift = 3
                        else: shift = 1
                    #UV_shift.append(shift)
                    UV_shift[f.index] = shift

            UV_shift = np.array(UV_shift)[mask]
            bm.free()

        # Rotate Patch
        rotation_shift = np.zeros((n_patches))+rotation_shift
        rot = weight_shift + random_shift + UV_shift + rotation_shift
        rot = rot%4
        flip_u = np.logical_or(rot==2,rot==3)
        flip_v = np.logical_or(rot==1,rot==2)
        flip_uv = np.logical_or(rot==1,rot==3)
        all_verts[flip_u] = all_verts[flip_u,::-1,:]
        all_verts[flip_v] = all_verts[flip_v,:,::-1]
        all_verts[flip_uv] = np.transpose(all_verts[flip_uv],(0,2,1))

        tt = tissue_time(tt, "Rotations", levels=2)

    #for o in bpy.context.view_layer.objects: o.select_set(False)
    new_patch = None

    ### COMPONENT ###
    new_objects = []

    # Store original values
    _com_modifiers = com_modifiers
    _bool_shapekeys = bool_shapekeys

    for mat_id, _ob1 in enumerate(components):
        if _ob1 == None: continue

        # Set original values (for next commponents)
        com_modifiers = _com_modifiers
        bool_shapekeys = _bool_shapekeys

        if bool_multi_components:
            masked_verts = all_verts[materials == mat_id]
        elif bool_material_id:
            masked_verts = all_verts[materials == material_id]
        else:
            masked_verts = all_verts
        n_patches = len(masked_verts)
        if n_patches == 0: continue

        if com_modifiers or _ob1.type != 'MESH': bool_shapekeys = False

        # set Shape Keys to zero
        original_key_values = None
        if bool_shapekeys or not com_modifiers:
            if _ob1.data.shape_keys:
                original_key_values = []
                for sk in _ob1.data.shape_keys.key_blocks:
                    original_key_values.append(sk.value)
                    sk.value = 0
            else:
                bool_shapekeys = False

        if not com_modifiers and not bool_shapekeys:
            mod_visibility = []
            for m in _ob1.modifiers:
                mod_visibility.append(m.show_viewport)
                m.show_viewport = False
            com_modifiers = True
        ob1 = convert_object_to_mesh(_ob1, com_modifiers, False)
        ob1, com_area = tessellate_prepare_component(ob1, props)
        ob1.name = "_tissue_tmp_ob1"

        # restore original modifiers visibility for component object
        try:
            for m, vis in zip(_ob1.modifiers, mod_visibility):
                m.show_viewport = vis
        except: pass

        me1 = ob1.data
        verts1 = [v.co for v in me1.vertices]
        n_verts1 = len(verts1)
        if n_verts1 == 0:
            bpy.data.objects.remove(ob1)
            continue

        ### COMPONENT GRID COORDINATES ###

        # find relative UV component's vertices
        if fill_mode == 'PATCH':
            verts1_uv_quads = [0]*n_verts1
            verts1_uv = [0]*n_verts1
            for i, vert in enumerate(verts1):
                # grid coordinates
                u = int(vert[0]//step)
                v = int(vert[1]//step)
                u1 = min(u+1, sides)
                v1 = min(v+1, sides)
                if mode != 'BOUNDS':
                    if u > sides-1:
                        u = sides-1
                        u1 = sides
                    if u < 0:
                        u = 0
                        u1 = 1
                    if v > sides-1:
                        v = sides-1
                        v1 = sides
                    if v < 0:
                        v = 0
                        v1 = 1
                verts1_uv_quads[i] = (u,v,u1,v1)
                # factor coordinates
                fu = (vert[0]-u*step)/step
                fv = (vert[1]-v*step)/step
                fw = vert.z
                # interpolate Z scaling factor
                verts1_uv[i] = Vector((fu,fv,fw))
        else:
            verts1_uv = verts1

        if bool_shapekeys:
            sk_uv_quads = []
            sk_uv = []
            for sk in ob1.data.shape_keys.key_blocks[1:]:
                source = sk.data
                _sk_uv_quads = [0]*n_verts1
                _sk_uv = [0]*n_verts1
                for i, sk_v in enumerate(source):
                    sk_vert = sk_v.co

                    # grid coordinates
                    u = int(sk_vert[0]//step)
                    v = int(sk_vert[1]//step)
                    u1 = min(u+1, sides)
                    v1 = min(v+1, sides)
                    if mode != 'BOUNDS':
                        if u > sides-1:
                            u = sides-1
                            u1 = sides
                        if u < 0:
                            u = 0
                            u1 = 1
                        if v > sides-1:
                            v = sides-1
                            v1 = sides
                        if v < 0:
                            v = 0
                            v1 = 1
                    _sk_uv_quads[i] = (u,v,u1,v1)
                    # factor coordinates
                    fu = (sk_vert[0]-u*step)/step
                    fv = (sk_vert[1]-v*step)/step
                    fw = sk_vert.z
                    _sk_uv[i] = Vector((fu,fv,fw))
                sk_uv_quads.append(_sk_uv_quads)
                sk_uv.append(_sk_uv)
            store_sk_coordinates = [[] for t in ob1.data.shape_keys.key_blocks[1:]]
            sk_uv_quads = np.array(sk_uv_quads)
            sk_uv = np.array(sk_uv)

        np_verts1_uv = np.array(verts1_uv)
        if fill_mode == 'PATCH':
            verts1_uv_quads = np.array(verts1_uv_quads)
            np_u = verts1_uv_quads[:,0]
            np_v = verts1_uv_quads[:,1]
            np_u1 = verts1_uv_quads[:,2]
            np_v1 = verts1_uv_quads[:,3]
        else:
            np_u = 0
            np_v = 0
            np_u1 = 1
            np_v1 = 1

        tt = tissue_time(tt, "Component preparation", levels=2)

        ### DEFORM PATCHES ###

        verts_xyz = verts0_co[masked_verts]
        v00 = verts_xyz[:, np_u, np_v].reshape((n_patches,-1,3))
        v10 = verts_xyz[:, np_u1, np_v].reshape((n_patches,-1,3))
        v01 = verts_xyz[:, np_u, np_v1].reshape((n_patches,-1,3))
        v11 = verts_xyz[:, np_u1, np_v1].reshape((n_patches,-1,3))
        vx = np_verts1_uv[:,0].reshape((1,n_verts1,1))
        vy = np_verts1_uv[:,1].reshape((1,n_verts1,1))
        vz = np_verts1_uv[:,2].reshape((1,n_verts1,1))
        co2 = np_lerp2(v00, v10, v01, v11, vx, vy, 'verts')

        ### PATCHES WEIGHT ###
        weight_thickness = None
        if bool_vertex_group:
            n_vg = len(weight)
            patches_weight = weight[:, masked_verts]
            w00 = patches_weight[:, :, np_u, np_v].reshape((n_vg, n_patches,-1,1))
            w10 = patches_weight[:, :, np_u1, np_v].reshape((n_vg, n_patches,-1,1))
            w01 = patches_weight[:, :, np_u, np_v1].reshape((n_vg, n_patches,-1,1))
            w11 = patches_weight[:, :, np_u1, np_v1].reshape((n_vg, n_patches,-1,1))
            store_weight = np_lerp2(w00,w10,w01,w11,vx[None,:,:,:],vy[None,:,:,:],'weight')

            if vertex_group_thickness in ob0.vertex_groups.keys():
                vg_id = ob0.vertex_groups[vertex_group_thickness].index
                weight_thickness = store_weight[vg_id,:,:]
            if vertex_group_smooth_normals in ob0.vertex_groups.keys():
                vg_id = ob0.vertex_groups[vertex_group_smooth_normals].index
                weight_smooth_normals = store_weight[vg_id,:,:]
        else:
            # Read vertex group Thickness
            if vertex_group_thickness in ob0.vertex_groups.keys():
                vg = ob0.vertex_groups[vertex_group_thickness]
                weight_thickness = get_weight_numpy(vg, n_verts0)
                wt = weight_thickness[masked_verts]
                wt = wt[:,:,:,np.newaxis]
                w00 = wt[:, np_u, np_v].reshape((n_patches, -1, 1))
                w10 = wt[:, np_u1, np_v].reshape((n_patches, -1, 1))
                w01 = wt[:, np_u, np_v1].reshape((n_patches, -1, 1))
                w11 = wt[:, np_u1, np_v1].reshape((n_patches, -1, 1))
                weight_thickness = np_lerp2(w00,w10,w01,w11,vx,vy,'verts')
                try:
                    weight_thickness.shape
                    if invert_vertex_group_thickness:
                        weight_thickness = 1-weight_thickness
                    fact = vertex_group_thickness_factor
                    if fact > 0:
                        weight_thickness = weight_thickness*(1-fact) + fact
                except: pass

            # Read vertex group smooth normals
            if vertex_group_smooth_normals in ob0.vertex_groups.keys():
                vg = ob0.vertex_groups[vertex_group_smooth_normals]
                weight_smooth_normals = get_weight_numpy(vg, n_verts0)
                wt = weight_smooth_normals[masked_verts]
                wt = wt[:,:,:,None]
                w00 = wt[:, np_u, np_v].reshape((n_patches, -1, 1))
                w10 = wt[:, np_u1, np_v].reshape((n_patches, -1, 1))
                w01 = wt[:, np_u, np_v1].reshape((n_patches, -1, 1))
                w11 = wt[:, np_u1, np_v1].reshape((n_patches, -1, 1))
                weight_smooth_normals = np_lerp2(w00,w10,w01,w11,vx,vy,'verts')
                try:
                    weight_smooth_normals.shape
                    if invert_vertex_group_smooth_normals:
                        weight_smooth_normals = 1-weight_smooth_normals
                    #fact = vertex_group_thickness_factor
                    #if fact > 0:
                    #    weight_thickness = weight_thickness*(1-fact) + fact
                except: pass

        if normals_mode == 'FACES':
            n2 = get_attribute_numpy(before_subsurf.polygons,'normal',3)
            #n2 = [0]*len(mask)*3
            #before_subsurf.polygons.foreach_get('normal',n2)
            #n2 = np.array(n2).reshape(-1,1,3)[mask]#[:,None,:]
            n2 = n2[mask][:,None,:]
            #n2 = np.mean(verts_norm, axis=(1,2))
            #n2 = np.expand_dims(n2, axis=1)
        else:
            if normals_mode == 'CUSTOM':
                me0.calc_normals_split()
                normals_split = [0]*len(me0.loops)*3
                vertex_indexes = [0]*len(me0.loops)
                me0.loops.foreach_get('normal', normals_split)
                me0.loops.foreach_get('vertex_index', vertex_indexes)
                normals_split = np.array(normals_split).reshape(-1,3)
                vertex_indexes = np.array(vertex_indexes)
                verts0_normal = np.zeros((len(me0.vertices),3))
                np.add.at(verts0_normal, vertex_indexes, normals_split)
                indexes, counts = np.unique(vertex_indexes,return_counts=True)
                verts0_normal[indexes] /= counts[:,np.newaxis]

            if 'Eval_Normals' in me1.uv_layers.keys():
                bm1 = bmesh.new()
                bm1.from_mesh(me1)
                uv_co = np.array(uv_from_bmesh(bm1, 'Eval_Normals'))
                vx_nor = uv_co[:,0]#.reshape((1,n_verts1,1))
                #vy_nor = uv_co[:,1]#.reshape((1,n_verts1,1))

                # grid coordinates
                np_u = np.maximum(vx_nor//step, 0).astype('int')
                #np_v = np.maximum(vy_nor//step, 0).astype('int')
                np_u1 = np.minimum(np_u+1, sides).astype('int')
                #np_v1 = np.minimum(np_v+1, sides).astype('int')

                vx_nor = (vx_nor - np_u * step)/step
                #vy_nor = (vy_nor - np_v * step)/step
                vx_nor = vx_nor.reshape((1,n_verts1,1))
                #vy_nor = vy_nor.reshape((1,n_verts1,1))
                vy_nor = vy
                bm1.free()
            else:
                vx_nor = vx
                vy_nor = vy

            verts_norm = verts0_normal[masked_verts]
            n00 = verts_norm[:, np_u, np_v].reshape((n_patches,-1,3))
            n10 = verts_norm[:, np_u1, np_v].reshape((n_patches,-1,3))
            n01 = verts_norm[:, np_u, np_v1].reshape((n_patches,-1,3))
            n11 = verts_norm[:, np_u1, np_v1].reshape((n_patches,-1,3))
            n2 = np_lerp2(n00, n10, n01, n11, vx_nor, vy_nor, 'verts')

        # thickness variation
        mean_area = []
        a2 = None
        if scale_mode == 'ADAPTIVE' and normals_mode not in ('SHAPEKEYS','OBJECT'):
            #com_area = bb[0]*bb[1]
            if mode != 'BOUNDS' or com_area == 0: com_area = 1
            if normals_mode == 'FACES':
                if levels == 0:
                    areas = [0]*len(mask)
                    before_subsurf.polygons.foreach_get('area',areas)
                    areas = np.sqrt(np.array(areas)/com_area)[mask]
                    a2 = areas[:,np.newaxis,np.newaxis]
                else:
                    areas = calc_verts_area_bmesh(me0)
                    verts_area = np.sqrt(areas*patch_faces/com_area)
                    verts_area = verts_area[masked_verts]
                    verts_area = verts_area.mean(axis=(1,2)).reshape((n_patches,1,1))
                    a2 = verts_area
            else:
                areas = calc_verts_area_bmesh(me0)
                verts_area = np.sqrt(areas*patch_faces/com_area)
                verts_area = verts_area[masked_verts]
                a00 = verts_area[:, np_u, np_v].reshape((n_patches,-1,1))
                a10 = verts_area[:, np_u1, np_v].reshape((n_patches,-1,1))
                a01 = verts_area[:, np_u, np_v1].reshape((n_patches,-1,1))
                a11 = verts_area[:, np_u1, np_v1].reshape((n_patches,-1,1))
                # remapped z scale
                a2 = np_lerp2(a00,a10,a01,a11,vx,vy,'verts')

        store_coordinates = calc_thickness(co2,n2,vz,a2,weight_thickness)
        co2 = n2 = vz = a2 = None

        if bool_shapekeys:
            tt_sk = time.time()
            n_sk = len(sk_uv_quads)
            # ids of face corners for each vertex (n_sk, n_verts1, 4)
            np_u = sk_uv_quads[:,:,0][:,None,:]
            np_v = sk_uv_quads[:,:,1][:,None,:]
            np_u1 = sk_uv_quads[:,:,2][:,None,:]
            np_v1 = sk_uv_quads[:,:,3][:,None,:]
            # face corners for each vertex  (n_patches, n_sk, n_verts1, 4)
            v00 = verts_xyz[:,np_u,np_v].reshape((n_patches,n_sk,n_verts1,3))#.swapaxes(0,1)
            v10 = verts_xyz[:,np_u1,np_v].reshape((n_patches,n_sk,n_verts1,3))#.swapaxes(0,1)
            v01 = verts_xyz[:,np_u,np_v1].reshape((n_patches,n_sk,n_verts1,3))#.swapaxes(0,1)
            v11 = verts_xyz[:,np_u1,np_v1].reshape((n_patches,n_sk,n_verts1,3))#.swapaxes(0,1)
            vx = sk_uv[:,:,0].reshape((1,n_sk,n_verts1,1))
            vy = sk_uv[:,:,1].reshape((1,n_sk,n_verts1,1))
            vz = sk_uv[:,:,2].reshape((1,n_sk,n_verts1,1))
            co2 = np_lerp2(v00,v10,v01,v11,vx,vy,mode='shapekeys')

            if normals_mode == 'FACES':
                n2 = n2[None,:,:,:]
            else:
                n00 = verts_norm[:, np_u, np_v].reshape((n_patches,n_sk,n_verts1,3))
                n10 = verts_norm[:, np_u1, np_v].reshape((n_patches,n_sk,n_verts1,3))
                n01 = verts_norm[:, np_u, np_v1].reshape((n_patches,n_sk,n_verts1,3))
                n11 = verts_norm[:, np_u1, np_v1].reshape((n_patches,n_sk,n_verts1,3))
                n2 = np_lerp2(n00,n10,n01,n11,vx,vy,'shapekeys')

            # NOTE: weight thickness is based on the base position of the
            #       vertices, not on the coordinates of the shape keys

            if scale_mode == 'ADAPTIVE':
                if normals_mode == 'FACES':
                    a2 = mean_area
                else:
                    a00 = verts_area[:, np_u, np_v].reshape((n_patches,n_sk,n_verts1,1))
                    a10 = verts_area[:, np_u1, np_v].reshape((n_patches,n_sk,n_verts1,1))
                    a01 = verts_area[:, np_u, np_v1].reshape((n_patches,n_sk,n_verts1,1))
                    a11 = verts_area[:, np_u1, np_v1].reshape((n_patches,n_sk,n_verts1,1))
                    # remapped z scale
                    a2 = np_lerp2(a00,a10,a01,a11,vx,vy,'shapekeys')

            store_sk_coordinates = calc_thickness(co2,n2,vz,a2,weight_thickness)
            co2 = n2 = vz = a2 = weight_thickness = None
            tissue_time(tt_sk, "Compute ShapeKeys", levels=3)

        tt = tissue_time(tt, "Compute Coordinates", levels=2)

        new_me = array_mesh(ob1, len(masked_verts))
        tt = tissue_time(tt, "Repeat component", levels=2)

        new_patch = bpy.data.objects.new("_tissue_tmp_patch", new_me)
        bpy.context.collection.objects.link(new_patch)

        store_coordinates = np.concatenate(store_coordinates, axis=0).reshape((-1)).tolist()
        new_me.vertices.foreach_set('co',store_coordinates)

        for area in bpy.context.screen.areas:
            for space in area.spaces:
                try: new_patch.local_view_set(space, True)
                except: pass
        tt = tissue_time(tt, "Inject coordinates", levels=2)

        # Vertex Group
        for vg in ob1.vertex_groups:
            vg_name = vg.name
            if vg_name in ob0.vertex_groups.keys():
                vg_name = '_{}_'.format(vg_name)
            new_patch.vertex_groups.new(name=vg_name)
        if bool_vertex_group:
            new_groups = []
            for vg in ob0.vertex_groups:
                new_groups.append(new_patch.vertex_groups.new(name=vg.name))
            for vg, w in zip(new_groups, store_weight):
                set_weight_numpy(vg, w.reshape(-1))
            tt = tissue_time(tt, "Write Vertex Groups", levels=2)

        if bool_shapekeys:
            for sk, val in zip(_ob1.data.shape_keys.key_blocks, original_key_values):
                sk.value = val
                new_patch.shape_key_add(name=sk.name, from_mix=False)
                new_patch.data.shape_keys.key_blocks[sk.name].value = val
            for i in range(n_sk):
                coordinates = np.concatenate(store_sk_coordinates[:,i], axis=0)
                coordinates = coordinates.flatten().tolist()
                new_patch.data.shape_keys.key_blocks[i+1].data.foreach_set('co', coordinates)

            # set original values and combine Shape Keys and Vertex Groups
            for sk, val in zip(_ob1.data.shape_keys.key_blocks, original_key_values):
                sk.value = val
                new_patch.data.shape_keys.key_blocks[sk.name].value = val
            if bool_vertex_group:
                vg_keys = new_patch.vertex_groups.keys()
                for sk in new_patch.data.shape_keys.key_blocks:
                    if sk.name in vg_keys:
                        sk.vertex_group = sk.name
            tt = tissue_time(tt, "Shape Keys", levels=2)
        elif original_key_values:
            for sk, val in zip(_ob1.data.shape_keys.key_blocks, original_key_values):
                sk.value = val

        new_name = ob0.name + "_" + ob1.name
        new_patch.name = "_tissue_tmp_patch"
        new_patch.data.update() # needed for updating the normals
        new_objects.append(new_patch)
        bpy.data.objects.remove(ob1)
    bpy.data.objects.remove(ob0)
    tt = tissue_time(tt, "Closing Tessellate Iteration", levels=2)
    return new_objects

class tissue_tessellate(Operator):
    bl_idname = "object.tissue_tessellate"
    bl_label = "Tissue Tessellate"
    bl_description = ("Create a copy of selected object on the active object's "
                      "faces, adapting the shape to the different faces")
    bl_options = {'REGISTER', 'UNDO'}


    bool_hold : BoolProperty(
            name="Hold",
            description="Wait...",
            default=False
    )
    '''
    copy_settings : EnumProperty(
            items=[(ob.name, ob.name, '') for ob in bpy.data.objects],
            name="Copy Settings",
            description="Copy settings from a previously tessellate dobject"
    )
    '''
    '''
    bool_lock : BoolProperty(
            name="Lock",
            description="Prevent automatic update on settings changes or if other objects have it in the hierarchy.",
            default=False
    )
    bool_dependencies : BoolProperty(
            name="Update Dependencies",
            description="Automatically updates base and components as well, if results of other tessellations",
            default=False
    )
    '''
    object_name : StringProperty(
            name="",
            description="Name of the generated object"
            )
    zscale : FloatProperty(
            name="Scale",
            default=1,
            soft_min=0,
            soft_max=10,
            description="Scale factor for the component thickness"
            )
    scale_mode : EnumProperty(
            items=(
                ('CONSTANT', "Constant", "Uniform thickness"),
                ('ADAPTIVE', "Relative", "Preserve component's proportions")
                ),
            default='ADAPTIVE',
            name="Z-Scale according to faces size"
            )
    offset : FloatProperty(
            name="Surface Offset",
            default=1,
            min=-1, max=1,
            soft_min=-1,
            soft_max=1,
            description="Surface offset"
            )
    mode : EnumProperty(
            items=(
                ('BOUNDS', "Bounds", "The component fits automatically the size of the target face"),
                ('LOCAL', "Local", "Based on Local coordinates, from 0 to 1"),
                ('GLOBAL', 'Global', "Based on Global coordinates, from 0 to 1")),
            default='BOUNDS',
            name="Component Mode"
            )
    rotation_mode : EnumProperty(
            items=(('RANDOM', "Random", "Random faces rotation"),
                   ('UV', "Active UV", "Face rotation is based on UV coordinates"),
                   ('WEIGHT', "Weight Gradient", "Rotate according to Vertex Group gradient"),
                   ('DEFAULT', "Default", "Default rotation")),
            default='DEFAULT',
            name="Component Rotation"
            )
    rotation_direction : EnumProperty(
            items=(('ORTHO', "Orthogonal", "Component main directions in XY"),
                   ('DIAG', "Diagonal", "Component main direction aligned with diagonal")),
            default='ORTHO',
            name="Direction"
            )
    rotation_shift : IntProperty(
            name="Shift",
            default=0,
            soft_min=0,
            soft_max=3,
            description="Shift components rotation"
            )
    fill_mode : EnumProperty(
            items=(
                ('TRI', 'Tri', 'Triangulate the base mesh'),
                ('QUAD', 'Quad', 'Regular quad tessellation. Uses only 3 or 4 vertices'),
                ('FAN', 'Fan', 'Radial tessellation for polygonal faces'),
                ('PATCH', 'Patch', 'Curved tessellation according to the last ' +
                'Subsurf\n(or Multires) modifiers. Works only with 4 sides ' +
                'patches.\nAfter the last Subsurf (or Multires) only ' +
                'deformation\nmodifiers can be used'),
                ('FRAME', 'Frame', 'Essellation along the edges of each face')),
            default='QUAD',
            name="Fill Mode"
            )
    combine_mode : EnumProperty(
            items=(
                ('LAST', 'Last', 'Show only the last iteration'),
                ('UNUSED', 'Unused', 'Combine each iteration with the unused faces of the previous iteration. Used for branching systems'),
                ('ALL', 'All', 'Combine the result of all iterations')),
            default='LAST',
            name="Combine Mode",
            )
    gen_modifiers : BoolProperty(
            name="Generator Modifiers",
            default=False,
            description="Apply Modifiers and Shape Keys to the base object"
            )
    com_modifiers : BoolProperty(
            name="Component Modifiers",
            default=False,
            description="Apply Modifiers and Shape Keys to the component object"
            )
    merge : BoolProperty(
            name="Merge",
            default=False,
            description="Merge vertices in adjacent duplicates"
            )
    merge_open_edges_only : BoolProperty(
            name="Open edges only",
            default=True,
            description="Merge only open edges"
            )
    merge_thres : FloatProperty(
            name="Distance",
            default=0.0001,
            soft_min=0,
            soft_max=10,
            description="Limit below which to merge vertices"
            )
    bool_random : BoolProperty(
            name="Randomize",
            default=False,
            description="Randomize component rotation"
            )
    rand_seed : IntProperty(
            name="Seed",
            default=0,
            soft_min=0,
            soft_max=10,
            description="Random seed"
            )
    rand_step : IntProperty(
            name="Step",
            default=1,
            min=1,
            soft_max=2,
            description="Random step"
            )
    bool_vertex_group : BoolProperty(
            name="Map Vertex Groups",
            default=False,
            description="Transfer all Vertex Groups from Base object"
            )
    bool_selection : BoolProperty(
            name="On selected Faces",
            default=False,
            description="Create Tessellation only on selected faces"
            )
    bool_shapekeys : BoolProperty(
            name="Use Shape Keys",
            default=False,
            description="Transfer Component's Shape Keys. If the name of Vertex "
                        "Groups and Shape Keys are the same, they will be "
                        "automatically combined"
            )
    bool_smooth : BoolProperty(
            name="Smooth Shading",
            default=False,
            description="Output faces with smooth shading rather than flat shaded"
            )
    bool_materials : BoolProperty(
            name="Transfer Materials",
            default=True,
            description="Preserve component's materials"
            )
    generator : StringProperty(
            name="",
            description="Base object for the tessellation",
            default = ""
            )
    component : StringProperty(
            name="",
            description="Component object for the tessellation",
            default = ""
            )
    target : StringProperty(
            name="",
            description="Target object for custom direction",
            default = ""
            )
    bool_material_id : BoolProperty(
            name="Tessellation on Material ID",
            default=False,
            description="Apply the component only on the selected Material"
            )
    bool_dissolve_seams : BoolProperty(
            name="Dissolve Seams",
            default=False,
            description="Dissolve all seam edges"
            )
    material_id : IntProperty(
            name="Material ID",
            default=0,
            min=0,
            description="Material ID"
            )
    iterations : IntProperty(
            name="Iterations",
            default=1,
            min=1,
            soft_max=5,
            description="Automatically repeat the Tessellation using the "
                        + "generated geometry as new base object.\nUsefull for "
                        + "for branching systems. Dangerous!"
            )
    bool_combine : BoolProperty(
            name="Combine unused",
            default=False,
            description="Combine the generated geometry with unused faces"
            )
    bool_advanced : BoolProperty(
            name="Advanced Settings",
            default=False,
            description="Show more settings"
            )
    normals_mode : EnumProperty(
            items=(
                ('VERTS', 'Normals', 'Consistent direction based on vertices normal'),
                ('FACES', 'Faces', 'Based on individual faces normal'),
                ('SHAPEKEYS', 'Keys', "According to base object's shape keys"),
                ('OBJECT', 'Object', "According to a target object")),
            default='VERTS',
            name="Direction"
            )
    bool_multi_components : BoolProperty(
            name="Multi Components",
            default=False,
            description="Combine different components according to materials name"
            )
    bounds_x : EnumProperty(
            items=(
                ('EXTEND', 'Extend', 'Default X coordinates'),
                ('CLIP', 'Clip', 'Trim out of bounds in X direction'),
                ('CYCLIC', 'Cyclic', 'Cyclic components in X direction')),
            default='EXTEND',
            name="Bounds X",
            )
    bounds_y : EnumProperty(
            items=(
                ('EXTEND', 'Extend', 'Default Y coordinates'),
                ('CLIP', 'Clip', 'Trim out of bounds in Y direction'),
                ('CYCLIC', 'Cyclic', 'Cyclic components in Y direction')),
            default='EXTEND',
            name="Bounds Y",
            )
    close_mesh : EnumProperty(
            items=(
                ('NONE', 'None', 'Keep the mesh open'),
                ('CAP', 'Cap Holes', 'Automatically cap open loops'),
                ('BRIDGE', 'Bridge Open Loops', 'Automatically bridge loop pairs'),
                ('BRIDGE_CAP', 'Custom', 'Bridge loop pairs and cap holes according to vertex groups')),
            default='NONE',
            name="Close Mesh"
            )
    cap_faces : BoolProperty(
            name="Cap Holes",
            default=False,
            description="Cap open edges loops"
            )
    frame_boundary : BoolProperty(
            name="Frame Boundary",
            default=False,
            description="Support face boundaries"
            )
    fill_frame : BoolProperty(
            name="Fill Frame",
            default=False,
            description="Fill inner faces with Fan tessellation"
            )
    frame_boundary_mat : IntProperty(
            name="Material Offset",
            default=0,
            description="Material Offset for boundaries (with Multi Components or Material ID)"
            )
    fill_frame_mat : IntProperty(
            name="Material Offset",
            default=0,
            description="Material Offset for inner faces (with Multi Components or Material ID)"
            )
    open_edges_crease : FloatProperty(
            name="Open Edges Crease",
            default=0,
            min=0,
            max=1,
            description="Automatically set crease for open edges"
            )
    bridge_edges_crease : FloatProperty(
            name="Bridge Edges Crease",
            default=0,
            min=0,
            max=1,
            description="Automatically set crease for bridge edges"
            )
    bridge_smoothness : FloatProperty(
            name="Smoothness",
            default=1,
            min=0,
            max=1,
            description="Bridge Smoothness"
            )
    frame_thickness : FloatProperty(
            name="Frame Thickness",
            default=0.2,
            min=0,
            soft_max=2,
            description="Frame Thickness"
            )
    frame_mode : EnumProperty(
            items=(
                ('CONSTANT', 'Constant', 'Even thickness'),
                ('RELATIVE', 'Relative', 'Frame offset depends on face areas')),
            default='CONSTANT',
            name="Offset"
            )
    bridge_cuts : IntProperty(
            name="Cuts",
            default=0,
            min=0,
            max=20,
            description="Bridge Cuts"
            )
    cap_material_offset : IntProperty(
            name="Material Offset",
            default=0,
            min=0,
            description="Material index offset for the cap faces"
            )
    bridge_material_offset : IntProperty(
            name="Material Offset",
            default=0,
            min=0,
            description="Material index offset for the bridge faces"
            )
    patch_subs : IntProperty(
            name="Patch Subdivisions",
            default=1,
            min=0,
            description="Subdivisions levels for Patch tessellation after the first iteration"
            )
    use_origin_offset : BoolProperty(
            name="Align to Origins",
            default=False,
            description="Define offset according to components origin and local Z coordinate"
            )

    vertex_group_thickness : StringProperty(
            name="Thickness weight", default='',
            description="Vertex Group used for thickness"
            )
    invert_vertex_group_thickness : BoolProperty(
            name="Invert", default=False,
            description="Invert the vertex group influence"
            )
    vertex_group_thickness_factor : FloatProperty(
            name="Factor",
            default=0,
            min=0,
            max=1,
            description="Thickness factor to use for zero vertex group influence"
            )

    vertex_group_cap_owner : EnumProperty(
            items=(
                ('BASE', 'Base', 'Use base vertex group'),
                ('COMP', 'Component', 'Use component vertex group')),
            default='COMP',
            name="Source"
            )
    vertex_group_cap : StringProperty(
            name="Cap Vertex Group", default='',
            description="Vertex Group used for cap open edges"
            )
    invert_vertex_group_cap : BoolProperty(
            name="Invert", default=False,
            description="Invert the vertex group influence"
            )

    vertex_group_bridge_owner : EnumProperty(
            items=(
                ('BASE', 'Base', 'Use base vertex group'),
                ('COMP', 'Component', 'Use component vertex group')),
            default='COMP',
            name="Source"
            )
    vertex_group_bridge : StringProperty(
            name="Thickness weight", default='',
            description="Vertex Group used for bridge open edges"
            )
    invert_vertex_group_bridge : BoolProperty(
            name="Invert", default=False,
            description="Invert the vertex group influence"
            )

    vertex_group_rotation : StringProperty(
            name="Rotation weight", default='',
            description="Vertex Group used for rotation"
            )
    invert_vertex_group_rotation : BoolProperty(
            name="Invert", default=False,
            description="Invert the vertex group influence"
            )

    smooth_normals : BoolProperty(
            name="Smooth Normals", default=False,
            description="Smooth normals of the surface in order to reduce intersections"
            )
    smooth_normals_iter : IntProperty(
            name="Iterations",
            default=5,
            min=0,
            description="Smooth iterations"
            )
    smooth_normals_uv : FloatProperty(
            name="UV Anisotropy",
            default=0,
            min=-1,
            max=1,
            description="0 means no anysotropy, -1 represent the U direction, while 1 represent the V direction"
            )
    vertex_group_smooth_normals : StringProperty(
            name="Smooth Normals weight", default='',
            description="Vertex Group used for smoothing normals"
            )
    invert_vertex_group_smooth_normals : BoolProperty(
            name="Invert", default=False,
            description="Invert the vertex group influence"
            )

    working_on = ""

    def draw(self, context):
        allowed_obj = ('MESH', 'CURVE', 'SURFACE', 'FONT', 'META')
        '''
        try:
            bool_working = self.working_on == self.object_name and \
            self.working_on != ""
        except:
            bool_working = False
        '''

        bool_working = False
        bool_allowed = False
        ob0 = None
        ob1 = None

        sel = context.selected_objects
        if len(sel) == 1:
            try:
                ob0 = sel[0].tissue_tessellate.generator
                ob1 = sel[0].tissue_tessellate.component
                self.generator = ob0.name
                self.component = ob1.name
                if self.working_on == '':
                    load_parameters(self,sel[0])
                    self.working_on = sel[0].name
                bool_working = True
                bool_allowed = True
            except:
                pass

        if len(sel) == 2:
            bool_allowed = True
            for o in sel:
                if o.type not in allowed_obj:
                    bool_allowed = False

        if len(sel) != 2 and not bool_working:
            layout = self.layout
            layout.label(icon='INFO')
            layout.label(text="Please, select two different objects")
            layout.label(text="Select first the Component object, then select")
            layout.label(text="the Base object.")
        elif not bool_allowed and not bool_working:
            layout = self.layout
            layout.label(icon='INFO')
            layout.label(text="Only Mesh, Curve, Surface or Text objects are allowed")
        else:
            if ob0 == ob1 == None:
                ob0 = context.active_object
                self.generator = ob0.name
                for o in sel:
                    if o != ob0:
                        ob1 = o
                        self.component = o.name
                        self.no_component = False
                        break

            # new object name
            if self.object_name == "":
                if self.generator == "":
                    self.object_name = "Tessellation"
                else:
                    #self.object_name = self.generator + "_Tessellation"
                    self.object_name = "Tessellation"

            layout = self.layout
            # Base and Component
            col = layout.column(align=True)
            #col.prop(self, "copy_settings")
            row = col.row(align=True)
            row.label(text="BASE : " + self.generator)
            row.label(text="COMPONENT : " + self.component)

            # Base Modifiers
            row = col.row(align=True)
            col2 = row.column(align=True)
            col2.prop(self, "gen_modifiers", text="Use Modifiers", icon='MODIFIER')
            base = bpy.data.objects[self.generator]
            try:
                if not (base.modifiers or base.data.shape_keys):
                    col2.enabled = False
                    self.gen_modifiers = False
            except:
                col2.enabled = False
                self.gen_modifiers = False

            # Component Modifiers
            row.separator()
            col3 = row.column(align=True)
            col3.prop(self, "com_modifiers", text="Use Modifiers", icon='MODIFIER')
            component = bpy.data.objects[self.component]
            try:
                if not (component.modifiers or component.data.shape_keys):
                    col3.enabled = False
                    self.com_modifiers = False
            except:
                col3.enabled = False
                self.com_modifiers = False
            col.separator()
            # Fill and Rotation
            row = col.row(align=True)
            row.label(text="Fill Mode:")
            row = col.row(align=True)
            row.prop(
                self, "fill_mode", icon='NONE', expand=True,
                slider=True, toggle=False, icon_only=False, event=False,
                full_event=False, emboss=True, index=-1)
            row = col.row(align=True)
            # merge settings
            row.prop(self, "merge")
            row.prop(self, "bool_smooth")

            # frame settings
            if self.fill_mode == 'FRAME':
                col.separator()
                col.label(text="Frame Settings:")
                row = col.row(align=True)
                row.prop(self, "frame_mode", expand=True)
                col.prop(self, "frame_thickness", text='Thickness', icon='NONE')
                col.separator()
                row = col.row(align=True)
                row.prop(self, "fill_frame", icon='NONE')
                show_frame_mat = self.bool_multi_components or self.bool_material_id
                col2 = row.column(align=True)
                col2.prop(self, "fill_frame_mat", icon='NONE')
                col2.enabled = self.fill_frame and show_frame_mat
                row = col.row(align=True)
                row.prop(self, "frame_boundary", text='Boundary', icon='NONE')
                col2 = row.column(align=True)
                col2.prop(self, "frame_boundary_mat", icon='NONE')
                col2.enabled = self.frame_boundary and show_frame_mat

            if self.rotation_mode == 'UV':
                uv_error = False
                if ob0.type != 'MESH':
                    row = col.row(align=True)
                    row.label(
                        text="UV rotation supported only for Mesh objects",
                        icon='ERROR')
                    uv_error = True
                else:
                    if len(ob0.data.uv_layers) == 0:
                        row = col.row(align=True)
                        check_name = self.generator
                        row.label(text="'" + check_name +
                                  "' doesn't have UV Maps", icon='ERROR')
                        uv_error = True
                if uv_error:
                    row = col.row(align=True)
                    row.label(text="Default rotation will be used instead",
                              icon='INFO')

            # Component Z
            col.separator()
            col.label(text="Thickness:")
            row = col.row(align=True)
            row.prop(
                self, "scale_mode", text="Scale Mode", icon='NONE', expand=True,
                slider=False, toggle=False, icon_only=False, event=False,
                full_event=False, emboss=True, index=-1)
            col.prop(
                self, "zscale", text="Scale", icon='NONE', expand=False,
                slider=True, toggle=False, icon_only=False, event=False,
                full_event=False, emboss=True, index=-1)
            if self.mode == 'BOUNDS':
                row = col.row(align=True)
                row.prop(
                    self, "offset", text="Offset", icon='NONE', expand=False,
                    slider=True, toggle=False, icon_only=False, event=False,
                    full_event=False, emboss=True, index=-1)
                row.enabled = not self.use_origin_offset
                '''
                col.prop(self, 'use_origin_offset')

                col.separator()
                row = col.row(align=True)
                row.prop_search(self, 'vertex_group_thickness',
                    ob0, "vertex_groups", text='')
                col2 = row.column(align=True)
                row2 = col2.row(align=True)
                row2.prop(self, "invert_vertex_group_thickness", text="",
                    toggle=True, icon='ARROW_LEFTRIGHT')
                row2.prop(self, "vertex_group_thickness_factor")
                row2.enabled = self.vertex_group_thickness in ob0.vertex_groups.keys()
                '''
            '''
            # Component XY
            col.separator()
            row = col.row(align=True)
            row.label(text="Component Coordinates:")
            row = col.row(align=True)
            row.prop(
                self, "mode", text="Component XY", icon='NONE', expand=True,
                slider=False, toggle=False, icon_only=False, event=False,
                full_event=False, emboss=True, index=-1)

            if self.mode != 'BOUNDS':
                col.separator()
                row = col.row(align=True)
                row.label(text="X:")
                row.prop(
                    self, "bounds_x", text="Bounds X", icon='NONE', expand=True,
                    slider=False, toggle=False, icon_only=False, event=False,
                    full_event=False, emboss=True, index=-1)

                row = col.row(align=True)
                row.label(text="Y:")
                row.prop(
                    self, "bounds_y", text="Bounds X", icon='NONE', expand=True,
                    slider=False, toggle=False, icon_only=False, event=False,
                    full_event=False, emboss=True, index=-1)
            '''
            col.separator()
            col.label(text="More settings in the Object Data Properties panel...", icon='PROPERTIES')


    def execute(self, context):
        allowed_obj = ('MESH', 'CURVE', 'META', 'SURFACE', 'FONT')
        try:
            ob0 = bpy.data.objects[self.generator]
            ob1 = bpy.data.objects[self.component]
        except:
            return {'CANCELLED'}

        self.object_name = "Tessellation"
        # Check if existing object with same name
        names = [o.name for o in bpy.data.objects]
        if self.object_name in names:
            count_name = 1
            while True:
                test_name = self.object_name + '.{:03d}'.format(count_name)
                if not (test_name in names):
                    self.object_name = test_name
                    break
                count_name += 1

        if ob1.type not in allowed_obj:
            message = "Component must be Mesh, Curve, Surface, Text or Meta object!"
            self.report({'ERROR'}, message)
            self.component = None

        if ob0.type not in allowed_obj:
            message = "Generator must be Mesh, Curve, Surface, Text or Meta object!"
            self.report({'ERROR'}, message)
            self.generator = ""

        if True:#self.component not in ("",None) and self.generator not in ("",None):
            if bpy.ops.object.select_all.poll():
                bpy.ops.object.select_all(action='TOGGLE')
            bpy.ops.object.mode_set(mode='OBJECT')

            #data0 = ob0.to_mesh(False)
            #data0 = ob0.data.copy()
            bool_update = False
            if context.object == ob0:
                auto_layer_collection()
                #new_ob = bpy.data.objects.new(self.object_name, data0)
                new_ob = convert_object_to_mesh(ob0,False,False)
                new_ob.data.name = self.object_name
                #bpy.context.collection.objects.link(new_ob)
                #bpy.context.view_layer.objects.active = new_ob
                new_ob.name = self.object_name
                #new_ob.select_set(True)
            else:
                new_ob = context.object
                bool_update = True
            new_ob = store_parameters(self, new_ob)
            try: bpy.ops.object.tissue_update_tessellate()
            except RuntimeError as e:
                bpy.data.objects.remove(new_ob)
                self.report({'ERROR'}, str(e))
                return {'CANCELLED'}
            if not bool_update:
                self.object_name = new_ob.name
                #self.working_on = self.object_name
                new_ob.location = ob0.location
                new_ob.matrix_world = ob0.matrix_world
            new_ob.tissue.tissue_type = 'TESSELLATE'
            return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

def update_dependencies(ob, objects):
    type = ob.tissue.tissue_type
    if type == 'NONE': return objects
    if ob.tissue.bool_dependencies:
        deps = get_deps(ob)
        for o in deps:
            if o.tissue.tissue_type == 'NONE' or o.tissue.bool_lock or o in objects:
                continue
            objects.append(o)
            objects = update_dependencies(o, objects)
    return objects

def get_deps(ob):
    type = ob.tissue.tissue_type
    if type == 'TESSELLATE':
        return [ob.tissue_tessellate.generator, ob.tissue_tessellate.component]
    elif type == 'TO_CURVE':
        return [ob.tissue_to_curve.object]
    else: return []

class tissue_update_tessellate_deps(Operator):
    bl_idname = "object.tissue_update_tessellate_deps"
    bl_label = "Tissue Refresh"
    bl_description = ("Fast update the tessellated mesh according to base and "
                      "component changes.")
    bl_options = {'REGISTER', 'UNDO'}

    go = False

    @classmethod
    def poll(cls, context):
        try:
            ob = context.object
            tess_props = ob.tissue_tessellate
            tessellated = tess_props.generator != None and tess_props.component != None
            to_curve = ob.tissue_to_curve.object != None
            return tessellated or to_curve
        except:
            return False

    #@staticmethod
    #def check_gen_comp(checking):
        # note pass the stored name key in here to check it out
    #    return checking in bpy.data.objects.keys()

    def execute(self, context):

        active_ob = context.object
        selected_objects = context.selected_objects
        '''
        ob0 = ob.tissue_tessellate.generator
        ob1 = ob.tissue_tessellate.component
        try:
            ob0.name
            ob1.name
        except:
            self.report({'ERROR'},
                        "Active object must be Tessellate before Update")
            return {'CANCELLED'}
        '''
        ### TO-DO: sorting according to dependencies
        update_objects = [o for o in selected_objects if o.tissue.tissue_type != 'NONE']
        for ob in selected_objects:
            update_objects = list(reversed(update_dependencies(ob, update_objects)))
            #update_objects = list(reversed(update_dependencies(ob, [ob])))
        for o in update_objects:
            override = {
                'object': o,
                'selected_objects' : [o]
                }
            if o.type == 'MESH':
                try:
                    bpy.ops.object.tissue_update_tessellate(override)
                except:
                    self.report({'ERROR'}, "Can't Tessellate :-(")
            else:
                try:
                    bpy.ops.object.tissue_convert_to_curve_update(override)
                except:
                    self.report({'ERROR'}, "Can't compute Curve :-(")

        context.view_layer.objects.active = active_ob
        for o in context.view_layer.objects:
            o.select_set(o in selected_objects)

        return {'FINISHED'}


class tissue_update_tessellate(Operator):
    bl_idname = "object.tissue_update_tessellate"
    bl_label = "Tissue Refresh Simple"
    bl_description = ("Fast update the tessellated mesh according to base and "
                      "component changes. Does not update dependencies")
    bl_options = {'REGISTER', 'UNDO'}

    go = False

    @classmethod
    def poll(cls, context):
        try:
            return context.object.tissue_tessellate.generator != None and \
                context.object.tissue_tessellate.component != None
        except:
            return False

    def execute(self, context):

        tissue_time(None,'Tissue: Tessellating...', levels=0)
        start_time = time.time()


        ob = context.object
        tess_props = props_to_dict(ob)
        if not self.go:
            generator = ob.tissue_tessellate.generator
            component = ob.tissue_tessellate.component
            zscale = ob.tissue_tessellate.zscale
            scale_mode = ob.tissue_tessellate.scale_mode
            rotation_mode = ob.tissue_tessellate.rotation_mode
            rotation_shift = ob.tissue_tessellate.rotation_shift
            rotation_direction = ob.tissue_tessellate.rotation_direction
            offset = ob.tissue_tessellate.offset
            merge = ob.tissue_tessellate.merge
            merge_open_edges_only = ob.tissue_tessellate.merge_open_edges_only
            merge_thres = ob.tissue_tessellate.merge_thres
            mode = ob.tissue_tessellate.mode
            gen_modifiers = ob.tissue_tessellate.gen_modifiers
            com_modifiers = ob.tissue_tessellate.com_modifiers
            bool_random = ob.tissue_tessellate.bool_random
            rand_seed = ob.tissue_tessellate.rand_seed
            rand_step = ob.tissue_tessellate.rand_step
            fill_mode = ob.tissue_tessellate.fill_mode
            bool_vertex_group = ob.tissue_tessellate.bool_vertex_group
            bool_selection = ob.tissue_tessellate.bool_selection
            bool_shapekeys = ob.tissue_tessellate.bool_shapekeys
            bool_smooth = ob.tissue_tessellate.bool_smooth
            bool_materials = ob.tissue_tessellate.bool_materials
            bool_dissolve_seams = ob.tissue_tessellate.bool_dissolve_seams
            bool_material_id = ob.tissue_tessellate.bool_material_id
            material_id = ob.tissue_tessellate.material_id
            iterations = ob.tissue_tessellate.iterations
            bool_combine = ob.tissue_tessellate.bool_combine
            normals_mode = ob.tissue_tessellate.normals_mode
            bool_advanced = ob.tissue_tessellate.bool_advanced
            bool_multi_components = ob.tissue_tessellate.bool_multi_components
            combine_mode = ob.tissue_tessellate.combine_mode
            bounds_x = ob.tissue_tessellate.bounds_x
            bounds_y = ob.tissue_tessellate.bounds_y
            cap_faces = ob.tissue_tessellate.cap_faces
            close_mesh = ob.tissue_tessellate.close_mesh
            open_edges_crease = ob.tissue_tessellate.open_edges_crease
            bridge_edges_crease = ob.tissue_tessellate.bridge_edges_crease
            bridge_smoothness = ob.tissue_tessellate.bridge_smoothness
            frame_thickness = ob.tissue_tessellate.frame_thickness
            frame_mode = ob.tissue_tessellate.frame_mode
            frame_boundary = ob.tissue_tessellate.frame_boundary
            fill_frame = ob.tissue_tessellate.fill_frame
            frame_boundary_mat = ob.tissue_tessellate.frame_boundary_mat
            fill_frame_mat = ob.tissue_tessellate.fill_frame_mat
            bridge_cuts = ob.tissue_tessellate.bridge_cuts
            cap_material_offset = ob.tissue_tessellate.cap_material_offset
            bridge_material_offset = ob.tissue_tessellate.bridge_material_offset
            patch_subs = ob.tissue_tessellate.patch_subs
            use_origin_offset = ob.tissue_tessellate.use_origin_offset
            vertex_group_thickness = ob.tissue_tessellate.vertex_group_thickness
            invert_vertex_group_thickness = ob.tissue_tessellate.invert_vertex_group_thickness
            vertex_group_thickness_factor = ob.tissue_tessellate.vertex_group_thickness_factor
            vertex_group_cap_owner = ob.tissue_tessellate.vertex_group_cap_owner
            vertex_group_cap = ob.tissue_tessellate.vertex_group_cap
            invert_vertex_group_cap = ob.tissue_tessellate.invert_vertex_group_cap
            vertex_group_bridge_owner = ob.tissue_tessellate.vertex_group_bridge_owner
            vertex_group_bridge = ob.tissue_tessellate.vertex_group_bridge
            invert_vertex_group_bridge = ob.tissue_tessellate.invert_vertex_group_bridge
            vertex_group_rotation = ob.tissue_tessellate.vertex_group_rotation
            invert_vertex_group_rotation = ob.tissue_tessellate.invert_vertex_group_rotation
            vertex_group_smooth_normals = ob.tissue_tessellate.vertex_group_smooth_normals
            invert_vertex_group_smooth_normals = ob.tissue_tessellate.invert_vertex_group_smooth_normals
            target = ob.tissue_tessellate.target
        try:
            generator.name
            component.name
        except:
            self.report({'ERROR'},
                        "Active object must be Tessellate before Update")
            return {'CANCELLED'}

        # reset messages
        ob.tissue_tessellate.warning_message_merge = ''

        tess_props = props_to_dict(ob)

        # Solve Local View issues
        local_spaces = []
        local_ob0 = []
        local_ob1 = []
        for area in context.screen.areas:
            for space in area.spaces:
                try:
                    if ob.local_view_get(space):
                        local_spaces.append(space)
                        local_ob0 = ob0.local_view_get(space)
                        ob0.local_view_set(space, True)
                        local_ob1 = ob1.local_view_get(space)
                        ob1.local_view_set(space, True)
                except:
                    pass

        starting_mode = context.object.mode

        #if starting_mode == 'PAINT_WEIGHT': starting_mode = 'WEIGHT_PAINT'
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        ob0 = generator
        ob1 = component
        ##### auto_layer_collection()

        ob0_hide = ob0.hide_get()
        ob0_hidev = ob0.hide_viewport
        ob0_hider = ob0.hide_render
        ob1_hide = ob1.hide_get()
        ob1_hidev = ob1.hide_viewport
        ob1_hider = ob1.hide_render
        ob0.hide_set(False)
        ob0.hide_viewport = False
        ob0.hide_render = False
        ob1.hide_set(False)
        ob1.hide_viewport = False
        ob1.hide_render = False

        if ob0.type == 'META':
            base_ob = convert_object_to_mesh(ob0, False, True)
        else:
            base_ob = ob0.copy()
            base_ob.data = ob0.data#
            context.collection.objects.link(base_ob)
        base_ob.name = '_tissue_tmp_base'


        # In Blender 2.80 cache of copied objects is lost, must be re-baked
        bool_update_cloth = False
        for m in base_ob.modifiers:
            if m.type == 'CLOTH':
                m.point_cache.frame_end = context.scene.frame_current
                bool_update_cloth = True
        if bool_update_cloth:
            scene = context.scene
            for mod in base_ob.modifiers:
                if mod.type == 'CLOTH':
                    override = {'scene': scene, 'active_object': base_ob, 'point_cache': mod.point_cache}
                    bpy.ops.ptcache.bake(override, bake=True)
                    break
        base_ob.modifiers.update()

        # clear vertex groups before creating new ones
        ob.vertex_groups.clear()

        if bool_selection:
            faces = base_ob.data.polygons
            selections = [False]*len(faces)
            faces.foreach_get('select',selections)
            selections = np.array(selections)
            if not selections.any():
                message = "There are no faces selected."
                context.view_layer.objects.active = ob
                ob.select_set(True)
                bpy.ops.object.mode_set(mode=starting_mode)
                bpy.data.objects.remove(base_ob)
                self.report({'ERROR'}, message)
                return {'CANCELLED'}

        iter_objects = [base_ob]
        ob_location = ob.location
        ob_matrix_world = ob.matrix_world

        ob.data.clear_geometry()    # Faster with previous heavy geometries

        for iter in range(iterations):
            tess_props['generator'] = base_ob

            if iter > 0 and len(iter_objects) == 0: break
            if iter > 0 and normals_mode in ('SHAPEKEYS','OBJECT'):
                tess_props['normals_mode'] = 'VERTS'
            same_iteration = []
            matched_materials = []

            if bool_multi_components:
                components = []
                objects_keys = bpy.data.objects.keys()
                for mat_slot in base_ob.material_slots:
                    mat_name = mat_slot.material.name
                    if mat_name in objects_keys:
                        ob1 = bpy.data.objects[mat_name]
                        if ob1.type in ('MESH', 'CURVE','SURFACE','FONT','META'):
                            components.append(bpy.data.objects[mat_name])
                        else:
                            components.append(None)
                    else:
                        components.append(None)
            else:
                components = [ob1]
            tess_props['component'] = components

            # patch subdivisions for additional iterations
            if iter > 0 and fill_mode == 'PATCH':
                temp_mod = base_ob.modifiers.new('Tissue_Subsurf', type='SUBSURF')
                temp_mod.levels = patch_subs

            # patch tessellation
            tissue_time(None,"Tessellate iteration...",levels=1)
            tt = time.time()
            same_iteration = tessellate_patch(tess_props)
            tissue_time(tt, "Tessellate iteration",levels=1)

            tt = time.time()
            if iter > 0 and fill_mode == 'PATCH':
                base_ob.modifiers.remove(temp_mod)

            # if empty or error, continue
            if type(same_iteration) != list:#is not bpy.types.Object and :
                continue

            for id, new_ob in enumerate(same_iteration):
                # rename, make active and change transformations
                new_ob.name = '_tissue_tmp_{}_{}'.format(iter,id)
                new_ob.select_set(True)
                context.view_layer.objects.active = new_ob
                new_ob.location = ob_location
                new_ob.matrix_world = ob_matrix_world

            base_ob.location = ob_location
            base_ob.matrix_world = ob_matrix_world
            # join together multiple components iterations
            if type(same_iteration) == list:
                if len(same_iteration) > 1:
                    #join_objects(context, same_iteration)
                    new_ob = join_objects(same_iteration)

            if type(new_ob) in (int,str):
                if iter == 0:
                    try:
                        bpy.data.objects.remove(iter_objects[0])
                        iter_objects = []
                    except: continue
                continue

            # Clean last iteration, needed for combine object
            if (bool_selection or bool_material_id) and combine_mode == 'UNUSED':
                # remove faces from last mesh
                bm = bmesh.new()
                if fill_mode == 'PATCH' and iter == 0:
                    last_mesh = simple_to_mesh(ob0)
                else:
                    last_mesh = iter_objects[-1].data.copy()
                bm.from_mesh(last_mesh)
                bm.faces.ensure_lookup_table()
                if bool_multi_components:
                    remove_materials = matched_materials
                elif bool_material_id:
                    remove_materials = [material_id]
                else: remove_materials = []
                if bool_selection:
                    if bool_multi_components or bool_material_id:
                        remove_faces = [f for f in bm.faces if f.material_index in remove_materials and f.select]
                    else:
                        remove_faces = [f for f in bm.faces if f.select]
                else:
                    remove_faces = [f for f in bm.faces if f.material_index in remove_materials]
                bmesh.ops.delete(bm, geom=remove_faces, context='FACES')
                bm.to_mesh(last_mesh)
                bm.free()
                last_mesh.update()
                last_mesh.name = '_tissue_tmp_previous_unused'

                # delete previous iteration if empty or update it
                if len(last_mesh.vertices) > 0:
                    iter_objects[-1].data = last_mesh.copy()
                    iter_objects[-1].data.update()
                else:
                    bpy.data.objects.remove(iter_objects[-1])
                    iter_objects = iter_objects[:-1]
                # set new base object for next iteration
                base_ob = convert_object_to_mesh(new_ob,True,True)
                if iter < iterations-1: new_ob.data = base_ob.data
                # store new iteration and set transformations
                iter_objects.append(new_ob)
                base_ob.name = '_tissue_tmp_base'
            elif combine_mode == 'ALL':
                base_ob = new_ob.copy()
                iter_objects = [new_ob] + iter_objects
            else:
                if base_ob != new_ob:
                    bpy.data.objects.remove(base_ob)
                base_ob = new_ob
                iter_objects = [new_ob]

            # Combine
            if combine_mode != 'LAST' and len(iter_objects) > 1:
                if base_ob not in iter_objects and type(base_ob) == bpy.types.Object:
                    bpy.data.objects.remove(base_ob)
                new_ob = join_objects(iter_objects)
                iter_objects = [new_ob]

            tissue_time(tt, "Combine tessellations", levels=1)

            if merge:
                use_bmesh = not (bool_shapekeys and fill_mode == 'PATCH' and bool_multi_components)
                merged = merge_components(new_ob, ob.tissue_tessellate, use_bmesh)
                if merged == 'bridge_error':
                    message = "Can't make the bridge!"
                    ob.tissue_tessellate.warning_message_merge = message

            base_ob = new_ob #context.view_layer.objects.active

        tt = time.time()

        if new_ob == 0:
            #bpy.data.objects.remove(base_ob.data)
            try: bpy.data.objects.remove(base_ob)
            except: pass
            message = "The generated object is an empty geometry!"
            context.view_layer.objects.active = ob
            ob.select_set(True)
            bpy.ops.object.mode_set(mode=starting_mode)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        errors = {}
        errors["modifiers_error"] = "Modifiers that change the topology of the mesh \n" \
                                    "after the last Subsurf (or Multires) are not allowed."
        if new_ob in errors:
            for o in iter_objects:
                try: bpy.data.objects.remove(o)
                except: pass
            try: bpy.data.meshes.remove(data1)
            except: pass
            context.view_layer.objects.active = ob
            ob.select_set(True)
            message = errors[new_ob]
            ob.tissue_tessellate.error_message = message
            bpy.ops.object.mode_set(mode=starting_mode)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

        # update data and preserve name
        if ob.type != 'MESH':
            loc, matr = ob.location, ob.matrix_world
            ob = convert_object_to_mesh(ob,False,True)
            ob.location, ob.matrix_world = loc, matr
        data_name = ob.data.name
        old_data = ob.data
        old_data.name = '_tissue_tmp_old_data'
        #ob.data = bpy.data.meshes.new_from_object(new_ob)#
        ob.data = new_ob.data
        ob.data.name = data_name
        bpy.data.meshes.remove(old_data)

        # copy vertex group
        for vg in new_ob.vertex_groups:
            if not vg.name in ob.vertex_groups.keys():
                ob.vertex_groups.new(name=vg.name)

        selected_objects = [o for o in context.selected_objects]
        for o in selected_objects: o.select_set(False)

        ob.select_set(True)
        context.view_layer.objects.active = ob

        is_multiple = iterations > 1 or combine_mode != 'LAST'# or bool_multi_components
        if merge and is_multiple:
            use_bmesh = not (bool_shapekeys and fill_mode == 'PATCH' and bool_multi_components)
            merge_components(new_ob, ob.tissue_tessellate, use_bmesh)

        if bool_smooth: bpy.ops.object.shade_smooth()

        for mesh in bpy.data.meshes:
            if not mesh.users: bpy.data.meshes.remove(mesh)

        for o in selected_objects:
            try: o.select_set(True)
            except: pass

        ob.tissue_tessellate.error_message = ""

        # Restore Base visibility
        ob0.hide_set(ob0_hide)
        ob0.hide_viewport = ob0_hidev
        ob0.hide_render = ob0_hider
        # Restore Component visibility
        ob1.hide_set(ob1_hide)
        ob1.hide_viewport = ob1_hidev
        ob1.hide_render = ob1_hider
        # Restore Local visibility
        for space, local0, local1 in zip(local_spaces, local_ob0, local_ob1):
            ob0.local_view_set(space, local0)
            ob1.local_view_set(space, local1)

        bpy.data.objects.remove(new_ob)

        # clean objects
        for o in bpy.data.objects:
            #if o.name not in context.view_layer.objects and "_tissue_tmp" in o.name:
            if "_tissue_tmp" in o.name:
                bpy.data.objects.remove(o)

        tissue_time(tt, "Closing tessellation", levels=1)

        tissue_time(start_time,'Tessellation of "{}"'.format(ob.name),levels=0)
        return {'FINISHED'}

    def check(self, context):
        return True

class TISSUE_PT_tessellate(Panel):
    bl_label = "Tissue Tools"
    bl_category = "Tissue"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    #bl_options = {'DEFAULT_OPEN'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'}

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.label(text="Generate:")
        col.operator("object.tissue_tessellate", text='Tessellate')
        col.operator("object.dual_mesh_tessellated", text='Dual Mesh')
        col.separator()

        #col.label(text="Curves:")
        col.operator("object.tissue_convert_to_curve", icon='OUTLINER_OB_CURVE', text="Convert to Curve")
        #row.operator("object.tissue_convert_to_curve_update", icon='FILE_REFRESH', text='')

        col.separator()
        col.operator("object.tissue_update_tessellate_deps", icon='FILE_REFRESH', text='Refresh') #####

        col.separator()
        col.label(text="Rotate Faces:")
        row = col.row(align=True)
        row.operator("mesh.tissue_rotate_face_left", text='Left', icon='LOOP_BACK')
        row.operator("mesh.tissue_rotate_face_flip", text='Flip', icon='UV_SYNC_SELECT')
        row.operator("mesh.tissue_rotate_face_right", text='Right', icon='LOOP_FORWARDS')

        col.separator()
        col.label(text="Other:")
        col.operator("object.dual_mesh")
        col.operator("object.polyhedra_wireframe", icon='MOD_WIREFRAME', text='Polyhedra Wireframe')
        col.operator("object.lattice_along_surface", icon="OUTLINER_OB_LATTICE")

        act = context.object
        if act and act.type == 'MESH':
            col.operator("object.uv_to_mesh", icon="UV")

            if act.mode == 'EDIT':
                col.separator()
                col.label(text="Weight:")
                col.operator("object.tissue_weight_distance", icon="TRACKING")
                col.operator("object.tissue_weight_streamlines", icon="ANIM")

        col.separator()
        col.label(text="Materials:")
        col.operator("object.random_materials", icon='COLOR')
        col.operator("object.weight_to_materials", icon='GROUP_VERTEX')

        col.separator()
        col.label(text="Utils:")
        col.operator("render.tissue_render_animation", icon='RENDER_ANIMATION')

class TISSUE_PT_tessellate_object(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_label = "Tissue Tessellate"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try: return context.object.type == 'MESH'
        except: return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        tissue_props = ob.tissue
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        if not bool_tessellated:
            layout.label(text="The selected object is not a Tessellated object",
                        icon='INFO')
        else:
            if props.error_message != "":
                layout.label(text=props.error_message,
                            icon='ERROR')
            col = layout.column(align=True)
            row = col.row(align=True)

            set_tessellate_handler(self,context)
            ###### set_animatable_fix_handler(self,context)
            row.operator("object.tissue_update_tessellate_deps", icon='FILE_REFRESH', text='Refresh') ####
            lock_icon = 'LOCKED' if tissue_props.bool_lock else 'UNLOCKED'
            #lock_icon = 'PINNED' if props.bool_lock else 'UNPINNED'
            deps_icon = 'LINKED' if tissue_props.bool_dependencies else 'UNLINKED'
            row.prop(tissue_props, "bool_dependencies", text="", icon=deps_icon)
            row.prop(tissue_props, "bool_lock", text="", icon=lock_icon)
            col2 = row.column(align=True)
            col2.prop(tissue_props, "bool_run", text="",icon='TIME')
            col2.enabled = not tissue_props.bool_lock
            layout.use_property_split = True
            layout.use_property_decorate = False  # No animation.
            col = layout.column(align=True)
            row = col.row(align=True)
            row.label(text='Base:')
            row.prop_search(props, "generator", context.scene, "objects")
            col2 = row.column(align=True)
            col2.prop(props, "gen_modifiers", text='',icon='MODIFIER')
            try:
                if not (props.generator.modifiers or props.generator.data.shape_keys):
                    col2.enabled = False
            except:
                    col2.enabled = False
            col.separator()
            row = col.row(align=True)
            row.label(text='Component:')
            row.prop_search(props, "component", context.scene, "objects")
            col2 = row.column(align=True)
            col2.prop(props, "com_modifiers", text='',icon='MODIFIER')
            try:
                if not (props.component.modifiers or props.component.data.shape_keys):
                    col2.enabled = False
            except:
                    col2.enabled = False
            layout.use_property_split = False

            # Fill
            col = layout.column(align=True)
            col.label(text="Fill Mode:")

            # fill
            row = col.row(align=True)
            row.prop(props, "fill_mode", icon='NONE', expand=True,
                     slider=True, toggle=False, icon_only=False, event=False,
                     full_event=False, emboss=True, index=-1)

            #layout.use_property_split = True
            col = layout.column(align=True)
            col.prop(props, "bool_smooth")


class TISSUE_PT_tessellate_frame(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = "Frame Settings"
    #bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            bool_frame = context.object.tissue_tessellate.fill_mode == 'FRAME'
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_frame and bool_tessellated
        except:
            return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        if bool_tessellated:
            col = layout.column(align=True)
            row = col.row(align=True)
            row.prop(props, "frame_mode", expand=True)
            row = col.row(align=True)
            row.prop(props, "frame_thickness", icon='NONE', expand=True)
            col.separator()
            row = col.row(align=True)
            row.prop(props, "fill_frame", icon='NONE')
            show_frame_mat = props.bool_multi_components or props.bool_material_id
            col2 = row.column(align=True)
            col2.prop(props, "fill_frame_mat", icon='NONE')
            col2.enabled = props.fill_frame and show_frame_mat
            row = col.row(align=True)
            row.prop(props, "frame_boundary", text='Boundary', icon='NONE')
            col2 = row.column(align=True)
            col2.prop(props, "frame_boundary_mat", icon='NONE')
            col2.enabled = props.frame_boundary and show_frame_mat


class TISSUE_PT_tessellate_coordinates(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = "Component Coordinates"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_tessellated
        except:
            return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        if bool_tessellated:
            col = layout.column(align=True)
            # component XY
            row = col.row(align=True)
            row.prop(props, "mode", expand=True)

            if props.mode != 'BOUNDS':
                col.separator()
                row = col.row(align=True)
                row.label(text="X:")
                row.prop(
                    props, "bounds_x", text="Bounds X", icon='NONE', expand=True,
                    slider=False, toggle=False, icon_only=False, event=False,
                    full_event=False, emboss=True, index=-1)

                row = col.row(align=True)
                row.label(text="Y:")
                row.prop(
                    props, "bounds_y", text="Bounds X", icon='NONE', expand=True,
                    slider=False, toggle=False, icon_only=False, event=False,
                    full_event=False, emboss=True, index=-1)


class TISSUE_PT_tessellate_rotation(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = "Rotation"
    bl_options = {'DEFAULT_CLOSED'}


    @classmethod
    def poll(cls, context):
        try:
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_tessellated
        except:
            return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        if bool_tessellated:
            # rotation
            layout.use_property_split = True
            layout.use_property_decorate = False  # No animation.
            col = layout.column(align=True)
            col.prop(props, "rotation_mode", text='Rotation', icon='NONE', expand=False,
                     slider=True, toggle=False, icon_only=False, event=False,
                     full_event=False, emboss=True, index=-1)
            if props.rotation_mode == 'WEIGHT':
                col.separator()
                row = col.row(align=True)
                row.separator()
                row.separator()
                row.separator()
                row.prop_search(props, 'vertex_group_rotation',
                    ob0, "vertex_groups", text='Vertex Group')
                col2 = row.column(align=True)
                col2.prop(props, "invert_vertex_group_rotation", text="", toggle=True, icon='ARROW_LEFTRIGHT')
                col2.enabled = props.vertex_group_rotation in ob0.vertex_groups.keys()
                col.separator()
                col.prop(props, "rotation_direction", expand=False,
                          slider=True, toggle=False, icon_only=False, event=False,
                          full_event=False, emboss=True, index=-1)
            if props.rotation_mode == 'RANDOM':
                col.prop(props, "rand_seed")
                col.prop(props, "rand_step")
            else:
                col.prop(props, "rotation_shift")

            if props.rotation_mode == 'UV':
                uv_error = False
                if props.generator.type != 'MESH':
                    row = col.row(align=True)
                    row.label(
                        text="UV rotation supported only for Mesh objects",
                        icon='ERROR')
                    uv_error = True
                else:
                    if len(props.generator.data.uv_layers) == 0:
                        row = col.row(align=True)
                        row.label(text="'" + props.generator.name +
                                  " doesn't have UV Maps", icon='ERROR')
                        uv_error = True
                if uv_error:
                    row = col.row(align=True)
                    row.label(text="Default rotation will be used instead",
                              icon='INFO')

class TISSUE_PT_tessellate_thickness(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = "Thickness"
    #bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_tessellated
        except:
            return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        #layout.use_property_split = True
        if bool_tessellated:
            col = layout.column(align=True)
            # component Z
            row = col.row(align=True)
            row.prop(props, "scale_mode", expand=True)
            col.prop(props, "zscale", text="Scale", icon='NONE', expand=False,
                     slider=True, toggle=False, icon_only=False, event=False,
                     full_event=False, emboss=True, index=-1)
            if props.mode == 'BOUNDS':
                row = col.row(align=True)
                row.prop(props, "offset", text="Offset", icon='NONE', expand=False,
                         slider=True, toggle=False, icon_only=False, event=False,
                         full_event=False, emboss=True, index=-1)
                row.enabled = not props.use_origin_offset
                col.prop(props, 'use_origin_offset')

            col.separator()
            row = col.row(align=True)
            row.prop_search(props, 'vertex_group_thickness',
                ob0, "vertex_groups", text='')
            col2 = row.column(align=True)
            row2 = col2.row(align=True)
            row2.prop(props, "invert_vertex_group_thickness", text="",
                toggle=True, icon='ARROW_LEFTRIGHT')
            row2.prop(props, "vertex_group_thickness_factor")
            row2.enabled = props.vertex_group_thickness in ob0.vertex_groups.keys()

class TISSUE_PT_tessellate_direction(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = "Direction"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_tessellated
        except:
            return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        #layout.use_property_split = True
        if bool_tessellated:
            col = layout.column(align=True)
            row = col.row(align=True)
            row.prop(
            props, "normals_mode", text="Direction", icon='NONE', expand=True,
                slider=False, toggle=False, icon_only=False, event=False,
                full_event=False, emboss=True, index=-1)
            if props.normals_mode == 'OBJECT':
                col.separator()
                row = col.row(align=True)
                row.prop_search(props, "target", context.scene, "objects", text='Target')
            if props.warning_message_thickness != '':
                col.separator()
                col.label(text=props.warning_message_thickness, icon='ERROR')
            if props.normals_mode != 'FACES':
                col.separator()
                col.prop(props, "smooth_normals")
                if props.smooth_normals:
                    row = col.row(align=True)
                    row.prop(props, "smooth_normals_iter")
                    row.separator()
                    row.prop_search(props, 'vertex_group_smooth_normals',
                        ob0, "vertex_groups", text='')
                    col2 = row.column(align=True)
                    col2.prop(props, "invert_vertex_group_smooth_normals", text="", toggle=True, icon='ARROW_LEFTRIGHT')
                    col2.enabled = props.vertex_group_smooth_normals in ob0.vertex_groups.keys()



class TISSUE_PT_tessellate_options(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = " "
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_tessellated
        except:
            return False

    def draw_header(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        self.layout.prop(props, "merge")

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.
        if bool_tessellated:
            col = layout.column(align=True)
            if props.merge:
                col.prop(props, "merge_thres")
                col.prop(props, "merge_open_edges_only")
                col.prop(props, "bool_dissolve_seams")
                col.prop(props, "close_mesh")
                if props.close_mesh in ('BRIDGE', 'BRIDGE_CAP'):
                    col.separator()
                    if props.close_mesh == 'BRIDGE_CAP':
                        if props.vertex_group_bridge_owner == 'BASE': ob_bridge = ob0
                        else: ob_bridge = ob1
                        row = col.row(align=True)
                        row.prop_search(props, 'vertex_group_bridge',
                            ob_bridge, "vertex_groups")
                        row.prop(props, "invert_vertex_group_bridge", text="",
                            toggle=True, icon='ARROW_LEFTRIGHT')
                        row = col.row(align=True)
                        row.prop(props, "vertex_group_bridge_owner", expand=True,
                                slider=False, toggle=False, icon_only=False, event=False,
                                full_event=False, emboss=True, index=-1)
                        col2 = row.column(align=True)
                        row2 = col2.row(align=True)
                    col.prop(props, "bridge_edges_crease", text="Crease")
                    col.prop(props, "bridge_material_offset", text='Material Offset')
                    '''
                    if props.close_mesh == 'BRIDGE' and False:
                        col.separator()
                        col.prop(props, "bridge_cuts")
                        col.prop(props, "bridge_smoothness")
                    '''
                if props.close_mesh in ('CAP', 'BRIDGE_CAP'):
                    #row = col.row(align=True)
                    col.separator()
                    if props.close_mesh == 'BRIDGE_CAP':
                        if props.vertex_group_cap_owner == 'BASE': ob_cap = ob0
                        else: ob_cap = ob1
                        row = col.row(align=True)
                        row.prop_search(props, 'vertex_group_cap',
                            ob_cap, "vertex_groups")
                        row.prop(props, "invert_vertex_group_cap", text="",
                            toggle=True, icon='ARROW_LEFTRIGHT')
                        row = col.row(align=True)
                        row.prop(props, "vertex_group_cap_owner", expand=True,
                            slider=False, toggle=False, icon_only=False, event=False,
                            full_event=False, emboss=True, index=-1)
                    col.prop(props, "open_edges_crease", text="Crease")
                    col.prop(props, "cap_material_offset", text='Material Offset')
                if props.warning_message_merge:
                    col.separator()
                    col.label(text=props.warning_message_merge, icon='ERROR')

class TISSUE_PT_tessellate_morphing(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = "Weight and Morphing"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_tessellated
        except:
            return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        if bool_tessellated:
            allow_shapekeys = not props.com_modifiers
            for m in ob0.data.materials:
                try:
                    o = bpy.data.objects[m.name]
                    allow_multi = True
                    try:
                        if o.data.shape_keys is None: continue
                        elif len(o.data.shape_keys.key_blocks) < 2: continue
                        else: allow_shapekeys = not props.com_modifiers
                    except: pass
                except: pass
            col = layout.column(align=True)
            #col.label(text="Morphing:")
            row = col.row(align=True)
            col2 = row.column(align=True)
            col2.prop(props, "bool_vertex_group", icon='GROUP_VERTEX')
            #col2.prop_search(props, "vertex_group", props.generator, "vertex_groups")
            try:
                if len(props.generator.vertex_groups) == 0:
                    col2.enabled = False
            except:
                col2.enabled = False
            row.separator()
            col2 = row.column(align=True)
            row2 = col2.row(align=True)
            row2.prop(props, "bool_shapekeys", text="Use Shape Keys",  icon='SHAPEKEY_DATA')
            row2.enabled = allow_shapekeys
            if not allow_shapekeys and props.bool_shapekeys:
                col2 = layout.column(align=True)
                row2 = col2.row(align=True)
                row2.label(text="Use Shape Keys is not compatible with Use Modifiers", icon='INFO')


class TISSUE_PT_tessellate_selective(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = "Selective"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_tessellated
        except:
            return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        if bool_tessellated:
            allow_multi = False
            allow_shapekeys = not props.com_modifiers
            for m in ob0.data.materials:
                try:
                    o = bpy.data.objects[m.name]
                    allow_multi = True
                    try:
                        if o.data.shape_keys is None: continue
                        elif len(o.data.shape_keys.key_blocks) < 2: continue
                        else: allow_shapekeys = not props.com_modifiers
                    except: pass
                except: pass
            # LIMITED TESSELLATION
            col = layout.column(align=True)
            #col.label(text="Limited Tessellation:")
            row = col.row(align=True)
            col2 = row.column(align=True)
            col2.prop(props, "bool_selection", text="On selected Faces", icon='RESTRICT_SELECT_OFF')
            row.separator()
            if props.generator.type != 'MESH':
                col2.enabled = False
            col2 = row.column(align=True)
            col2.prop(props, "bool_material_id", icon='MATERIAL_DATA', text="Material ID")
            if props.bool_material_id and not props.bool_multi_components:
                #col2 = row.column(align=True)
                col2.prop(props, "material_id")
            if props.bool_multi_components:
                col2.enabled = False

            col.separator()
            row = col.row(align=True)
            col2 = row.column(align=True)
            col2.prop(props, "bool_multi_components", icon='MOD_TINT')
            if not allow_multi:
                col2.enabled = False


class TISSUE_PT_tessellate_iterations(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_parent_id = "TISSUE_PT_tessellate_object"
    bl_label = "Iterations"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        try:
            bool_tessellated = context.object.tissue_tessellate.generator != None
            return context.object.type == 'MESH' and bool_tessellated
        except:
            return False

    def draw(self, context):
        ob = context.object
        props = ob.tissue_tessellate
        allowed_obj = ('MESH','CURVE','SURFACE','FONT', 'META')

        try:
            bool_tessellated = props.generator or props.component != None
            ob0 = props.generator
            ob1 = props.component
        except: bool_tessellated = False
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.
        if bool_tessellated:
            col = layout.column(align=True)
            row = col.row(align=True)
            #row.label(text='', icon='FILE_REFRESH')
            col.prop(props, 'iterations', text='Repeat')#, icon='FILE_REFRESH')
            if props.iterations > 1 and props.fill_mode == 'PATCH':
                col.separator()
                #row = col.row(align=True)
                col.prop(props, 'patch_subs')
            layout.use_property_split = False
            col = layout.column(align=True)
            #row = col.row(align=True)
            col.label(text='Combine Iterations:')
            row = col.row(align=True)
            row.prop(
                props, "combine_mode", text="Combine:",icon='NONE', expand=True,
                slider=False, toggle=False, icon_only=False, event=False,
                full_event=False, emboss=True, index=-1)

class tissue_rotate_face_right(Operator):
    bl_idname = "mesh.tissue_rotate_face_right"
    bl_label = "Tissue Rotate Faces Right"
    bl_description = "Rotate clockwise selected faces and update tessellated meshes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        try:
            #bool_tessellated = context.object.tissue_tessellate.generator != None
            ob = context.object
            return ob.type == 'MESH' and ob.mode == 'EDIT'# and bool_tessellated
        except:
            return False

    def execute(self, context):
        ob = context.active_object
        me = ob.data

        bm = bmesh.from_edit_mesh(me)
        mesh_select_mode = [sm for sm in context.tool_settings.mesh_select_mode]

        for face in bm.faces:
            if (face.select):
                vs = face.verts[:]
                vs2 = vs[-1:]+vs[:-1]
                material_index = face.material_index
                bm.faces.remove(face)
                f2 = bm.faces.new(vs2)
                f2.select = True
                f2.material_index = material_index
                bm.normal_update()

        # trigger UI update
        bmesh.update_edit_mesh(me)
        bm.free()
        ob.select_set(False)

        # update tessellated meshes
        bpy.ops.object.mode_set(mode='OBJECT')
        for o in [obj for obj in bpy.data.objects if
                  obj.tissue_tessellate.generator == ob and obj.visible_get()]:
            context.view_layer.objects.active = o

            #override = {'object': o, 'mode': 'OBJECT', 'selected_objects': [o]}
            if not o.tissue.bool_lock:
                bpy.ops.object.tissue_update_tessellate()
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        context.tool_settings.mesh_select_mode = mesh_select_mode

        return {'FINISHED'}

class tissue_rotate_face_flip(Operator):
    bl_idname = "mesh.tissue_rotate_face_flip"
    bl_label = "Tissue Rotate Faces Flip"
    bl_description = "Fully rotate selected faces and update tessellated meshes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        try:
            #bool_tessellated = context.object.tissue_tessellate.generator != None
            ob = context.object
            return ob.type == 'MESH' and ob.mode == 'EDIT'# and bool_tessellated
        except:
            return False

    def execute(self, context):
        ob = context.active_object
        me = ob.data

        bm = bmesh.from_edit_mesh(me)
        mesh_select_mode = [sm for sm in context.tool_settings.mesh_select_mode]

        for face in bm.faces:
            if (face.select):
                vs = face.verts[:]
                nrot = int(len(vs)/2)
                vs2 = vs[-nrot:]+vs[:-nrot]
                material_index = face.material_index
                bm.faces.remove(face)
                f2 = bm.faces.new(vs2)
                f2.select = True
                f2.material_index = material_index
                bm.normal_update()

        # trigger UI update
        bmesh.update_edit_mesh(me)
        bm.free()
        ob.select_set(False)

        # update tessellated meshes
        bpy.ops.object.mode_set(mode='OBJECT')
        for o in [obj for obj in bpy.data.objects if
                  obj.tissue_tessellate.generator == ob and obj.visible_get()]:
            context.view_layer.objects.active = o

            #override = {'object': o, 'mode': 'OBJECT', 'selected_objects': [o]}
            if not o.tissue.bool_lock:
                bpy.ops.object.tissue_update_tessellate()
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        context.tool_settings.mesh_select_mode = mesh_select_mode

        return {'FINISHED'}

class tissue_rotate_face_left(Operator):
    bl_idname = "mesh.tissue_rotate_face_left"
    bl_label = "Tissue Rotate Faces Left"
    bl_description = "Rotate counterclockwise selected faces and update tessellated meshes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        try:
            #bool_tessellated = context.object.tissue_tessellate.generator != None
            ob = context.object
            return ob.type == 'MESH' and ob.mode == 'EDIT'# and bool_tessellated
        except:
            return False

    def execute(self, context):
        ob = context.active_object
        me = ob.data

        bm = bmesh.from_edit_mesh(me)
        mesh_select_mode = [sm for sm in context.tool_settings.mesh_select_mode]

        for face in bm.faces:
            if (face.select):
                vs = face.verts[:]
                vs2 = vs[1:]+vs[:1]
                material_index = face.material_index
                bm.faces.remove(face)
                f2 = bm.faces.new(vs2)
                f2.select = True
                f2.material_index = material_index
                bm.normal_update()

        # trigger UI update
        bmesh.update_edit_mesh(me)
        bm.free()
        ob.select_set(False)

        # update tessellated meshes
        bpy.ops.object.mode_set(mode='OBJECT')
        for o in [obj for obj in bpy.data.objects if
                  obj.tissue_tessellate.generator == ob and obj.visible_get()]:
            context.view_layer.objects.active = o
            if not o.tissue.bool_lock:
                bpy.ops.object.tissue_update_tessellate()
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        context.tool_settings.mesh_select_mode = mesh_select_mode

        return {'FINISHED'}


def convert_to_frame(ob, props, use_modifiers):
    new_ob = convert_object_to_mesh(ob, use_modifiers, True)

    # create bmesh
    bm = bmesh.new()
    bm.from_mesh(new_ob.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    if props['bool_selection']:
        original_faces = [f for f in bm.faces if f.select]
    else:
        original_faces = list(bm.faces)
    # detect edge loops

    loops = []
    boundaries_mat = []
    neigh_face_center = []
    face_normals = []
    # append boundary loops
    if props['frame_boundary']:
        #selected_edges = [e for e in bm.edges if e.select]
        selected_edges = [e for e in bm.edges if e.is_boundary]
        if len(selected_edges) > 0:
            loop = []
            count = 0
            e0 = selected_edges[0]
            face = e0.link_faces[0]
            boundary_mat = [face.material_index + props['frame_boundary_mat']]
            face_center = [face.calc_center_median()]
            loop_normals = [face.normal]
            selected_edges = selected_edges[1:]
            if props['bool_vertex_group']:
                n_verts = len(new_ob.data.vertices)
                base_vg = [get_weight(vg,n_verts) for vg in new_ob.vertex_groups]
            while True:
                new_vert = None
                face = None
                for e1 in selected_edges:
                    if e1.verts[0] in e0.verts: new_vert = e1.verts[1]
                    elif e1.verts[1] in e0.verts: new_vert = e1.verts[0]
                    if new_vert != None:
                        if len(loop)==0:
                            loop = [v for v in e1.verts if v != new_vert]
                        loop.append(new_vert)
                        e0 = e1
                        face = e0.link_faces[0]
                        boundary_mat.append(face.material_index + props['frame_boundary_mat'])
                        face_center.append(face.calc_center_median())
                        loop_normals.append(face.normal)
                        selected_edges.remove(e0)
                        break
                if new_vert == None:
                    try:
                        loops.append(loop)
                        loop = []
                        e0 = selected_edges[0]
                        selected_edges = selected_edges[1:]
                        boundaries_mat.append(boundary_mat)
                        neigh_face_center.append(face_center)
                        face_normals.append(loop_normals)
                        face = e0.link_faces[0]
                        boundary_mat = [face.material_index + props['frame_boundary_mat']]
                        face_center = [face.calc_center_median()]
                        loop_normals = [face.normal]
                    except: break
            boundaries_mat.append(boundary_mat)
            neigh_face_center.append(face_center)
            face_normals.append(loop_normals)
    # compute boundary frames
    new_faces = []
    vert_ids = []

    # append regular faces
    for f in original_faces:#bm.faces:
        loop = list(f.verts)
        loops.append(loop)
        boundaries_mat.append([f.material_index for v in loop])
        face_normals.append([f.normal for v in loop])

    # calc areas for relative frame mode
    if props['frame_mode'] == 'RELATIVE':
        verts_area = []
        for v in bm.verts:
            linked_faces = v.link_faces
            if len(linked_faces) > 0:
                area = sum([sqrt(f.calc_area())/len(f.verts) for f in v.link_faces])*2
                area /= len(linked_faces)
            else: area = 0
            verts_area.append(area)

    for loop_index, loop in enumerate(loops):
        is_boundary = loop_index < len(neigh_face_center)
        materials = boundaries_mat[loop_index]
        new_loop = []
        loop_ext = [loop[-1]] + loop + [loop[0]]

        # calc tangents
        tangents = []
        for i in range(len(loop)):
            # vertices
            vert0 = loop_ext[i]
            vert = loop_ext[i+1]
            vert1 = loop_ext[i+2]
            # edge vectors
            vec0 = (vert0.co - vert.co).normalized()
            vec1 = (vert.co - vert1.co).normalized()
            # tangent
            _vec1 = -vec1
            _vec0 = -vec0
            ang = (pi - vec0.angle(vec1))/2
            normal = face_normals[loop_index][i]
            tan0 = normal.cross(vec0)
            tan1 = normal.cross(vec1)
            tangent = (tan0 + tan1).normalized()/sin(ang)*props['frame_thickness']
            tangents.append(tangent)

        # calc correct direction for boundaries
        mult = -1
        if is_boundary:
            dir_val = 0
            for i in range(len(loop)):
                surf_point = neigh_face_center[loop_index][i]
                tangent = tangents[i]
                vert = loop_ext[i+1]
                dir_val += tangent.dot(vert.co - surf_point)
            if dir_val > 0: mult = 1

        # add vertices
        for i in range(len(loop)):
            vert = loop_ext[i+1]
            if props['frame_mode'] == 'RELATIVE': area = verts_area[vert.index]
            else: area = 1
            new_co = vert.co + tangents[i] * mult * area
            # add vertex
            new_vert = bm.verts.new(new_co)
            new_loop.append(new_vert)
            vert_ids.append(vert.index)
        new_loop.append(new_loop[0])

        # add faces
        materials += [materials[0]]
        for i in range(len(loop)):
             v0 = loop_ext[i+1]
             v1 = loop_ext[i+2]
             v2 = new_loop[i+1]
             v3 = new_loop[i]
             face_verts = [v1,v0,v3,v2]
             if mult == -1: face_verts = [v0,v1,v2,v3]
             new_face = bm.faces.new(face_verts)
             new_face.material_index = materials[i+1]
             new_face.select = True
             new_faces.append(new_face)
        # fill frame
        if props['fill_frame'] and not is_boundary:
            n_verts = len(new_loop)-1
            loop_center = Vector((0,0,0))
            for v in new_loop[1:]: loop_center += v.co
            loop_center /= n_verts
            center = bm.verts.new(loop_center)
            for i in range(n_verts):
                v0 = new_loop[i+1]
                v1 = new_loop[i]
                face_verts = [v1,v0,center]
                new_face = bm.faces.new(face_verts)
                new_face.material_index = materials[i] + props['fill_frame_mat']
                new_face.select = True
                new_faces.append(new_face)
    #bpy.ops.object.mode_set(mode='OBJECT')
    #for f in bm.faces: f.select_set(f not in new_faces)
    for f in original_faces: bm.faces.remove(f)
    bm.to_mesh(new_ob.data)
    # propagate vertex groups
    if props['bool_vertex_group']:
        base_vg = []
        for vg in new_ob.vertex_groups:
            vertex_group = []
            for v in bm.verts:
                try:
                    vertex_group.append(vg.weight(v.index))
                except:
                    vertex_group.append(0)
            base_vg.append(vertex_group)
        new_vert_ids = range(len(bm.verts)-len(vert_ids),len(bm.verts))
        for vg_id, vg in enumerate(new_ob.vertex_groups):
            for ii, jj in zip(vert_ids, new_vert_ids):
                vg.add([jj], base_vg[vg_id][ii], 'REPLACE')
    new_ob.data.update()
    bm.free()
    return new_ob

def reduce_to_quads(ob, use_modifiers):
    '''
    Convert an input object to a mesh with polygons that have maximum 4 vertices
    '''
    new_ob = convert_object_to_mesh(ob, use_modifiers, True)
    me = new_ob.data

    # Check if there are polygons with more than 4 sides
    np_sides = get_attribute_numpy(me.polygons, 'loop_total')
    mask = np_sides > 4
    if not np.any(mask):
        return new_ob

    # create bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    np_faces = np.array(bm.faces)
    np_faces = np_faces[mask]

    new_faces = []
    for f in np_faces:
        verts = list(f.verts)
        while True:
            n_verts = len(verts)
            if n_verts < 3: break
            elif n_verts == 3:
                face_verts = [verts[-2], verts.pop(-1), verts.pop(0)]
            else:
                face_verts = [verts[-2], verts.pop(-1), verts.pop(0), verts[0]]
            new_face = bm.faces.new(face_verts)
            new_face.material_index = f.material_index
            new_face.select = f.select
            new_faces.append(new_face)

    for f in np_faces: bm.faces.remove(f)
    bm.to_mesh(me)
    me.update()
    bm.free()
    return new_ob

def convert_to_fan(ob, use_modifiers):
    new_ob = convert_object_to_mesh(ob, use_modifiers, True)
    bm = bmesh.new()
    bm.from_mesh(new_ob.data)
    bmesh.ops.poke(bm, faces=bm.faces)#, quad_method, ngon_method)
    bm.to_mesh(new_ob.data)
    new_ob.data.update()
    return new_ob

def convert_to_triangles(ob, use_modifiers):
    new_ob = convert_object_to_mesh(ob, use_modifiers, True)
    bm = bmesh.new()
    bm.from_mesh(new_ob.data)
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='FIXED', ngon_method='BEAUTY')
    bm.to_mesh(new_ob.data)
    new_ob.data.update()
    return new_ob

def merge_components(ob, props, use_bmesh):

    if not use_bmesh:
        skip = True
        ob.active_shape_key_index = 1
        if ob.data.shape_keys != None:
            for sk in ob.data.shape_keys.key_blocks:
                if skip:
                    skip = False
                    continue
                sk.mute = True
        ob.data.update()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.object.mode_set(mode='OBJECT')
        if ob.data.shape_keys != None:
            for sk in ob.data.shape_keys.key_blocks:
                sk.mute = False
        ob.data.update()

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(
            use_extend=False, use_expand=False, type='VERT')
        bpy.ops.mesh.select_non_manifold(
            extend=False, use_wire=True, use_boundary=True,
            use_multi_face=False, use_non_contiguous=False, use_verts=False)

        bpy.ops.mesh.remove_doubles(
            threshold=props.merge_thres, use_unselected=False)

        if props.bool_dissolve_seams:
            bpy.ops.mesh.select_mode(type='EDGE')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            for e in new_ob.data.edges:
                e.select = e.use_seam
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.dissolve_edges()
        bpy.ops.object.mode_set(mode='OBJECT')

        if props.close_mesh != 'NONE':
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_mode(
                use_extend=False, use_expand=False, type='EDGE')
            bpy.ops.mesh.select_non_manifold(
                extend=False, use_wire=False, use_boundary=True,
                use_multi_face=False, use_non_contiguous=False, use_verts=False)
            if props.close_mesh == 'CAP':
                if props.open_edges_crease != 0:
                    bpy.ops.transform.edge_crease(value=props.open_edges_crease)
                bpy.ops.mesh.edge_face_add()
                bpy.ops.object.mode_set(mode='OBJECT')
                for f in ob.data.polygons:
                    if f.select: f.material_index += props.cap_material_offset
            elif props.close_mesh == 'BRIDGE':
                try:
                    if props.bridge_edges_crease != 0:
                        bpy.ops.transform.edge_crease(value=props.bridge_edges_crease)
                    bpy.ops.mesh.bridge_edge_loops(
                        type='PAIRS',
                        number_cuts=props.bridge_cuts,
                        interpolation='SURFACE',
                        smoothness=props.bridge_smoothness)
                    bpy.ops.object.mode_set(mode='OBJECT')
                    for f in ob.data.polygons:
                        if f.select: f.material_index += props.bridge_material_offset
                except: pass
            elif props.close_mesh == 'BRIDGE_CAP':
                # BRIDGE
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                    vg = ob.vertex_groups[props.vertex_group_bridge]
                    weight = get_weight_numpy(vg, len(ob.data.vertices))
                    for e in ob.data.edges:
                        if weight[e.vertices[0]]*weight[e.vertices[1]] < 1:
                            e.select = False
                    bpy.ops.object.mode_set(mode='EDIT')
                    if props.bridge_edges_crease != 0:
                        bpy.ops.transform.edge_crease(value=props.bridge_edges_crease)
                    bpy.ops.mesh.bridge_edge_loops(
                        type='PAIRS',
                        number_cuts=props.bridge_cuts,
                        interpolation='SURFACE',
                        smoothness=props.bridge_smoothness)
                    for f in ob.data.polygons:
                        if f.select: f.material_index += props.bridge_material_offset
                    bpy.ops.mesh.select_all(action='DESELECT')
                    bpy.ops.mesh.select_non_manifold(
                        extend=False, use_wire=False, use_boundary=True,
                        use_multi_face=False, use_non_contiguous=False, use_verts=False)
                    bpy.ops.object.mode_set(mode='OBJECT')
                except: pass
                # CAP
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                    vg = ob.vertex_groups[props.vertex_group_cap]
                    weight = get_weight_numpy(vg, len(ob.data.vertices))
                    for e in ob.data.edges:
                        if weight[e.vertices[0]]*weight[e.vertices[1]] < 1:
                            e.select = False
                    bpy.ops.object.mode_set(mode='EDIT')
                    if props.open_edges_crease != 0:
                        bpy.ops.transform.edge_crease(value=props.open_edges_crease)
                    bpy.ops.mesh.edge_face_add()
                    for f in ob.data.polygons:
                        if f.select: f.material_index += props.cap_material_offset
                    bpy.ops.object.mode_set(mode='OBJECT')
                except: pass
    else:
        bm = bmesh.new()
        bm.from_mesh(ob.data.copy())
        if props.merge_open_edges_only:
            boundary_verts = [v for v in bm.verts if v.is_boundary or v.is_wire]
        else:
            boundary_verts = bm.verts
        bmesh.ops.remove_doubles(bm, verts=boundary_verts, dist=props.merge_thres)

        if props.bool_dissolve_seams:
            seam_edges = [e for e in bm.edges if e.seam]
            bmesh.ops.dissolve_edges(bm, edges=seam_edges, use_verts=True, use_face_split=False)
        if props.close_mesh != 'NONE':
            bm.edges.ensure_lookup_table()
            # set crease
            crease_layer = bm.edges.layers.crease.verify()
            boundary_edges = [e for e in bm.edges if e.is_boundary]
            if props.close_mesh == 'BRIDGE':
                try:
                    for e in boundary_edges:
                        e[crease_layer] = props.bridge_edges_crease
                    closed = bmesh.ops.bridge_loops(bm, edges=boundary_edges, use_pairs=True)
                    for f in closed['faces']: f.material_index += props.bridge_material_offset
                except:
                    return 'bridge_error'
            elif props.close_mesh == 'CAP':
                for e in boundary_edges:
                    e[crease_layer] = props.open_edges_crease
                closed = bmesh.ops.holes_fill(bm, edges=boundary_edges)
                for f in closed['faces']: f.material_index += props.cap_material_offset
            elif props.close_mesh == 'BRIDGE_CAP':
                # BRIDGE
                dvert_lay = bm.verts.layers.deform.active
                try:
                    dvert_lay = bm.verts.layers.deform.active
                    group_index = ob.vertex_groups[props.vertex_group_bridge].index
                    bw = bmesh_get_weight_numpy(group_index, dvert_lay, bm.verts)
                    if props.invert_vertex_group_bridge: bw = 1-bw
                    bridge_edges = [e for e in boundary_edges if bw[e.verts[0].index]*bw[e.verts[1].index] >= 1]
                    for e in bridge_edges:
                        e[crease_layer] = props.bridge_edges_crease
                    closed = bmesh.ops.bridge_loops(bm, edges=bridge_edges, use_pairs=True)
                    for f in closed['faces']: f.material_index += props.bridge_material_offset
                    boundary_edges = [e for e in bm.edges if e.is_boundary]
                except: pass
                # CAP
                try:
                    dvert_lay = bm.verts.layers.deform.active
                    group_index = ob.vertex_groups[props.vertex_group_cap].index
                    bw = bmesh_get_weight_numpy(group_index, dvert_lay, bm.verts)
                    if props.invert_vertex_group_cap: bw = 1-bw
                    cap_edges = [e for e in boundary_edges if bw[e.verts[0].index]*bw[e.verts[1].index] >= 1]
                    for e in cap_edges:
                        e[crease_layer] = props.open_edges_crease
                    closed = bmesh.ops.holes_fill(bm, edges=cap_edges)
                    for f in closed['faces']: f.material_index += props.cap_material_offset
                except: pass
        bm.to_mesh(ob.data)

class tissue_render_animation(Operator):
    bl_idname = "render.tissue_render_animation"
    bl_label = "Tissue Render Animation"
    bl_description = "Turnaround for issues related to animatable tessellation"
    bl_options = {'REGISTER', 'UNDO'}

    start = True
    path = ""
    timer = None

    def invoke(self, context, event):
        self.start = True
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="All frames will be rendered in the background.")
        col.label(text="Press ESC to abort.")

    def modal(self, context, event):
        '''
        # check render format
        format = context.scene.render.image_settings.file_format
        if format in ('FFMPEG', 'AVI_RAW', 'AVI_JPEG'):
            message = "Please use an image format as render output"
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        '''
        remove_tessellate_handler()
        scene = context.scene
        if event.type == 'ESC' or scene.frame_current >= scene.frame_end:
            scene.render.filepath = self.path
            # set again the handler
            blender_handlers = bpy.app.handlers.frame_change_post
            blender_handlers.append(anim_tessellate)
            blender_handlers.append(reaction_diffusion_scene)
            context.window_manager.event_timer_remove(self.timer)
            if event.type == 'ESC':
                print("Tissue: Render Animation aborted.")
                return {'CANCELLED'}
            else:
                print("Tissue: Render Animation completed!")
                return {'FINISHED'}
        else:
            self.execute(context)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # check output format
        format = context.scene.render.image_settings.file_format
        if format in ('FFMPEG', 'AVI_RAW', 'AVI_JPEG'):
            message = "Please use an image format as render output"
            self.report({'ERROR'}, message)
            return {'CANCELLED'}

        scene = context.scene
        if self.start:
            remove_tessellate_handler()
            reaction_diffusion_remove_handler(self, context)
            scene = context.scene
            scene.frame_current = scene.frame_start
            self.path = scene.render.filepath
            context.window_manager.modal_handler_add(self)
            self.timer = context.window_manager.event_timer_add(0.1, window = context.window)
            self.start = False
        else:
            scene.frame_current += scene.frame_step
        anim_tessellate(scene)
        reaction_diffusion_scene(scene)
        scene.render.filepath = "{}{:04d}".format(self.path,scene.frame_current)
        bpy.ops.render.render(write_still=True)
        return {'RUNNING_MODAL'}
