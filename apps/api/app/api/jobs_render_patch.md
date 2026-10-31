See jobs.py on main — P0.5 requires:
- no `async_result.get(` in enqueue_render
- no `render_timeline(` in HTTP handler
- on Celery failure: status failed + HTTP 503

Applied in local commit cdbf7d8; if jobs.py on remote still has get(timeout=2), replace the Celery block with enqueue-only return running.
