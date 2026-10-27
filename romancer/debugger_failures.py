"""Observed native exit categories; do not infer a cause from every failure."""
class NativeCaptureError(ValueError):
    def __init__(self,code,message,remedy,exit_code=None):
        self.code=code;self.remedy=remedy;self.exit_code=exit_code
        super().__init__(message+' '+remedy)

def process_failure(backend,exit_code,output=''):
    code=exit_code&0xffffffff
    if code==0xc000001d:
        category='ILLEGAL_INSTRUCTION';message=backend+' reported an illegal instruction.';remedy='Check its documented CPU requirements and reinstall the reviewed package.'
    elif code in (0xc0000135,0xc0000142):
        category='MISSING_DEPENDENCY';message=backend+' reported a missing dependency or failed library initialization.';remedy='Repair the full installation, then run diagnostics.'
    elif code in (0xc0000005,0xc0000374,0xc0000409):
        category='NATIVE_CRASH';message=backend+' crashed during capture.';remedy='Keep your edit, try a shorter capture, and export a support report if it repeats.'
    elif '[lua error]' in output.lower() or 'error loading script' in output.lower():
        category='CAPTURE_SCRIPT_ERROR';message=backend+' reported a capture-script error.';remedy='Check the selected capture settings and reinstall the matching application and observer versions.'
    else:
        category='NATIVE_EXIT';message=backend+' ended unsuccessfully (exit '+str(exit_code)+').';remedy='Run diagnostics and include this exit code in the support report; the cause is not established.'
    return NativeCaptureError(category,message,remedy,exit_code)

def capture_output(job):
    chunks=[]
    for name in ('stdout.txt','stderr.txt'):
        path=job/name
        if path.is_file():
            with path.open('rb') as f:f.seek(max(0,path.stat().st_size-8192));chunks.append(f.read(8192).decode('utf-8','replace'))
    return '\n'.join(chunks)
