import hashlib
from pathlib import Path
import tempfile
import unittest
from romancer import workbench_projects as p


def iso_fixture():
    data=bytearray(24*2048);data[:16]=b'SEGADISCSYSTEM'.ljust(16,b' ')
    def both(value,width=4):return value.to_bytes(width,'little')+value.to_bytes(width,'big')
    def record(name,extent,length,flags=0):
        size=33+len(name)+(len(name)%2==0);r=bytearray(size);r[0]=size;r[2:10]=both(extent);r[10:18]=both(length);r[25]=flags;r[28:32]=both(1,2);r[32]=len(name);r[33:33+len(name)]=name;return r
    v=16*2048;data[v:v+7]=b'\x01CD001\x01';data[v+80:v+88]=both(24);data[v+128:v+132]=both(2048,2);data[v+156:v+190]=record(b'\x00',20,2048,2)
    v=17*2048;data[v:v+7]=b'\xffCD001\x01'
    directory=record(b'\x00',20,2048,2)+record(b'\x01',20,2048,2)+record(b'HELLO.BIN;1',21,4)
    data[20*2048:20*2048+len(directory)]=directory;data[21*2048:21*2048+4]=b'ABCD'
    return bytes(data)


class ContainerTests(unittest.TestCase):
    def test_api_container_and_integrity_routes_are_connected(self):
        from romancer.workbench_api import WorkbenchAPI
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);image=root/'own.iso';image.write_bytes(iso_fixture());api=WorkbenchAPI(root/'workspace')
            try:
                project=api.dispatch('project.create',{'name':'Containers'});args={'project_id':project['project_id']}
                row=api.dispatch('source.import',{**args,'path':str(image),'system':None})
                self.assertFalse(row['ok']);self.assertEqual(api.dispatch('project.open',args)['sources'],[])
                self.assertFalse(api.dispatch('containers.import_disc',{**args,'cue':str(image)})['ok'])
            finally:api.close()

    def test_wrong_identity_cancel_and_outside_extent_publish_nothing(self):
        from romancer.container_workspace import inventory_container,build_container
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'disc.iso';source.write_bytes(iso_fixture());sha=hashlib.sha256(source.read_bytes()).hexdigest();out=root/'out.iso'
            with self.assertRaises(ValueError):inventory_container(source,'0'*64)
            with self.assertRaises(KeyboardInterrupt):inventory_container(source,sha,cancelled=lambda:True)
            with self.assertRaises(ValueError):build_container(source,sha,out,0,b'XXXX',layout='mode1-2048',expected_before=b'SEGA')
            self.assertFalse(out.exists())
    def test_cooked_disc_inventory_extract_and_scoped_build(self):
        from romancer.container_workspace import inventory_container,extract_extent,build_container
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'disc.iso';source.write_bytes(iso_fixture());sha=hashlib.sha256(source.read_bytes()).hexdigest()
            inv=inventory_container(source,sha);file=next(f for f in inv['files'] if f['name']=='HELLO.BIN;1')
            self.assertEqual((file['offset'],file['length']),(21*2048,4))
            self.assertEqual(extract_extent(source,sha,file['offset'],file['length'],layout='mode1-2048'),b'ABCD')
            output=root/'build.iso';build_container(source,sha,output,file['offset'],b'AXCD',layout='mode1-2048',expected_before=b'ABCD')
            expected=bytearray(iso_fixture());expected[21*2048+1]=ord('X');self.assertEqual(output.read_bytes(),expected)
            self.assertEqual(source.read_bytes(),iso_fixture())

    def test_cue_set_preserves_audio_and_refuses_missing_or_escaping_track(self):
        from romancer.container_workspace import import_disc_set,build_disc_set
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'data.bin').write_bytes(iso_fixture());audio=b'\x12\x34'*(2352//2);(root/'music.bin').write_bytes(audio)
            cue=root/'test.cue';cue.write_text('FILE "data.bin" BINARY\n TRACK 01 MODE1/2048\n INDEX 01 00:00:00\nFILE "music.bin" BINARY\n TRACK 02 AUDIO\n INDEX 01 00:00:00\n')
            project=Path(p.create_project(root/'projects','Disc')['path']);result=import_disc_set(project,cue)
            built=build_disc_set(project,result['container_id'],1,21*2048,b'AXCD',expected_before=b'ABCD')
            folder=Path(built['path']);self.assertEqual((folder/'music.bin').read_bytes(),audio)
            self.assertEqual((folder/'test.cue').read_bytes(),cue.read_bytes())
            self.assertEqual((folder/'data.bin').read_bytes()[21*2048:21*2048+4],b'AXCD')
            cue.write_text('FILE "../escape.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n')
            with self.assertRaises(ValueError):import_disc_set(project,cue)
            cue.write_text('FILE "missing.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n')
            with self.assertRaises((ValueError,OSError)):import_disc_set(project,cue)

    def test_raw_mode1_edit_repairs_integrity_and_preserves_neighbors(self):
        from romancer.container_workspace import inventory_container,build_container
        from romancer.cdrom import repair_mode1,validate_mode1,SYNC
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cooked=iso_fixture();sectors=[]
            for offset in range(0,len(cooked),2048):
                sector=bytearray(2352);sector[:12]=SYNC;sector[15]=1;sector[16:2064]=cooked[offset:offset+2048];sectors.append(repair_mode1(bytes(sector)))
            source=root/'raw.bin';source.write_bytes(b''.join(sectors));sha=hashlib.sha256(source.read_bytes()).hexdigest()
            inv=inventory_container(source,sha);self.assertEqual(inv['files'][0]['length'],4)
            out=root/'out.bin';build_container(source,sha,out,21*2048,b'AXCD',layout='mode1-2352',expected_before=b'ABCD')
            actual=out.read_bytes();validate_mode1(actual[21*2352:22*2352]);self.assertEqual(actual[:21*2352],b''.join(sectors[:21]));self.assertEqual(actual[22*2352:],b''.join(sectors[22:]))

    def test_checksum_edits_have_independent_literal_oracles(self):
        from romancer.system_integrity import integrity_edits
        from romancer.system_demo import make_system_fixtures
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for system in ('snes','genesis'):
                data=make_system_fixtures()[system];source=root/system;source.write_bytes(data);sha=hashlib.sha256(data).hexdigest()
                offset={'snes':0x100,'genesis':0x200}[system]
                edits=integrity_edits(source,sha,system,[{'offset':offset,'before':data[offset:offset+1].hex(),'after':'41'}])
                target=bytearray(data)
                for e in edits:target[e['offset']:e['offset']+len(bytes.fromhex(e['after']))]=bytes.fromhex(e['after'])
                if system=='snes':
                    checksum=int.from_bytes(target[0x7fde:0x7fe0],'little');self.assertEqual(checksum,sum(target)&65535);self.assertEqual(checksum^int.from_bytes(target[0x7fdc:0x7fde],'little'),65535)
                elif system=='genesis':self.assertEqual(int.from_bytes(target[0x18e:0x190],'big'),sum(int.from_bytes(target[i:i+2],'big') for i in range(0x200,len(target),2))&65535)
                else:self.assertEqual((sum(target[0xa0:0xbe])+0x19)&255,0)
