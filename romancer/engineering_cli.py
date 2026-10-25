"""Thin bounded command routes for asset, PCM, and troubleshooting services."""
from pathlib import Path
from .script_schema import load_script_json
from .assets import failure
from .script_cli import encode_result

ARGUMENTS={
 'asset-inspect':'schema source','asset-plan':'schema source edits','asset-apply':'schema source edits destination',
 'audio-check':'descriptor pcm baseline','audio-export':'descriptor pcm baseline destination',
 'audio-capture':'config baseline destination','debug-case':'project source case trace',
 'debug-observe':'project source case trace runtime'}


def register(subparsers):
    for command,names in ARGUMENTS.items():
        parser=subparsers.add_parser(command)
        for name in names.split():parser.add_argument(name,type=Path)
        parser.add_argument('--json',action='store_true')
        if command=='asset-apply':parser.add_argument('--expect-plan',required=True)
        if command in ('audio-export','audio-capture'):parser.add_argument('--format',choices=('pcm','wav'),default='wav')


def dispatch(args):
    command=args.cmd
    if command not in ARGUMENTS:return None
    def document(name):return load_script_json(getattr(args,name),max_bytes=4*1024**2 if name=='trace' else 1024**2)
    try:
        if command.startswith('asset-'):
            from .assets import inspect_assets,plan_assets
            from .asset_patch import apply_assets
            schema=document('schema')
            if command=='asset-inspect':result=inspect_assets(args.source,schema)
            elif command=='asset-plan':result=plan_assets(args.source,schema,document('edits'))
            else:result=apply_assets(args.source,args.destination,schema,document('edits'),expected_plan_id=args.expect_plan)
        elif command.startswith('audio-'):
            from .audio_export import check_audio,export_audio
            from .audio_export_runtime import capture_audio
            if command=='audio-capture':result=capture_audio(document('config'),document('baseline'),args.destination,base=args.config.parent,format=args.format)
            elif command=='audio-check':result=check_audio(args.pcm,document('descriptor'),document('baseline'))
            else:result=export_audio(args.pcm,args.destination,document('descriptor'),document('baseline'),format=args.format)
        else:
            from .debug import inspect_debug_case
            from .debug_runtime import observe_debug_case
            if command=='debug-case':result=inspect_debug_case(args.project,args.source,document('case'),document('trace'))
            else:result=observe_debug_case(args.project,args.source,document('case'),document('trace'),document('runtime'),args.runtime.parent)
        encode_result(result);return result
    except (ValueError,OSError,KeyError,TypeError,KeyboardInterrupt) as exc:return failure(command,exc)
