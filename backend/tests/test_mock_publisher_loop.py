from unittest.mock import patch

from mock_publisher.__main__ import run_publish_loop


def _fake_clock_and_sleep():
    # Relógio falso: começa em 0.0 e só avança quando "sleep" é chamado --
    # isso deixa o teste 100% determinístico e instantâneo, sem depender
    # de tempo real (nada de time.sleep de verdade, nada de flakiness).
    state = {"t": 0.0}

    def clock():
        return state["t"]

    def sleep(seconds):
        state["t"] += seconds

    return clock, sleep


@patch("mock_publisher.__main__.publish_snapshot")
def test_run_publish_loop_stops_after_duration(mock_publish):
    clock, sleep = _fake_clock_and_sleep()

    run_publish_loop(client=None, dry_run=True, duration=0.1, clock=clock, sleep=sleep)

    # PUBLISH_HZ=20 -> tick=0.05s. Com duration=0.1s, publica em t=0.0,
    # 0.05 e 0.10 (0.10 > 0.1 é False, ainda publica); para em t=0.15.
    assert mock_publish.call_count == 3


@patch("mock_publisher.__main__.publish_snapshot")
def test_run_publish_loop_passes_increasing_t_to_publish_snapshot(mock_publish):
    clock, sleep = _fake_clock_and_sleep()

    run_publish_loop(client=None, dry_run=True, duration=0.1, clock=clock, sleep=sleep)

    t_values = [call.args[1] for call in mock_publish.call_args_list]
    assert t_values == [0.0, 0.05, 0.1]


@patch("mock_publisher.__main__.publish_snapshot")
def test_run_publish_loop_forwards_dry_run_flag(mock_publish):
    clock, sleep = _fake_clock_and_sleep()

    run_publish_loop(client=None, dry_run=True, duration=0.0, clock=clock, sleep=sleep)

    _, kwargs = mock_publish.call_args
    assert kwargs["dry_run"] is True


@patch("mock_publisher.__main__.publish_snapshot")
def test_run_publish_loop_passes_client_through(mock_publish):
    clock, sleep = _fake_clock_and_sleep()
    sentinel_client = object()

    run_publish_loop(client=sentinel_client, dry_run=False, duration=0.0, clock=clock, sleep=sleep)

    assert mock_publish.call_args.args[0] is sentinel_client


@patch("mock_publisher.__main__.publish_snapshot")
def test_run_publish_loop_runs_forever_without_duration(mock_publish):
    # duration=None é o modo "pra sempre" -- simulamos isso limitando o
    # relógio falso a avançar só N vezes antes de forçar uma saída via
    # exceção, provando que o loop não teria parado sozinho.
    clock, real_sleep = _fake_clock_and_sleep()
    calls = {"n": 0}

    def sleep(seconds):
        real_sleep(seconds)
        calls["n"] += 1
        if calls["n"] >= 5:
            raise RuntimeError("simulando interrupção externa após 5 ticks")

    try:
        run_publish_loop(client=None, dry_run=True, duration=None, clock=clock, sleep=sleep)
    except RuntimeError:
        pass

    assert mock_publish.call_count == 5
