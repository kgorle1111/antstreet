import random

from minheap import MinHeap


def test_random_operations_match_a_sorted_list_model():
    rng = random.Random(20260930)
    for _ in range(30):
        heap = MinHeap(key=lambda t: t[0])
        model = []
        seq = 0
        for _ in range(300):
            action = rng.choice(["push", "push", "pop", "replace", "peek"])
            if action == "push" or not model:
                item = (rng.randrange(8), seq)
                seq += 1
                heap.push(item)
                model.append(item)
                model.sort()
            elif action == "pop":
                assert heap.pop() == model.pop(0)
            elif action == "peek":
                assert heap.peek() == model[0]
            else:
                item = (rng.randrange(8), seq)
                seq += 1
                assert heap.replace(item) == model.pop(0)
                model.append(item)
                model.sort()
            assert len(heap) == len(model)
        assert heap.items() == model
