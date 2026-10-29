"""Shared immutable identities and bounded resource dependency contracts."""
from dataclasses import dataclass,asdict
import hashlib,re
from pathlib import Path
from ..asset_schema import label,number


def checked_sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):
        raise ValueError('adapter needs an exact SHA-256 identity')
    return value


@dataclass(frozen=True)
class Resource:
    id:str
    kind:str
    source_sha256:str
    offset:int
    length:int
    dependencies:tuple

    def document(self,size):
        checked_sha(self.id);checked_sha(self.source_sha256);label(self.kind,64)
        number(self.offset,0,size-1);number(self.length,1,size-self.offset)
        if type(self.dependencies) is not tuple or len(set(self.dependencies))!=len(self.dependencies):
            raise ValueError('invalid adapter dependencies')
        for identity in self.dependencies:checked_sha(identity)
        return {**asdict(self),'dependencies':list(self.dependencies),
                'operations':['inspect','noop','edit','undo_redo','reopen','native','patch']}


def implementation_sha(paths):
    """Bind the declared implementation files; the app commit binds the full app."""
    root=Path(__file__).resolve().parents[2];digest=hashlib.sha256()
    for name in sorted(paths):
        data=(root/name).read_bytes()
        digest.update(name.encode('utf-8')+b'\0'+len(data).to_bytes(8,'big')+data)
    return digest.hexdigest()


def validate_resources(resources,size,source_sha256):
    checked_sha(source_sha256)
    if not 1<=len(resources)<=256:raise ValueError('adapter resource inventory exceeds its budget')
    rows=[resource.document(size) for resource in resources];by_id={row['id']:row for row in rows}
    if len(by_id)!=len(rows):raise ValueError('duplicate adapter resource identity')
    end=0
    for row in sorted(rows,key=lambda r:r['offset']):
        if row['source_sha256']!=source_sha256:raise ValueError('adapter resource belongs to another source')
        if row['offset']<end:raise ValueError('adapter resource ranges overlap')
        end=row['offset']+row['length']
        if any(d not in by_id for d in row['dependencies']):raise ValueError('adapter dependency is missing')
    completed=set();active=set()
    def visit(identity):
        if identity in active:raise ValueError('adapter dependencies contain a cycle')
        if identity in completed:return
        active.add(identity)
        for dependency in by_id[identity]['dependencies']:visit(dependency)
        active.remove(identity);completed.add(identity)
    for identity in by_id:visit(identity)
    return rows


def resource_impact(resources,edits):
    changed={r['id'] for r in resources if any(e['offset']<r['offset']+r['length'] and e['offset']+len(bytes.fromhex(e['after']))>r['offset'] for e in edits)}
    while True:
        expanded=changed|{r['id'] for r in resources if any(d in changed for d in r['dependencies'])}
        if expanded==changed:return sorted(changed)
        changed=expanded
