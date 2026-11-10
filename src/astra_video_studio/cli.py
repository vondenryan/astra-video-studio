import argparse
import json
import logging

from astra_video_studio.ae_bridge.probe import prepare_probe, verify_probe
from astra_video_studio.config import Settings
from astra_video_studio.status import studio_status
from astra_video_studio.project_manager import ProjectManager
from astra_video_studio.schemas import ProjectCreateRequest, ProjectOpenCopyRequest
from astra_video_studio.existing_projects import ExistingProjectService
from astra_video_studio.motion_engine.schemas import MotionRequest, TransformRequest
from astra_video_studio.motion_engine.service import MotionService
from astra_video_studio.treatments import EffectRequest, MaskRequest, TreatmentService
from astra_video_studio.media.preview import PreviewRequest, PreviewService
from astra_video_studio.ae_bridge.idle_transport import IdleTransport
from astra_video_studio.ae_bridge.discovery import discover_ae
from astra_video_studio.ae_bridge.locking import AELock
from astra_video_studio.layers import LayerCreateRequest, MediaImportRequest, LayerService
from astra_video_studio.motion_engine.batch import BatchRequest, BatchService, StaggerRequest
from astra_video_studio.director import Director, SceneBrief, SceneRevision, ReviewRecord
from astra_video_studio.references import ReferenceRequest, analyze as analyze_reference
from astra_video_studio.scene_editing import REQUESTS as SCENE_REQUESTS, SceneService
from astra_video_studio.design import DESIGN_REQUESTS, DesignService, FontsQuery, DesignTokens, store_tokens
from astra_video_studio.animation import ANIMATION_REQUESTS, AnimationInspect, AnimationService
from astra_video_studio.revisions import REVISION_REQUESTS, RevisionService
from astra_video_studio.responses import (present, EvidenceQuery, ProjectQuery, query_evidence, query_project)
from astra_video_studio.schemas import OperationResult, JobStatus
from astra_video_studio.director import ScenePlan, SceneExecution


