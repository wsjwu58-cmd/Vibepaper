from .celery_app import celery_app


@celery_app.task(name="src.generation.workers.tasks.run_generation_task")
def run_generation_task(task_id: int):
    from ..services.task_service import task_service

    task_service.execute_task(task_id)


@celery_app.task(name="src.generation.workers.tasks.media_process")
def media_process(task_id: int, operation: str, params: dict):
    """媒体加工（FFmpeg 剪辑/提帧/超分）预留：真实环境调用 FFmpeg。"""
    from ..services.task_service import task_service

    task_service.execute_task(task_id)
    return {"taskId": task_id, "operation": operation}
