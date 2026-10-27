# -*- coding: utf-8 -*-
"""Optional integration check against a dedicated Blockbench debug instance.

pip install websocket-client
Blockbench.exe --userData NEW_TEST_PROFILE --remote-debugging-port=19326
python validate_in_blockbench.py OUTPUT.bbmodel --port 19326
Uses localhost CDP only as a test transport; converter itself has no service.
"""
import argparse
import json
from pathlib import Path
import sys
import urllib.request

import websocket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--port", type=int, default=19326)
    args = parser.parse_args()
    project = json.loads(args.model.read_text(encoding="utf-8"))
    checkpoints = json.loads(args.model.with_name("validation_checkpoints.json").read_text(encoding="utf-8"))
    exports = {}
    for key, suffix in (("geometry", ".geo.json"), ("animations", ".animation.json")):
        path = args.model.with_name(project["name"] + suffix)
        if path.is_file():
            exports[key] = json.loads(path.read_text(encoding="utf-8"))
    tabs = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % args.port, timeout=10))
    tab = next(t for t in tabs if t["type"] == "page")
    socket = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=240)
    script = """
    async function(model, check, exports) {
        // This must be a dedicated test profile: close prior test documents.
        for (const project of [...ModelProject.all]) {project.saved = true; await project.close();}
        const errors = [];
        const listener = event => errors.push(event.message);
        window.addEventListener('error', listener);
        const loadStart = performance.now();
        Codecs.project.load(model, {name: model.name + '.bbmodel', path: ''});
        const codecLoadMs = performance.now() - loadStart;
        await new Promise(resolve => setTimeout(resolve, 800));
        Canvas.updateAll();
        let maxError = 0, samples = 0;
        const matrices = [];
        for (const sample of check.checkpoints) {
            const animation = Animation.all.find(a => a.name === sample.clip);
            if (!animation) throw new Error('Missing animation: ' + sample.clip);
            animation.select();
            Timeline.setTime(sample.time);
            Animator.preview();
            Project.model_3d.updateMatrixWorld(true);
            for (const expected of sample.groups) {
                const group = Group.all.find(g => g.uuid === check.groups[expected.group]);
                const actual = group.mesh.matrixWorld.elements;
                const delta = Math.max(...actual.map((v,i) => Math.abs(v-expected.matrix[i])));
                maxError = Math.max(maxError, delta); samples++;
                if (delta > 0.002) matrices.push({clip:sample.clip,time:sample.time,bone:group.name,error:delta,actual:[...actual],expected:expected.matrix});
            }
        }
        if (Animation.all.length) {Timeline.setTime(0); Animator.preview();}
        const result = {blockbench:Blockbench.version, format:Format.id,
            elements:Outliner.elements.length, groups:Group.all.length,
            triangles:Mesh.all.reduce((n,m)=>n+Object.keys(m.faces).length,0),
            cubes:Cube.all.length, textures:Texture.all.length,
            texture_errors:Texture.all.filter(t=>t.error).map(t=>({name:t.name,error:t.error})),
            animations:Animation.all.map(a=>({name:a.name,length:a.length,loop:a.loop,animators:Object.keys(a.animators).length})),
            animation_matrix_samples:samples,max_animation_matrix_error:maxError,
            matrix_failures:matrices, runtime_errors:errors};
        // Exercise the native save codec too, without replacing the delivered file.
        const saved = Codecs.project.compile({raw:true,bitmaps:false});
        result.roundtrip_elements=saved.elements.length;
        result.roundtrip_groups=saved.groups.length;
        result.roundtrip_animations=(saved.animations||[]).length;
        result.codec_load_ms = codecLoadMs;
        result.cube_surface_failures = [];
        for (const element of model.elements.filter(e=>e.type==='cube' && !e.box_uv)) {
            const cube=Cube.all.find(c=>c.uuid===element.uuid);
            const again=saved.elements.find(c=>c.uuid===element.uuid);
            if (cube.box_uv || again.box_uv) result.cube_surface_failures.push(element.name+':box_uv');
            for(const [face, source] of Object.entries(element.faces)) {
                const actual=cube.faces[face];
                if(source.texture===null) {
                    if(actual.texture!==null) result.cube_surface_failures.push(element.name+':hidden:'+face);
                } else if(actual.uv.some((v,i)=>Math.abs(v-source.uv[i])>0.00001)
                       || again.faces[face].uv.some((v,i)=>Math.abs(v-source.uv[i])>0.00001)) {
                    result.cube_surface_failures.push(element.name+':uv:'+face);
                }
            }
        }
        if (Format.id==='bedrock') {
            const geo=Codecs.bedrock.compile({raw:true});
            result.official_geo=typeof geo==='string'?JSON.parse(geo):geo;
        }
        result.bedrock_reimport = null;
        if(exports.geometry && exports.animations) {
            Project.saved=true;
            await Project.close();
            Codecs.bedrock.load(exports.geometry, {path:'', name:model.name+'.geo.json'});
            AnimationCodec.codecs.bedrock.loadFile({json:exports.animations, path:''});
            let max=0, samples=0;
            const failures=[];
            for(const sample of check.checkpoints) {
                const animation=Animation.all.find(a=>a.name==='animation.'+sample.clip);
                if(!animation) throw new Error('Missing exported animation: '+sample.clip);
                animation.select();Timeline.setTime(sample.time);Animator.preview();
                Project.model_3d.updateMatrixWorld(true);
                for(const expected of sample.groups) {
                    const source=model.groups.find(g=>g.uuid===check.groups[expected.group]);
                    const group=Group.all.find(g=>g.name===source.name);
                    const actual=group.mesh.matrixWorld.elements;
                    const delta=Math.max(...actual.map((v,i)=>Math.abs(v-expected.matrix[i])));
                    max=Math.max(max,delta);samples++;
                    if(delta>0.002)failures.push({clip:sample.clip,time:sample.time,bone:group.name,error:delta});
                }
            }
            result.bedrock_reimport={samples,max_matrix_error:max,failures,
                cubes:Cube.all.length,animations:Animation.all.length};
            Project.saved=true;
            await Project.close();
            Codecs.project.load(model,{path:'',name:model.name+'.bbmodel'});
            await new Promise(resolve=>setTimeout(resolve,300));
        }
        Project.saved=true;
        window.removeEventListener('error',listener);
        return result;
    }"""
    socket.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": "globalThis", "returnByValue": False}}))
    while True:
        response = json.loads(socket.recv())
        if response.get("id") == 1:
            object_id = response["result"]["result"]["objectId"]
            break
    socket.send(json.dumps({"id": 2, "method": "Runtime.callFunctionOn", "params": {
        "objectId": object_id, "functionDeclaration": script,
        "arguments": [{"value": project}, {"value": checkpoints}, {"value": exports}], "awaitPromise": True, "returnByValue": True}}))
    while True:
        response = json.loads(socket.recv())
        if response.get("id") == 2:
            break
    socket.close()
    if "exceptionDetails" in response.get("result", {}):
        print(json.dumps(response, indent=2), file=sys.stderr)
        return 1
    result = response["result"]["result"]["value"]
    official = result.pop("official_geo", None)
    geometry_path = args.model.with_name(project["name"] + ".geo.json")
    if official and geometry_path.is_file():
        expected = json.loads(geometry_path.read_text(encoding="utf-8"))
        official_bones = official["minecraft:geometry"][0]["bones"]
        local_bones = expected["minecraft:geometry"][0]["bones"]
        by_name = {b["name"]: b for b in official_bones}
        checked = 0
        for bone in local_bones:
            native = by_name.get(bone["name"])
            if native is None or len(native.get("cubes", [])) != len(bone["cubes"]):
                result["cube_surface_failures"].append(bone["name"] + ":geo_cube_count")
                continue
            for exported, actual in zip(bone["cubes"], native.get("cubes", [])):
                if exported["uv"] != actual["uv"]:
                    result["cube_surface_failures"].append(bone["name"] + ":official_geo_uv")
                checked += 1
        result["official_geo_uv_cubes_checked"] = checked
    if result.get("bedrock_reimport"):
        reimport = result["bedrock_reimport"]
        if reimport["failures"] or reimport["cubes"] != len(project["elements"]) or reimport["animations"] != len(project["animations"]):
            result["cube_surface_failures"].append("bedrock_geometry_animation_reimport")
    result["passed"] = (not result["texture_errors"] and not result["runtime_errors"] and result["max_animation_matrix_error"] < 0.002
                        and not result["cube_surface_failures"]
                        and result["elements"] == len(project["elements"]) and result["groups"] == len(project["groups"])
                        and result["roundtrip_elements"] == len(project["elements"])
                        and result["roundtrip_animations"] == len(project["animations"]))
    args.model.with_name("blockbench_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:6000])
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
