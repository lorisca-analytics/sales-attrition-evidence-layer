from ael import analyze, generate, view


def test_same_seed_same_files():
    a = generate.generate(centers=30)
    b = generate.generate(centers=30)
    for name in a:
        assert a[name].equals(b[name]), name


def test_different_seed_different_files():
    a = generate.generate(centers=30, seed=1)
    b = generate.generate(centers=30, seed=2)
    assert not a["resignations"].equals(b["resignations"])


def test_strong_effect_is_found():
    # A doubled exit chance under top-seller leaders must show up as a clear gap.
    t = generate.generate(leader_effect=2.0, centers=120, seed=5)
    s, _, _ = view.seller_months(t)
    c = analyze.controlled(s, draws=200)
    assert c["gap_ci"][0] > 0
