from scripts.market_ops.pipeline.runner import PipelineRunner


def test_runner_executes_steps_in_order():
    order = []

    def s1(ctx):
        order.append("a")

    def s2(ctx):
        order.append("b")

    runner = PipelineRunner(ctx={}, steps=[("s1", s1), ("s2", s2)])
    runner.run()
    assert order == ["a", "b"]