def main() -> None:
    parser = argparse.ArgumentParser(description="Astra local AE diagnostics and safe project creation")
    parser.add_argument("command", choices=["status", "prepare-probe", "verify-probe", "create-demo", "inspect", "job-status", "motion-apply", "layer-transform", "open-copy", "save", "effect-apply", "mask-create", "preview-render", "job-cancel", "bridge-start", "layer-create", "media-import", "stagger-layers", "motion-batch", "plan-scene", "execute-scene", "scene-status", "revise-scene", "review-scene", "reference-analyze", "fonts-list", "design-tokens-set"] + [name.replace('_', '-') for name in (*SCENE_REQUESTS, *DESIGN_REQUESTS, *ANIMATION_REQUESTS, *REVISION_REQUESTS, 'animation_inspect', 'operation_query', 'project_query')])
    parser.add_argument("--job-id")
    parser.add_argument("--response-mode", choices=['compact', 'receipt', 'full'], default='compact', help='Compact by default; receipt is minimal; full retains the legacy payload')
    parser.add_argument("--project-id")
    parser.add_argument("--plan-id")
    parser.add_argument("--source", help="Existing .aep in workspace or approved import roots")
    parser.add_argument("--request", help="Typed JSON request; file sources only in supported approved-root tools")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        settings = Settings.from_env()
        scene_action = args.command.replace('-', '_')
        if scene_action in ('operation_query', 'project_query'):
            payload = json.loads(args.request or '{}')
            result = (query_evidence(settings, EvidenceQuery.model_validate(payload)) if scene_action == 'operation_query' else query_project(settings, ProjectQuery.model_validate(payload))).model_dump()
        elif scene_action in REVISION_REQUESTS:
            payload = REVISION_REQUESTS[scene_action].model_validate(json.loads(args.request or '{}'))
            method = {'revision_plan': 'plan', 'revision_apply': 'apply', 'version_compare': 'compare', 'version_restore': 'restore', 'director_revision_plan': 'director_plan'}[scene_action]
            result = getattr(RevisionService(settings), method)(payload).model_dump()
        elif scene_action in ANIMATION_REQUESTS or scene_action == 'animation_inspect':
            payload = json.loads(args.request or '{}')
            if scene_action == 'animation_inspect': result = AnimationService(settings).inspect(AnimationInspect.model_validate(payload)).model_dump()
            else: result = AnimationService(settings).apply(scene_action, ANIMATION_REQUESTS[scene_action].model_validate(payload)).model_dump()
        elif scene_action in DESIGN_REQUESTS or args.command in ('fonts-list', 'design-tokens-set'):
            payload = json.loads(args.request or '{}')
            if args.command == 'fonts-list': result = DesignService(settings).fonts(FontsQuery.model_validate(payload)).model_dump()
            elif args.command == 'design-tokens-set': result = store_tokens(settings, DesignTokens.model_validate(payload)).model_dump()
            else: result = DesignService(settings).apply(scene_action, DESIGN_REQUESTS[scene_action].model_validate(payload)).model_dump()
        elif scene_action in SCENE_REQUESTS:
            if not args.request:
                parser.error('Scene editing requires --request JSON')
            request = SCENE_REQUESTS[scene_action].model_validate(json.loads(args.request))
            result = SceneService(settings).apply(scene_action, request).model_dump()
        elif args.command == "status":
            result = studio_status(settings).model_dump()
        elif args.command == "prepare-probe":
            result = prepare_probe(settings)
        elif args.command == "create-demo":
            result = ProjectManager(settings).create(ProjectCreateRequest()).model_dump()
        elif args.command == "inspect":
            if not args.project_id:
                parser.error("inspect requires --project-id")
            result = ProjectManager(settings).inspect(args.project_id).model_dump()
        elif args.command == "job-status":
            if not args.job_id:
                parser.error("job-status requires --job-id")
            result = ProjectManager(settings).job_status(args.job_id)
        elif args.command in ("motion-apply", "layer-transform"):
            if not args.request:
                parser.error("motion-apply/layer-transform requires --request JSON")
            payload = json.loads(args.request)
            service = MotionService(settings)
            result = (service.apply(MotionRequest.model_validate(payload)) if args.command == "motion-apply" else service.transform(TransformRequest.model_validate(payload))).model_dump()
        elif args.command == "open-copy":
            if not args.source:
                parser.error("open-copy requires --source")
            result = ExistingProjectService(settings).open_copy(ProjectOpenCopyRequest(source_path=args.source)).model_dump()
        elif args.command == "save":
            if not args.project_id:
                parser.error("save requires --project-id")
            result = ExistingProjectService(settings).save(args.project_id).model_dump()
        elif args.command in ("effect-apply", "mask-create", "preview-render"):
            if not args.request:
                parser.error("This command requires --request JSON")
            payload = json.loads(args.request)
            if args.command == "preview-render":
                result = PreviewService(settings).submit(PreviewRequest.model_validate(payload)).model_dump()
            else:
                request = (EffectRequest if args.command == "effect-apply" else MaskRequest).model_validate(payload)
                result = TreatmentService(settings).apply(request).model_dump()
        elif args.command == "job-cancel":
            if not args.job_id:
                parser.error("job-cancel requires --job-id")
            result = PreviewService(settings).cancel(args.job_id)
        elif args.command == "bridge-start":
            if settings.contained_path("ae-pending.json").exists():
                raise ValueError("An operation is unresolved; inspect AE and the pending job before bridge startup")
            ae = discover_ae(settings.ae_executable)
            if not ae.available or ae.error:
                raise ValueError(ae.error or "AE unavailable")
            with AELock():
                result = IdleTransport(settings).ensure_ready(ae.path)
        elif args.command in ('layer-create','media-import','stagger-layers','motion-batch','plan-scene','revise-scene','review-scene','reference-analyze'):
            if not args.request: parser.error('This command requires --request JSON')
            payload=json.loads(args.request)
            if args.command=='layer-create': outcome=LayerService(settings).create(LayerCreateRequest.model_validate(payload))
            elif args.command=='media-import': outcome=LayerService(settings).import_media(MediaImportRequest.model_validate(payload))
            elif args.command=='stagger-layers': outcome=BatchService(settings).apply(StaggerRequest.model_validate(payload).batch())
            elif args.command=='motion-batch': outcome=BatchService(settings).apply(BatchRequest.model_validate(payload))
            elif args.command=='plan-scene': outcome=Director(settings).plan(SceneBrief.model_validate(payload))
            elif args.command=='revise-scene': outcome=Director(settings).revise(SceneRevision.model_validate(payload))
            elif args.command=='review-scene': outcome=Director(settings).review(ReviewRecord.model_validate(payload))
            else: outcome=analyze_reference(settings,ReferenceRequest.model_validate(payload))
            result=outcome.model_dump()
        elif args.command=='execute-scene':
            if not args.plan_id: parser.error('execute-scene requires --plan-id')
            result=Director(settings).execute(args.plan_id).model_dump()
        elif args.command=='scene-status':
            if not args.job_id: parser.error('scene-status requires --job-id execution ID')
            result=Director(settings).status(args.job_id).model_dump()
        else:
            if not args.job_id:
                parser.error("verify-probe requires --job-id")
            result = verify_probe(settings, args.job_id)
        if 'evidence' not in result:
            model = None
            if 'events' in result and 'action' in result: model = JobStatus
            elif 'operation_id' in result and 'data' in result: model = OperationResult
            elif 'execution_id' in result and 'plan_id' in result: model = SceneExecution
            elif 'elements' in result and 'plan_id' in result: model = ScenePlan
            if model:
                projected = present(model.model_validate(result), args.response_mode, settings)
                if args.response_mode in ('compact','receipt'): result = projected.model_dump(mode='json')
        print(json.dumps(result, separators=(',', ':'), ensure_ascii=True))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
