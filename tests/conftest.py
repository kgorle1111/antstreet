import signal


def pytest_configure(config):
    # A shell starts a backgrounded command (`pytest &`) with SIGINT ignored, and Python keeps it
    # ignored, so the fakes' simulated Ctrl-C would be dropped and every interrupt test would fail.
    signal.signal(signal.SIGINT, signal.default_int_handler)
