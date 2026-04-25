from backend.app.routing import WorkerType


def run_local_job_sync(job_id: str, worker_type: WorkerType) -> None:
    """Run worker logic synchronously (intended to run in a thread pool, not on the event loop)."""
    if worker_type is WorkerType.TABULAR:
        from workers.tabular.worker import run_tabular_job

        run_tabular_job(job_id)
        return
    from workers.pdf.worker import run_pdf_job

    run_pdf_job(job_id)
