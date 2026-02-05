import time


class PipelineRunner:
    def __init__(self, *, ctx, steps, continue_on_error=True, skip=None, only=None):
        self.ctx = ctx
        self.steps = steps
        self.continue_on_error = continue_on_error
        self.skip = set(skip or [])
        self.only = set(only or [])

    def _should_run(self, name: str) -> bool:
        if self.only and name not in self.only:
            return False
        if name in self.skip:
            return False
        return True

    def run(self):
        for name, fn in self.steps:
            if not self._should_run(name):
                continue
            t0 = time.perf_counter()
            try:
                fn(self.ctx)
            except Exception as e:
                errors = self._errors_bucket()
                errors.append(f"step_failed:{name}:{type(e).__name__}:{e}")
                if not self.continue_on_error:
                    raise
            finally:
                perf = self._perf_bucket()
                perf[f"step_{name}"] = round(time.perf_counter() - t0, 3)

    def _errors_bucket(self):
        if isinstance(self.ctx, dict):
            return self.ctx.setdefault("errors", [])
        return self.ctx.errors

    def _perf_bucket(self):
        if isinstance(self.ctx, dict):
            return self.ctx.setdefault("perf", {})
        return self.ctx.perf
