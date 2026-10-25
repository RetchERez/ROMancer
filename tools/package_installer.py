"""Build a per-user Windows setup EXE with a pinned NSIS compiler.

The verified payload and user projects remain separate. Silent mode never opens
the app; /NOINTEGRATION isolates automated installation tests from user shortcuts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.install_windows import verify_tree

NSIS_PIN={'file':'nsis-3.13.zip','sha256':'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8',
          'url':'https://downloads.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip'}


def literal(value):
    value=str(value)
    if any(ord(c)<32 for c in value):raise ValueError('installer paths cannot contain control characters')
    return value.replace('$','$$').replace('"','$\\"')


def installer_script(payload,output,version):
    payload=literal(Path(payload).absolute());output=literal(Path(output).absolute())
    if not __import__('re').fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('installer requires an immutable numeric build revision')
    return r'''Unicode true
RequestExecutionLevel user
SetCompressor /SOLID zlib
SetDatablockOptimize on
Name "ROMancer"
OutFile "@OUTPUT@"
InstallDir "$LOCALAPPDATA\ROMancer"
InstallDirRegKey HKCU "Software\ROMancer" "InstallDir"
BrandingText "By RetchEWretched"
VIProductVersion "@VERSION@.0"
VIAddVersionKey "ProductName" "ROMancer"
VIAddVersionKey "FileDescription" "ROMancer v1.0 Setup"
VIAddVersionKey "FileVersion" "@VERSION@"
VIAddVersionKey "LegalCopyright" "RetchEWretched and credited component authors"
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
Var NoIntegration
!define MUI_ABORTWARNING
!define MUI_LICENSEPAGE_TEXT_TOP "ROMancer code uses MIT. Included runtimes and engines retain their own licenses and source; see the installed component notices."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "@PAYLOAD@\app\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Open ROMancer"
!define MUI_FINISHPAGE_RUN_FUNCTION OpenApp
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
 ${IfNot} ${RunningX64}
  MessageBox MB_OK|MB_ICONSTOP "This release requires 64-bit Windows 10 or later." /SD IDOK
  SetErrorLevel 1
  Quit
 ${EndIf}
 ${IfNot} ${AtLeastWin10}
  MessageBox MB_OK|MB_ICONSTOP "This release requires Windows 10 or later." /SD IDOK
  SetErrorLevel 1
  Quit
 ${EndIf}
 SetRegView 64
 SetShellVarContext current
 StrCpy $NoIntegration 0
 ${GetParameters} $R0
 ClearErrors
 ${GetOptions} $R0 "/NOINTEGRATION" $R1
 ${IfNot} ${Errors}
  StrCpy $NoIntegration 1
 ${EndIf}
FunctionEnd

Section "Install"
 InitPluginsDir
 SetOutPath "$PLUGINSDIR\payload"
 File /r "@PAYLOAD@\*.*"
 ExecWait '$\"$PLUGINSDIR\payload\python\python.exe$\" -I -B $\"$PLUGINSDIR\payload\app\tools\install_windows.py$\" --payload $\"$PLUGINSDIR\payload$\" --install-root $\"$INSTDIR$\"' $0
 ${If} $0 != 0
  MessageBox MB_OK|MB_ICONSTOP "ROMancer could not verify or install this package. Your projects were preserved." /SD IDOK
  SetErrorLevel 1
  Quit
 ${EndIf}
 SetOutPath "$INSTDIR"
 WriteUninstaller "$INSTDIR\Uninstall ROMancer.exe"
 ${If} $NoIntegration == 0
  CreateDirectory "$SMPROGRAMS\ROMancer"
  CreateShortcut "$DESKTOP\ROMancer.lnk" "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $\"$INSTDIR\Open ROMancer.ps1$\"' "$INSTDIR\versions\@VERSION@\ROMancer.ico"
  CreateShortcut "$SMPROGRAMS\ROMancer\ROMancer.lnk" "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $\"$INSTDIR\Open ROMancer.ps1$\"' "$INSTDIR\versions\@VERSION@\ROMancer.ico"
  CreateShortcut "$SMPROGRAMS\ROMancer\Uninstall ROMancer.lnk" "$INSTDIR\Uninstall ROMancer.exe"
  WriteRegStr HKCU "Software\ROMancer" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "DisplayName" "ROMancer"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "DisplayVersion" "@VERSION@"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "Publisher" "RetchEWretched"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "DisplayIcon" "$INSTDIR\versions\@VERSION@\ROMancer.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "UninstallString" '$\"$INSTDIR\Uninstall ROMancer.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "QuietUninstallString" '$\"$INSTDIR\Uninstall ROMancer.exe$\" /S'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer" "NoRepair" 1
 ${EndIf}
SectionEnd

Function OpenApp
 Exec '$\"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe$\" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $\"$INSTDIR\Open ROMancer.ps1$\"'
FunctionEnd

Function un.onInit
 SetRegView 64
 SetShellVarContext current
 StrCpy $NoIntegration 0
 ${GetParameters} $R0
 ClearErrors
 ${GetOptions} $R0 "/NOINTEGRATION" $R1
 ${IfNot} ${Errors}
  StrCpy $NoIntegration 1
 ${EndIf}
FunctionEnd

Section "Uninstall"
 ExecWait '$\"$INSTDIR\versions\@VERSION@\python\python.exe$\" -I -B $\"$INSTDIR\versions\@VERSION@\app\tools\install_windows.py$\" --install-root $\"$INSTDIR$\" --uninstall' $0
 ${If} $0 != 0
  SetErrorLevel 1
  Quit
 ${EndIf}
 ${If} $NoIntegration == 0
  Delete "$DESKTOP\ROMancer.lnk"
  Delete "$SMPROGRAMS\ROMancer\ROMancer.lnk"
  Delete "$SMPROGRAMS\ROMancer\Uninstall ROMancer.lnk"
  RMDir "$SMPROGRAMS\ROMancer"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ROMancer"
  DeleteRegValue HKCU "Software\ROMancer" "InstallDir"
 ${EndIf}
 Delete "$INSTDIR\Uninstall ROMancer.exe"
 ; Version folders and workspace are deliberately retained for recovery.
SectionEnd
'''.replace('@PAYLOAD@',payload).replace('@OUTPUT@',output).replace('@VERSION@',version)


def build_installer(payload,compiler_archive,output):
    if os.name!='nt':raise ValueError('the pinned NSIS compiler is a Windows build tool')
    payload=Path(payload).absolute();output=Path(output).absolute();verified=verify_tree(payload)
    if not verified['manifest'].get('engines',{}).get('included'):raise ValueError('the standard installer requires the bundled engines for all six systems')
    from romancer.bundled_cores import core_members
    core_members(payload/'cores')
    compiler_archive=Path(compiler_archive)
    with compiler_archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=NSIS_PIN['sha256']:raise ValueError('NSIS archive differs from compiler pin')
    if output.exists():raise ValueError('installer output already exists')
    output.parent.mkdir(parents=True,exist_ok=True)
    import zipfile
    with tempfile.TemporaryDirectory(prefix='.setup-build-',dir=output.parent) as temp:
        temp=Path(temp)
        with zipfile.ZipFile(compiler_archive) as z:z.extractall(temp/'compiler') # Exact trusted archive hash checked above.
        compiler=temp/'compiler/nsis-3.13/makensis.exe';target=temp/'Setup.exe';script=temp/'setup.nsi'
        script.write_text(installer_script(payload,target,verified['manifest']['version']),encoding='utf-8-sig',newline='\n')
        result=subprocess.run([str(compiler),'/V2',str(script)],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=300)
        if result.returncode:raise RuntimeError('NSIS compiler failed: '+result.stdout[-8000:]+result.stderr[-8000:])
        if verify_tree(payload)['manifest_sha256']!=verified['manifest_sha256']:raise ValueError('payload changed while building installer')
        if not target.is_file():raise ValueError('compiler produced no setup executable')
        os.link(target,output)
    with output.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'ok':True,'path':str(output),'sha256':sha,'version':verified['manifest']['version'],'signed':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--payload',type=Path,required=True);parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(build_installer(args.payload,args.compiler,args.output)))
