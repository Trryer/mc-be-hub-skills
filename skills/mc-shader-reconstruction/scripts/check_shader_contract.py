"""Check numeric GLSL constants and PNG dimensions against bake metadata.

The contract maps shader constant names to dotted JSON paths. This is for
custom model adapters; it does not emulate the engine, preprocess macros,
evaluate arbitrary GLSL expressions, or establish visual correctness.
Only the Python standard library is required. Exit 0: pass; 1: mismatch/error.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct


NUMBER = re.compile(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?[fF]?\Z')


def metadata_value(data, path):
    if isinstance(path, list):
        return [metadata_value(data, item) for item in path]
    if not isinstance(path, str) or not path:
        raise ValueError('Metadata selectors must be nonempty dotted paths')
    value = data
    for key in path.split('.'):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def constant_reader(source):
    source = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*', '', source)
    declarations = re.findall(
        r'\bconst\s+(?:(?:lowp|mediump|highp)\s+)?'
        r'(float|int|vec[234])\s+([A-Za-z_]\w*)\s*=\s*([^;]+);', source)
    constants = {}
    for type_name, name, expression in declarations:
        if name in constants:
            raise ValueError('Ambiguous constant in source: '+name+'; select the active macro branch first')
        constants[name] = (type_name, expression.strip())

    def resolve_expression(expression, stack):
        if NUMBER.fullmatch(expression):
            return float(expression.rstrip('fF'))
        if re.fullmatch(r'[A-Za-z_]\w*', expression):
            return resolve(expression, stack)
        constructor = re.fullmatch(r'vec([234])\s*\(([^()]*)\)', expression)
        if constructor:
            size = int(constructor.group(1))
            parts = [resolve_expression(item.strip(), stack) for item in constructor.group(2).split(',')]
            if len(parts)==1 and isinstance(parts[0], (int,float)):
                parts *= size
            if len(parts)!=size or any(not isinstance(item,(int,float)) for item in parts):
                raise ValueError('Unsupported vector initializer: '+expression)
            return parts
        raise ValueError('Unsupported expression: '+expression+'; resolve it using the actual GLSL compiler')

    def resolve(name, stack=()):
        if name in stack:
            raise ValueError('Constant alias cycle: '+' -> '.join(stack+(name,)))
        if name not in constants:
            raise ValueError('Constant not found: '+name)
        type_name, expression = constants[name]
        value = resolve_expression(expression, stack+(name,))
        if type_name.startswith('vec'):
            if not isinstance(value,list) or len(value)!=int(type_name[-1]):
                raise ValueError('Vector type mismatch: '+name)
        elif isinstance(value,list):
            raise ValueError('Scalar type mismatch: '+name)
        return value
    return resolve


def equal_numbers(actual, expected, tolerance):
    if isinstance(actual,list) or isinstance(expected,list):
        return isinstance(actual,list) and isinstance(expected,list) and len(actual)==len(expected) \
            and all(equal_numbers(a,b,tolerance) for a,b in zip(actual,expected))
    if isinstance(actual,bool) or isinstance(expected,bool):
        return False
    return isinstance(actual,(int,float)) and isinstance(expected,(int,float)) \
        and math.isfinite(actual) and math.isfinite(expected) \
        and math.isclose(actual,expected,abs_tol=tolerance,rel_tol=1e-9)


def png_dimensions(path):
    with path.open('rb') as stream:
        header = stream.read(24)
    if len(header)!=24 or header[:8]!=b'\x89PNG\r\n\x1a\n' or header[12:16]!=b'IHDR':
        raise ValueError('Not a PNG header: '+str(path))
    return list(struct.unpack('>II',header[16:24]))


def check(contract_path, shader_path, tolerance):
    contract_path = contract_path.resolve()
    contract = json.loads(contract_path.read_text(encoding='utf-8-sig'))
    metadata_path = (contract_path.parent / contract['metadata']).resolve()
    metadata_bytes = metadata_path.read_bytes()
    metadata = json.loads(metadata_bytes.decode('utf-8-sig'))
    source_bytes = shader_path.read_bytes()
    resolve = constant_reader(source_bytes.decode('utf-8-sig'))
    checks = []
    mapping = contract.get('constants',{})
    if not mapping:
        raise ValueError('Contract needs at least one constant-to-metadata mapping')
    for name, selector in mapping.items():
        row = {'constant':name,'metadata_path':selector}
        try:
            row['expected'] = metadata_value(metadata,selector)
            row['actual'] = resolve(name)
            row['pass'] = equal_numbers(row['actual'],row['expected'],tolerance)
        except (ValueError,KeyError,IndexError,TypeError) as error:
            row.update({'pass':False,'error':str(error)})
        checks.append(row)
    for texture in contract.get('textures',[]):
        path = (contract_path.parent / texture['file']).resolve()
        row = {'texture':str(path)}
        try:
            row['expected'] = metadata_value(metadata,texture['size'])
            row['actual'] = png_dimensions(path)
            row['pass'] = equal_numbers(row['actual'],row['expected'],0)
        except (OSError,ValueError,KeyError,IndexError,TypeError) as error:
            row.update({'pass':False,'error':str(error)})
        checks.append(row)
    return {'status':'PASS' if all(row['pass'] for row in checks) else 'FAIL',
            'shader':str(shader_path.resolve()),'metadata':str(metadata_path),
            'shader_sha256':hashlib.sha256(source_bytes).hexdigest(),
            'metadata_sha256':hashlib.sha256(metadata_bytes).hexdigest(),
            'absolute_tolerance':tolerance,'checks':checks,
            'scope':'Literal/alias constant values and PNG headers only; visual and engine checks remain required'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',type=Path,required=True)
    parser.add_argument('--shader',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--tolerance',type=float,default=1e-6)
    args = parser.parse_args()
    try:
        if not math.isfinite(args.tolerance) or args.tolerance<0:
            raise ValueError('Tolerance must be a finite nonnegative number')
        report = check(args.contract,args.shader,args.tolerance)
    except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
        report = {'status':'ERROR','error':str(error)}
    output = json.dumps(report,ensure_ascii=False,indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(output+'\n',encoding='utf-8')
    print(output)
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
