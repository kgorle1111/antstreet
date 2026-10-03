import random
from collections import deque

import pytest
from ringbuffer import BufferFull, RingBuffer


@pytest.mark.parametrize("overwrite", [True, False])
def test_random_operations_match_a_deque_model(overwrite):
    rng = random.Random(11 if overwrite else 12)
    for _ in range(40):
        cap = rng.randint(1, 6)
        buf = RingBuffer(cap, overwrite=overwrite)
        model = deque()
        for step in range(150):
            action = rng.choice(["append", "append", "extend", "popleft", "clear", "check"])
            if action == "append":
                if len(model) == cap and not overwrite:
                    with pytest.raises(BufferFull):
                        buf.append(step)
                else:
                    buf.append(step)
                    model.append(step)
                    if len(model) > cap:
                        model.popleft()
            elif action == "extend":
                batch = [step, step + 1000, step + 2000]
                for item in batch:
                    if len(model) == cap and not overwrite:
                        with pytest.raises(BufferFull):
                            buf.extend(batch[batch.index(item) :])
                        break
                    buf.extend([item])
                    model.append(item)
                    if len(model) > cap:
                        model.popleft()
            elif action == "popleft":
                if model:
                    assert buf.popleft() == model.popleft()
                else:
                    with pytest.raises(IndexError):
                        buf.popleft()
            elif action == "clear":
                buf.clear()
                model.clear()
            assert list(buf) == list(model)
            assert len(buf) == len(model)
            assert buf.full == (len(model) == cap)
            for i in range(len(model)):
                assert buf[i] == model[i]
                assert buf[i - len(model)] == model[i]
